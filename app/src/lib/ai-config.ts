export type ReasoningEffort = 'minimal' | 'low' | 'medium' | 'high';
export type AiConfig = { baseUrl: string; apiKey: string; model: string; reasoningEffort: ReasoningEffort };
export const REASONING_EFFORT_OPTIONS: { value: ReasoningEffort; label: string }[] = [
  { value: 'minimal', label: '最省' }, { value: 'low', label: '低' }, { value: 'medium', label: '中' }, { value: 'high', label: '高' },
];
const KEY = 'wenshu.ai';
const EMPTY: AiConfig = { baseUrl: '', apiKey: '', model: '', reasoningEffort: 'medium' };
export function loadAiConfig(): AiConfig {
  try { return { ...EMPTY, ...JSON.parse(localStorage.getItem(KEY) || '{}') }; }
  catch { return { ...EMPTY }; }
}
export function saveAiConfig(patch: Partial<AiConfig>): AiConfig {
  const next = { ...loadAiConfig(), ...patch };
  next.baseUrl = next.baseUrl.trim().replace(/\/+$/, '');
  if (next.baseUrl && !/^https?:\/\//i.test(next.baseUrl)) throw new Error('接口地址必须以 http:// 或 https:// 开头');
  localStorage.setItem(KEY, JSON.stringify(next));
  return next;
}
export function hasAiKey(config = loadAiConfig()) { return Boolean(config.baseUrl && config.apiKey); }
async function request(path: string, config: AiConfig, body?: unknown) {
  if (!hasAiKey(config)) throw new Error('请在设置中填写 AI 接口地址与 Key');
  const response = await fetch(config.baseUrl + '/' + path, {
    method: body ? 'POST' : 'GET',
    headers: { Authorization: 'Bearer ' + config.apiKey, 'Content-Type': 'application/json' },
    ...(body ? { body: JSON.stringify(body) } : {}),
  });
  if (!response.ok) throw new Error('AI 请求失败 (' + response.status + ')');
  return response.json();
}
export async function fetchAiModels(config = loadAiConfig()): Promise<string[]> {
  const result = await request('models', config);
  return [...new Set<string>((result.data || []).map((item: { id?: string }) => item.id).filter(Boolean))].sort();
}
export async function ensureAiModel(config = loadAiConfig()): Promise<AiConfig> {
  if (config.model) return config;
  const models = await fetchAiModels(config);
  if (!models.length) throw new Error('接口没有返回可用模型');
  return saveAiConfig({ model: models[0] });
}
export async function chatCompletions(prompt: string, config = loadAiConfig()): Promise<string> {
  if (!config.model) throw new Error('请在设置中指定模型');
  const result = await request('chat/completions', config, {
    model: config.model, temperature: 0.2, reasoning_effort: config.reasoningEffort,
    messages: [{ role: 'system', content: 'You are a bilingual learner dictionary. Reply with JSON only, no markdown fences.' }, { role: 'user', content: prompt }],
  });
  return result.choices?.[0]?.message?.content?.trim() || '';
}
