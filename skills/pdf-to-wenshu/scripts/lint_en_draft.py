#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
lint_en_draft.py —— 英文正文草稿的**入库前**质检：用 web_lint 的真实规则验尚未入库的文件。

为什么单独有这么一个脚本：`web_lint.py --paper` 只能查已经躺在集群里的文件，
等于「先塞进库、再看合不合格」，不合格的那一版已经污染了 vault。
本脚本直接 import web_lint 的检查函数，对 `_work/en-draft/` 里的草稿按同一口径跑，
**过了再搬进集群**。多子代理并行校订时，每个子代理都该先跑这一条。

    # 全批体检，顺便出报告
    python lint_en_draft.py --draft-dir _work/en-draft --report _work/lint_en_draft.txt
    # 子代理只验自己那几篇
    python lint_en_draft.py --draft-dir _work/en-draft --only "Example2024"

退出码：默认被检范围内有 error 则 1；`--fail-on-warnings` 下 warning 也返回 1。
"""
from __future__ import annotations

import argparse
import importlib.util
import io
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from shared.config import load_config as load_skill_config  # noqa: E402

SKILL_DIR = Path(__file__).resolve().parent.parent
SUFFIX = '.正文.en.md'


def blocking_count(errors: list, warnings: list, fail_on_warnings: bool) -> int:
    return len(errors) + (len(warnings) if fail_on_warnings else 0)


def load_cfg() -> dict:
    cfg = SKILL_DIR / 'config.json'
    return load_skill_config(cfg)


def load_module(path: Path, name: str):
    if not path.exists():
        sys.exit('找不到 %s：%s（config.json 里的路径指对了吗）' % (path.name, path))
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main() -> None:
    if sys.platform == 'win32':
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
    cfg = load_cfg()
    ap = argparse.ArgumentParser(description='英文草稿入库前质检（口径同 web_lint）')
    ap.add_argument('--vault', default=cfg.get('vault', 'vault'))
    ap.add_argument('--wenshu', default=cfg.get('wenshu', 'wenshu-pro'))
    ap.add_argument('--draft-dir', default='_work/en-draft')
    ap.add_argument('--only', default=None, help='只验 pid 含此子串的草稿')
    ap.add_argument('--report', default=None, help='把逐篇明细写到这个文件')
    ap.add_argument('--list', choices=['ok', 'blocked'], default=None,
                    help='只打印 pid 清单（一行一个），直接喂给 workboard.py init --items-file')
    ap.add_argument('--list-out', default=None,
                    help='把 --list 的清单直接写到这个文件（UTF-8）。'
                         'PowerShell 重定向会按控制台代码页解码 Python 的 UTF-8 输出，'
                         '中文 pid 会变成乱码，落盘清单一律走这个参数')
    ap.add_argument('--fail-on-warnings', action='store_true',
                    help='严格晋级：warning 与 error 一样阻断草稿入库')
    a = ap.parse_args()

    vault, draft_dir = Path(a.vault), Path(a.draft_dir)
    if not draft_dir.is_dir():
        sys.exit('找不到草稿目录：%s' % draft_dir)
    wl = load_module(Path(a.wenshu) / 'scripts' / 'web_lint.py', 'web_lint')
    # vault 侧的英文版式契约（## Abstract 等）只写在 lint_cluster 里；不一起跑的话
    # 「草稿验过了再搬」就是句空话——搬进去照样被 lint_cluster 拦下。
    lc = load_module(SKILL_DIR / 'scripts' / 'lint_cluster.py', 'lint_cluster')

    clusters = {pid: (ip, cd, idr) for pid, ip, cd, idr in wl.collect_clusters(vault)}
    pids = set(clusters)                      # 悬空链接按全库判定
    term_aliases = wl.load_term_aliases(vault, wl.Lint())

    rows, tally = [], Counter()
    for f in sorted(draft_dir.glob('*' + SUFFIX)):
        pid = f.name[:-len(SUFFIX)]
        if a.only and a.only not in pid:
            continue
        if pid not in clusters:
            rows.append((99, pid, ['集群里找不到这个 pid（草稿文件名与 index 对不上）'], []))
            continue
        _ip, cdir, idir = clusters[pid]
        en = f.read_text(encoding='utf-8')
        zh = wl.rd(cdir / (pid + '.正文.md'))

        lint = wl.Lint()
        wl.check_doc(lint, pid, '英文正文', en, idir, pids, term_aliases)
        wl.check_captions(lint, pid, en)
        wl.check_english_article(lint, pid, en, zh)
        cluster_lint = lc.Lint()
        lc.check_english_shell(cluster_lint, pid, en, wl.rd(cdir / (pid + '.txt')) or None)
        errs = [m for _p, m in lint.errors] + [m for _p, m in cluster_lint.errors]
        warns = [m for _p, m in lint.warns] + [m for _p, m in cluster_lint.warns]
        for m in errs:
            tally[re.sub(r'[：:].*', '', m)[:30]] += 1
        rows.append((blocking_count(errs, warns, a.fail_on_warnings), pid, errs, warns))

    if not rows:
        print('草稿目录里没有匹配的文件：%s' % (a.only or '*'))
        sys.exit(0)

    rows.sort(key=lambda r: (-r[0], r[1]))
    blocked = [r for r in rows if r[0]]

    if a.list:
        want = bool(a.list == 'blocked')
        listed = [pid for n, pid, _e, _w in sorted(rows, key=lambda r: r[1]) if bool(n) == want]
        if a.list_out:
            Path(a.list_out).parent.mkdir(parents=True, exist_ok=True)
            Path(a.list_out).write_text('\n'.join(listed) + '\n', encoding='utf-8')
            print('%s 清单 %d 项 → %s' % (a.list, len(listed), a.list_out))
        else:
            print('\n'.join(listed))
        sys.exit(0)
    gate = 'error 或 warning' if a.fail_on_warnings else 'error'
    out = ['# 英文草稿入库前质检 —— 共 %d 篇' % len(rows), '',
           '**会阻断入库（%s）：%d 篇；可入库（严格门槛通过）：%d 篇**'
           % (gate, len(blocked), len(rows) - len(blocked)), '']
    if tally:
        out += ['## error 类型分布', '']
        out += ['- %s：%d 篇' % (k, v) for k, v in tally.most_common()] + ['']
    out += ['## 逐篇', '']
    for _n, pid, errs, warns in rows:
        if not errs and not warns:
            out.append('- ✅ %s' % pid)
            continue
        out.append('### %s' % pid)
        out += ['- ❌ %s' % m for m in errs]
        out += ['- ⚠️ %s' % m for m in warns]
        out.append('')

    text = '\n'.join(out)
    if a.report:
        Path(a.report).parent.mkdir(parents=True, exist_ok=True)
        Path(a.report).write_text(text, encoding='utf-8')
    print(text if (a.only or len(rows) <= 12) else '\n'.join(out[:4]))
    print('—— lint_en_draft：%d 篇阻断 · %d 篇可入库%s'
          % (len(blocked), len(rows) - len(blocked),
             '，明细见 ' + a.report if a.report else ''))
    sys.exit(1 if blocked else 0)


if __name__ == '__main__':
    main()
