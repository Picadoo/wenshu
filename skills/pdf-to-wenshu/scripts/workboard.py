#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
workboard.py —— 多子代理并行的共享任务板：原子认领 + 崩溃回收 + 进度归集。

为什么需要它：主代理一次派 N 个子代理处理同一批论文时，如果只在 prompt 里写死
「你做第 1-5 篇」，任何一个子代理中途死掉，那几篇就静默丢了，主代理也看不出来。
任务板把「谁在做哪篇、做到哪一步」落到磁盘，子代理死了租约到期自动回收给别人。

用法（任务名自取，一个任务一块板）：

    # 主代理：建板
    python workboard.py init  --task en-revise --items-file _work/todo.txt
    python workboard.py init  --task en-revise --items "Example2024 ...,Example2024B ..."

    # 子代理：认领（原子，多个子代理同时喊也不会拿到同一篇）
    python workboard.py claim --task en-revise --agent A1 --n 3

    # 子代理：每做完一篇立刻回报（别攒到最后）
    python workboard.py report --task en-revise --agent A1 --item "<pid>" --status done
    python workboard.py report --task en-revise --agent A1 --item "<pid>" --status failed --note "原因"

    # 子代理：提前收工，把没做完的还回去
    python workboard.py release --task en-revise --agent A1

    # 主代理：随时看全局
    python workboard.py status --task en-revise

