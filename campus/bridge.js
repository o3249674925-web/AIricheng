import { extractionSchema, uid } from './domain.js';

export function parseBridgeResults(value) {
  const records = Array.isArray(value) ? value : [value];
  return records.flatMap(record => {
    const parsed = extractionSchema.parse(record?.result);
    const source = String(record?.event?.chat_name || '微信通知').trim() || '微信通知';
    return parsed.candidates.map(candidate => ({
      ...candidate,
      id: uid(),
      source,
      warning: '微信桥接 AI 结果，请核对原文后确认。',
    }));
  });
}
