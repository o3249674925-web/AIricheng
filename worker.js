const MAX_TEXT = 12000;
const MAX_TASKS = 100;
const MAX_ERROR_DETAIL = 280;
const allowOrigin = origin => !origin || origin === 'http://localhost:5173' || origin.endsWith('.workers.dev');
const json = (body, status = 200, origin = '') => new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store', ...(origin && allowOrigin(origin) ? { 'access-control-allow-origin': origin, 'vary': 'Origin' } : {}) } });

/**
 * Accept either a complete OpenAI-compatible endpoint or a provider base URL.
 * The latter is a common source of an opaque 404/model preflight error when
 * configuring a Worker by hand (for example, https://api.openai.com/v1).
 */
export function normalizeChatCompletionsUrl(value) {
  if (typeof value !== 'string' || !value.trim()) return null;
  let url;
  try { url = new URL(value.trim()); } catch { return null; }
  if (!['http:', 'https:'].includes(url.protocol)) return null;
  const path = url.pathname.replace(/\/+$/, '');
  if (/\/chat\/completions$/i.test(path)) { url.pathname = path; return url.toString(); }
  if (/\/v\d+$/i.test(path)) { url.pathname = `${path}/chat/completions`; return url.toString(); }
  if (!path || path === '/') { url.pathname = '/v1/chat/completions'; return url.toString(); }
  return url.toString();
}

function configured(env) {
  return Boolean(env?.AI_API_KEY && env?.AI_MODEL && normalizeChatCompletionsUrl(env?.AI_API_URL));
}

function redactDetail(value) {
  return String(value || '')
    .replace(/\b(sk|sess|key|token)-[A-Za-z0-9._-]+/gi, '[redacted]')
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, MAX_ERROR_DETAIL);
}

async function upstreamDetail(response) {
  try {
    const text = await response.text();
    if (!text) return '';
    try {
      const body = JSON.parse(text);
      const error = body?.error;
      const code = error?.code || body?.code || '';
      const message = error?.message || body?.message || '';
      return redactDetail([code, message].filter(Boolean).join(': ') || text);
    } catch {
      // Never echo an unstructured provider body: it may contain request IDs,
      // headers, or other sensitive data. Preserve only a safe diagnostic code.
      const code = text.match(/\bmodel_[a-z0-9_]+\b/i)?.[0] || '';
      return redactDetail(code);
    }
  } catch { return ''; }
}

function upstreamFailure(status, detail = '') {
  const lower = detail.toLowerCase();
  if (lower.includes('model_preflight_failed')) return { code: 'model_preflight_failed', message: '模型服务无法使用当前模型，请检查模型名称、接口地址或模型权限。' };
  if (status === 401 || status === 403) return { code: 'model_auth_failed', message: '模型服务鉴权失败，请检查 AI_API_KEY。' };
  if (status === 404) return { code: 'model_endpoint_or_name_not_found', message: '模型接口地址或模型名称不存在；接口地址应填写完整 URL，或填写服务商的 /v1 基础地址。' };
  if (status === 400 || status === 422) return { code: 'model_request_rejected', message: '模型服务拒绝了请求参数，请检查模型名称是否支持 Chat Completions。' };
  if (status === 429) return { code: 'model_rate_limited', message: '模型服务暂时限流，请稍后再试。' };
  if (status >= 500) return { code: 'model_upstream_failed', message: '模型服务暂时不可用，请稍后再试。' };
  return { code: 'model_http_failed', message: `模型服务返回 HTTP ${status}。` };
}

function contentText(raw) {
  const content = raw?.choices?.[0]?.message?.content ?? raw?.choices?.[0]?.text ?? raw?.output_text;
  if (typeof content === 'string') return content;
  if (Array.isArray(content)) return content.map(part => typeof part === 'string' ? part : part?.text || part?.content || '').join('');
  return '';
}

function parseJsonContent(content) {
  const value = String(content || '').trim();
  if (!value) return null;
  const candidates = [value, value.replace(/^```(?:json)?\s*/i, '').replace(/\s*```$/, '').trim()];
  for (const candidate of candidates) {
    try { return JSON.parse(candidate); } catch { /* try the next tolerant form */ }
  }
  const start = value.indexOf('{');
  const end = value.lastIndexOf('}');
  if (start >= 0 && end > start) {
    try { return JSON.parse(value.slice(start, end + 1)); } catch { /* report a useful API error below */ }
  }
  return null;
}

