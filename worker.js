const MAX_TEXT = 12000;
const MAX_TASKS = 100;
const allowOrigin = origin => !origin || origin === 'http://localhost:5173' || origin.endsWith('.workers.dev');
const json = (body, status = 200, origin = '') => new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store', ...(origin && allowOrigin(origin) ? { 'access-control-allow-origin': origin, 'vary': 'Origin' } : {}) } });
function prompt(text, reference, source, tasks) {
  return `你是校园任务抽取器。只返回 JSON：{"candidates":[{"action":"create|update|cancel|complete","title":"","deadline":"YYYY-MM-DDTHH:MM 或空字符串","duration":60,"priority":"high|normal|low","targetId":"已有任务id或null","evidence":"原文片段","notes":""}]}。消息来源：${source}。消息日期（北京时间）：${reference}。只在原文明确给出时填写 deadline；“下节课前”“第八周”等无课表上下文时留空。延期、取消、完成必须关联已有任务；不要臆造标题、时间或任务。已有任务：${JSON.stringify(tasks)}。原文：${text}`;
}
export default { async fetch(request, env) {
  const origin = request.headers.get('Origin') || '';
  if (request.method === 'OPTIONS') return new Response(null, { status: 204, headers: { 'access-control-allow-origin': allowOrigin(origin) ? origin : 'null', 'access-control-allow-methods': 'GET,POST,OPTIONS', 'access-control-allow-headers': 'Content-Type,Authorization' } });
  const url = new URL(request.url);
  if (url.pathname === '/api/health') return json({ ok: true, aiConfigured: Boolean(env.AI_API_KEY && env.AI_API_URL && env.AI_MODEL) }, 200, origin);
  if (url.pathname !== '/api/extract' || request.method !== 'POST') return env.ASSETS?.fetch(request) || new Response('Not found', { status: 404 });
  if (!env.AI_API_KEY || !env.AI_API_URL || !env.AI_MODEL) return json({ error: '服务端尚未配置 AI 模型。请使用本地规则模式。' }, 503, origin);
  if (env.AI_ACCESS_TOKEN && request.headers.get('Authorization') !== `Bearer ${env.AI_ACCESS_TOKEN}`) return json({ error: '接口访问码无效' }, 401, origin);
  let body;
  try { body = await request.json(); } catch { return json({ error: '请求格式无效' }, 400, origin); }
  const text = typeof body.text === 'string' ? body.text.trim() : '';
  if (!text || text.length > MAX_TEXT) return json({ error: '通知原文不能为空且不能超过 12,000 字' }, 400, origin);
  const tasks = Array.isArray(body.tasks) ? body.tasks.slice(0, MAX_TASKS) : [];
  const controller = new AbortController(); const timer = setTimeout(() => controller.abort(), 35000);
  try {
    const upstream = await fetch(env.AI_API_URL, { method: 'POST', signal: controller.signal, headers: { authorization: `Bearer ${env.AI_API_KEY}`, 'content-type': 'application/json' }, body: JSON.stringify({ model: env.AI_MODEL, temperature: 0, response_format: { type: 'json_object' }, messages: [{ role: 'system', content: '你是严谨的结构化信息抽取服务，只输出有效 JSON。' }, { role: 'user', content: prompt(text, body.reference || '', body.source || '', tasks) }] }) });
    if (!upstream.ok) return json({ error: `模型服务返回 ${upstream.status}` }, 502, origin);
    const raw = await upstream.json(); const content = raw.choices?.[0]?.message?.content;
    let parsed; try { parsed = typeof content === 'string' ? JSON.parse(content) : content; } catch { return json({ error: '模型返回的 JSON 无法解析' }, 502, origin); }
    if (!parsed || !Array.isArray(parsed.candidates)) return json({ error: '模型返回结构不符合约定' }, 502, origin);
    return json({ candidates: parsed.candidates.slice(0, 30) }, 200, origin);
  } catch (e) { return json({ error: e.name === 'AbortError' ? '模型响应超时' : '模型服务暂时不可用' }, 502, origin); } finally { clearTimeout(timer); }
} };
