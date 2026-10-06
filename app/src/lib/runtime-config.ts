export type ServerConfig = { baseUrl: string };
const KEY = 'wenshu.server';
export function loadServerConfig(): ServerConfig {
  try { return { baseUrl: (JSON.parse(localStorage.getItem(KEY) || '{}') as ServerConfig).baseUrl || '' }; }
  catch { return { baseUrl: '' }; }
}
export function saveServerConfig(baseUrl: string) {
  const value = baseUrl.trim().replace(/\/+$/, '');
  if (value && !/^https?:\/\//i.test(value)) throw new Error('服务器地址必须以 http:// 或 https:// 开头');
  localStorage.setItem(KEY, JSON.stringify({ baseUrl: value }));
  return { baseUrl: value };
}