function chatPayload(model, userPrompt, jsonMode = false) {
  const payload = {
    model,
    temperature: 0,
    messages: [
      { role: 'system', content: '你是严谨的结构化信息抽取服务，只输出有效 JSON。' },
      { role: 'user', content: userPrompt },
    ],
  };
  // Disabled by default: many OpenAI-compatible providers reject
  // response_format even though they can follow the JSON instruction.
  if (jsonMode) payload.response_format = { type: 'json_object' };
  return payload;
}

function prompt(text, reference, source, tasks) {
  return `你是校园任务抽取器。只返回 JSON：{"candidates":[{"action":"create|update|cancel|complete","title":"","deadline":"YYYY-MM-DDTHH:MM 或空字符串","duration":60,"priority":"high|normal|low","targetId":"已有任务id或null","evidence":"原文片段","notes":""}]}。消息来源：${source}。消息日期（北京时间）：${reference}。只在原文明确给出时填写 deadline；“下节课前”“第八周”等无课表上下文时留空。延期、取消、完成必须关联已有任务；不要臆造标题、时间或任务。已有任务：${JSON.stringify(tasks)}。原文：${text}`;
}
export default { async fetch(request, env) {
  const origin = request.headers.get('Origin') || '';
  if (request.method === 'OPTIONS') return new Response(null, { status: 204, headers: { 'access-control-allow-origin': allowOrigin(origin) ? origin : 'null', 'access-control-allow-methods': 'GET,POST,OPTIONS', 'access-control-allow-headers': 'Content-Type,Authorization' } });
  const url = new URL(request.url);
  if (url.pathname === '/api/health') return json({ ok: true, aiConfigured: configured(env) }, 200, origin);
  if (url.pathname !== '/api/extract' || request.method !== 'POST') return env.ASSETS?.fetch(request) || new Response('Not found', { status: 404 });
  const modelUrl = normalizeChatCompletionsUrl(env.AI_API_URL);
  if (!env.AI_API_KEY || !env.AI_MODEL || !modelUrl) return json({ error: '服务端尚未正确配置 AI 模型。请检查 AI_API_KEY、AI_API_URL 和 AI_MODEL。', diagnosticCode: 'model_config_missing' }, 503, origin);
  if (env.AI_ACCESS_TOKEN && request.headers.get('Authorization') !== `Bearer ${env.AI_ACCESS_TOKEN}`) return json({ error: '接口访问码无效' }, 401, origin);
  let body;
  try { body = await request.json(); } catch { return json({ error: '请求格式无效' }, 400, origin); }
  const text = typeof body.text === 'string' ? body.text.trim() : '';
  if (!text || text.length > MAX_TEXT) return json({ error: '通知原文不能为空且不能超过 12,000 字' }, 400, origin);
  const tasks = Array.isArray(body.tasks) ? body.tasks.slice(0, MAX_TASKS) : [];
  const controller = new AbortController(); const timer = setTimeout(() => controller.abort(), 35000);
  try {
    const upstream = await fetch(modelUrl, { method: 'POST', signal: controller.signal, headers: { authorization: `Bearer ${env.AI_API_KEY}`, 'content-type': 'application/json', accept: 'application/json', 'user-agent': 'kexu-campus-mvp/0.1' }, body: JSON.stringify(chatPayload(env.AI_MODEL, prompt(text, body.reference || '', body.source || '', tasks), env.AI_JSON_MODE === 'json_object')) });
    if (!upstream.ok) {
      const detail = await upstreamDetail(upstream);
      const failure = upstreamFailure(upstream.status, detail);
      return json({ error: `${failure.message}${detail ? `（${detail}）` : ''}`, diagnosticCode: failure.code, upstreamStatus: upstream.status }, 502, origin);
    }
    let raw;
    try { raw = await upstream.json(); } catch { return json({ error: '模型返回的内容不是有效 JSON', diagnosticCode: 'model_response_not_json' }, 502, origin); }
    const parsed = parseJsonContent(contentText(raw));
    if (!parsed) return json({ error: '模型返回的 JSON 无法解析，请更换支持文本 JSON 输出的模型。', diagnosticCode: 'model_response_json_invalid' }, 502, origin);
    if (!Array.isArray(parsed.candidates)) return json({ error: '模型返回结构不符合约定，请确认使用了正确的模型接口。', diagnosticCode: 'model_response_schema_invalid' }, 502, origin);
    return json({ candidates: parsed.candidates.slice(0, 30) }, 200, origin);
  } catch (e) { return json({ error: e.name === 'AbortError' ? '模型响应超时' : '模型服务暂时不可用', diagnosticCode: e.name === 'AbortError' ? 'model_timeout' : 'model_network_failed' }, 502, origin); } finally { clearTimeout(timer); }
} };
