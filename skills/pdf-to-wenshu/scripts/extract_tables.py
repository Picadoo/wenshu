#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 PDF 确定性抽出**英文原表** → `content/<pid>.tables.md`（表格索引）。

为什么要有这一步：PDF 机器 dump（`doc[i].get_text()`）会把表格打散成一列一列的
碎字符，表体数字整段丢失。于是同一批数字被 AI 手工重建两遍——中文正文一遍、
英文正文一遍。而 `pymupdf4llm` 的版面模型本来就能把表格解析成 Markdown（技能
早已依赖它做版面级抽图），只是从没拿它抽过表。

抽出来的表是**英文原表**：
  · 英文正文可以原样注入，一个字都不用改；
  · 中文正文只需把表头/行标签译成中文，表体数字照搬（数字与语言无关）。

抽不干净的表**如实标注**，不猜：合并单元格、行列数对不上都会打上「需人工核对」，
并保留原始 `<br>`，让人一眼看出哪儿要动手。宁可标出来，也不静默编一张看着整齐的假表。

用法：
    python extract_tables.py "<pdf>" "<out.tables.md>" [--pid <pid>] [--quiet]
    python extract_tables.py --scan vault/Papers [--force]     # 全库补齐/刷新

stdout 末行是机器可读的 COVERAGE JSON，供编排脚本判定。
"""
from __future__ import annotations

import argparse
import io
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lint_cluster import restore_math_glyphs      # noqa: E402  字形判据全技能共用一份

# 表标签行只认「整体被强调过」的三种写法：加粗标签 `**Table 3**`、整行加粗的
# `**Table 3. 题注**`、或独占一行的裸 `Table 3`。绝不放宽到「行首是 Table N」——正文
# 「…are presented in Table 5. The data of…」被硬折行后同样是行首，放宽就会把一整段
# 正文当成表题收进来。
LABEL_BOLD = re.compile(r'^\*\*\s*Table\s+(\d{1,2})\s*[.:]?\s*\*\*\s*(.*)$', re.I)
LABEL_WHOLE = re.compile(r'^\*\*\s*Table\s+(\d{1,2})\s*[.:]?\s+(.+?)\s*\*\*\s*$', re.I)
LABEL_BARE = re.compile(r'^Table\s+(\d{1,2})\s*[.:]?\s*$', re.I)
# pymupdf4llm 见到大号/加粗字就按标题渲染，表题常出来是 `###### **Table 2**`。
# 不剥掉这层前缀，上面三条一条都对不上（实测 Example2024 因此漏了 5 张表）。
HEADING = re.compile(r'^#{1,6}\s*')
# 表题被排进表格首列时，`**Table 3**` 会连着题注一起挤在 (0,0) 这一格里
CAPTION_CELL = re.compile(r'^\*\*\s*Table\s+(\d{1,2})\s*[.:]?\s*\*\*\s*(.*)$', re.I)
MENTION = re.compile(r'\bTable\s+(\d{1,2})\b', re.I)
SEP_ROW = re.compile(r'^\|[\s:|-]+\|$')
# 「/」「—」是期刊表里「本行是分组标题、无数值」的占位，与数字同属「体值」
VALUE = re.compile(r'^(?:[−–—+-]?\d[\d,]*(?:\.\d+)?\s*%?|/|—|-|N/?A)$', re.I)


def _cells(row: str) -> list[str]:
    """按 `|` 切格；只削掉首尾**各一个**空元素。

    不能用 `strip('|')`：`||L3|3.47|…|` 的首格本来就是空的（跨行合并留下的空位），
    一路削光会让整行左移一格，数字全部对错列。
    """
    parts = row.rstrip().split('|')
    if parts and not parts[0].strip():
        parts = parts[1:]
    if parts and not parts[-1].strip():
        parts = parts[:-1]
    return [c.strip() for c in parts]


def _join_wrap(parts: list[str]) -> str:
    """把同一格里被排版折行的碎片接回去：`ResNet-` + `34` → `ResNet-34`。"""
    out = ''
    for p in parts:
        p = p.strip()
        if not p:
            continue
        if not out:
            out = p
        elif out.endswith('-'):
            out += p
        else:
            out += ' ' + p
    return out


def _contract_safe(cell: str) -> str:
    """渲染契约：表格单元格里的裸不等号会被当 HTML 转义、崩掉整张表。"""
    cell = cell.replace('<br>', '\x00')
    cell = cell.replace('<', r'\lt ').replace('>', r'\gt ')
    cell = re.sub(r'\s{2,}', ' ', cell).strip()
    return cell.replace('\x00', '<br>')


def _merge_continuation(rows: list[list[str]]) -> list[list[str]]:
    """整行只剩首格、且上一行首格以连字符收尾 → 是被折下来的半个词，接回去。

    只认「上一行以 `-` 收尾」这一种，绝不按「本行只有一格」就并——期刊表里
    「Heavy-weight Models」这类分组标题行本来就只有一格有字，并错了就丢数据。
    """
    out: list[list[str]] = []
    for row in rows:
        head, rest = row[0], row[1:]
        if out and head and not any(rest) and out[-1][0].endswith('-'):
            out[-1][0] += head
            continue
        out.append(list(row))
    return out


def _is_multi_value(parts: list[str]) -> bool:
    """这一格是「k 个数值被并进同一格」，而不是一个词被排版折了行。"""
    vals = [p.strip() for p in parts if p.strip()]
    return len(vals) > 1 and all(VALUE.match(v) for v in vals)


def _split_merged(rows: list[list[str]]) -> tuple[list[list[str]], int]:
    """一格里塞了 k 个数值 = 版面把 k 个物理行并成了一行，拆回 k 行。

    只拆**数值格**：文字格里的多段几乎都是排版折行（`ResNet-` + `34`、
    `Efficient` + `Modules`），按 k 均分只会拼出一张对不上号的整齐假表。
    数值拆开、文字并进本组第一行，并计一笔待核对交给人眼。
    """
    out: list[list[str]] = []
    unsure = 0
    for row in rows:
        split = [[p.strip() for p in c.split('<br>')] for c in row]
        ks = {len(p) for p in split if _is_multi_value(p)}
        if len(ks) != 1:
            if any(_is_multi_value(p) for p in split):
                unsure += 1
            out.append(['<br>'.join(p) if _is_multi_value(p) else _join_wrap(p) for p in split])
            continue
        k = ks.pop()
        new = [['' for _ in row] for _ in range(k)]
        for ci, parts in enumerate(split):
            if _is_multi_value(parts) and len(parts) == k:
                for ri in range(k):
                    new[ri][ci] = parts[ri]
            else:
                new[0][ci] = _join_wrap(parts)
                if len(parts) > 1:      # 文字被折成多段，落点无法确定
                    unsure += 1
        out.extend(new)
    return out, unsure


def normalize(raw_rows: list[str]) -> tuple[list[list[str]], list[str]]:
    """把 pymupdf4llm 的原始表格行整理成干净 Markdown 表，并返回待核对原因。"""
    notes: list[str] = []
    grid = [_cells(r) for r in raw_rows if not SEP_ROW.match(r.strip())]
    if not grid:
        return [], ['解析不出任何行']
    width = max(len(r) for r in grid)
    grid = [r + [''] * (width - len(r)) for r in grid]

    header = [_join_wrap(c.split('<br>')) for c in grid[0]]
    body, unsure = _split_merged(_merge_continuation(grid[1:]))
    if unsure:
        notes.append(f'{unsure} 处单元格被版面并过，落点定不下来（数值已拆行，文字并进本组首行）')
    body = [r for r in body if any(c.strip() for c in r)]
    if not body:
        notes.append('只解析出表头、没有表体')

    table = [[_contract_safe(c) for c in header]] + [[_contract_safe(c) for c in r] for r in body]
    return table, notes


def render(table: list[list[str]]) -> str:
    if not table:
        return ''
    width = len(table[0])
    lines = ['| ' + ' | '.join(table[0]) + ' |',
             '| ' + ' | '.join(['---'] * width) + ' |']
    for row in table[1:]:
        lines.append('| ' + ' | '.join(row) + ' |')
    return '\n'.join(lines)


def _caption_column(rows: list[str]):
    """Springer 一类版式把表题排在表格**首列**里，版面模型于是把它折进了 (0,0) 格。

    形如 `|**Table 3**Mass-based size<br>fractions…|Case|2.8–4|…`——表题不成行，
    上面三条标签正则一条都碰不到，整张表就此隐形（Example2024 因此漏了 5 张）。
    认出来之后把首列整列摘掉当题注：题注太长时本来就是顺着首列往下续排的。
    返回 (pending, 去掉题注列的行)；不是这种版式则返回 (None, 原行)。
    """
    head = _cells(rows[0])
    m = CAPTION_CELL.match(head[0].strip()) if head else None
    if not m or len(head) < 2:
        return None, rows
    caption = [m.group(2)]
    for r in rows[1:]:
        cells = _cells(r)
        first = cells[0].strip() if cells else ''
        if first and not set(first) <= {'-', ':'}:
            caption.append(first)
    stripped = ['|' + '|'.join(_cells(r)[1:]) + '|' for r in rows]
    return {'num': int(m.group(1)),
            'caption': [c.replace('<br>', ' ') for c in caption if c],
            'rows': []}, stripped


def _page_tables(md: str) -> list[dict]:
    """在一页的 Markdown 里，把「表标签 + 题注 + 表体」配成组。

    版面顺序就是配对依据：标签在前、题注紧随、表体最后。中间隔了别的表体就说明
    这个标签的表没抽出来，不硬凑。
    """
    lines = md.splitlines()
    found, pending = [], None
    i = 0
    while i < len(lines):
        line = HEADING.sub('', lines[i].strip())
        if line.startswith('|') and i + 1 < len(lines) and SEP_ROW.match(lines[i + 1].strip()):
            rows = []
            while i < len(lines) and lines[i].strip().startswith('|'):
                rows.append(lines[i].strip())
                i += 1
            if pending is None:
                pending, rows = _caption_column(rows)
            if pending:
                pending['rows'] = rows
                found.append(pending)
                pending = None
            continue
        m = LABEL_BOLD.match(line) or LABEL_WHOLE.match(line) or LABEL_BARE.match(line)
        if m and not line.startswith('|'):
            if pending:
                found.append(pending)              # 上一个标签没配到表体，如实记空
            tail = m.group(2).strip() if m.re is not LABEL_BARE else ''
            pending = {'num': int(m.group(1)),
                       'caption': [tail] if tail else [], 'rows': []}
        elif pending and line and len(pending['caption']) < 4:
            pending['caption'].append(line)
        i += 1
    if pending:
        found.append(pending)
    return found


def extract(pdf: Path) -> tuple[list[dict], set, str]:
    try:
        import pymupdf4llm
    except ImportError:
        return [], set(), 'pymupdf4llm 未安装，无法抽表（pip install pymupdf4llm）'
    try:
        chunks = pymupdf4llm.to_markdown(str(pdf), page_chunks=True, write_images=False)
    except Exception as exc:                        # noqa: BLE001 - 抽表失败不该阻断入库
        return [], set(), f'pymupdf4llm 解析失败：{exc}'

    out: list[dict] = []
    mentioned: set = set()
    for pno, chunk in enumerate(chunks, 1):
        text = chunk.get('text', '')
        mentioned |= {int(n) for n in MENTION.findall(text) if 0 < int(n) < 30}
        for item in _page_tables(text):
            caption = re.sub(r'\s+', ' ', ' '.join(item['caption'])).strip()
            caption = re.sub(r'^\*+|\*+$', '', caption).strip()
            table, notes = normalize(item['rows']) if item['rows'] else ([], ['没抽到表体'])
            out.append({'num': item['num'], 'page': pno, 'caption': caption,
                        'table': table, 'notes': notes})
    return out, mentioned, ''


def dedupe(tables: list[dict]) -> list[dict]:
    """同一表号出现多次（跨页续表 / 版面重复解析）：留行数最多的那份，其余标为续表。"""
    best: dict[int, dict] = {}
    extra: list[dict] = []
    for t in tables:
        cur = best.get(t['num'])
        if cur is None or len(t['table']) > len(cur['table']):
            if cur is not None:
                extra.append(cur)
            best[t['num']] = t
        else:
            extra.append(t)
    for t in extra:
        t['notes'] = t['notes'] + ['同表号的另一份解析结果（可能是续表或重复识别）']
        t['duplicate'] = True
    return sorted(best.values(), key=lambda x: x['num']) + sorted(extra, key=lambda x: x['num'])


def build_md(pid: str, tables: list[dict], mentioned: set, err: str) -> tuple[str, dict]:
    mains = [t for t in tables if not t.get('duplicate')]
    clean = [t for t in mains if not t['notes'] and t['table']]
    dirty = [t for t in mains if t['notes'] or not t['table']]
    got = {t['num'] for t in mains}
    missing = sorted(n for n in mentioned if n not in got and n <= (max(got) if got else 0))
    lines = ['# 表格索引', '',
             '> 由 `extract_tables.py` 从 PDF 版面确定性解析，**英文原表**。'
             '英文正文可原样使用；中文正文只需译表头与行标签，表体数字照搬。', '',
             f'总计：{len(mains)} 张表格']
    if err:
        lines.append(f'- ⚠️ {err}')
    lines += [f'- 逐格可用：{len(clean)} 张' + (
                  '（' + '、'.join(f'表{t["num"]}' for t in clean) + '）' if clean else ''),
              f'- 需人工核对：{len(dirty)} 张' + (
                  '（' + '、'.join(f'表{t["num"]}' for t in dirty) + '）' if dirty else ''),
              '', '## 覆盖检查',
              '- 抽到表号：' + ('、'.join(f'表{t["num"]}(p{t["page"]})' for t in mains) or '无'),
              '- 正文提到却没抽到：' + ('、'.join(f'表{n}' for n in missing) if missing else '无'),
              '']
    for t in tables:
        title = f'## 表 {t["num"]}' + ('（重复解析）' if t.get('duplicate') else '')
        lines += [title, f'- 页码：{t["page"]}',
                  '- 状态：' + ('逐格可用' if not t['notes'] else '需人工核对（'
                                + '；'.join(t['notes']) + '）'),
                  f'- 题注：{t["caption"] or "（未解析到）"}', '']
        body = render(t['table'])
        lines += [body, ''] if body else ['<!-- 未解析到表体 -->', '']
    coverage = {'total': len(mains), 'clean': [t['num'] for t in clean],
                'needsReview': [t['num'] for t in dirty], 'missing': missing,
                'error': err or None}
    return '\n'.join(lines).rstrip() + '\n', coverage


# --------------------------------------------------------------------------
# 供 prep_article_en.py 复用：把索引读回内存
# --------------------------------------------------------------------------
def load_tables(path) -> dict:
    """读回 `<pid>.tables.md` → {表号: {'caption', 'markdown', 'cells', 'clean'}}。"""
    p = Path(path)
    if not p.is_file():
        return {}
    out: dict[int, dict] = {}
    num = None
    cur: dict = {}
    # 表体也是从 PDF 版面抽的，同样会带 Plane-1 丢位的数学字母（`휇` 其实是 `𝜇`）。
    # prep_article_en 只洗了 dump，注入的表格绕过那道清洗，乱码就跟着进了英文正文。
    raw, _n = restore_math_glyphs(p.read_text(encoding='utf-8', errors='replace'))
    for line in raw.splitlines():
        m = re.match(r'^##\s*表\s*(\d{1,2})\s*(（重复解析）)?\s*$', line)
        if m:
            num = None if m.group(2) else int(m.group(1))
            if num is not None:
                cur = out.setdefault(num, {'caption': '', 'rows': [], 'clean': False})
            continue
        if num is None:
            continue
        if line.startswith('- 题注：'):
            cur['caption'] = line.split('：', 1)[1].strip()
        elif line.startswith('- 状态：'):
            cur['clean'] = line.split('：', 1)[1].strip() == '逐格可用'
        elif line.startswith('|'):
            cur['rows'].append(line.rstrip())
    for cur in out.values():
        cur['markdown'] = '\n'.join(cur['rows'])
        cur['cells'] = {c.strip() for row in cur['rows'] for c in _cells(row)
                        if c.strip() and not set(c.strip()) <= {'-', ':'}}
    # 没抽到表体的表也留着：它的题注是英文草稿判定「这行到底是不是表题」的锚点，
    # 丢掉等于把那张表连同它的落点一起变成隐形的，谁也不知道要去补。
    return out


def main() -> None:
    if sys.platform == 'win32':
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
    ap = argparse.ArgumentParser(description='从 PDF 抽英文原表 → <pid>.tables.md')
    ap.add_argument('pdf', nargs='?')
    ap.add_argument('out', nargs='?', help='输出的 <pid>.tables.md 路径')
    ap.add_argument('--pid', default='')
    ap.add_argument('--scan', help='扫库补齐：递归找 content/<pid>.pdf，就地产 <pid>.tables.md')
    ap.add_argument('--force', action='store_true', help='--scan 时连已有的也重抽')
    ap.add_argument('--quiet', action='store_true')
    args = ap.parse_args()

    if args.scan:
        scan(Path(args.scan), args.force, args.quiet)
        return
    if not args.pdf or not args.out:
        ap.error('给 <pdf> <out>，或用 --scan <目录> 批量补齐')
    pdf = Path(args.pdf)
    if not pdf.is_file():
        raise SystemExit(f'PDF 不存在：{pdf}')
    coverage = run_one(pdf, Path(args.out), args.pid or pdf.stem, args.quiet)
    print('TABLE_COVERAGE ' + json.dumps(coverage, ensure_ascii=False))


def run_one(pdf: Path, out: Path, pid: str, quiet: bool) -> dict:
    tables, mentioned, err = extract(pdf)
    tables = dedupe(tables)
    md, coverage = build_md(pid, tables, mentioned, err)
    # 落盘前就把 Plane-1 丢位的数学字母还原掉，别让索引本身存着乱码
    md, _n = restore_math_glyphs(md)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md, encoding='utf-8')
    if not quiet:
        for t in tables:
            if t.get('duplicate'):
                continue
            state = '逐格可用' if not t['notes'] else '需核对：' + '；'.join(t['notes'])
            print(f'  表 {t["num"]:>2}  p{t["page"]:<3} {len(t["table"]):>2} 行  {state}')
        print(f'{coverage["total"]} 张表 -> {out}')
    return coverage


def scan(root: Path, force: bool, quiet: bool) -> None:
    """给已入库论文批量补 `content/<pid>.tables.md`（改进抽表规则后全库刷新也走这里）。"""
    tot = clean = review = missing = 0
    done = skipped = 0
    for pdf in sorted(root.rglob('content/*.pdf')):
        out = pdf.with_suffix('.tables.md')
        if out.is_file() and not force:
            skipped += 1
            continue
        cov = run_one(pdf, out, pdf.stem, quiet=True)
        done += 1
        tot += cov['total']
        clean += len(cov['clean'])
        review += len(cov['needsReview'])
        missing += len(cov['missing'])
        if not quiet:
            flag = ''
            if cov['needsReview']:
                flag += ' 待核' + '、'.join(f'表{n}' for n in cov['needsReview'])
            if cov['missing']:
                flag += ' 没抽到' + '、'.join(f'表{n}' for n in cov['missing'])
            print('%-46s %2d 张%s' % (pdf.stem[:46], cov['total'], flag))
    pct = 100 * clean / tot if tot else 0
    print('—— %d 篇新抽（跳过 %d 篇已有）：共 %d 张表，逐格可用 %d（%.0f%%），'
          '需人工核对 %d，正文提到没抽到 %d' % (done, skipped, tot, clean, pct, review, missing))


if __name__ == '__main__':
    main()
