#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成文枢"笔记集群" + 归档 PDF。结构：外面只露 index，其余收进子文件夹。

    <vault>/Papers/<domain>/<作者年份 全标题>/        ← 文件夹用全名(严谨)
    ├── <pid>.index.md        🧭 只露这个(入口/论文节点)；<pid>=作者年份+洁净关键词
    ├── content/
    │   ├── <pid>.md          📄 中文全文翻译
    │   ├── <pid>.notes.md    🎓 学习卡 + 🔬 深度分析 + ✍️ 写作逻辑
    │   └── <pid>.pdf         原始 PDF(原文看它)
    └── images/

要点：链接全用 basename(与路径无关)，收进子文件夹不断链。构造标记最后由 strip_markers.py 去掉。
"""

import os
import re
import sys
import json
import shutil
import hashlib
import argparse
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

ZH_DOMAIN_TAGS = {
    "CFD-DEM耦合模拟": ["CFD-DEM", "流固耦合"],
    "局部冲刷": ["局部冲刷", "scour"],
    "滑坡识别与监测": ["滑坡", "landslide"],
    "计算流体力学": ["CFD", "计算流体力学"],
    "颗粒流与离散元": ["DEM", "颗粒流"],
}


def sha256_of(path, chunk=1 << 20):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return "sha256:" + h.hexdigest()


def dump_pdf_text(pdf_path, max_chars=400000):
    """抽取 PDF 全文文本（机器可读缓存，0 token；供日后/别的 AI 低成本复用）。
    超长时保头+尾（参考文献在尾部，build_refs.py 依赖它，不能一刀切砍尾）。"""
    try:
        import fitz
    except ImportError:
        return ""
    try:
        doc = fitz.open(pdf_path)
    except Exception:
        return ""
    parts = []
    try:
        for i in range(len(doc)):
            parts.append(f"\n\n----- Page {i + 1} -----\n\n{doc[i].get_text()}")
    finally:
        doc.close()
    txt = "".join(parts).strip()
    if len(txt) > max_chars:
        tail = 120000
        txt = (txt[:max_chars - tail]
               + "\n\n----- （全文过长，中段截断；以下为文末部分，含参考文献） -----\n\n"
               + txt[-tail:])
    return txt


def yq(s):
    if s is None:
        return '""'
    s = str(s).replace('\\', '\\\\').replace('"', '\\"')
    return f'"{s}"'


def ylist(items, indent="  "):
    items = [i for i in (items or []) if i not in (None, "")]
    if not items:
        return " []"
    return "\n" + "\n".join(f"{indent}- {yq(i)}" for i in items)


def render(template, mapping):
    out = template
    for k, v in mapping.items():
        out = out.replace(f"@@{k}@@", v if v is not None else "")
    return out


def safe_folder(name, limit=120):
    name = re.sub(r'[\\/:*?"<>|]+', ' ', str(name))
    name = re.sub(r'\s+', ' ', name).strip(' .')
    if len(name) > limit:
        cut = name[:limit].rsplit(' ', 1)[0]
        name = (cut or name[:limit]).strip()
    return name or 'paper'


def build_index_frontmatter(meta, pid, domain, translated_title, mode, src_hash, date):
    tags = ["论文笔记"] + ZH_DOMAIN_TAGS.get(domain, [domain])
    # 精简属性：只留文枢必填(translatedTitle/authors/year/domain/tags/status/reading)
    # + 脚本要用的(sourceHash/noteType)；完整书目信息仍在正文「文献卡」里。
    lines = ["---"]
    lines.append(f"translatedTitle: {yq(translated_title or meta.get('title'))}")
    lines.append("authors:" + ylist(meta.get('authors')))
    lines.append(f"year: {yq(meta.get('year'))}")
    lines.append(f"journal: {yq(meta.get('journal'))}")
    lines.append(f"doi: {yq(meta.get('doi'))}")
    lines.append(f"sourceHash: {yq(src_hash)}")
    lines.append(f"domain: {yq(domain)}")
    lines.append("tags:" + ylist(tags))
    lines.append('quality_score: "[SCORE]/10"')
    lines.append("noteType: index")
    lines.append("status: skeleton")
    lines.append("reading: 待读")  # 阅读进度：待读/在读/已读/重读 —— 文枢列表/概览据此统计
    lines.append("---")
    return "\n".join(lines)


INDEX_BODY = '''

# @@DISPLAY@@

## 📇 文献卡
- **原题**：@@TITLE@@
- **译名**：@@TTITLE@@
- **作者**：@@AUTHORS@@
- **期刊**：@@JLINE@@
- **DOI**：@@DOILINK@@
- **开放获取**：@@OA@@
- **被引**：@@CC@@
- **领域**：@@DOMAIN@@
- **关键概念**：@@CONCEPTS@@
- **元数据来源**：@@SOURCES@@
- **📎 原始 PDF**：[[@@PID@@.pdf]]

## ❓ 科学问题
<!--SCI_Q-->（本文要回答的核心科学问题 —— 待分析子代理填充）<!--/SCI_Q-->

## 📝 一句话总结
<!--TLDR-->（一句话说清这篇论文做了什么 —— 待填充）<!--/TLDR-->

## ⭐ 评分
<!--SCORE-->（X.X/10 —— 待填充）<!--/SCORE-->
'''

ARTICLE_BODY = '''---
noteType: article
paper: "[[@@PID@@]]"
---

# @@DISPLAY@@

<!--ARTICLE-->
> 待**翻译子代理**填充：逐节全文中译；图片原位内嵌 `![[@@PID@@_pageX_figY.png|700]]`；
> 关键公式转写为 LaTeX（`$...$` / `$$...$$`）；表格转写为 Markdown 表格。
<!--/ARTICLE-->
'''

# 英文原文重排版：不翻译，只把 PDF 文本 dump 恢复成结构化 Markdown（供英文精读/生词标注）
ARTICLE_EN_BODY = '''---
noteType: article_en
paper: "[[@@PID@@]]"
---

# @@TITLE@@

<!--ARTICLE_EN-->
> 待**英文重排子代理**填充：不翻译、忠于原文措辞；按论文真实章节恢复标题层级；
> 断行/断词接回成完整段落；图片原位内嵌 `![[@@PID@@_pageX_figY.png|700]]` + 原文英文图注；
> 公式转 LaTeX、表格转 Markdown 表格；页眉页脚/页码/期刊水印删除；引用记号 [N] 原样保留；
> References 一节不收录（看中文正文末尾的自动参考文献或原 PDF）。
<!--/ARTICLE_EN-->
'''

# 学习卡在上、深度分析居中、写作逻辑在下
NOTES_BODY = '''---
noteType: notes
paper: "[[@@PID@@]]"
---

# 🎓 学习卡：@@DISPLAY@@

## 📌 摘要要点
<!--HINT: 写成"他们做了什么/发现了什么"的可秒扫清单，不是抄原文摘要-->

<!--KEYPOINTS-->
1. （要点1 —— 待笔记子代理填充）
2. （要点2）
3. （要点3）
<!--/KEYPOINTS-->

## 📖 术语表
<!--HINT: 术语链接到全局术语库，定义只存一份，本表只填"本文语境"列-->

<!--TERMS_START-->
| 术语 | 术语库 | 本文语境 |
| -- | -- | -- |
| （待 update_terms.py 填充） |  |  |
<!--TERMS_END-->

## ❓ 问答
<!--QA-->
### Q1：本文要回答的科学问题是什么？
A1：（待填充）

### Q2：（提出的方法/框架是什么？）
A2：

### Q3：（关键结果与量化指标？）
A3：

### Q4：（主要局限是什么？）
A4：
<!--/QA-->

---

# 🔬 深度分析
<!--HINT: 必填；读 PDF 全文后填写；图只挑与论点相关的关键图-->

## 研究问题
（本文要解决的核心科学问题 + 现有方法的不足）

## 方法概述
### 核心方法
1. [方法步骤 / 关键设计 / 创新点]

### 关键公式（LaTeX）
- 行内 `$...$`，块级 `$$...$$` 单独成行；符号语义与原文一致。

### 方法架构
[架构描述 + 关键图 `![[@@PID@@_pageX_figY.png|700]]`]

### 关键创新
1. [创新1 — 为什么重要]

## 实验结果
### 数据集与设置
- 数据集 / 基线 / 评估指标 / 硬件超参

### 主要结果（表格）
[把论文关键结果表转写成 Markdown 表格，别只截图]

## 深度分析
### 研究价值
- 理论贡献 / 实际应用 / 领域影响

### 优势
- [优势]

### 局限性
- [局限]

### 适用场景
- [场景]

## 与相关论文对比
### [[相关论文]] - [关系]
- 差异 / 改进 / 性能对比

## 技术路线定位
本文属于 [技术路线]，主要关注 [子方向]。

## 未来工作建议
1. [作者建议 / 基于分析的延伸]

## 我的综合评价
- **总体评分**：[X.X/10]
- **分项**：创新性 [X/10]｜技术质量 [X/10]｜实验充分性 [X/10]｜写作质量 [X/10]｜实用性 [X/10]
- **突出亮点**：[...]
- **可借鉴点**：[...]
- **批判性思考**：[...]
@@WRITING_LOGIC@@'''

WRITING_LOGIC_BLOCK = '''
---

# ✍️ 写作逻辑（学写论文用）

> 这篇论文是怎么"写"出来的——论证结构与行文手法，供你模仿。

## 论证骨架
（问题背景 → 研究缺口 → 本文主张/贡献 → 各部分如何环环支撑这个主张）

## 谋篇布局
（每个章节承担什么任务、章节之间怎么过渡衔接）

## 值得模仿的写法
（开头怎么抓住读者、贡献怎么定位拔高、图表怎么配合论证、局限怎么写得体面）
'''

# 用户自己的笔记（AI 重跑不覆盖）——独立文件，链在索引「笔记集群」
MYNOTE_BODY = '''---
noteType: mynote
paper: "[[@@PID@@]]"
tags: ["我的笔记"]
---
> 这是**你自己**的地盘 —— AI 重跑论文不会动这里。

# ✍️ 我的笔记 · @@DISPLAY@@

## 💡 为什么读它 / 一句话


## 🎯 关键收获（对我课题）
-

## 🧰 可借鉴·要复现（方法 / 公式 / 数据 / 代码）
-

## ❓ 存疑 / 要追的
-

## 🔗 与我研究的联系


## ✅ 待办
- [ ]
'''


def write_note(path, content, force):
    if os.path.exists(path) and not force:
        logger.info("跳过已存在: %s", os.path.basename(path))
        return False
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content)
    logger.info("写入: %s", os.path.basename(path))
    return True


def main():
    if sys.platform == 'win32':
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

    logging.basicConfig(level=logging.INFO,
                        format='%(asctime)s [%(levelname)s] %(message)s',
                        datefmt='%H:%M:%S', stream=sys.stderr)

    ap = argparse.ArgumentParser(description='生成论文笔记集群(外露index + content子文件夹) + 归档 PDF')
    ap.add_argument('--paper-id', required=True, help='洁净短ID(作者年份+完整关键词)，用作文件名/链接')
    ap.add_argument('--folder-name', default=None, help='论文文件夹名(建议作者年份+全标题)；缺省用 pid')
    ap.add_argument('--domain', required=True)
    ap.add_argument('--pdf', required=True)
    ap.add_argument('--meta', required=True, help='doi_enrich.py 的元数据 JSON')
    ap.add_argument('--vault', required=True)
    ap.add_argument('--translated-title', default=None)
    ap.add_argument('--mode', default='beginner', choices=['beginner', 'standard'])
    ap.add_argument('--archive', default='move', choices=['move', 'copy'])
    ap.add_argument('--no-writing-logic', action='store_true', help='不生成 ✍️ 写作逻辑 一节')
    ap.add_argument('--no-fulltext', action='store_true', help='不保存全文文本缓存 content/<pid>.txt')
    ap.add_argument('--force', action='store_true')
    args = ap.parse_args()

    with open(args.meta, 'r', encoding='utf-8') as f:
        meta = json.load(f)

    # 保留内部空格(Windows 下安全，与库内既有「作者年份 中文短题」可读命名一致)；
    # 仅替换真正非法的文件名字符，避免新论文产出下划线、与老库不一致。
    pid = re.sub(r'[/\\:*?"<>|]+', '_', args.paper_id).strip().strip('_')
    pid = re.sub(r'\s+', ' ', pid)
    domain = args.domain.strip('/\\').replace('..', '') or '其他'
    folder = safe_folder(args.folder_name or pid)
    date = datetime.now().strftime("%Y-%m-%d")

    papers_dir = os.path.join(args.vault, "Papers")
    domain_dir = os.path.join(papers_dir, domain)
    cluster_dir = os.path.join(domain_dir, folder)
    index_path = os.path.join(domain_dir, f"{pid}.md")  # index 放子类层、不带 .index 后缀(图谱节点干净)
    content_dir = os.path.join(cluster_dir, "content")
    images_dir = os.path.join(cluster_dir, "images")
    os.makedirs(content_dir, exist_ok=True)
    os.makedirs(images_dir, exist_ok=True)

    if not os.path.isfile(args.pdf):
        logger.error("源 PDF 不存在: %s", args.pdf)
        sys.exit(1)
    src_hash = sha256_of(args.pdf)

    pdf_dest = os.path.join(content_dir, f"{pid}.pdf")
    if os.path.abspath(args.pdf) == os.path.abspath(pdf_dest):
        logger.info("PDF 已在目标位置")
    elif os.path.exists(pdf_dest) and not args.force:
        logger.info("PDF 目标已存在，跳过归档")
    else:
        if args.archive == 'move':
            shutil.move(args.pdf, pdf_dest)
        else:
            shutil.copy2(args.pdf, pdf_dest)
        logger.info("PDF 已%s到: %s", "移动" if args.archive == 'move' else "复制", pdf_dest)

    # 全文文本缓存（机器可读，0 token）：供日后/别的 AI 复用，省去重抽 PDF 或读 PDF 图
    fulltext_path = None
    if not args.no_fulltext:
        src_pdf = pdf_dest if os.path.exists(pdf_dest) else args.pdf
        txt = dump_pdf_text(src_pdf)
        if txt:
            fulltext_path = os.path.join(content_dir, f"{pid}.txt")
            with open(fulltext_path, 'w', encoding='utf-8') as f:
                f.write(txt)
            logger.info("全文缓存: %s (%d 字符)", os.path.basename(fulltext_path), len(txt))
        # 另存一份带上下标的 dump：纯文本模式会把 C_D 压成 CD、a_{p1} 压成 ap1，
        # 英文正文的行内公式因此全库为零。`.txt` 有四个消费者不便改格式，故并存。
        try:
            from extract_rich_text import build_rich_text, count_scripts
        except ImportError:
            sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
            from extract_rich_text import build_rich_text, count_scripts
        rich = build_rich_text(src_pdf)
        if rich:
            rich_path = os.path.join(content_dir, f"{pid}.rich.txt")
            with open(rich_path, 'w', encoding='utf-8') as f:
                f.write(rich)
            logger.info("带上下标的 dump: %s (%d 字符 / 上下标 %d 处)",
                        os.path.basename(rich_path), len(rich), count_scripts(rich))

    title = meta.get('title') or '(标题待补)'
    ttitle = args.translated_title or title
    lang = meta.get('detectedSourceLanguage') or 'en'
    authors = "、".join(meta.get('authors') or []) or "（待补）"
    vip = ""
    if meta.get('volume'):
        vip = f"，{meta['volume']}"
        if meta.get('issue'):
            vip += f"({meta['issue']})"
        if meta.get('pages'):
            vip += f"：{meta['pages']}"
    jline = (meta.get('journal') or '--')
    if meta.get('year'):
        jline += f" {meta['year']}"
    jline += vip
    doi = meta.get('doi') or ''
    doilink = f"[{doi}]({meta.get('url')})" if doi else "（无 DOI）"
    oa = f"[PDF]({meta['openAccessUrl']})" if meta.get('openAccessUrl') else "--"
    cc = meta.get('citationCount')
    cc = str(cc) if isinstance(cc, int) else "--"
    concepts = "；".join(meta.get('concepts') or []) or "--"
    sources = "、".join(meta.get('metadataSources') or [])

    common = {
        "PID": pid, "TITLE": title, "TTITLE": ttitle, "DISPLAY": ttitle, "LANG": lang,
        "AUTHORS": authors, "JLINE": jline, "DOILINK": doilink, "OA": oa, "CC": cc,
        "CONCEPTS": concepts, "DOMAIN": domain, "BIGDOMAIN": domain.split("/")[0], "SOURCES": sources,
        "WRITING_LOGIC": "" if args.no_writing_logic else WRITING_LOGIC_BLOCK,
    }

    fm = build_index_frontmatter(meta, pid, domain, ttitle, args.mode, src_hash, date)

    created = []
    if write_note(index_path,
                  fm + render(INDEX_BODY, common), args.force):
        created.append("index")
    if write_note(os.path.join(content_dir, f"{pid}.正文.md"),
                  render(ARTICLE_BODY, common), args.force):
        created.append("article")
    # 英文原文重排版：仅英文源论文需要（中文母语论文没有"英文原文"）
    if lang != 'zh' and write_note(os.path.join(content_dir, f"{pid}.正文.en.md"),
                                   render(ARTICLE_EN_BODY, common), args.force):
        created.append("articleEn")
    if write_note(os.path.join(content_dir, f"{pid}.notes.md"),
                  render(NOTES_BODY, common), args.force):
        created.append("notes")
    if write_note(os.path.join(content_dir, f"{pid}.我的笔记.md"),
                  render(MYNOTE_BODY, common), args.force):
        created.append("mynote")

    result = {
        "paperId": pid, "folder": folder, "clusterDir": cluster_dir,
        "contentDir": content_dir, "imagesDir": images_dir, "pdfPath": pdf_dest,
        "imageIndexPath": os.path.join(images_dir, f"{pid}.images.md"),
        "fulltextPath": fulltext_path,
        "sourceHash": src_hash,
        "notes": {
            "index": index_path,
            "article": os.path.join(content_dir, f"{pid}.正文.md"),
            "articleEn": os.path.join(content_dir, f"{pid}.正文.en.md") if lang != 'zh' else None,
            "notes": os.path.join(content_dir, f"{pid}.notes.md"),
            "mynote": os.path.join(content_dir, f"{pid}.我的笔记.md"),
        },
        "created": created,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
