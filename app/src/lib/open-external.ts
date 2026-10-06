/** 在系统默认浏览器打开 http(s) 链接；桌面版不走 WebView。 */

export function isHttpUrl(url: string) {
  return /^https?:\/\//i.test(url.trim());
}

export async function openExternal(url: string) {
  const href = url.trim();
  if (!isHttpUrl(href)) return;

  if (typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window) {
    const { invoke } = await import('@tauri-apps/api/core');
    await invoke('open_external', { url: href });
    return;
  }

  window.open(href, '_blank', 'noopener,noreferrer');
}
