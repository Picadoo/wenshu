#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""专题文档（Topics/）确定性质检——防 AI 偷懒的机器验收。

检查项（E=错误，退出码 1；W=警告）：
  通用（所有 noteType: topic）：
    E1  frontmatter 必填：noteType/docType/domain/translatedTitle/papers/updated
    E2  papers: 账本里每个 pid 必须真实存在于 vault/Papers/**/<pid>.md
    E3  H1 之后紧跟 blockquote —— 会被 Web 渲染成「说明」卡片并吞掉下文（历史 bug）
    E4  $$ 出现次数为奇数（公式未闭合）
    E8  嵌入图片 ![[...]] 在 vault/Papers/**/images/ 中找不到同名文件
        （专题可跨论文引图：Web 端按图名 <pid>_pageX_figY 前缀自动定位所属论文）
    W1  正文出现空话/口语黑名单（各研究有所不同/不再赘述/地盘/赛道/一坨/打架…）
    W2  正文 [[pid]] 指向已入库论文但 papers: 账本漏记（账本失真 → 前端"该主题论文"漏筛）
  方法专题（docType: 方法专题）追加：
    E5  必备章节缺失：方法定义/适用范围/计算流程总览/控制方程/数值实现要点/
        方法变体/配置对照/验证与标定/待补文献（按 H2 子串匹配，emoji 不影响）
    E6  「控制方程」节内无 $$ 块（不接受纯文字描述方程）
    E7  papers: 账本中的 pid 未出现在「配置对照」节（每篇论文必须有对照表行）
    E9  「数值实现要点」节内无 $$ 块——时间步/网格等约束必须判据公式先行
        （Rayleigh 时间步、CFL 条件等），只报库内数值不报判据视为偷懒

用法：
  python topic_lint.py --vault <VAULT>                 # 全量 Topics/**/*.md
  python topic_lint.py --vault <VAULT> --doc <path>    # 单文件
