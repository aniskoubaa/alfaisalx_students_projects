import type { TopicInfo } from '../api/setup-types';

export const MAX_WATCHES = 4;
export const WATCH_MAX_HZ = 5;

export function sortTopics(list: TopicInfo[]): TopicInfo[] {
  return [...list].sort((a, b) => a.name.localeCompare(b.name));
}

/** Topics whose name or type contains the filter text (case does not matter). */
export function filterTopics(list: TopicInfo[], filter: string): TopicInfo[] {
  const f = filter.trim().toLowerCase();
  if (!f) return list;
  return list.filter(
    (t) => t.name.toLowerCase().includes(f) || (t.types ?? []).join(' ').toLowerCase().includes(f),
  );
}

export function rateText(rate: number | null | undefined): string {
  return rate == null ? 'waiting…' : rate.toFixed(1) + ' Hz';
}

/** A message as readable text. Long values are cut so a big array cannot freeze the page. */
export function messageText(data: unknown, limit = 6000): string {
  if (data == null) return '(waiting for the first message)';
  let t: string;
  try {
    t = JSON.stringify(data, null, 2) ?? String(data);
  } catch {
    t = String(data);
  }
  return t.length > limit ? t.slice(0, limit) + '\n… (cut, the message is longer)' : t;
}
