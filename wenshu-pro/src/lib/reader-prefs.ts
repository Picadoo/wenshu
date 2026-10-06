const HOVER_KEY = 'wenshu.reader-hover';

type HoverListener = (on: boolean) => void;

const hoverListeners = new Set<HoverListener>();

export function loadHoverTips() {
  try {
    return window.localStorage.getItem(HOVER_KEY) !== '0';
  } catch {
    return true;
  }
}

export function setHoverTips(on: boolean) {
  try {
    window.localStorage.setItem(HOVER_KEY, on ? '1' : '0');
  } catch {
    // 忽略
  }
  hoverListeners.forEach((fn) => fn(on));
}

export function subscribeHoverTips(fn: HoverListener) {
  hoverListeners.add(fn);
  fn(loadHoverTips());
  return () => {
    hoverListeners.delete(fn);
  };
}

// ----------------------------------------------------------------------
// 正文术语标注开关：熟悉的术语（如 DEM）满篇标注反而碍眼，可整体关掉

const TERM_KEY = 'wenshu.reader-terms';

const termListeners = new Set<HoverListener>();

export function loadTermLinks() {
  try {
    return window.localStorage.getItem(TERM_KEY) !== '0';
  } catch {
    return true;
  }
}

export function setTermLinks(on: boolean) {
  try {
    window.localStorage.setItem(TERM_KEY, on ? '1' : '0');
  } catch {
    // 忽略
  }
  termListeners.forEach((fn) => fn(on));
}

export function subscribeTermLinks(fn: HoverListener) {
  termListeners.add(fn);
  fn(loadTermLinks());
  return () => {
    termListeners.delete(fn);
  };
}
