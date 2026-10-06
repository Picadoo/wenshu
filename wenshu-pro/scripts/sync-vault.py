#!/usr/bin/env python3
"""把 pdf-to-wenshu 文库集群同步到前端 public/vault，并生成目录数据。"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_VAULT = ROOT.parent / "vault"
PUBLIC_VAULT = ROOT / "public" / "vault"
GENERATED_TS = ROOT / "src" / "data" / "generated-catalog.ts"
GENERATED_TERMS_TS = ROOT / "src" / "data" / "generated-terms.ts"
GENERATED_ACTIVITY_TS = ROOT / "src" / "data" / "generated-activity.ts"
WEB_LINT = ROOT / "scripts" / "web_lint.py"
MD2HTML: Path | None = None
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
WIKI_IMAGE = re.compile(r"!\[\[([^\]|#]+)(?:\|[^\]]*)?\]\]")
PAGE_FIG = re.compile(r"_page(\d+)_fig(?:([A-Za-z]))?(\d+)", re.I)
CAPTION_LINE = re.compile(r"^(?:\*\*|__)?\s*(?:图|表|Fig|Figure|Table|Graphical)", re.I)

# ----------------------------------------------------------------------
# 增量镜像：不再每次 rmtree 全量重拷（600+ 文件事件会让 vite watcher 内存暴涨、
# 同步也慢）。改为按 size+mtime / 内容比对跳过未变文件，收尾清掉孤儿。

PRODUCED: set[Path] = set()  # 本轮产出的 public/vault 内文件，收尾据此清孤儿


def keep(path: Path) -> Path:
    PRODUCED.add(path.resolve())
    return path


def mirror_copy(src: Path, dst: Path) -> bool:
    """增量拷贝：目标存在且 size 一致、mtime 不早于源（容忍 2s 粒度）则跳过。"""
    keep(dst)
    try:
        st_s, st_d = src.stat(), dst.stat()
        if st_s.st_size == st_d.st_size and st_d.st_mtime >= st_s.st_mtime - 2:
            return False
    except OSError:
        pass
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return True


def write_if_changed(dst: Path, text: str) -> bool:
    """按内容比对写入：内容没变就不落盘（不扰动 mtime / watcher）。"""
    keep(dst)
    try:
        if dst.read_text(encoding="utf-8") == text:
            return False
    except OSError:
        pass
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(text, encoding="utf-8")
    return True


def sweep_orphans() -> int:
    """删除 public/vault 里本轮没有产出的文件（源头已删的论文/图片），清空目录。"""
    removed = 0
    if not PUBLIC_VAULT.exists():
        return 0
    for path in sorted(PUBLIC_VAULT.rglob("*"), reverse=True):
        if path.is_file():
            if path.resolve() not in PRODUCED:
                path.unlink()
                removed += 1
        else:
            try:
                path.rmdir()
            except OSError:
                pass
    return removed


def normalize_link_key(name: str) -> str:
    """链接名归一：小写 + 只留字母/数字/汉字。前端 TS 里有同款实现，两边必须一致。"""
    return "".join(ch for ch in name.lower() if ch.isalnum() or "\u4e00" <= ch <= "\u9fff")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def parse_frontmatter(text: str) -> tuple[dict, str]:
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end < 0:
        return {}, text
    raw = text[4:end]
    body = text[end + 4 :].lstrip("\n")
    data: dict = {}
    key = None
    for line in raw.splitlines():
        if re.match(r"^\s+-\s+", line) and key:
            item = line.strip()[1:].strip().strip('"').strip("'")
            current = data.setdefault(key, [])
            if not isinstance(current, list):
                data[key] = [current]
            data[key].append(item)
            continue
        match = re.match(r"^([A-Za-z0-9_/-]+):\s*(.*)$", line)
        if not match:
            continue
        key, value = match.group(1), match.group(2).strip()
        if value == "":
            data[key] = []
            continue
        data[key] = value.strip('"').strip("'")
    return data, body


def as_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    if text.startswith("[") and text.endswith("]"):
        text = text[1:-1]
    return [part.strip().strip('"').strip("'") for part in text.split(",") if part.strip()]


def section_after(body: str, heading: str) -> str:
    pattern = rf"^##\s+.*{re.escape(heading)}.*$"
    match = re.search(pattern, body, flags=re.M)
    if not match:
        return ""
    rest = body[match.end() :]
    nxt = re.search(r"^##\s+", rest, flags=re.M)
    chunk = rest[: nxt.start()] if nxt else rest
    lines = [line.strip() for line in chunk.splitlines() if line.strip() and not line.startswith("<!--")]
    return "\n".join(lines).strip()


def field_from_card(body: str, label: str) -> str:
    match = re.search(rf"-\s+\*\*{re.escape(label)}\*\*[：:]\s*(.+)", body)
    if not match:
        return ""
    value = match.group(1).strip()
    value = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", value)
    return value


def slugify(meta: dict, pid: str) -> str:
    citekey = str(meta.get("citekey") or "").strip()
    if citekey:
        return re.sub(r"[^a-z0-9-]+", "-", citekey.lower()).strip("-")
    ascii_part = re.sub(r"[^A-Za-z0-9]+", "-", pid).strip("-").lower()
    return ascii_part or "paper"


def infer_kind(tags: list[str], domain: str) -> str:
    hay = " ".join(tags + [domain]).lower()
    if any(word in hay for word in ("综述", "review")):
        return "review"
    if any(word in hay for word in ("实验", "experiment")):
        return "experiment"
    return "method"


def infer_status(meta: dict) -> tuple[str, str]:
    reading = str(meta.get("reading") or "")
    status = str(meta.get("status") or "")
    if reading in {"在读", "精读中"}:
        return "reading", "private"
    if reading in {"写笔记"} or status in {"notes", "skeleton"}:
        return "notes", "private"
    if reading in {"已读", "重读"} or status in {"analyzed", "ready"}:
        return "ready", "shared"
    if status == "shared":
        return "shared", "shared"
    return "reading", "private"


def find_cluster_dir(index_path: Path, pid: str) -> Path | None:
    parent = index_path.parent
    candidates = [
        parent / pid,
        *sorted(parent.glob("*")),
    ]
    wanted = [
        f"{pid}.正文.md",
        f"{pid}.md",
        f"{pid}.notes.md",
        f"{pid}.pdf",
        f"{pid}.txt",
    ]
    for folder in candidates:
        if not folder.is_dir():
            continue
        content = folder / "content"
        if not content.is_dir():
            continue
        if any((content / name).exists() for name in wanted):
            return folder
    return None


def encode_url_path(path: str) -> str:
    return "/".join(quote(part, safe="") for part in path.split("/") if part != "")


def public_file(slug: str, rel: Path) -> str:
    return "/" + encode_url_path("vault/papers/" + slug + "/" + rel.as_posix())


def extract_figure_meta(article_path: Path | None) -> dict[str, dict]:
    """从正文抽每张图的出现顺序与图注（图片行后紧跟的「图 N：/**图形摘要**」段落）。
    复合图 (a)(b) 多张连续嵌入共享一个图注：跳过后续图片行继续找，整组同注。"""
    if article_path is None or not article_path.exists():
        return {}
    lines = read_text(article_path).splitlines()
    meta: dict[str, dict] = {}
    order = 0
    for i, line in enumerate(lines):
        match = WIKI_IMAGE.search(line)
        if not match:
            continue
        name = Path(match.group(1).strip()).name
        order += 1
        caption = ""
        for j in range(i + 1, min(i + 8, len(lines))):
            nxt = lines[j].strip()
            if not nxt or WIKI_IMAGE.search(nxt):
                continue
            if CAPTION_LINE.match(nxt):
                caption = re.sub(r"\*\*|__", "", nxt).strip()
            break
        if name not in meta:
            meta[name] = {"order": order, "caption": caption}
    return meta


def fallback_caption(name: str) -> str:
    match = PAGE_FIG.search(name)
    if match:
        app = (match.group(2) or "").upper()
        num = int(match.group(3))
        tag = f"{app}.{num}" if app else str(num)
        return f"第 {int(match.group(1))} 页 · 图 {tag}"
    return name


def collect_images(images_dir: Path, slug: str, fig_meta: dict[str, dict] | None = None) -> list[dict]:
    if not images_dir.is_dir():
        return []
    fig_meta = fig_meta or {}
    items = []
    for path in sorted(images_dir.iterdir(), key=lambda item: item.name):
        if path.suffix.lower() not in IMAGE_EXTS:
            continue
        # 跳过 generate_web_variants 生成的网络压缩档（x.png.webp）
        if path.name.lower().endswith((".png.webp", ".jpg.webp", ".jpeg.webp")):
            continue
        info = fig_meta.get(path.name, {})
        items.append(
            {
                "name": path.name,
                "url": public_file(slug, Path("images") / path.name),
                "size": path.stat().st_size,
                "caption": info.get("caption") or fallback_caption(path.name),
                "order": info.get("order") or 0,
            }
        )
    items.sort(key=lambda item: (item["order"] or 9999, item["name"]))
    return items


WEBP_LONG_EDGE = 1600
WEBP_QUALITY = 80


def generate_web_variants(images_dir: Path) -> int:
    """为大图生成 `<原名>.webp` 网络档：web 正文用压缩档省带宽，原图保留给大图查看/下载。"""
    if not images_dir.is_dir():
        return 0
    try:
        from PIL import Image
    except ImportError:
        print("提示：未安装 Pillow，跳过 webp 网络档生成")
        return 0
    count = 0
    for path in sorted(images_dir.iterdir()):
        if path.suffix.lower() not in {".png", ".jpg", ".jpeg"}:
            continue
        target = keep(path.with_name(path.name + ".webp"))
        try:
            if target.stat().st_mtime >= path.stat().st_mtime:
                continue  # 压缩档已是最新，跳过
        except OSError:
            pass
        with Image.open(path) as img:
            if img.mode not in ("RGB", "RGBA"):
                img = img.convert("RGBA" if "A" in img.getbands() else "RGB")
            long_edge = max(img.size)
            if long_edge > WEBP_LONG_EDGE:
                scale = WEBP_LONG_EDGE / long_edge
                img = img.resize((round(img.width * scale), round(img.height * scale)), Image.LANCZOS)
            img.save(target, "WEBP", quality=WEBP_QUALITY, method=6)
        count += 1
    return count


def infer_paper_lang(meta: dict, title: str, title_en: str) -> str:
    explicit = str(meta.get("lang") or "").strip().lower()
    if explicit in {"zh", "cn", "zh-cn"}:
        return "zh"
    if explicit in {"en", "eng"}:
        return "en"
    zh_title = any("\u4e00" <= ch <= "\u9fff" for ch in title)
    en = (title_en or "").strip()
    if zh_title and (not en or en == title):
        return "zh"
    return "en"


def pick_cover(images: list[dict]) -> str:
    if not images:
        return "/assets/images/cover/cover-1.webp"
    for key in ("page1_fig3", "page1_fig2", "page3_fig1", "page1_fig1"):
        for item in images:
            if key in item["name"]:
                return item["url"]
    return images[0]["url"]


def rewrite_markdown(text: str, images_dir_url: str) -> str:
    def repl(match: re.Match[str]) -> str:
        name = match.group(1).strip()
        url = images_dir_url.rstrip("/") + "/" + quote(name, safe="")
        return f"![{name}]({url})"

    return WIKI_IMAGE.sub(repl, text)


def render_reading_html(markdown_paths: list[Path]) -> dict[str, Path]:
    outputs: dict[str, Path] = {}
    if MD2HTML is None:
        return outputs
    if not MD2HTML.is_file():
        raise FileNotFoundError(f"指定的 md2html 工具不存在：{MD2HTML}")
    for path in markdown_paths:
        result = subprocess.run(
            [sys.executable, str(MD2HTML), str(path)],
            check=False,
            capture_output=True,
        )
        html_path = path.with_suffix(".html")
        if result.returncode != 0:
            err = (result.stderr or result.stdout or b"").decode("utf-8", errors="replace").strip()
            print(f"md2html 失败 {path.name}: {err}")
            continue
        if html_path.exists():
            outputs[path.name] = html_path
    return outputs


def content_file(content_dir: Path, pid: str, *suffixes: str) -> Path | None:
    for suffix in suffixes:
        path = content_dir / f"{pid}{suffix}"
        if path.exists():
            return path
    return None


def collect_papers(vault: Path) -> list[dict]:
    papers_dir = vault / "Papers"
    if not papers_dir.is_dir():
        raise SystemExit(f"找不到文库 Papers 目录: {papers_dir}")

    papers: list[dict] = []
    for index_path in papers_dir.rglob("*.md"):
        if index_path.name.startswith("_"):
            continue
        text = read_text(index_path)
        meta, body = parse_frontmatter(text)
        if str(meta.get("noteType") or "") != "index":
            continue

        pid = index_path.stem
        cluster = find_cluster_dir(index_path, pid)
        if cluster is None:
            print(f"跳过（无集群目录）: {index_path}")
            continue

        content_dir = cluster / "content"
        images_dir = cluster / "images"
        slug = slugify(meta, pid)
        tags = [tag for tag in as_list(meta.get("tags")) if tag and tag not in {"论文笔记", "p2o/paper"}]
        topics = [tag.split("/", 1)[1] for tag in tags if tag.startswith("主题/")]
        domain = str(meta.get("domain") or "")
        title = str(meta.get("translatedTitle") or pid)
        title_en = field_from_card(body, "原题")
        lang = infer_paper_lang(meta, title, title_en)
        authors = as_list(meta.get("authors"))
        year = int(str(meta.get("year") or "0") or 0)
        venue = str(meta.get("journal") or "")
        doi = str(meta.get("doi") or "")
        status, visibility = infer_status(meta)
        kind = infer_kind(tags, domain)
        tldr = section_after(body, "一句话总结")
        question = section_after(body, "科学问题")
        updated = datetime.fromtimestamp(index_path.stat().st_mtime, tz=timezone.utc).date().isoformat()

        article = content_file(content_dir, pid, ".正文.md", ".md")
        article_en = content_file(content_dir, pid, ".正文.en.md")
        notes = content_file(content_dir, pid, ".notes.md")
        pdf = content_file(content_dir, pid, ".pdf")
        txt = content_file(content_dir, pid, ".txt")

        dest = PUBLIC_VAULT / "papers" / slug
        images_dir_url = public_file(slug, Path("images"))

        # md：读源→重写图链→按内容比对写入；二进制（pdf/txt/图片）：size+mtime 增量拷贝
        all_md: list[Path] = []
        md_changed: list[Path] = []

        def sync_doc(src: Path, dst: Path) -> None:
            # <pid>.tables.md 是入库中间产物（英文原表，供译者/草稿脚本取数），
            # 前端没有它的 tab；当普通 md 走会白渲一份阅读版 HTML，纯属占地方。
            if src.name.endswith(".tables.md"):
                mirror_copy(src, dst)
            elif src.suffix.lower() == ".md":
                all_md.append(dst)
                if write_if_changed(dst, rewrite_markdown(read_text(src), images_dir_url)):
                    md_changed.append(dst)
            else:
                mirror_copy(src, dst)

        sync_doc(index_path, dest / "index.md")
        if content_dir.is_dir():
            for src in sorted(content_dir.rglob("*")):
                if src.is_file():
                    sync_doc(src, dest / "content" / src.relative_to(content_dir))
        if images_dir.is_dir():
            src_names = {p.name for p in images_dir.iterdir() if p.is_file()}
            dst_images = dest / "images"
            if dst_images.is_dir():  # 先清源头已删的图，避免本轮目录数据引用死图
                for stale in dst_images.iterdir():
                    base = stale.name[:-5] if stale.name.endswith(".webp") else stale.name
                    if base not in src_names:
                        stale.unlink()
            for src in sorted(images_dir.iterdir()):
                if src.is_file():
                    mirror_copy(src, dst_images / src.name)
            generate_web_variants(dst_images)

        images = collect_images(dest / "images", slug, extract_figure_meta(article))
        # 阅读版 HTML：只重渲「内容变化」或「html 缺失」的 md
        to_render = md_changed + [
            md for md in all_md if md not in md_changed and not md.with_suffix(".html").exists()
        ]
        render_reading_html(to_render)
        for md in all_md:
            html = md.with_suffix(".html")
            if html.exists():
                keep(html)

        files = {
            "index": public_file(slug, Path("index.md")),
            "imagesDir": images_dir_url,
        }
        if article:
            files["article"] = public_file(slug, Path("content") / article.name)
        if article_en:
            files["articleEn"] = public_file(slug, Path("content") / article_en.name)
        if notes:
            files["notes"] = public_file(slug, Path("content") / notes.name)
        if pdf:
            files["pdf"] = public_file(slug, Path("content") / pdf.name)
        if txt:
            files["txt"] = public_file(slug, Path("content") / txt.name)
        if (dest / "index.html").exists():
            files["indexHtml"] = public_file(slug, Path("index.html"))
        if article and (dest / "content" / article.with_suffix(".html").name).exists():
            files["articleHtml"] = public_file(slug, Path("content") / article.with_suffix(".html").name)
        if article_en and (dest / "content" / article_en.with_suffix(".html").name).exists():
            files["articleEnHtml"] = public_file(slug, Path("content") / article_en.with_suffix(".html").name)
        if notes and (dest / "content" / notes.with_suffix(".html").name).exists():
            files["notesHtml"] = public_file(slug, Path("content") / notes.with_suffix(".html").name)
        papers.append(
            {
                "id": pid.split()[0],
                "slug": slug,
                "pid": pid,
                "title": title,
                "titleEn": title_en,
                "authors": "、".join(authors),
                "authorList": authors,
                "year": year,
                "venue": venue,
                "doi": doi,
                "citekey": str(meta.get("citekey") or ""),
                "lang": lang,
                "kind": kind,
                "topic": domain.split("/")[0] if domain else (topics[0] if topics else "未分类"),
                "domain": domain,
                "tags": tags or topics,
                "status": status,
                "visibility": visibility,
                "reading": str(meta.get("reading") or ""),
                "vaultStatus": str(meta.get("status") or ""),
                "qualityScore": str(meta.get("quality_score") or ""),
                "sciQuestion": question,
                "tldr": tldr,
                "updatedAt": updated,
                "coverUrl": pick_cover(images),
                "excerpt": tldr or question or title,
                "images": images,
                "files": files,
                "hasTranslation": bool(article),
                "hasNotes": bool(notes),
                "hasPdf": bool(pdf),
                "hasTxt": bool(txt),
                "vault": {
                    "folder": cluster.relative_to(vault).as_posix(),
                    "index": index_path.relative_to(vault).as_posix(),
                    "article": article.relative_to(vault).as_posix() if article else "",
                    "articleEn": article_en.relative_to(vault).as_posix() if article_en else "",
                    "notes": notes.relative_to(vault).as_posix() if notes else "",
                    "pdf": pdf.relative_to(vault).as_posix() if pdf else "",
                    "txt": txt.relative_to(vault).as_posix() if txt else "",
                },
            }
        )
        print(f"已同步 {pid} -> {slug}")

    papers.sort(key=lambda item: (item["year"], item["id"]), reverse=True)
    return papers


def collect_topic_docs(vault: Path) -> list[dict]:
    """专题文档（综述/方法复刻/…）：vault/Topics/**/*.md → public/vault/topics/。"""
    topics_dir = vault / "Topics"
    docs: list[dict] = []
    if not topics_dir.is_dir():
        return docs
    dest_root = PUBLIC_VAULT / "topics"
    dest_root.mkdir(parents=True, exist_ok=True)
    for path in sorted(topics_dir.rglob("*.md")):
        if path.name.startswith("_"):
            continue
        meta, _body = parse_frontmatter(read_text(path))
        slug = normalize_link_key(path.stem) or f"topic-{len(docs) + 1}"
        dest = dest_root / f"{slug}.md"
        mirror_copy(path, dest)
        docs.append(
            {
                "slug": slug,
                "title": str(meta.get("translatedTitle") or meta.get("title") or path.stem),
                "docType": str(meta.get("docType") or "专题"),
                "domain": str(meta.get("domain") or path.parent.name if path.parent != topics_dir else str(meta.get("domain") or "")),
                "updatedAt": datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).date().isoformat(),
                "papers": as_list(meta.get("papers")),
                "file": "/" + encode_url_path(f"vault/topics/{slug}.md"),
            }
        )
    docs.sort(key=lambda item: item["updatedAt"], reverse=True)
    return docs


MINE_MARKERS = (".我的笔记.", "_web批注", "_生词", "_活动日志")


def collect_activity(vault: Path, papers: list[dict]) -> dict:
    """按天活动统计：mine=我的笔记/批注/生词/日志，ai=入库产物；papersByDay=每日入库篇数。"""
    days: dict[str, dict] = {}

    def bump(date: str, kind: str, count: int = 1) -> None:
        slot = days.setdefault(date, {"mine": 0, "ai": 0})
        slot[kind] += count

    scan_roots = [vault / "Papers", vault / "30_Terms", vault / "Topics"]
    for root in scan_roots:
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or ".obsidian" in path.parts:
                continue
            date = datetime.fromtimestamp(path.stat().st_mtime).date().isoformat()
            name = str(path)
            bump(date, "mine" if any(marker in name for marker in MINE_MARKERS) else "ai")

    # 应用写回的真实活动日志（P4 起），一行一个 JSON：{"date": "YYYY-MM-DD", "type": "note|highlight|vocab"}
    log_path = vault / "90_系统" / "_活动日志.jsonl"
    if log_path.exists():
        for line in read_text(log_path).splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except Exception:
                continue
            date = str(entry.get("date") or "")[:10]
            if date:
                bump(date, "mine")

    papers_by_day: dict[str, int] = {}
    for paper in papers:
        date = str(paper.get("updatedAt") or "")
        if date:
            papers_by_day[date] = papers_by_day.get(date, 0) + 1

    return {
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "days": dict(sorted(days.items())),
        "papersByDay": dict(sorted(papers_by_day.items())),
    }


def write_activity(activity: dict) -> None:
    keep(PUBLIC_VAULT / "activity.json").write_text(
        json.dumps(activity, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    ts = (
        "/* 由 scripts/sync-vault.py 生成，勿手改。按天活动统计（mine=我的笔记/批注，ai=入库产物）。 */\n"
        "import type { ActivityData } from './activity';\n\n"
        f"export const generatedActivity = {json.dumps(activity, ensure_ascii=False, indent=2)} as ActivityData;\n"
    )
    GENERATED_ACTIVITY_TS.write_text(ts, encoding="utf-8")


def write_catalog(papers: list[dict], topic_docs: list[dict]) -> None:
    PUBLIC_VAULT.mkdir(parents=True, exist_ok=True)
    catalog = {
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "count": len(papers),
        "papers": papers,
        "topicDocs": topic_docs,
    }
    keep(PUBLIC_VAULT / "catalog.json").write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    ts = (
        "/* 由 scripts/sync-vault.py 生成，勿手改。更新文库后重新运行该脚本。 */\n"
        "import type { Paper, TopicDoc } from './papers';\n\n"
        f"export const catalogGeneratedAt = {json.dumps(catalog['generatedAt'])};\n\n"
        f"export const generatedPapers = {json.dumps(papers, ensure_ascii=False, indent=2)} as Paper[];\n\n"
        f"export const generatedTopicDocs = {json.dumps(topic_docs, ensure_ascii=False, indent=2)} as TopicDoc[];\n"
    )
    GENERATED_TS.write_text(ts, encoding="utf-8")


def collect_terms(vault: Path) -> list[dict]:
    """读 30_Terms/术语/_registry.json（pdf-to-wenshu 术语库），转成前端术语列表。"""
    registry_path = vault / "30_Terms" / "术语" / "_registry.json"
    if not registry_path.exists():
        print(f"提示：找不到术语库 registry，跳过术语同步：{registry_path}")
        return []
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    terms: list[dict] = []
    for key, entry in registry.items():
        note = str(entry.get("note") or "")
        term = str(entry.get("term") or key)
        aliases = [str(item) for item in entry.get("aliases") or [] if str(item).strip()]
        domains = entry.get("domain") or []
        if isinstance(domains, str):
            domains = [domains]
        usages = [
            {
                "paper": str(usage.get("paper") or ""),
                "context": str(usage.get("context") or ""),
            }
            for usage in entry.get("usages") or []
            if str(usage.get("paper") or "")
        ]
        terms.append(
            {
                "key": key,
                "term": term,
                "zhName": str(entry.get("zhName") or ""),
                "fullName": str(entry.get("fullName") or ""),
                "aliases": aliases,
                "type": str(entry.get("type") or ""),
                "domains": [str(item) for item in domains],
                "definition": str(entry.get("definition") or ""),
                "noteStem": note[:-3] if note.endswith(".md") else note,
                "usages": usages,
            }
        )
    terms.sort(key=lambda item: item["term"].lower())
    return terms


def term_alias_map(terms: list[dict]) -> dict[str, str]:
    """归一化别名 -> 术语 key。含 term/zhName/fullName/aliases/笔记文件名。"""
    alias_map: dict[str, str] = {}
    for entry in terms:
        names = [entry["term"], entry["zhName"], entry["fullName"], entry["noteStem"], *entry["aliases"]]
        for name in names:
            normalized = normalize_link_key(str(name))
            if normalized:
                alias_map.setdefault(normalized, entry["key"])
    return alias_map


def write_terms(terms: list[dict]) -> None:
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    PUBLIC_VAULT.mkdir(parents=True, exist_ok=True)
    keep(PUBLIC_VAULT / "terms.json").write_text(
        json.dumps({"generatedAt": generated_at, "count": len(terms), "terms": terms}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    ts = (
        "/* 由 scripts/sync-vault.py 生成，勿手改。来源：vault/30_Terms/术语/_registry.json。 */\n"
        "import type { TermEntry } from './terms';\n\n"
        f"export const generatedTerms = {json.dumps(terms, ensure_ascii=False, indent=2)} as TermEntry[];\n"
    )
    GENERATED_TERMS_TS.write_text(ts, encoding="utf-8")


def write_link_map(papers: list[dict], terms: list[dict]) -> None:
    link_map = {
        "papers": {paper["pid"]: paper["slug"] for paper in papers},
        "terms": term_alias_map(terms),
    }
    keep(PUBLIC_VAULT / "link-map.json").write_text(
        json.dumps(link_map, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def run_web_lint(vault: Path) -> int:
    """同步收尾自动质检；返回退出码（非 0 = 有错误，让入库流水线能感知）。"""
    if not WEB_LINT.exists():
        return 0
    result = subprocess.run(
        [sys.executable, str(WEB_LINT), "--vault", str(vault)],
        check=False,
    )
    return result.returncode


def main() -> None:
    global MD2HTML
    import argparse

    parser = argparse.ArgumentParser(description="同步文枢文库到前端")
    parser.add_argument("--vault", default=str(DEFAULT_VAULT), help="文库根目录")
    parser.add_argument("--no-lint", action="store_true", help="跳过 web_lint 质检")
    parser.add_argument("--no-activity", action="store_true", help="示例库不从文件时间生成活动记录")
    parser.add_argument("--md2html", type=Path, help="可选的外部 Markdown 转 HTML 脚本；默认仅同步原 Markdown")
    args = parser.parse_args()
    MD2HTML = args.md2html.resolve() if args.md2html else None
    if MD2HTML is not None and not MD2HTML.is_file():
        parser.error("--md2html 指向的脚本不存在")
    vault = Path(args.vault).expanduser().resolve()
    papers = collect_papers(vault)
    topic_docs = collect_topic_docs(vault)
    write_catalog(papers, topic_docs)
    terms = collect_terms(vault)
    write_terms(terms)
    write_link_map(papers, terms)
    activity = (
        {"generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "days": {}, "papersByDay": {}}
        if args.no_activity else collect_activity(vault, papers)
    )
    write_activity(activity)
    orphans = sweep_orphans()
    if orphans:
        print(f"清理孤儿文件 {orphans} 个（源头已删除）")
    print(f"共同步 {len(papers)} 篇论文、{len(terms)} 条术语、{len(topic_docs)} 篇专题文档 -> {PUBLIC_VAULT}")
    print(f"目录数据 -> {GENERATED_TS}")
    print(f"术语数据 -> {GENERATED_TERMS_TS}")
    print(f"活动数据 -> {GENERATED_ACTIVITY_TS}")
    lint_rc = 0 if args.no_lint else run_web_lint(vault)
    if lint_rc:
        print("web_lint 发现错误（见上方报告），同步已完成但内容需要修复。")
    sys.exit(lint_rc)


if __name__ == "__main__":
    main()