板文件：<VAULT>/90_系统/_ingest/_workboard.<task>.json
claim / report / release 都会打印一行 JSON，供子代理直接解析。
"""
from __future__ import annotations

import argparse
import io
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from shared.config import load_config as load_skill_config  # noqa: E402

SKILL_DIR = Path(__file__).resolve().parent.parent
LEASE_MIN_DEFAULT = 45
LOCK_STALE_SEC = 90


def now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec='seconds')


def age_min(iso: str | None) -> float:
    if not iso:
        return 1e9
    try:
        return (datetime.now(timezone.utc) - datetime.fromisoformat(iso).astimezone(
            timezone.utc)).total_seconds() / 60
    except ValueError:
        return 1e9


def default_vault() -> Path:
    cfg = SKILL_DIR / 'config.json'
    if cfg.exists():
        return Path(load_skill_config(cfg)['vault'])
    return Path('vault')


def board_path(vault: Path, task: str) -> Path:
    d = vault / '90_系统' / '_ingest'
    d.mkdir(parents=True, exist_ok=True)
    return d / ('_workboard.%s.json' % task)


class Lock:
    """跨进程互斥：O_EXCL 建锁文件，超时抢占陈旧锁。

    Windows 上没有 fcntl，文件独占创建是最稳的一招；锁只在读-改-写的
    毫秒级窗口里持有，正常不会撞上。
    """

    def __init__(self, target: Path, timeout: float = 20.0):
        self.path = target.with_suffix(target.suffix + '.lock')
        self.timeout = timeout
        self.fd = None

    def __enter__(self):
        deadline = time.time() + self.timeout
        while True:
            try:
                self.fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(self.fd, str(os.getpid()).encode())
                return self
            except FileExistsError:
                try:
                    if time.time() - self.path.stat().st_mtime > LOCK_STALE_SEC:
                        self.path.unlink(missing_ok=True)   # 持锁进程已死，抢回来
                        continue
                except OSError:
                    pass
                if time.time() > deadline:
                    raise TimeoutError('任务板被占用超过 %.0f 秒：%s' % (self.timeout, self.path))
                time.sleep(0.05)

    def __exit__(self, *exc):
        if self.fd is not None:
            os.close(self.fd)
        self.path.unlink(missing_ok=True)


def load(bp: Path) -> dict:
    if not bp.exists():
        sys.exit('找不到任务板：%s（先跑 init）' % bp)
    return json.loads(bp.read_text(encoding='utf-8'))


def save(bp: Path, board: dict) -> None:
    tmp = bp.with_suffix('.tmp')
    tmp.write_text(json.dumps(board, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(tmp, bp)


def emit(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False))


def known_pids(vault: Path) -> set[str]:
    """库内已成立的集群 pid（有中文正文的即算成立）。"""
    out = set()
    for f in (vault / 'Papers').rglob('*.正文.md'):
        if not f.name.endswith('.正文.en.md'):
            out.add(f.name[:-len('.正文.md')])
    return out


def cmd_init(a, bp: Path, vault: Path) -> None:
    items = []
    if a.items_file:
        items += [x.strip() for x in Path(a.items_file).read_text(encoding='utf-8').splitlines()]
    if a.items:
        items += [x.strip() for x in a.items.split(',')]
    items = [x.lstrip('\ufeff').strip() for x in items]
    items = [x for x in items if x and not x.startswith('#')]
    if not items:
        sys.exit('没有任务项：--items-file 或 --items 至少给一个')

    # 清单大多来自 shell 重定向，而 PowerShell 会按控制台代码页解码 Python 的
    # UTF-8 输出，中文 pid 落盘即成乱码。乱码 pid 建板不会报错，子代理认领后
    # 才发现一篇都找不到，所以在建板这一步就拦住。
    if not a.no_verify:
        pool = known_pids(vault)
        bad = [x for x in items if x not in pool]
        if bad:
            print('❌ 有 %d 项在库里找不到对应集群，任务板没有建立：' % len(bad))
            for x in bad[:10]:
                print('   %s' % x)
            if len(bad) > 10:
                print('   …另有 %d 项' % (len(bad) - 10))
            print('清单若由 shell 重定向产生，改用脚本自身的落盘参数'
                  '（如 lint_en_draft.py --list ok --list-out <文件>）重出一份；'
                  '确认清单无误要强行建板则加 --no-verify')
            sys.exit(1)

    if bp.exists() and not a.force:
        sys.exit('任务板已存在：%s（要重建加 --force；重建会丢掉已有进度）' % bp)
    board = {
        'task': a.task, 'note': a.note or '', 'createdAt': now(),
        'items': [{'id': x, 'status': 'todo', 'agent': None, 'claimedAt': None,
                   'finishedAt': None, 'attempts': 0, 'note': ''} for x in dict.fromkeys(items)],
    }
    with Lock(bp):
        save(bp, board)
    emit({'ok': True, 'task': a.task, 'board': str(bp), 'total': len(board['items'])})


def cmd_claim(a, bp: Path) -> None:
    with Lock(bp):
        board = load(bp)
        pick = [it for it in board['items'] if it['status'] == 'todo']
        # 租约过期的认领视为子代理已死，回收再派
        stale = [it for it in board['items']
                 if it['status'] == 'claimed' and age_min(it['claimedAt']) > a.lease_min]
        got = (pick + stale)[:max(1, a.n)]
        for it in got:
            it.update(status='claimed', agent=a.agent, claimedAt=now(),
                      attempts=it['attempts'] + 1)
        if got:
            save(bp, board)
    emit({'ok': True, 'agent': a.agent, 'assigned': [it['id'] for it in got],
          'reclaimed': [it['id'] for it in got if it in stale],
          'remainingTodo': sum(1 for it in board['items'] if it['status'] == 'todo')})


def cmd_report(a, bp: Path) -> None:
    with Lock(bp):
        board = load(bp)
        hit = next((it for it in board['items'] if it['id'] == a.item), None)
        if hit is None:
            emit({'ok': False, 'error': '任务板里没有这一项：%s' % a.item})
            sys.exit(1)
        # 不校验认领人：租约过期被别人接手后，原主回报仍应记账而不是报错丢结果
        hit.update(status=a.status, finishedAt=now(), note=a.note or '')
        if hit['agent'] and hit['agent'] != a.agent:
            hit['reportedBy'] = a.agent      # 租约被别人接手过，两边都留痕
        hit['agent'] = hit['agent'] or a.agent
        save(bp, board)
    left = sum(1 for it in board['items'] if it['status'] in ('todo', 'claimed'))
    emit({'ok': True, 'item': a.item, 'status': a.status, 'remaining': left})


def cmd_release(a, bp: Path) -> None:
    with Lock(bp):
        board = load(bp)
        back = [it for it in board['items']
                if it['status'] == 'claimed' and it['agent'] == a.agent]
        for it in back:
            it.update(status='todo', agent=None, claimedAt=None)
        if back:
            save(bp, board)
    emit({'ok': True, 'agent': a.agent, 'released': [it['id'] for it in back]})


def cmd_status(a, bp: Path) -> None:
    board = load(bp)
    items = board['items']
    tally = {k: sum(1 for it in items if it['status'] == k)
             for k in ('todo', 'claimed', 'done', 'failed')}
    if a.json:
        emit({'ok': True, 'task': board['task'], 'tally': tally, 'items': items})
        return
    print('任务板 %s ｜ 共 %d 项：待办 %d · 在做 %d · 完成 %d · 失败 %d'
          % (board['task'], len(items), tally['todo'], tally['claimed'],
             tally['done'], tally['failed']))
    if board.get('note'):
        print('说明：' + board['note'])
    for it in items:
        if it['status'] == 'todo':
            continue
        extra = ''
        if it['status'] == 'claimed':
            extra = ' ｜已认领 %.0f 分钟' % age_min(it['claimedAt'])
        if it.get('reportedBy'):
            extra += ' ｜回报人 ' + it['reportedBy']
        if it['note']:
            extra += ' ｜' + it['note'][:60]
        print('  [%-7s] %-46s %s%s' % (it['status'], it['id'][:46], it['agent'] or '-', extra))
    if tally['todo']:
        print('  待办 %d 项未列出（用 --json 看全量）' % tally['todo'])


def main() -> None:
    if sys.platform == 'win32':
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
    ap = argparse.ArgumentParser(description='多子代理并行任务板')
    ap.add_argument('--vault', default=None)
    sub = ap.add_subparsers(dest='cmd', required=True)

    p = sub.add_parser('init', help='建板')
    p.add_argument('--task', required=True)
    p.add_argument('--items-file')
    p.add_argument('--items')
    p.add_argument('--note', default='')
    p.add_argument('--force', action='store_true')
    p.add_argument('--no-verify', action='store_true',
                   help='跳过「每一项都得对上库内集群」的校验（清单不是 pid 时才用）')

    p = sub.add_parser('claim', help='认领（原子）')
    p.add_argument('--task', required=True)
    p.add_argument('--agent', required=True)
    p.add_argument('--n', type=int, default=1)
    p.add_argument('--lease-min', type=float, default=LEASE_MIN_DEFAULT)

    p = sub.add_parser('report', help='回报单项结果')
    p.add_argument('--task', required=True)
    p.add_argument('--agent', required=True)
    p.add_argument('--item', required=True)
    p.add_argument('--status', required=True, choices=['done', 'failed'])
    p.add_argument('--note', default='')

    p = sub.add_parser('release', help='把自己没做完的还回去')
    p.add_argument('--task', required=True)
    p.add_argument('--agent', required=True)

    p = sub.add_parser('status', help='看全局')
    p.add_argument('--task', required=True)
    p.add_argument('--json', action='store_true')

    a = ap.parse_args()
    vault = Path(a.vault) if a.vault else default_vault()
    bp = board_path(vault, a.task)
    if a.cmd == 'init':
        cmd_init(a, bp, vault)
        return
    {'claim': cmd_claim, 'report': cmd_report,
     'release': cmd_release, 'status': cmd_status}[a.cmd](a, bp)


if __name__ == '__main__':
    main()
