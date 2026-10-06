import { generatedActivity } from './generated-activity';

// ----------------------------------------------------------------------

export type ActivityDay = {
  mine: number;
  ai: number;
};

export type ActivityData = {
  generatedAt: string;
  days: Record<string, ActivityDay>;
  papersByDay: Record<string, number>;
};

/** 运行时从 /vault/activity.json 水化（见 hydrate-vault.ts），烤入数据为兜底。 */
export const activity: ActivityData = { ...generatedActivity };

export function hydrateActivity(next: ActivityData) {
  activity.generatedAt = next.generatedAt;
  activity.days = next.days;
  activity.papersByDay = next.papersByDay;
}

const LOCAL_KEY = 'wenshu.activity.local';

/** 本地时区的 YYYY-MM-DD。不能用 toISOString（UTC）：北京时间凌晨的活动会被记到前一天 */
export function localIsoDate(date = new Date()) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
}

/** 浏览器内记笔记/高亮/生词也计入热力图（本地暂存，桌面版会写进 vault 活动日志）。 */
export function recordLocalActivity(date = new Date()) {
  try {
    const key = localIsoDate(date);
    const store = JSON.parse(window.localStorage.getItem(LOCAL_KEY) || '{}') as Record<string, number>;
    store[key] = (store[key] ?? 0) + 1;
    window.localStorage.setItem(LOCAL_KEY, JSON.stringify(store));
  } catch {
    // 忽略存储失败
  }
}

export function mergedActivityDays(): Record<string, ActivityDay> {
  const merged: Record<string, ActivityDay> = {};
  Object.entries(activity.days).forEach(([date, day]) => {
    merged[date] = { ...day };
  });
  try {
    const local = JSON.parse(window.localStorage.getItem(LOCAL_KEY) || '{}') as Record<string, number>;
    Object.entries(local).forEach(([date, count]) => {
      const slot = merged[date] ?? { mine: 0, ai: 0 };
      slot.mine += count;
      merged[date] = slot;
    });
  } catch {
    // 忽略
  }
  return merged;
}

export type Granularity = 'day' | 'week' | 'month' | 'year';

function toIsoDate(date: Date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
}

function shiftDate(date: Date, days: number) {
  const next = new Date(date);
  next.setDate(date.getDate() + days);
  return next;
}

function mondayOf(date: Date) {
  const monday = new Date(date.getFullYear(), date.getMonth(), date.getDate());
  monday.setDate(monday.getDate() - ((monday.getDay() + 6) % 7));
  return monday;
}

function rangeWeeks(count: number) {
  const monday = mondayOf(new Date());
  return Array.from({ length: count }, (_, index) => toIsoDate(shiftDate(monday, (index - count + 1) * 7)));
}

function rangeMonths(count: number) {
  const now = new Date();
  return Array.from({ length: count }, (_, index) => {
    const date = new Date(now.getFullYear(), now.getMonth() - count + 1 + index, 1);
    return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`;
  });
}

function rangeYears(count: number) {
  const year = new Date().getFullYear();
  return Array.from({ length: count }, (_, index) => String(year - count + 1 + index));
}

function bucketKey(date: string, granularity: Granularity) {
  const parsed = new Date(`${date}T00:00:00`);
  if (Number.isNaN(parsed.getTime())) return '';
  if (granularity === 'year') return date.slice(0, 4);
  if (granularity === 'month') return date.slice(0, 7);
  if (granularity === 'week') return toIsoDate(mondayOf(parsed));
  return date;
}

function formatWeekLabel(iso: string) {
  const date = new Date(`${iso}T00:00:00`);
  return `${date.getMonth() + 1}/${date.getDate()}`;
}

function formatMonthLabel(ym: string) {
  return `${Number(ym.slice(5))}月`;
}

/** 按天/周/月聚合成堆叠柱状图数据（近 windowDays 天）。 */
export function aggregateActivity(granularity: Granularity, windowDays = 365) {
  const days = mergedActivityDays();
  const buckets = new Map<string, { mine: number; ai: number }>();
  const since = new Date();
  since.setDate(since.getDate() - windowDays);

  Object.entries(days).forEach(([date, day]) => {
    const parsed = new Date(`${date}T00:00:00`);
    if (Number.isNaN(parsed.getTime()) || parsed < since) return;
    const key = bucketKey(date, granularity);
    if (!key) return;
    const slot = buckets.get(key) ?? { mine: 0, ai: 0 };
    slot.mine += day.mine;
    slot.ai += day.ai;
    buckets.set(key, slot);
  });

  const keys = [...buckets.keys()].sort();
  return {
    categories: keys,
    mine: keys.map((key) => buckets.get(key)!.mine),
    ai: keys.map((key) => buckets.get(key)!.ai),
  };
}

export type ActivityChartSeries = {
  name: string;
  categories: string[];
  data: { name: string; data: number[] }[];
};

function seriesFromKeys(
  name: string,
  keys: string[],
  granularity: Granularity,
  labels: string[]
): ActivityChartSeries {
  const filled = aggregateActivity(granularity);
  const lookup = new Map(filled.categories.map((key, index) => [key, index]));
  return {
    name,
    categories: labels,
    data: [
      { name: '笔记', data: keys.map((key) => filled.mine[lookup.get(key) ?? -1] ?? 0) },
      { name: '入库', data: keys.map((key) => filled.ai[lookup.get(key) ?? -1] ?? 0) },
    ],
  };
}

/** File 模板 Data activity 同款：补齐空档，周 / 月 / 年各一套。 */
export function activityChartSeries(): ActivityChartSeries[] {
  const weeks = rangeWeeks(8);
  const months = rangeMonths(9);
  const years = rangeYears(4);
  return [
    seriesFromKeys('按周', weeks, 'week', weeks.map(formatWeekLabel)),
    seriesFromKeys('按月', months, 'month', months.map(formatMonthLabel)),
    seriesFromKeys('按年', years, 'year', years),
  ];
}
