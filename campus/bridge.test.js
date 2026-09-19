import { describe, expect, it } from 'vitest';
import { parseBridgeResults } from './bridge.js';

const candidate = {
  action: 'create', title: '实验报告', deadline: '2026-09-20T18:00', duration: 60,
  priority: 'normal', targetId: null, evidence: '请提交实验报告', notes: '',
};

describe('bridge result import', () => {
  it('maps a done record into review candidates', () => {
    const result = parseBridgeResults({ event: { chat_name: '微信接入测试' }, result: { candidates: [candidate] } });
    expect(result).toHaveLength(1);
    expect(result[0]).toMatchObject({ ...candidate, source: '微信接入测试' });
    expect(result[0].id).toBeTruthy();
    expect(result[0].warning).toContain('微信桥接');
  });

  it('rejects malformed records', () => {
    expect(() => parseBridgeResults({ event: {}, result: { candidates: [{ title: '' }] } })).toThrow();
  });
});
