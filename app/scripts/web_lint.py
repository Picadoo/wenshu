#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
web_lint.py —— 文枢 Web 发布质检：入库文稿是否符合前端渲染契约（docs/content-contract.md）。

与 paper-ingest 的 verify.py 配合：前者检查入库内容，这里检查阅读端格式。
sync-vault.py 收尾自动调用；也可单独跑：

    python scripts/web_lint.py --vault "D:/.../vault"
    python scripts/web_lint.py --vault "D:/.../vault" --paper "Example2024"   # 只查这一篇

`--paper` 供多子代理并行时各自自验：只报被点名那些集群的问题，秒级返回，
但悬空链接仍按**全库** pid 表判定，不会因为缩小范围而误报。

检查项（E=错误必修，W=警告酌情）：
- index：frontmatter 必填字段缺失(E)、构造标记/占位符残留(E)
- 正文/notes：$$ 未闭合(E)、REFS_AUTO 标记破损(E)、图片嵌入指向不存在文件(E)、
  表格裸 <>(W)、三层括号链接(W)、占位符残留(E)
- 链接：悬空 [[链接]]（既不是已入库论文、也不在术语库、也不是 MOC/集群内部链接）(W+清单)
- 术语库：registry JSON 可解析(E)

退出码：有 E 则 1，否则 0；`--fail-on-warnings` 用于新论文严格验收，出现 W 也返回 1。
"""
from __future__ import annotations

import io
import re
import sys
import json
import argparse
from pathlib import Path

MARKER = re.compile(
    r"<!--(?:/?(?:SCI_Q|TLDR|SCORE|RELATED|KEYPOINTS|QA|ARTICLE_EN|ARTICLE|ORIGINAL)|TERMS_(?:START|END))-->"
)
EMBED = re.compile(r"!\[\[([^\]|#]+?)(?:\|[^\]]*)?\]\]")
WIKI = re.compile(r"(?<!\!)\[\[(?!#)([^\]|]+?)(?:\|[^\]]*)?\]\]")
IMAGE_EXTS = re.compile(r"\.(png|jpe?g|gif|webp|svg)$", re.I)

PLACEHOLDERS = [
    "（本文要回答的核心科学问题",
    "（一句话说清",
    "待填充",
    "[SCORE]",
    "待**翻译子代理**填充",
    "待翻译子代理填充",
    "待**英文重排子代理**填充",
    "待英文重排子代理填充",
    "待笔记子代理填充",
    "待 update_terms.py 填充",
    "（待填充）",
]

REQUIRED_FM = ["translatedTitle", "authors", "year", "domain", "tags", "status", "reading"]
RECOMMENDED_FM = ["journal", "doi", "quality_score", "citekey"]

CLUSTER_SUFFIXES = (".正文", ".notes", ".images", ".我的笔记", ".pdf", ".txt")


def normalize_key(name: str) -> str:
    """链接名归一，与 sync-vault.py / src/data/terms.ts 保持一致。"""
    return "".join(ch for ch in name.lower() if ch.isalnum() or "\u4e00" <= ch <= "\u9fff")


def rd(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        return ""


def fm_body(text: str) -> tuple[str, str]:
    if text.startswith("---"):
        parts = text.split("---", 2)
        if len(parts) >= 3:
            return parts[1], parts[2]
    return "", text


class Lint:
    def __init__(self) -> None:
        self.errors: list[tuple[str, str]] = []
        self.warns: list[tuple[str, str]] = []

    def e(self, pid: str, msg: str) -> None:
        self.errors.append((pid, msg))

    def w(self, pid: str, msg: str) -> None:
        self.warns.append((pid, msg))


def collect_clusters(vault: Path) -> list[tuple[str, Path, Path | None, Path | None]]:
    """index(noteType: index) → (pid, index路径, content目录, images目录)。"""
    out = []
    papers_dir = vault / "Papers"
    if not papers_dir.is_dir():
        return out
    for path in papers_dir.rglob("*.md"):
        if path.name.startswith("_"):
            continue
        if "content" in path.parts or "images" in path.parts:
            continue
        head = rd(path)[:2400]
        if "noteType: index" not in head and "p2o/paper" not in head:
            continue
        pid = path.stem
        cdir = idir = None
        base = path.parent
        for sub in base.iterdir():
            if not sub.is_dir():
                continue
            cand = sub / "content"
            if cand.is_dir() and (cand / f"{pid}.正文.md").exists():
                cdir = cand
                idir = sub / "images"
                break
        out.append((pid, path, cdir, idir))
    return out


def load_term_aliases(vault: Path, lint: Lint) -> set[str]:
    registry_path = vault / "30_Terms" / "术语" / "_registry.json"
    aliases: set[str] = set()
    if not registry_path.exists():
        return aliases
    try:
        registry = json.loads(registry_path.read_text(encoding="utf-8"))
    except Exception as exc:
        lint.e("术语库", f"registry JSON 解析失败：{exc}")
        return aliases
    for key, entry in registry.items():
        names = [
            key,
            entry.get("term") or "",
            entry.get("zhName") or "",
            entry.get("fullName") or "",
            (entry.get("note") or "").removesuffix(".md"),
            *(entry.get("aliases") or []),
        ]
        for name in names:
            normalized = normalize_key(str(name))
            if normalized:
                aliases.add(normalized)
    return aliases


def check_links(lint: Lint, pid: str, where: str, text: str, pids: set[str], term_aliases: set[str]) -> None:
    dangling: list[str] = []
    for target in WIKI.findall(text):
        target = target.strip()
        if not target:
            continue
        if target.startswith("_"):
            continue  # MOC：Web 渲染为筛选导航，总是可解析
        base = target
        for suffix in CLUSTER_SUFFIXES:
            if suffix in base:
                base = base.split(suffix)[0]
                break
        if base in pids:
            continue
        if normalize_key(target) in term_aliases:
            continue
        if target not in dangling:
            dangling.append(target)
    if dangling:
        preview = "、".join(dangling[:6]) + ("…" if len(dangling) > 6 else "")
        lint.w(pid, f"{where}有 {len(dangling)} 个悬空链接（Web 渲染为纯文本）：{preview}")


def check_images(lint: Lint, pid: str, where: str, text: str, idir: Path | None) -> None:
    local = {p.name for p in idir.iterdir()} if (idir and idir.is_dir()) else set()
    for name in EMBED.findall(text):
        name = name.strip()
        if not IMAGE_EXTS.search(name):
            continue
        if Path(name).name not in local:
            lint.e(pid, f"{where}嵌入的图片不存在：{name}")


CAPTION_LINE = re.compile(r"^(?:\*\*|__)?\s*(?:图|表|Fig|Figure|Table|Graphical)", re.I)
CAPTION_PREFIX = re.compile(
    r"^(?:\*\*|__)?\s*(?:图形摘要|图|表|Fig(?:ure)?\.?|Table|Graphical(?:\s+Abstract)?)"
    r"\s*(?:\d+[A-Za-z]?|[一二三四五六七八九十]+)?\s*[:：。.]*\s*(?:\*\*|__)?\s*",
    re.I,
)
EN_FORBIDDEN_H2 = re.compile(
    r"^##\s+(Key Points|要点|通俗摘要|Plain Language Summary)\b", re.I | re.M
)
EN_AUTHOR_SUP = re.compile(r"\^\{\d")
EN_JOURNAL_SHELL = re.compile(
    r"^(Correspondence to:|Citation:|Received \d|Accepted \d)", re.I | re.M
)


def english_byline_block(text: str) -> str:
    match = re.search(r"^# .+$", text, re.M)
    if not match:
        return ""
    rest = text[match.end() :]
    next_h = re.search(r"^##\s+", rest, re.M)
    return rest[: next_h.start()] if next_h else rest[:800]


def check_english_article(lint: Lint, pid: str, text: str, zh_text: str) -> None:
    byline = english_byline_block(text)
    if EN_AUTHOR_SUP.search(byline):
        lint.e(pid, "英文正文作者行含 ^{单位号}（应写成一段加粗作者 + 一段单位）")
    if EN_FORBIDDEN_H2.search(text):
        lint.e(pid, "英文正文含禁用标题（Key Points / 要点 / Plain Language Summary / 通俗摘要）；用 ## Highlights")
    if EN_JOURNAL_SHELL.search(byline) or EN_JOURNAL_SHELL.search(text):
        lint.e(pid, "英文正文残留期刊页眉（Correspondence / Citation / Received / Accepted）")
    if zh_text:
        zh_n = len(EMBED.findall(zh_text))
        en_n = len(EMBED.findall(text))
        if zh_n and abs(zh_n - en_n) > 2:
            lint.e(pid, f"英文正文图数 {en_n} 与中文 {zh_n} 相差过大")


def check_captions(lint: Lint, pid: str, text: str) -> None:
    """图注检查：图片行（或连续图组）后应紧跟「**图 N：**说明」段。
    只有标签没有说明文字也视为缺失；复合图 (a)(b) 拆成多张连续嵌入、
    共享一个图注是合法的。"""
    lines = text.splitlines()
    total = missing = 0
    for i, line in enumerate(lines):
        if not EMBED.search(line):
            continue
        total += 1
        has_caption = False
        j = i + 1
        while j < min(i + 8, len(lines)):
            nxt = lines[j].strip()
            if not nxt:
                j += 1
                continue
            if EMBED.search(nxt):
                # 连续图组：图注允许出现在整组之后
                j += 1
                continue
            match = CAPTION_LINE.match(nxt)
            has_caption = bool(match and CAPTION_PREFIX.sub("", nxt, count=1).strip())
            break
        if not has_caption:
            missing += 1
    if total and missing:
        lint.w(pid, f"正文 {total} 张图有 {missing} 张缺图注（图片行后紧跟「**图 N：**说明」段）")


def check_topic_docs(lint: Lint, vault: Path) -> None:
    topics_dir = vault / "Topics"
    if not topics_dir.is_dir():
        return
    for path in topics_dir.rglob("*.md"):
        if path.name.startswith("_"):
            continue
        fm, _body = fm_body(rd(path))
        name = f"Topics/{path.stem}"
        missing = [field for field in ("noteType", "docType", "domain", "translatedTitle")
                   if not re.search(rf'^{field}:\s*\S', fm, re.M)]
        if missing:
            lint.w(name, f"专题文档 frontmatter 建议补充：{'、'.join(missing)}")


def check_doc(lint: Lint, pid: str, where: str, text: str, idir: Path | None,
              pids: set[str], term_aliases: set[str]) -> None:
    if where == "正文" and re.search(r"结构化摘译|中文精读版|摘要版译文", text):
        lint.e(pid, "中文正文标记为摘译/精读版，须补齐全文；学习笔记可保留精读内容")
    if MARKER.search(text):
        lint.e(pid, f"{where}残留构造标记（strip_markers 没跑）")
    for ph in PLACEHOLDERS:
        if ph in text:
            lint.e(pid, f"{where}占位符未回填：{ph[:24]}")
            break
    if text.count("$$") % 2 == 1:
        lint.e(pid, f"{where}块公式 $$ 未闭合（奇数个定界符）")
    if ("<!--REFS_AUTO-->" in text) != ("<!--/REFS_AUTO-->" in text):
        lint.e(pid, f"{where}REFS_AUTO 标记破损（有开无关或反之）")
    if "[[[" in text:
        lint.w(pid, f"{where}残留三层括号链接（重跑 build_refs --inline 自愈）")
    for line in text.splitlines():
        if line.startswith("|"):
            cleaned = (
                line.replace("\\lt", "").replace("\\gt", "").replace("&lt;", "").replace("&gt;", "")
            )
            if re.search(r"(?<!\\)[<>]", cleaned):
                lint.w(pid, f"{where}表格行含裸 </>（会崩表）：{line[:50]}")
                break
    check_images(lint, pid, where, text, idir)
    check_links(lint, pid, where, text, pids, term_aliases)


def run(vault: Path, paper: str | None = None) -> Lint:
    lint = Lint()
    clusters = collect_clusters(vault)
    # pid 全集始终取全库：缩小检查范围不能让库内互链变成悬空
    pids = {pid for pid, *_ in clusters}
    term_aliases = load_term_aliases(vault, lint)
    if paper:
        clusters = [c for c in clusters if paper in c[0]]
        if not clusters:
            lint.e(paper, "--paper 没匹配到任何集群（pid 子串写错？）")
            return lint

    for pid, index_path, cdir, idir in clusters:
        index_text = rd(index_path)
        fm, _body = fm_body(index_text)

        missing = [field for field in REQUIRED_FM
                   if not re.search(rf'^{field}:\s*\S', fm, re.M)]
        if missing:
            lint.e(pid, f"index frontmatter 缺必填字段：{'、'.join(missing)}")
        soft_missing = [field for field in RECOMMENDED_FM
                        if not re.search(rf'^{field}:\s*\S', fm, re.M)]
        if soft_missing:
            lint.w(pid, f"index frontmatter 建议补充：{'、'.join(soft_missing)}")
        if MARKER.search(index_text):
            lint.e(pid, "index 残留构造标记")
        for ph in PLACEHOLDERS:
            if ph in index_text:
                lint.e(pid, f"index 占位符未回填：{ph[:24]}")
                break
        check_links(lint, pid, "index ", index_text, pids, term_aliases)

        if cdir is None:
            lint.e(pid, "找不到 content/ 目录（集群结构破损，Web 无法展示正文）")
            continue

        article = rd(cdir / f"{pid}.正文.md")
        if article:
            check_doc(lint, pid, "正文", article, idir, pids, term_aliases)
            check_captions(lint, pid, article)
        else:
            lint.e(pid, "缺正文文件 content/<pid>.正文.md")

        article_en = rd(cdir / f"{pid}.正文.en.md")
        if article_en:
            check_doc(lint, pid, "英文正文", article_en, idir, pids, term_aliases)
            check_captions(lint, pid, article_en)
            check_english_article(lint, pid, article_en, article)
        elif (cdir / f"{pid}.txt").exists():
            # 中文母语论文不产英文正文（契约第 4 节），不告警
            m = re.search(r"^\-\s*\*\*原题\*\*：(.+)$", index_text, re.M)
            orig_title = m.group(1) if m else ""
            is_zh_source = bool(orig_title) and any("\u4e00" <= ch <= "\u9fff" for ch in orig_title)
            if not is_zh_source:
                lint.w(pid, "缺英文正文 content/<pid>.正文.en.md（Web 英文 tab 回退 txt 简排版，阅读体验差）")

        notes_path = cdir / f"{pid}.notes.md"
        notes = rd(notes_path)
        if notes:
            check_doc(lint, pid, "notes ", notes, idir, pids, term_aliases)
        else:
            lint.w(pid, "缺 notes 文件（学习笔记 tab 将为空）")

    if not paper:
        check_topic_docs(lint, vault)
    return lint


def main() -> None:
    if sys.platform == "win32":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")
    parser = argparse.ArgumentParser(description="文枢 Web 发布质检")
    parser.add_argument("--vault", default=str(Path(__file__).resolve().parents[2] / "vault"))
    parser.add_argument("--paper", default=None,
                        help="只查 pid 含此子串的集群（多子代理并行时各自自验用）")
    parser.add_argument("--fail-on-warnings", action="store_true",
                        help="严格模式：警告也返回退出码 1（建议只与 --paper 一起用于新论文）")
    args = parser.parse_args()
    vault = Path(args.vault)
    if not vault.is_dir():
        print(f"找不到 vault：{vault}")
        sys.exit(1)

    lint = run(vault, args.paper)
    scope = f"（范围：{args.paper}）" if args.paper else ""
    lines = [f"❌ {pid} ｜ {msg}" for pid, msg in lint.errors]
    lines += [f"⚠️ {pid} ｜ {msg}" for pid, msg in lint.warns]
    print("\n".join(lines) if lines else f"✅ Web 发布质检全部通过{scope}")
    print(f"—— web_lint{scope}：{len(lint.errors)} 错误 · {len(lint.warns)} 警告")
    sys.exit(1 if lint.errors or (args.fail_on_warnings and lint.warns) else 0)


if __name__ == "__main__":
    main()
