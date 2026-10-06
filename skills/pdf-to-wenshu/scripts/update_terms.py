#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
全局术语库：跨论文查重 + 原子术语笔记 + 自动 MOC + 回填学习卡术语表。

设计：registry(_registry.json) 是唯一真相源，术语笔记由它幂等再生。
- 同一术语只建一次；后续论文引用时只追加"本文语境"到 usages，并补 papers 反链。
- 查重用归一化键(小写、去标点、保留中英文)，并比对 term/全称/中文名/别名。
- 分类用 frontmatter + 嵌套标签(领域×类型)，不靠文件夹。

输入 terms JSON（数组）：
  [{term, zhName, fullName, type, domain, definition, context}, ...]
  - term: 规范主名（优先缩写，否则英文规范名）
  - type: 方法/模型/指标/算法/物理量/概念/数据集 …
  - domain: 字符串或字符串数组
  - definition: 通用定义（只在首次建词时入库）
  - context: 本文中的用法（每篇各异）

输出：JSON 摘要到 stdout；并可 --learn-note 直接回填 <!--TERMS_START/END--> 之间的表格。
"""

import os
import re
import sys
import json
import argparse
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

TERMS_SUBDIR = "30_Terms"
NOTES_SUBDIR = "术语"          # 术语笔记 + registry 收进 30_Terms/术语/，顶层只留总览MOC
REGISTRY = "_registry.json"
MOC = "_术语库总览.md"


def norm(s):
    if not s:
        return ""
    s = str(s).lower()
    return re.sub(r'[^0-9a-z一-鿿]+', '', s)


def safe_name(term):
    n = re.sub(r'[ /\\:*?"<>|#\^\[\]]+', '_', str(term)).strip('_')
    return n or 'term'


def as_list(x):
    if not x:
        return []
    if isinstance(x, list):
        return [str(i) for i in x if i]
    return [str(x)]


def load_registry(path):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def entry_keys(entry):
    ks = {norm(entry.get('term')), norm(entry.get('zhName')), norm(entry.get('fullName'))}
    ks |= {norm(a) for a in entry.get('aliases', [])}
    return ks - {""}


def find_existing(registry, incoming):
    cands = {norm(incoming.get('term')), norm(incoming.get('fullName')),
             norm(incoming.get('zhName'))} - {""}
    if not cands:
        return None
    for ck, entry in registry.items():
        if cands & (entry_keys(entry) | {ck}):
            return ck
    return None


def render_term_note(entry):
    aliases = entry.get('aliases', [])
    domain = entry.get('domain', [])
    tags = ["术语"]
    if entry.get('type'):
        tags.append(f"术语/类型/{entry['type']}")
    for d in domain:
        tags.append(f"术语/领域/{d}")
    papers = ["[[%s]]" % u['paper'] for u in entry.get('usages', [])]

    def yq(s):
        s = str(s).replace('\\', '\\\\').replace('"', '\\"')
        return f'"{s}"'

    fm = ["---"]
    fm.append(f"term: {yq(entry.get('term'))}")
    fm.append(f"zhName: {yq(entry.get('zhName'))}")
    fm.append(f"fullName: {yq(entry.get('fullName'))}")
    fm.append("aliases: " + (json.dumps(aliases, ensure_ascii=False) if aliases else "[]"))
    fm.append(f"type: {yq(entry.get('type'))}")
    fm.append("domain: " + (json.dumps(domain, ensure_ascii=False) if domain else "[]"))
    fm.append("tags: " + json.dumps(tags, ensure_ascii=False))
    fm.append("papers: " + (json.dumps(papers, ensure_ascii=False) if papers else "[]"))
    fm.append("noteType: term")
    fm.append("---")

    title = entry.get('term')
    if entry.get('zhName'):
        title += f"（{entry['zhName']}）"
    body = [f"\n# {title}\n"]
    if entry.get('fullName'):
        body.append(f"**全称**：{entry['fullName']}\n")
    body.append(f"**通用定义**\n\n{entry.get('definition') or '（待补充）'}\n")
    body.append("## 各论文中的用法")
    for u in entry.get('usages', []):
        body.append(f"- [[{u['paper']}]]：{u.get('context', '')}")
    body.append("")
    return "\n".join(fm) + "\n".join(body)


def render_moc(registry):
    # 纯 Markdown 总览：按领域分组，人和 AI 都能直接读/grep。
    # 文枢术语库页读 registry JSON，本文件只是 vault 侧索引。
    n = len(registry)
    by_domain = {}
    for e in registry.values():
        for d in (e.get('domain') or ["（未分类）"]):
            by_domain.setdefault(d, []).append(e)
    lines = [
        '---', 'noteType: terms-moc', 'tags: ["术语库"]', '---', '',
        '# 📚 术语库总览', '',
        f"共 **{n}** 条术语，按领域分组（同一术语可能跨多个领域出现）。点术语名进词条。",
        '',
    ]
    for d in sorted(by_domain):
        entries = sorted(by_domain[d],
                         key=lambda e: (-len(e.get('papers') or []), e.get('term') or ''))
        lines.append(f"## {d}（{len(entries)}）")
        for e in entries:
            base = os.path.splitext(e.get('note') or '')[0]
            label = e.get('term') or base
            if e.get('zhName'):
                label += f" {e['zhName']}"
            suffix = f"（{e['type']}）" if e.get('type') else ''
            lines.append(f"- [[{base}|{label}]]{suffix}")
        lines.append('')
    return "\n".join(lines)


def find_index_path(papers_dir, paper_id):
    import glob
    hits = glob.glob(os.path.join(papers_dir, '**', f'{paper_id}.md'), recursive=True)
    return hits[0] if hits else None


_PDOM_CACHE = {}


def paper_folder_domain(papers_dir, paper_id):
    """读论文 index.md 的 frontmatter domain（= 它在 Papers/ 下的文件夹领域，可能是 大类/子类）。"""
    if paper_id in _PDOM_CACHE:
        return _PDOM_CACHE[paper_id]
    ip = find_index_path(papers_dir, paper_id)
    dom = None
    if ip:
        try:
            with open(ip, 'r', encoding='utf-8') as f:
                m = re.search(r'^domain:\s*"?(.+?)"?\s*$', f.read(), flags=re.MULTILINE)
            if m:
                dom = m.group(1).strip().strip('"')
        except IOError:
            pass
    _PDOM_CACHE[paper_id] = dom
    return dom


def normalize_domains(registry, papers_dir):
    """术语领域 = 用它的论文的文件夹领域（确定性、与 Papers/ 目录一致），覆盖子代理自填的 domain，避免碎片化。"""
    _PDOM_CACHE.clear()
    for e in registry.values():
        out = set()
        for u in e.get('usages', []):
            d = paper_folder_domain(papers_dir, u['paper'])
            if d:
                out.add(d)
        if out:
            e['domain'] = sorted(out)


def paper_terms_map(registry):
    """paper_id -> set(canonical_key)：每篇论文用到的术语集合。"""
    m = {}
    for ck, e in registry.items():
        for u in e.get('usages', []):
            m.setdefault(u['paper'], set()).add(ck)
    return m


def related_for(pmap, paper, min_shared=2):
    """与 paper 共享 >=min_shared 个术语的其他论文，按共享数降序。"""
    mine = pmap.get(paper, set())
    out = []
    for other, theirs in pmap.items():
        if other == paper:
            continue
        n = len(mine & theirs)
        if n >= min_shared:
            out.append((other, n))
    out.sort(key=lambda x: -x[1])
    return out


def patch_related(index_path, related):
    """[已停用] 论文↔论文「共享术语」双链已移除（Obsidian 关系图时代的产物）。
    按术语查相关论文用 30_Terms 的 papers: 倒排。保留签名兼容调用，直接返回、不再写双链。"""
    return False
    try:
        with open(index_path, 'r', encoding='utf-8') as f:
            txt = f.read()
    except IOError:
        return False
    if related:
        body = "；".join(f"[[{rid}|{rid}]]（共享 {n} 术语）" for rid, n in related)
    else:
        body = "（暂无 —— 由术语库共现自动填充）"
    m = re.search(r'^##[^\n]*相关论文[^\n]*\n', txt, flags=re.MULTILINE)
    if not m:
        return False
    start = m.end()
    nxt = txt.find('\n## ', start)
    end = nxt if nxt != -1 else len(txt)
    new = txt[:start] + body + '\n' + txt[end:]
    if new == txt:
        return False
    with open(index_path, 'w', encoding='utf-8') as f:
        f.write(new)
    return True


def build_table(rows):
    # 表格内不用 [[a\|b]] 别名(部分 Obsidian 把 \| 当成链接的一部分导致断链)；
    # 改为 [[base]] + 中文名 纯文本，链接稳。
    out = ["| 术语 | 术语库 | 本文语境 |", "| -- | -- | -- |"]
    for r in rows:
        zh = (' ' + r['zh']) if r.get('zh') else ''
        out.append(f"| {r['term']} | [[{r['base']}]]{zh} | {r['context']} |")
    return "\n".join(out)


def patch_learn(learn_path, table_md):
    try:
        with open(learn_path, 'r', encoding='utf-8') as f:
            txt = f.read()
    except IOError as e:
        logger.warning("读取学习卡失败: %s", e)
        return False
    repl = '<!--TERMS_START-->\n' + table_md + '\n<!--TERMS_END-->'
    # 用函数式替换：避免 table_md 里的反斜杠(数学符号/LaTeX)被当成 re 替换转义符
    new = re.sub(r'<!--TERMS_START-->.*?<!--TERMS_END-->',
                 lambda _m: repl, txt, flags=re.DOTALL)
    if new == txt:
        logger.warning("学习卡未找到 TERMS 标记，未回填")
        return False
    with open(learn_path, 'w', encoding='utf-8') as f:
        f.write(new)
    logger.info("已回填术语表 -> %s", os.path.basename(learn_path))
    return True


def main():
    if sys.platform == 'win32':
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s [%(levelname)s] %(message)s',
                        datefmt='%H:%M:%S', stream=sys.stderr)

    ap = argparse.ArgumentParser(description='术语库查重 + 入库 + 回填学习卡')
    ap.add_argument('--terms', default=None, help='术语 JSON 路径')
    ap.add_argument('--paper-id', default=None, help='论文ID')
    ap.add_argument('--vault', required=True, help='vault 根路径')
    ap.add_argument('--notes-note', '--learn-note', dest='notes_note', default=None,
                    help='合并笔记(notes)路径，用于回填术语表 <!--TERMS_START/END-->')
    ap.add_argument('--rebuild', action='store_true',
                    help='只从 registry 重建所有术语笔记 + 总览MOC（不导入新论文，可随时刷新）')
    args = ap.parse_args()

    terms_dir = os.path.join(args.vault, TERMS_SUBDIR)       # 顶层：只放总览 MOC
    notes_dir = os.path.join(terms_dir, NOTES_SUBDIR)        # 子文件夹：术语笔记 + registry
    os.makedirs(notes_dir, exist_ok=True)
    reg_path = os.path.join(notes_dir, REGISTRY)
    registry = load_registry(reg_path)

    # 按需重建：从 registry 全量再生所有术语笔记 + 总览MOC（手动改过库/换过模板后用）
    if args.rebuild:
        normalize_domains(registry, os.path.join(args.vault, 'Papers'))
        for ck, e in registry.items():
            with open(os.path.join(notes_dir, e['note']), 'w', encoding='utf-8') as f:
                f.write(render_term_note(e))
        with open(reg_path, 'w', encoding='utf-8') as f:
            json.dump(registry, f, ensure_ascii=False, indent=2)
        with open(os.path.join(terms_dir, MOC), 'w', encoding='utf-8') as f:
            f.write(render_moc(registry))
        logger.info("已从 registry 重建 %d 条术语笔记 + 总览MOC（领域按论文文件夹规整）", len(registry))
        print(json.dumps({"rebuilt": len(registry),
                          "moc": os.path.join(terms_dir, MOC)}, ensure_ascii=False, indent=2))
        return

    if not args.terms or not args.paper_id:
        ap.error("非 --rebuild 模式必须提供 --terms 和 --paper-id")

    with open(args.terms, 'r', encoding='utf-8') as f:
        incoming = json.load(f)

    rows, n_new, n_exist = [], 0, 0
    for t in incoming:
        term = (t.get('term') or '').strip()
        if not term:
            continue
        zh = (t.get('zhName') or '').strip()
        full = (t.get('fullName') or '').strip()
        domain = as_list(t.get('domain'))
        context = (t.get('context') or '').strip()
        ck = find_existing(registry, t)

        if ck:  # 已有：只追加本文语境
            e = registry[ck]
            if not any(u['paper'] == args.paper_id for u in e.setdefault('usages', [])):
                e['usages'].append({'paper': args.paper_id, 'context': context})
            # term 也要收进别名：本篇用的写法（如 restitution coefficient）常与库内
            # 主名（coefficient of restitution）不同，丢掉它笔记里的 [[别写法]] 就会悬空。
            for a in (term, full, zh):
                if a and a not in e.setdefault('aliases', []) and norm(a) != norm(e.get('term')):
                    e['aliases'].append(a)
            for d in domain:
                if d not in e.setdefault('domain', []):
                    e['domain'].append(d)
            if not e.get('definition') and t.get('definition'):
                e['definition'] = t['definition'].strip()
            n_exist += 1
        else:   # 新词：建档
            key = norm(term) or norm(full) or norm(zh)
            if not key or key in registry:
                key = f"{norm(term)}_{len(registry)}"
            fname = safe_name(term)
            note = fname + ".md"
            # 文件名去重
            existing_names = {v['note'] for v in registry.values()}
            i = 1
            while note in existing_names:
                note = f"{fname}_{i}.md"
                i += 1
            aliases = [a for a in (full, zh) if a and norm(a) != norm(term)]
            registry[key] = {
                'note': note, 'term': term, 'zhName': zh, 'fullName': full,
                'aliases': aliases, 'type': (t.get('type') or '').strip(),
                'domain': domain, 'definition': (t.get('definition') or '').strip(),
                'usages': [{'paper': args.paper_id, 'context': context}],
            }
            ck = key
            n_new += 1

        e = registry[ck]
        base = os.path.splitext(e['note'])[0]
        rows.append({'term': term, 'base': base,
                     'zh': zh or e.get('zhName') or term, 'context': context})

    # 术语领域 = 用它的论文的文件夹领域（确定性，覆盖子代理自填的 domain，避免碎片化）
    normalize_domains(registry, os.path.join(args.vault, 'Papers'))

    # 再生所有受影响术语笔记（幂等：直接全量再生本批涉及的）
    touched = set()
    for t in incoming:
        ck = find_existing(registry, t)
        if ck and ck not in touched:
            touched.add(ck)
            note_path = os.path.join(notes_dir, registry[ck]['note'])
            with open(note_path, 'w', encoding='utf-8') as f:
                f.write(render_term_note(registry[ck]))

    # 保存 registry + 再生 MOC
    with open(reg_path, 'w', encoding='utf-8') as f:
        json.dump(registry, f, ensure_ascii=False, indent=2)
    with open(os.path.join(terms_dir, MOC), 'w', encoding='utf-8') as f:
        f.write(render_moc(registry))

    table_md = build_table(rows)
    patched = False
    if args.notes_note:
        patched = patch_learn(args.notes_note, table_md)

    # 论文↔论文：共享 >=2 术语的论文自动互链（写进各自 index 的 <!--RELATED-->）
    papers_dir = os.path.join(args.vault, 'Papers')
    pmap = paper_terms_map(registry)
    touched = {args.paper_id} | {p for p, _ in related_for(pmap, args.paper_id)}
    related_patched = 0
    for p in touched:
        ip = find_index_path(papers_dir, p)
        if ip and patch_related(ip, related_for(pmap, p)):
            related_patched += 1

    logger.info("术语：新增 %d，复用 %d，库存共 %d；相关论文回填 %d 篇",
                n_new, n_exist, len(registry), related_patched)
    print(json.dumps({
        "new": n_new, "existing": n_exist, "totalInBank": len(registry),
        "tableRows": len(rows), "notesPatched": patched, "relatedPatched": related_patched,
        "registry": reg_path, "moc": os.path.join(terms_dir, MOC),
        "table": table_md,
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
