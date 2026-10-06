#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
finish.py — 把子代理写好的 out/ 内容装配成文枢集群，合并术语库，跑前端质检并同步。

    python finish.py --work <workdir> --vault <vault> [--wenshu <app>] [--no-sync] [--no-lint]

需要 <workdir>/out/：zh.md · notes.md · terms.json · fields.json（英文原刊另需 en.md）。
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import shutil
import subprocess
import sys
import time
import unicodedata
from pathlib import Path

STOP = {"the", "and", "for", "with", "from", "into", "using", "based", "toward", "towards", "via", "on", "of", "in", "a", "an"}


def utf8() -> None:
    if sys.platform == "win32":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")


def rd(p: Path) -> str:
    return p.read_text(encoding="utf-8") if p.exists() else ""


def wr(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def sanitize(name: str, limit: int = 120) -> str:
    name = re.sub(r'[\\/:*?"<>|\n\r\t]+', " ", name)
    name = re.sub(r"\s+", " ", name).strip(" .")
    return name[:limit].strip(" .")


def ascii_name(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    return re.sub(r"[^A-Za-z0-9]+", "", "".join(ch for ch in text if not unicodedata.combining(ch)))


def normalize_key(name: str) -> str:
    return "".join(ch for ch in name.lower() if ch.isalnum() or "一" <= ch <= "鿿")


def yaml_str(v: str) -> str:
    return '"' + str(v).replace("\\", "\\\\").replace('"', '\\"') + '"'


def strip_front_junk(md: str) -> str:
    """子代理偶尔会把 frontmatter 或代码围栏带进来：去掉。"""
    md = md.strip()
    if md.startswith("---"):
        parts = md.split("---", 2)
        if len(parts) >= 3:
            md = parts[2].strip()
    if md.startswith("```"):
        md = re.sub(r"^```[a-z]*\n", "", md)
        md = re.sub(r"\n```\s*$", "", md)
    return md.strip() + "\n"


def drop_section(md: str, pattern: str) -> str:
    return re.sub(rf"^## {pattern}\b[^\n]*\n[\s\S]*?(?=^## |\Z)", "", md, flags=re.M | re.I)


def delink(md: str, pids: set[str], aliases: set[str]) -> tuple[str, list[str]]:
    dropped: list[str] = []

    def repl(m: re.Match) -> str:
        target, alias = m.group(1).strip(), m.group(2)
        if target.startswith("#") or target.startswith("_"):
            return m.group(0)
        base = re.split(r"\.(?:正文|notes|images|我的笔记|pdf|txt)", target)[0]
        if base in pids or normalize_key(target) in aliases:
            return m.group(0)
        dropped.append(target)
        return (alias or target).strip()

    return re.sub(r"(?<!!)\[\[([^\]|]+?)(?:\|([^\]]*))?\]\]", repl, md), dropped


def merge_terms(vault: Path, terms: list[dict], pid: str, domain: str) -> tuple[int, int]:
    tdir = vault / "30_Terms" / "术语"
    tdir.mkdir(parents=True, exist_ok=True)
    reg_path = tdir / "_registry.json"
    registry = json.loads(rd(reg_path) or "{}")
    added = reused = 0
    for t in terms:
        term = str(t.get("term") or "").strip()
        if not term:
            continue
        key = normalize_key(term)
        zh = str(t.get("zhName") or "").strip()
        full = str(t.get("fullName") or "").strip()
        entry = registry.get(key)
        if entry is None:
            note = sanitize(term, 80) + ".md"
            entry = {"note": note, "term": term, "zhName": zh, "fullName": full,
                     "aliases": [a for a in {full, zh} if a], "type": str(t.get("type") or "概念"),
                     "domain": [domain], "definition": str(t.get("definition") or ""), "usages": []}
            registry[key] = entry
            added += 1
        else:
            reused += 1
            if domain not in entry.setdefault("domain", []):
                entry["domain"].append(domain)
            for a in (full, zh):
                if a and a not in entry.setdefault("aliases", []):
                    entry["aliases"].append(a)
        usages = entry.setdefault("usages", [])
        if not any(u.get("paper") == pid for u in usages):
            usages.append({"paper": pid, "context": str(t.get("context") or "")})
        # 术语笔记（前端只读 registry，这份给 Obsidian/人看）
        title = f"{entry['term']}（{entry['zhName']}）" if entry.get("zhName") else entry["term"]
        body = [
            "---", f"term: {yaml_str(entry['term'])}", f"zhName: {yaml_str(entry.get('zhName', ''))}",
            f"fullName: {yaml_str(entry.get('fullName', ''))}", f"type: {yaml_str(entry.get('type', ''))}",
            "domain: [" + ", ".join(yaml_str(d) for d in entry.get("domain", [])) + "]",
            "papers: [" + ", ".join(yaml_str(f"[[{u['paper']}]]") for u in usages) + "]",
            "noteType: term", "---", "", f"# {title}", "",
        ]
        if entry.get("fullName"):
            body += [f"**全称**：{entry['fullName']}", ""]
        body += ["**通用定义**", "", entry.get("definition", ""), "", "## 各论文中的用法"]
        body += [f"- [[{u['paper']}]]：{u.get('context', '')}" for u in usages]
        wr(tdir / entry["note"], "\n".join(body) + "\n")
    wr(reg_path, json.dumps(registry, ensure_ascii=False, indent=1))
    return added, reused


def run(cmd: list[str], cwd: Path | None = None) -> tuple[int, str]:
    proc = subprocess.run(cmd, cwd=str(cwd) if cwd else None, capture_output=True)
    out = (proc.stdout + proc.stderr).decode("utf-8", errors="replace")
    return proc.returncode, out


def existing_paper(vault: Path, index: Path, doi: str, wenshu: Path | None) -> str:
    """优先查目标索引及已同步目录，避免重入库覆盖阅读状态与既有标识。"""
    if index.exists():
        return index.stem
    catalog = wenshu / "public" / "vault" / "catalog.json" if wenshu else None
    if not doi or not catalog or not catalog.is_file():
        return ""
    data = json.loads(rd(catalog))
    papers = data.get("papers", []) if isinstance(data, dict) else data
    normalized = doi.strip().lower().removeprefix("https://doi.org/")
    for paper in papers:
        if str(paper.get("doi", "")).strip().lower().removeprefix("https://doi.org/") != normalized:
            continue
        relative = (paper.get("vault") or {}).get("index")
        if not relative:
            continue
        target = (vault / relative).resolve()
        if target.is_relative_to(vault / "Papers") and target.is_file():
            return str(paper.get("pid") or target.stem)
    return ""


def main() -> None:
    utf8()
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    ap.add_argument("--vault", required=True)
    ap.add_argument("--wenshu", default="")
    ap.add_argument("--no-sync", action="store_true")
    ap.add_argument("--no-lint", action="store_true")
    ap.add_argument("--force", action="store_true", help="verify 有 error 也照样装配（只用于人工兜底）")
    a = ap.parse_args()
    t0 = time.time()
    work = Path(a.work).resolve()
    vault = Path(a.vault).resolve()
    out = work / "out"
    meta = json.loads(rd(work / "meta.json"))
    stats = json.loads(rd(work / "stats.json") or "{}")
    fields = json.loads(rd(out / "fields.json") or "{}")
    lang = meta.get("lang", "en")
    missing = [f for f in ("zh.md", "notes.md", "fields.json") + (("en.md",) if lang == "en" else ()) if not (out / f).exists()]
    if missing:
        raise SystemExit(f"out/ 缺文件：{missing}")

    # ---- 身份
    authors = fields.get("authors") or meta.get("authors") or []
    for field in ("doi", "journal"):
        if field in fields:
            meta[field] = str(fields[field] or "").strip()
    year = str(fields.get("year") or meta.get("year") or "")
    title = str(fields.get("title") or meta.get("title") or "").strip()
    if (not title or title == Path(meta.get("pdf", "")).stem) and fields.get("translatedTitle"):
        title = str(fields["translatedTitle"]).strip()   # 中文刊：题名抽不到时 meta 里是文件名，用子代理填的原题
    key = meta.get("key", "")
    if (not key or key.startswith("Paper")) and authors:
        key = f"{ascii_name(authors[0].split()[-1]) if ' ' in authors[0] else ascii_name(authors[0][:1] if lang == 'zh' else authors[0])}{year}"
        if lang == "zh" and authors and not re.search(r"[A-Za-z]", authors[0]):
            # 中文作者：用拼音不可靠，退回「姓氏首字 + 年」的 ASCII 形式由 fields.pinyin 提供，否则 Paper 键
            key = f"{ascii_name(fields.get('firstAuthorPinyin', '')) or 'Paper'}{year}"
    short = sanitize(str(fields.get("shortTitle") or "").replace(" ", ""), 30) or "未命名"
    pid = f"{key} {short}"
    folder = sanitize(f"{key} {title}", 120)
    domain = str(fields.get("domain") or "其他/未分类").strip("/ ")
    if "/" not in domain:
        domain = f"{domain}/综合"
    cluster = vault / "Papers" / domain / folder
    content = cluster / "content"
    images = cluster / "images"
    wenshu = Path(a.wenshu).resolve() if a.wenshu else None
    existing = existing_paper(vault, cluster.parent / f"{pid}.md", str(meta.get("doi") or ""), wenshu)
    if existing:
        raise SystemExit(f"已入库：{existing}；停止重复装配。直接打开现有条目，修复仅更新对应文件并单篇校验同步。")

    first_word = next((w for w in re.findall(r"[A-Za-z]{3,}", title.lower()) if w not in STOP), "paper")
    if authors and " " in authors[0]:
        surname = ascii_name(authors[0].split()[-1]).lower()
    else:
        surname = (ascii_name(str(fields.get("firstAuthorPinyin") or "")) or re.sub(r"\d+$", "", ascii_name(key))).lower()
    citekey = str(fields.get("citekey") or f"{surname}{year}{'book' if meta.get('documentType') == 'book' else ''}{first_word}")
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", citekey):
        raise SystemExit("fields.citekey 须为小写字母数字、下划线或连字符组成的阅读标识。")
    catalog = wenshu / "public" / "vault" / "catalog.json" if wenshu else None
    if catalog and catalog.is_file():
        data = json.loads(rd(catalog))
        papers = data.get("papers", []) if isinstance(data, dict) else data
        conflict = next((p for p in papers if str(p.get("citekey") or p.get("slug") or "") == citekey), None)
        if conflict:
            raise SystemExit(f"阅读标识冲突：{citekey} 已由 {conflict.get('pid', '')} 使用；请给新论文设置独立 fields.citekey，保留既有条目。")

    # ---- 闸门在任何正式库写入之前执行；已有条目无需重复检查草稿。
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from verify import verify  # noqa: E402
    checked = verify(work)
    if not checked["ok"] and not a.force:
        print(json.dumps({"verify": checked}, ensure_ascii=False, indent=1))
        raise SystemExit("verify 未通过：先修对应 out/ 内容再运行 finish")
    content.mkdir(parents=True, exist_ok=True)
    images.mkdir(parents=True, exist_ok=True)

    # ---- 图片：<key>_page → <pid>_page
    old_prefix = f"{meta.get('key', key)}_page"
    new_prefix = f"{pid}_page"
    copied = 0
    for p in (work / "images").glob("*.png"):
        if p.name.startswith("_"):
            continue
        shutil.copy2(p, images / p.name.replace(old_prefix, new_prefix))
        copied += 1

    def fix_images(md: str) -> str:
        return md.replace(old_prefix, new_prefix)

    # ---- 术语（先合并，delink 才知道哪些 [[术语]] 合法）
    try:
        terms = json.loads(rd(out / "terms.json") or "[]")
    except Exception as exc:
        print(f"terms.json 解析失败，跳过术语：{exc}")
        terms = []
    added, reused = merge_terms(vault, terms if isinstance(terms, list) else [], pid, domain)
    registry = json.loads(rd(vault / "30_Terms" / "术语" / "_registry.json") or "{}")
    aliases: set[str] = set()
    for k, e in registry.items():
        for n in [k, e.get("term", ""), e.get("zhName", ""), e.get("fullName", ""), (e.get("note") or "")[:-3], *(e.get("aliases") or [])]:
            if normalize_key(str(n)):
                aliases.add(normalize_key(str(n)))
    pids = {p.stem for p in (vault / "Papers").rglob("*.md")
            if "content" not in p.parts and "images" not in p.parts and not p.name.startswith("_")} | {pid}

    # ---- 正文 / 笔记
    fm_article = f'---\nnoteType: article\npaper: "[[{pid}]]"\ntags: ["p2o/sub"]\n---\n\n'
    zh = fix_images(strip_front_junk(rd(out / "zh.md")))
    zh = drop_section(zh, r"(?:参考文献|References)")
    zh, d1 = delink(zh, pids, aliases)
    refs = rd(work / "refs.md").strip()
    if refs:
        zh = zh.rstrip() + "\n\n## 参考文献\n\n<!--REFS_AUTO-->\n" + refs + "\n<!--/REFS_AUTO-->\n"
    wr(content / f"{pid}.正文.md", fm_article + zh)
    dropped = list(d1)
    if lang == "en":
        en = fix_images(strip_front_junk(rd(out / "en.md")))
        en = drop_section(en, r"References")
        en = re.sub(r"<!--EQ[^>]*-->\n?", "", en)
        en, d2 = delink(en, pids, aliases)
        dropped += d2
        if refs:
            en = en.rstrip() + "\n\n## References\n\n<!--REFS_AUTO-->\n" + refs + "\n<!--/REFS_AUTO-->\n"
        wr(content / f"{pid}.正文.en.md", fm_article + en)
    notes = fix_images(strip_front_junk(rd(out / "notes.md")))
    notes, d3 = delink(notes, pids, aliases)
    dropped += d3
    wr(content / f"{pid}.notes.md", f'---\nnoteType: notes\npaper: "[[{pid}]]"\ntags: ["p2o/sub"]\n---\n\n' + notes)
    shutil.copy2(meta["pdf"], content / f"{pid}.pdf")
    wr(content / f"{pid}.txt", rd(work / "fulltext.txt"))

    # ---- 索引
    if not meta.get("journal"):
        # 中文刊：Crossref 查不到，用子代理填的刊名；没填就从 zh.md 题名块的斜体期刊行里取
        jl = re.search(r"(?m)^\*([^*\d\n]{2,60}?)\s+(?:19|20)\d{2}\b[^*\n]*\*\s*$", zh[:3000])
        meta["journal"] = str(fields.get("journal") or (jl.group(1).strip() if jl else "")).strip()
    sha = hashlib.sha256(Path(meta["pdf"]).read_bytes()).hexdigest()
    topics = [str(t).strip() for t in fields.get("topics") or [] if str(t).strip()]
    tags = ["论文笔记", "p2o/paper", domain] + [f"主题/{t}" for t in topics]
    score = str(fields.get("score") or "").strip()
    jline = meta.get("journal", "")
    if jline:
        vol = meta.get("volume", "")
        jline = f"{jline} {year}" + (f"，{vol}" if vol else "") + (f"({meta['issue']})" if meta.get("issue") else "") + (f"：{meta['pages']}" if meta.get("pages") else "")
    kws = fields.get("keywords") or []
    index = [
        "---",
        f"translatedTitle: {yaml_str(fields.get('translatedTitle') or title)}",
        "authors:", *[f"  - {yaml_str(x)}" for x in authors],
        f"year: {yaml_str(year)}",
        f"journal: {yaml_str(meta.get('journal', ''))}",
        f"doi: {yaml_str(meta.get('doi', ''))}",
        f"citekey: {yaml_str(citekey)}",
        f"sourceHash: {yaml_str('sha256:' + sha)}",
        f"domain: {yaml_str(domain)}",
        "tags:", *[f"  - {yaml_str(x)}" for x in tags],
        f"quality_score: {yaml_str(score)}",
        "noteType: index", "status: analyzed", "reading: 待读", "---", "",
        f"# {fields.get('translatedTitle') or title}", "",
        "## 🗂️ 笔记集群",
        f"- [[{pid}.正文|📄 正文（中文翻译）]]",
        f"- [[{pid}.notes|🎓 学习卡 + 🔬 深度分析 + ✍️ 写作逻辑]]",
        f"- [[{pid}.images|🖼️ 图片索引]]",
        "- 全局术语库：[[_术语库总览]]", "",
        "## 📇 文献卡",
        f"- **原题**：{title}",
        f"- **译名**：{fields.get('translatedTitle') or title}",
        f"- **作者**：{'、'.join(authors)}",
        f"- **期刊**：{jline}",
        f"- **DOI**：[{meta.get('doi', '')}](https://doi.org/{meta.get('doi', '')})" if meta.get("doi") else "- **DOI**：无",
        f"- **领域**：{domain}",
        f"- **关键词**：{'；'.join(kws)}" if kws else "",
        f"- **📎 原始 PDF**：[[{pid}.pdf]]", "",
        "## ❓ 科学问题", str(fields.get("question") or "").strip(), "",
        "## 📝 一句话总结", str(fields.get("tldr") or "").strip(), "",
        "## ⭐ 评分", score or "未评分", "",
    ]
    wr(cluster.parent / f"{pid}.md", "\n".join(x for x in index if x is not None) + "\n")

    # ---- 图片索引（供人看；前端从正文取图注）。v2：裁图记录在 figcut.json（按 layout.json 清单裁的）
    figcut = json.loads(rd(work / "figcut.json") or "{}")
    figs = figcut.get("figures") or stats.get("figureList", [])
    lines = [f"# {pid} 图片索引", ""]
    for f in figs:
        if f.get("file"):
            lines += [f"![[{f['file'].replace(old_prefix, new_prefix)}|600]]", "", f"**Fig. {f['num']}.**（p{f['page']}，{f['status']}）{str(f.get('caption', ''))[:200]}", ""]
    wr(images / f"{pid}.images.md", "\n".join(lines))

    summary = {
        "pid": pid, "folder": str(cluster), "domain": domain, "lang": lang, "images": copied,
        "termsAdded": added, "termsReused": reused, "delinked": sorted(set(dropped)),
        "refs": len(re.findall(r"(?m)^- \*\*\[\d+\]\*\*", refs)), "finishSeconds": round(time.time() - t0, 2),
        "verify": {"ok": checked["ok"], "errors": len(checked["errors"]), "warnings": len(checked["warnings"]),
                   "forced": bool(a.force and not checked["ok"]), "counts": checked.get("counts", {})},
    }
    if wenshu and not a.no_lint:
        rc, text = run([sys.executable, str(wenshu / "scripts" / "web_lint.py"), "--vault", str(vault), "--paper", pid, "--fail-on-warnings"])
        summary["webLint"] = {"rc": rc, "tail": text.strip().splitlines()[-12:]}
    lint_failed = summary.get("webLint", {}).get("rc", 0) != 0
    if wenshu and not a.no_sync and not lint_failed:
        rc, text = run([sys.executable, str(wenshu / "scripts" / "sync-vault.py"), "--vault", str(vault), "--no-lint"], cwd=wenshu)
        summary["sync"] = {"rc": rc, "tail": text.strip().splitlines()[-4:]}
    failed = not checked["ok"] or lint_failed or summary.get("sync", {}).get("rc", 0) != 0
    ready = not failed and summary.get("webLint", {}).get("rc") == 0 and summary.get("sync", {}).get("rc") == 0
    summary["status"] = "failed" if failed else "ready" if ready else "assembled"
    summary["citekey"] = citekey
    summary["readingPath"] = f"/dashboard/papers/{citekey}"
    sysdir = vault / "90_系统" / "_ingest"
    sysdir.mkdir(parents=True, exist_ok=True)
    timing = json.loads(rd(work / "timing.json") or "{}")
    wr(sysdir / f"{pid}.lite.json", json.dumps({"summary": summary, "extract": {k: v for k, v in stats.items() if k != "figureList"}, "timing": timing}, ensure_ascii=False, indent=1))
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
