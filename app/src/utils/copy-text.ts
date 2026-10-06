export async function copyText(value: string, input?: HTMLInputElement | null): Promise<boolean> {
  if (!value) return false;

  // HTTPS / localhost 才有 Clipboard API；公网 IP 的 http://host:5010 会直接拒绝。
  if (window.isSecureContext && navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(value);
      return true;
    } catch {
      // 继续走选中输入框 / execCommand
    }
  }

  if (input) {
    try {
      input.focus();
      input.select();
      input.setSelectionRange(0, value.length);
      if (document.execCommand('copy')) return true;
    } catch {
      // 再试隐藏 textarea
    }
  }

  return copyViaTextarea(value);
}

function copyViaTextarea(value: string): boolean {
  const area = document.createElement('textarea');
  area.value = value;
  area.setAttribute('readonly', '');
  area.setAttribute('aria-hidden', 'true');
  area.style.cssText = 'position:fixed;top:0;left:0;width:1px;height:1px;padding:0;border:none;opacity:0;';
  document.body.appendChild(area);
  area.focus();
  area.select();
  area.setSelectionRange(0, value.length);
  let ok = false;
  try {
    ok = document.execCommand('copy');
  } catch {
    ok = false;
  }
  document.body.removeChild(area);
  return ok;
}
