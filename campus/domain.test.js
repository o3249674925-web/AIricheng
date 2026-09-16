import { describe, expect, it } from 'vitest';
import { applyCandidate, emptyState, parseLocal, schedule } from './domain.js';

const base = () => ({ ...emptyState(), settings: { start: 9 * 60, end: 22 * 60 } });
const candidate = (overrides = {}) => ({ action: 'create', title: '实验报告', deadline: '2026-09-20T18:00', duration: 60, priority: 'normal', targetId: null, evidence: '群通知：实验报告周日18:00前提交', notes: '', ...overrides });

describe('校园通知领域规则', () => {
  it('保留原文并将一次改期应用到同一任务', () => {
    let state = base();
    state = applyCandidate(state, candidate(), '课程群');
    const task = state.tasks[0];
    state = applyCandidate(state, candidate({ action: 'update', targetId: task.id, deadline: '2026-09-21T18:00', evidence: '老师：改到周一18:00，只交电子版', notes: '只交电子版' }), '课程群');
    expect(state.tasks).toHaveLength(1);
    expect(state.tasks[0].deadline).toBe('2026-09-21T18:00');
    expect(state.tasks[0].history).toHaveLength(2);
  });
  it('拒绝同来源同名重复任务', () => {
    const state = applyCandidate(base(), candidate(), '课程群');
    expect(() => applyCandidate(state, candidate(), '课程群')).toThrow(/同来源/);
  });
  it('为明确截止时间安排，并避开固定事项', () => {
    let state = applyCandidate(base(), candidate({ deadline: '2026-09-20T18:00', duration: 90 }), '课程群');
    state = { ...state, fixed: [{ id: 'class', title: '高数', date: '2026-09-19', start: 9 * 60, end: 12 * 60 }] };
    const result = schedule(state, '2026-09-19', new Date('2026-09-19T08:00:00+08:00'));
    expect(result.blocks).toHaveLength(1);
    expect(result.blocks[0].start).toBe(12 * 60);
    expect(result.blocks[0].date).toBe('2026-09-19');
  });
  it('对缺少课表上下文的相对时间不做猜测', () => {
    const result = parseLocal('请下节课前交作业', '2026-09-16', [], '课程群');
    expect(result[0].deadline).toBe('');
    expect(result[0].warning).toMatch(/核对/);
  });
});
