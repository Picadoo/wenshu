import { useRef, useEffect } from 'react';

import {
  isReadingTab,
  readingScroll,
  loadPaperSession,
  saveReadingProgress,
} from 'src/lib/reader-session';

type Args = {
  slug: string;
  title: string;
  tab: string;
  split: string;
  contentReady: boolean;
  suspendSave?: boolean;
};

/**
 * 按「论文 + 正文页签」记住滚动位置。
 * 图片 / PDF / 笔记不写进度；筛选段落时不写；未真正滚动过不会用 0 覆盖旧进度。
 */
export function useReadingProgress({ slug, title, tab, split, contentReady, suspendSave }: Args) {
  const suspendRef = useRef(Boolean(suspendSave));
  suspendRef.current = Boolean(suspendSave);

  useEffect(() => {
    if (!slug || !isReadingTab(tab) || !contentReady) return undefined;

    const resume = readingScroll(loadPaperSession(slug), tab);
    let allowSave = resume <= 0;
    let userScrolled = false;
    let lastY = resume;
    let tries = 0;
    let debounce = 0;
    let ignoreUntil = 0;

    const persist = (quiet: boolean) => {
      if (suspendRef.current) return;
      saveReadingProgress(
        {
          slug,
          title,
          tab,
          scroll: allowSave ? lastY : resume,
          split,
        },
        { quiet }
      );
    };

    persist(false);

    const finishRestore = () => {
      allowSave = true;
      lastY = resume;
      ignoreUntil = Date.now() + 400;
    };

    const restoreTimer =
      resume > 0
        ? window.setInterval(() => {
            tries += 1;
            const max = Math.max(0, document.documentElement.scrollHeight - window.innerHeight);
            const target = Math.min(resume, max);
            window.scrollTo(0, target);
            const closeEnough = Math.abs(window.scrollY - target) < 24;
            const waitedOut = tries >= 40;
            if ((max >= resume - 24 && closeEnough) || waitedOut) {
              window.clearInterval(restoreTimer);
              finishRestore();
            }
          }, 80)
        : 0;

    if (resume <= 0) {
      window.scrollTo(0, 0);
      lastY = 0;
      finishRestore();
    }

    const onScroll = () => {
      if (!allowSave || Date.now() < ignoreUntil || suspendRef.current) return;
      lastY = window.scrollY;
      userScrolled = true;
      window.clearTimeout(debounce);
      debounce = window.setTimeout(() => persist(true), 220);
    };

    const onLeave = () => {
      if (!allowSave || !userScrolled || suspendRef.current) return;
      persist(true);
    };

    const onHide = () => {
      if (document.visibilityState === 'hidden') onLeave();
    };

    window.addEventListener('scroll', onScroll, { passive: true });
    window.addEventListener('pagehide', onLeave);
    document.addEventListener('visibilitychange', onHide);

    return () => {
      window.clearTimeout(debounce);
      window.clearInterval(restoreTimer);
      window.removeEventListener('scroll', onScroll);
      window.removeEventListener('pagehide', onLeave);
      document.removeEventListener('visibilitychange', onHide);
      onLeave();
    };
  }, [slug, title, tab, split, contentReady]);
}
