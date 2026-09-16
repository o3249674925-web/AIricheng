import { z } from 'zod';
import { shiftDateStr } from '../packages/agenda-core/src/agenda.js';
export { shiftDateStr };
export const today = () => new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date());
export const clock = n => `${String(Math.floor(n / 60)).padStart(2, '0')}:${String(n % 60).padStart(2, '0')}`;
export const minutes = s => Number(s.slice(0, 2)) * 60 + Number(s.slice(3, 5));
export const uid = () => crypto.randomUUID();
export const dateSchema = z.string().regex(/^\d{4}-\d{2}-\d{2}$/).refine(s => !Number.isNaN(Date.parse(s)) && new Date(s).toISOString().slice(0, 10) === s);
export const deadlineSchema = z.string().refine(s => s === '' || (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(s) && dateSchema.safeParse(s.slice(0, 10)).success && /^([01]\d|2[0-3]):[0-5]\d$/.test(s.slice(11))));
export const candidateSchema = z.object({
  action: z.enum(['create', 'update', 'cancel', 'complete']), title: z.string().trim().min(1).max(160),
  deadline: deadlineSchema, duration: z.number().int().min(15).max(480), priority: z.enum(['high', 'normal', 'low']),
  targetId: z.string().max(100).nullable(), evidence: z.string().min(1).max(12000), notes: z.string().max(2000),
});
export const extractionSchema = z.object({ candidates: z.array(candidateSchema).max(30) });
const historySchema = z.object({ at: z.string(), action: z.string(), source: z.string(), evidence: z.string(), before: z.string(), after: z.string() });
export const taskSchema = candidateSchema.omit({ action: true, targetId: true, evidence: true }).extend({ id: z.string(), source: z.string(), status: z.enum(['active', 'done', 'cancelled']), history: z.array(historySchema).max(500) });
const fixedSchema = z.object({ id: z.string(), title: z.string().min(1).max(160), date: dateSchema, start: z.number().int().min(0).max(1439), end: z.number().int().min(1).max(1440) }).refine(v => v.end > v.start);
const blockSchema = z.object({ taskId: z.string(), date: dateSchema, start: z.number().int().min(0).max(1439), end: z.number().int().min(1).max(1440), locked: z.boolean() }).refine(v => v.end > v.start);
export const stateSchema = z.object({ version: z.literal(1), tasks: z.array(taskSchema).max(1000), fixed: z.array(fixedSchema).max(1000), blocks: z.array(blockSchema).max(1000), settings: z.object({ start: z.number().int().min(0).max(1439), end: z.number().int().min(1).max(1440) }).refine(v => v.end > v.start) });
export const emptyState = () => ({ version: 1, tasks: [], fixed: [], blocks: [], settings: { start: 9 * 60, end: 21 * 60 } });
export function validateBackup(value) {
  const state = stateSchema.parse(value);
  if (new Set(state.tasks.map(t => t.id)).size !== state.tasks.length || new Set(state.fixed.map(t => t.id)).size !== state.fixed.length) throw Error('备份存在重复标识');
  // Schedules are derived data: discard them on import and recompute from validated tasks.
  return { ...state, blocks: [] };
}
export function resolveDate(text, reference) {
  if (/下节课|第[一二三四五六七八九十\d]+周|月底|尽快|稍后/.test(text)) return '';
  const explicit = text.match(/(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})日?/);
  let date = explicit ? `${explicit[1]}-${explicit[2].padStart(2, '0')}-${explicit[3].padStart(2, '0')}` : '';
  if (!date && /后天|明天|今天/.test(text)) date = shiftDateStr(reference, text.includes('后天') ? 2 : text.includes('明天') ? 1 : 0);
  const weekday = text.match(/(下|本|这)?(?:周|星期)([一二三四五六日天])/);
  if (!date && weekday) {
    const current = (new Date(`${reference}T12:00:00`).getDay() + 6) % 7;
    const target = '一二三四五六日'.indexOf(weekday[2].replace('天', '日'));
    const offset = weekday[1] === '下' ? 7 + target - current : weekday[1] ? target - current : (target - current + 7) % 7;
    date = shiftDateStr(reference, offset);
  }
  if (!dateSchema.safeParse(date).success) return '';
  const time = text.match(/(\d{1,2})[:：](\d{2})/);
  let hour = time ? Number(time[1]) : null;
  if (hour !== null && /下午|晚上/.test(text) && hour < 12) hour += 12;
  // No invented end-of-day deadline: ask the user to supply a time.
  return time && hour <= 23 && Number(time[2]) <= 59 ? `${date}T${String(hour).padStart(2, '0')}:${time[2]}` : date;
}
export function parseLocal(text, reference, tasks, source) {
  return text.split(/\n+/).map(s => s.trim()).filter(Boolean).slice(0, 30).map(evidence => {
    const action = /取消|不用交|不必交/.test(evidence) ? 'cancel' : /已完成|已提交/.test(evidence) ? 'complete' : /改到|改为|延期|补充|提前/.test(evidence) ? 'update' : 'create';
    const quoted = evidence.match(/[「“《](.+?)[」”》]/)?.[1];
    const matches = tasks.filter(t => t.status === 'active' && t.source === source && (quoted ? t.title === quoted : evidence.includes(t.title)));
    const target = matches.length === 1 ? matches[0] : null;
    const resolved = resolveDate(evidence, reference);
    return { id: uid(), action, title: quoted || target?.title || evidence.replace(/^.{1,15}[：:](?!\d)/, '').slice(0, 80),
      deadline: resolved.length === 16 ? resolved : '', dateHint: resolved.length === 10 ? resolved : '',
      duration: target?.duration || 60, priority: target?.priority || 'normal', targetId: target?.id || null,
      notes: action === 'update' ? evidence : '', evidence,
      warning: '本地规则结果：请核对事项名称、关联任务和截止时间。' };
  });
}
export function applyCandidate(state, candidate, source, at = new Date().toISOString()) {
  const c = candidateSchema.parse(candidate);
  if (c.action !== 'create' && !c.targetId) throw Error('请先选择要变更的原任务');
  const target = state.tasks.find(t => t.id === c.targetId);
  if (c.action !== 'create' && !target) throw Error('关联任务已不存在');
  if (target && target.status !== 'active') throw Error('原任务已完成或取消，请重新核对');
  if (c.action === 'create' && state.tasks.some(t => t.status === 'active' && t.source === source && t.title.trim() === c.title.trim())) throw Error('同来源已有同名任务。请改为更新并选择原任务，或补充标题区分事项');
  const id = c.action === 'create' ? uid() : target.id;
  const history = { at, action: c.action, source, evidence: c.evidence, before: target ? `${target.title} · ${target.deadline || '未定时间'}` : '', after: `${c.title} · ${c.deadline || '未定时间'}` };
  const next = c.action === 'create' ? { id, title: c.title, deadline: c.deadline, duration: c.duration, priority: c.priority, notes: c.notes, status: 'active', source, history: [history] }
    : { ...target, ...(c.action === 'update' ? { title: c.title, deadline: c.deadline, duration: c.duration, priority: c.priority, notes: [target.notes, c.notes].filter(Boolean).join('\n').slice(-2000) } : { status: c.action === 'cancel' ? 'cancelled' : 'done' }), history: [...target.history, history] };
  return { ...state, tasks: c.action === 'create' ? [...state.tasks, next] : state.tasks.map(t => t.id === id ? next : t), blocks: state.blocks.filter(b => b.taskId !== id) };
}
export const overlap = (a, b) => a.start < b.end && b.start < a.end;
export function schedule(state, from, now = new Date()) {
  const blocks = [], reasons = [];
  const currentDate = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Shanghai' }).format(now);
  const parts = new Intl.DateTimeFormat('en-GB', { timeZone: 'Asia/Shanghai', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' }).format(now);
  const currentMinute = minutes(parts);
  const active = state.tasks.filter(t => t.status === 'active').sort((a, b) => (a.deadline || 'z').localeCompare(b.deadline || 'z') || ({ high: 0, normal: 1, low: 2 }[a.priority] - { high: 0, normal: 1, low: 2 }[b.priority]));
  const fitsDeadline = (t, b) => `${b.date}T${clock(b.end)}` <= t.deadline;
  const locked = state.blocks.filter(b => b.locked).sort((a, b) => a.date.localeCompare(b.date) || a.start - b.start);
  for (const b of locked) {
    const t = active.find(t => t.id === b.taskId);
    if (!t) continue;
    const valid = b.date >= from && b.date >= currentDate && (b.date !== currentDate || b.start >= currentMinute) && b.start >= state.settings.start && b.end <= state.settings.end && fitsDeadline(t, b) && b.end - b.start === t.duration && ![...state.fixed, ...blocks].some(v => v.date === b.date && overlap(v, b));
    if (valid) blocks.push(b);
    else reasons.push({ taskId: t.id, reason: '原锁定时段已不满足时间或冲突约束，请解锁或修改固定事项。' });
  }
  for (const t of active) {
    if (blocks.some(b => b.taskId === t.id) || reasons.some(r => r.taskId === t.id)) continue;
    if (!t.deadline) { reasons.push({ taskId: t.id, reason: '截止时间待确认，暂不自动安排。' }); continue; }
    let placed = false;
    for (let day = 0; day < 14 && !placed; day++) {
      const date = shiftDateStr(from, day);
      if (date < currentDate || date > t.deadline.slice(0, 10)) continue;
      const occupied = [...state.fixed, ...blocks].filter(b => b.date === date);
      const start = Math.max(state.settings.start, date === currentDate ? Math.ceil(currentMinute / 15) * 15 : 0);
      for (let min = start; min + t.duration <= state.settings.end; min += 15) {
        const b = { taskId: t.id, date, start: min, end: min + t.duration, locked: false };
        if (fitsDeadline(t, b) && !occupied.some(v => overlap(v, b))) { blocks.push(b); placed = true; break; }
      }
    }
    if (!placed) reasons.push({ taskId: t.id, reason: '未来 14 天内，截止前没有足够的连续空闲时间。请调整可用时间或任务时长。' });
  }
  return { blocks, reasons };
}