"""

import io
import re
import sys
import glob
import argparse
from pathlib import Path

LAZY_PHRASES = [
    '各研究有所不同', '视具体情况而定', '不再赘述', '此处从略', '详见原文',
    '限于篇幅', '不一而足', '等等等', '此处不展开',
    # 口语黑名单（学术文档禁用）
    '地盘', '赛道', '一坨', '三件套', '打架', '万事大吉', '挪来挪去',
    '跑不动', '算不起', '清一色', '打折版', '一句话定位',
]

METHOD_REQUIRED_SECTIONS = [
    '方法定义', '适用范围', '计算流程总览', '控制方程', '数值实现要点',
    '方法变体', '配置对照', '验证与标定', '待补文献',
]

FM_REQUIRED = ['noteType', 'docType', 'domain', 'translatedTitle', 'papers', 'updated']


def parse_frontmatter(text):
    """返回 (fields: dict[str,str], papers: list[str], body: str)。YAML-lite，够用即可。"""
    m = re.match(r'^---\n(.*?)\n---\n', text, re.S)
    if not m:
        return {}, [], text
    fm, body = m.group(1), text[m.end():]
    fields, papers = {}, []
    in_papers = False
    for line in fm.splitlines():
        item = re.match(r'^\s+-\s+["\']?(.+?)["\']?\s*$', line)
        if in_papers and item:
            papers.append(item.group(1))
            continue
        kv = re.match(r'^(\w+):\s*(.*)$', line)
        if kv:
            key, val = kv.group(1), kv.group(2).strip().strip('"\'')
            fields[key] = val
            in_papers = key == 'papers'
    return fields, papers, body


def split_sections(body):
    """按 H2 切分：返回 [(标题文本, 节内容)]，标题去掉 '## ' 前缀（含 emoji）。"""
    sections, cur_title, cur_lines = [], None, []
    for line in body.splitlines():
        if line.startswith('## '):
            if cur_title is not None:
                sections.append((cur_title, '\n'.join(cur_lines)))
            cur_title, cur_lines = line[3:].strip(), []
        elif cur_title is not None:
            cur_lines.append(line)
    if cur_title is not None:
        sections.append((cur_title, '\n'.join(cur_lines)))
    return sections


def collect_vault_pids(vault):
    """vault/Papers/**/<pid>.md 的 basename 集合（排除 content/ 内文件）。"""
    pids = set()
    for p in glob.glob(str(Path(vault) / 'Papers' / '**' / '*.md'), recursive=True):
        path = Path(p)
        if path.parent.name == 'content':
            continue
        pids.add(path.stem)
    return pids


def collect_vault_images(vault):
    """全库 Papers/**/images/ 下的图片文件名集合（专题跨论文引图靠文件名全局唯一）。"""
    names = set()
    for p in glob.glob(str(Path(vault) / 'Papers' / '**' / 'images' / '*.*'), recursive=True):
        if p.lower().endswith(('.png', '.jpg', '.jpeg', '.webp', '.gif')):
            names.add(Path(p).name)
    return names


def lint_doc(path, vault_pids, vault_images):
    errors, warns = [], []
    text = path.read_text(encoding='utf-8-sig').replace('\r\n', '\n')
    fields, papers, body = parse_frontmatter(text)

    if fields.get('noteType') != 'topic':
        return [], []  # 非专题文档不管

    # E1 必填字段
    for key in FM_REQUIRED:
        if key == 'papers':
            if not papers:
                errors.append('E1 frontmatter papers: 账本为空——专题必须挂至少一篇论文')
        elif not fields.get(key):
            errors.append(f'E1 frontmatter 缺 {key}')

    # E2 账本 pid 必须真实入库
    for pid in papers:
        if pid not in vault_pids:
            errors.append(f'E2 papers 账本里的「{pid}」在 vault/Papers 找不到索引')

    # E3 H1 后紧跟 blockquote
    lines = body.splitlines()
    for i, line in enumerate(lines):
        if line.startswith('# '):
            for nxt in lines[i + 1:]:
                if not nxt.strip():
                    continue
                if nxt.lstrip().startswith('>'):
                    errors.append('E3 H1 后紧跟 blockquote：Web 会渲染成「说明」卡片并把下文吞进去，改成普通段落')
                break
            break

    # E4 $$ 配对
    if body.count('$$') % 2 == 1:
        errors.append('E4 $$ 出现奇数次，公式未闭合')

    # E8 嵌入图片必须真实存在（专题引用库内论文的图，按文件名全局查找）
    for raw in re.findall(r'!\s*\[\[([^\]|#]+)(?:\|[^\]]*)?\]\]', body):
        img = raw.strip()
        if img not in vault_images:
            errors.append(f'E8 嵌入图片「{img}」在 vault/Papers/**/images/ 找不到')

    # W1 空话黑名单
    for phrase in LAZY_PHRASES:
        if phrase in body:
            warns.append(f'W1 出现空话「{phrase}」——请替换为具体内容或明确写"未提及"')

    # W2 正文互链但账本漏记
    body_links = set(re.findall(r'\[\[([^\]|#]+?)(?:\|[^\]]*)?\]\]', body))
    linked_papers = {t.strip() for t in body_links if t.strip() in vault_pids}
    for pid in sorted(linked_papers - set(papers)):
        warns.append(f'W2 正文引用了 [[{pid}]] 但 papers: 账本没记——前端"该主题论文"会漏筛')

    # 方法专题追加检查
    if fields.get('docType') == '方法专题':
        sections = split_sections(body)
        titles = [t for t, _ in sections]

        # E5 必备章节
        for req in METHOD_REQUIRED_SECTIONS:
            if not any(req in t for t in titles):
                errors.append(f'E5 缺必备章节「{req}」（H2）')

        # E6 控制方程节必须有 $$
        for title, content in sections:
            if '控制方程' in title and '$$' not in content:
                errors.append('E6 「控制方程」节没有 $$ 公式块——方程必须写成 LaTeX，不接受纯文字')

        # E9 数值实现要点节必须有判据公式（Rayleigh 时间步、CFL 等），不接受只报数值
        for title, content in sections:
            if '数值实现要点' in title and '$$' not in content:
                errors.append('E9 「数值实现要点」节没有 $$ 公式块——时间步/网格约束必须先给判据公式再报取值')

        # E7 每篇账本论文必须进配置对照表
        for title, content in sections:
            if '配置对照' in title:
                for pid in papers:
                    if pid not in content:
                        errors.append(f'E7 「{pid}」不在配置对照节——每篇覆盖论文必须有对照表行')
                break

    return errors, warns


def main():
    if sys.platform == 'win32':
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

    ap = argparse.ArgumentParser(description='专题文档质检（防偷懒机器验收）')
    ap.add_argument('--vault', required=True)
    ap.add_argument('--doc', help='只检查这一个文件；缺省扫全部 Topics/**/*.md')
    args = ap.parse_args()

    vault = Path(args.vault)
    docs = [Path(args.doc)] if args.doc else [
        Path(p) for p in glob.glob(str(vault / 'Topics' / '**' / '*.md'), recursive=True)
    ]
    if not docs:
        print('Topics/ 下没有专题文档')
        return

    vault_pids = collect_vault_pids(vault)
    vault_images = collect_vault_images(vault)
    total_e = total_w = 0
    for doc in docs:
        errors, warns = lint_doc(doc, vault_pids, vault_images)
        if errors or warns:
            print(f'📄 {doc.name}')
            for e in errors:
                print(f'  ❌ {e}')
            for w in warns:
                print(f'  ⚠️ {w}')
        total_e += len(errors)
        total_w += len(warns)

    print(f'—— topic_lint：{total_e} 错误 · {total_w} 警告（{len(docs)} 个文档）')
    sys.exit(1 if total_e else 0)


if __name__ == '__main__':
    main()
