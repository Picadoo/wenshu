#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
论文图片提取脚本 - 支持从arXiv源码包优先提取
优先级：
1. arXiv源码包中的pics/或figures/目录（真正的论文图片）
2. 源码包中的PDF图片（架构图、实验图等）
3. PDF直接提取的图片（最后备选）
"""

import fitz  # PyMuPDF
import os
import json
import sys
import re
import shutil
import tarfile
import tempfile
import logging
import hashlib
from pathlib import Path

logger = logging.getLogger(__name__)

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    import urllib.request
    HAS_REQUESTS = False
    logger.warning("requests not found, using urllib")


def extract_arxiv_source(arxiv_id, temp_dir):
    """下载并提取arXiv源码包"""
    source_url = f"https://arxiv.org/e-print/{arxiv_id}"
    print(f"正在下载arXiv源码包: {source_url}")

    try:
        if HAS_REQUESTS:
            response = requests.get(source_url, timeout=60)
            content = response.content if response.status_code == 200 else None
            status = response.status_code
        else:
            try:
                req = urllib.request.urlopen(source_url, timeout=60)
                content = req.read()
                status = req.status
            except urllib.error.HTTPError as http_err:
                logger.error("HTTP错误 %d: %s", http_err.code, http_err.reason)
                return False

        if status == 200 and content:
            tar_path = os.path.join(temp_dir, f"{arxiv_id}.tar.gz")
            with open(tar_path, 'wb') as f:
                f.write(content)
            print(f"源码包已下载: {tar_path}")

            with tarfile.open(tar_path, 'r:gz') as tar:
                # 过滤危险路径和符号链接，防止路径遍历攻击
                safe_members = []
                for member in tar.getmembers():
                    if member.name.startswith('/') or '..' in member.name:
                        continue
                    if member.issym() or member.islnk():
                        continue
                    safe_members.append(member)
                tar.extractall(path=temp_dir, members=safe_members)
            print(f"源码已提取到: {temp_dir}")
            return True
        else:
            print(f"下载失败: HTTP {status}")
            return False
    except Exception as e:
        logger.error("下载源码包失败: %s", e)
        return False


def find_figures_from_source(temp_dir):
    """从源码目录中查找图片（搜索所有匹配的目录）"""
    figures = []
    seen_files = set()

    figure_dirs = ['pics', 'figures', 'fig', 'images', 'img']

    for fig_dir in figure_dirs:
        fig_path = os.path.join(temp_dir, fig_dir)
        if os.path.exists(fig_path):
            print(f"找到图片目录: {fig_path}")
            for filename in os.listdir(fig_path):
                file_path = os.path.join(fig_path, filename)
                if os.path.isfile(file_path) and filename not in seen_files:
                    ext = os.path.splitext(filename)[1].lower()
                    if ext in ['.png', '.jpg', '.jpeg', '.pdf', '.eps', '.svg']:
                        seen_files.add(filename)
                        figures.append({
                            'type': 'source',
                            'source': 'arxiv-source',
                            'path': file_path,
                            'filename': filename
                        })

    # 如果没有找到单独的目录，检查根目录的图片文件
    if not figures:
        for filename in os.listdir(temp_dir):
            file_path = os.path.join(temp_dir, filename)
            if os.path.isfile(file_path):
                ext = os.path.splitext(filename)[1].lower()
                if ext in ['.png', '.jpg', '.jpeg'] and 'logo' not in filename.lower() and 'icon' not in filename.lower():
                    figures.append({
                        'type': 'source',
                        'source': 'arxiv-source',
                        'path': file_path,
                        'filename': filename
                    })

    return figures


def extract_pdf_figures(pdf_path, output_dir, prefix='', min_width=200, min_height=200, min_bytes=5000):
    """从PDF中提取图片（备选方案）

    Args:
        pdf_path: PDF文件路径
        output_dir: 输出目录
        prefix: 文件名前缀（如 'Kirkil2009_'），用于避免不同论文图片重名
        min_width: 最小宽度（像素），过滤图标/logo
        min_height: 最小高度（像素），过滤图标/logo
        min_bytes: 最小文件大小（字节），过滤小碎片
    """
    print("从PDF直接提取图片（备选方案）...")

    try:
        pdf_doc = fitz.open(pdf_path)
    except Exception as e:
        logger.error("无法打开PDF文件: %s (%s)", pdf_path, e)
        return []

    image_list = []
    skipped = 0
    seen_xrefs = set()      # 同一张图被多页引用时只提取一次
    seen_hashes = set()     # 内容完全相同的图（页眉logo/水印等）只保留一份

    try:
        for page_num in range(len(pdf_doc)):
            page = pdf_doc[page_num]
            image_list_page = page.get_images(full=True)

            if image_list_page:
                for img_index, img in enumerate(image_list_page):
                    xref = img[0]
                    if xref in seen_xrefs:
                        skipped += 1
                        continue
                    seen_xrefs.add(xref)
                    try:
                        base_image = pdf_doc.extract_image(xref)
                    except Exception as e:
                        logger.warning("  跳过无法提取的图片 (page %d, xref %d): %s", page_num + 1, xref, e)
                        continue

                    if base_image:
                        image_bytes = base_image['image']
                        image_ext = base_image['ext']
                        img_width = base_image.get('width', 0)
                        img_height = base_image.get('height', 0)

                        # 过滤小图标、logo和UI碎片
                        if img_width < min_width or img_height < min_height:
                            skipped += 1
                            continue
                        if len(image_bytes) < min_bytes:
                            skipped += 1
                            continue
                        # 首页刊头做得够大时会漏过尺寸阈值，按版式再拦一道
                        if page_num == 0 and img_height and (
                                img_width / img_height >= 3.5 or img_width / img_height <= 0.35):
                            skipped += 1
                            continue

                        # 去重：内容完全相同的图片只保留一份
                        digest = hashlib.md5(image_bytes).hexdigest()
                        if digest in seen_hashes:
                            skipped += 1
                            continue
                        seen_hashes.add(digest)

                        filename = f'{prefix}page{page_num + 1}_fig{img_index + 1}.{image_ext}'
                        filepath = os.path.join(output_dir, filename)

                        with open(filepath, 'wb') as img_file:
                            img_file.write(image_bytes)

                        image_list.append({
                            'page': page_num + 1,
                            'index': img_index + 1,
                            'filename': filename,
                            'path': f'images/{filename}',
                            'size': len(image_bytes),
                            'width': img_width,
                            'height': img_height,
                            'ext': image_ext
                        })
    finally:
        pdf_doc.close()

    if skipped:
        print(f"  已过滤/去重 {skipped} 张小图片、图标或重复图 (< {min_width}x{min_height}px / < {min_bytes/1024:.0f}KB / 内容重复)")

    return image_list


def extract_from_pdf_figures(figures_pdf, output_dir, prefix=''):
    """从PDF格式图片文件中提取图片"""
    print(f"从PDF图片文件提取: {os.path.basename(figures_pdf)}")

    extracted = []
    doc = fitz.open(figures_pdf)
    filename = os.path.splitext(os.path.basename(figures_pdf))[0]

    try:
        for i in range(len(doc)):
            page = doc[i]
            pix = page.get_pixmap(dpi=150)
            output_name = f'{prefix}{filename}_page{i+1}.png'
            output_path = os.path.join(output_dir, output_name)
            pix.save(output_path)

            extracted.append({
                'filename': output_name,
                'path': f'images/{output_name}',
                'size': os.path.getsize(output_path),  # 使用实际文件大小
                'ext': 'png'
            })
    finally:
        doc.close()

    return extracted


def _match_caption(rect, caption_boxes, page, max_gap=80):
    """为图片区域配对最近的图注（优先正下方、x 方向有重叠的 caption）"""
    best, best_gap = None, 1e9
    for cb in caption_boxes:
        cr = fitz.Rect(cb["bbox"])
        if min(rect.x1, cr.x1) - max(rect.x0, cr.x0) <= 0:
            continue  # x 方向无重叠，多半不是这张图的图注
        if cr.y0 >= rect.y1:            # 图注在图下方（最常见）
            gap = cr.y0 - rect.y1
        elif cr.y1 <= rect.y0:          # 图注在图上方，加罚分以优先下方
            gap = (rect.y0 - cr.y1) + 60
        else:
            gap = 0                     # 与图区重叠
        if gap < best_gap:
            best_gap, best = gap, cr
    if best is None or best_gap > max_gap:
        return ''
    txt = page.get_text("text", clip=best).strip()
    return ' '.join(txt.split())


_MARKS_CACHE = None


def _load_publisher_marks():
    """已确认的出版社商标 dHash 名单，见 assets/publisher_marks.json。"""
    global _MARKS_CACHE
    if _MARKS_CACHE is None:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            '..', 'assets', 'publisher_marks.json')
        try:
            with open(path, encoding='utf-8') as f:
                _MARKS_CACHE = [int(m['hash'], 16) for m in json.load(f)['marks']]
        except Exception:
            _MARKS_CACHE = []
    return _MARKS_CACHE


def _dhash(path, size=8):
    """差值哈希；对缩放和重编码稳定，能认出同一枚商标的不同渲染尺寸。"""
    try:
        from PIL import Image
    except ImportError:
        return None
    img = Image.open(path).convert('L').resize((size + 1, size), Image.LANCZOS)
    px = list(img.getdata())
    bits = 0
    for r in range(size):
        row = px[r * (size + 1):(r + 1) * (size + 1)]
        for c in range(size):
            bits = (bits << 1) | (row[c] < row[c + 1])
    return bits


def is_publisher_mark(path, width, height, page_num):
    """首页刊头 / 出版社徽标 / CrossMark 徽章 / 订阅广告，一律不入库。

    只在首页判定：正文页里同样细长的图往往是真的流程图或色标条。
    图文摘要也常出现在首页且没有图注，所以先用几何粗筛，再用指纹兜底，
    两者都不命中就放行——宁可多留一张，也不能吞掉图文摘要。
    """
    if page_num != 1:
        return None
    ratio = width / height if height else 0
    if ratio >= 3.5:
        return f'刊头横幅 {width}×{height}'
    if ratio and ratio <= 0.35:
        return f'侧边竖条 {width}×{height}'
    if width <= 260 and height <= 260:
        return f'出版社徽标 {width}×{height}'
    marks = _load_publisher_marks()
    if marks:
        h = _dhash(path)
        if h is not None and any(bin(h ^ m).count('1') <= 6 for m in marks):
            return f'命中商标指纹 {width}×{height}'
    return None


def extract_with_layout(pdf_path, output_dir, prefix='', dpi=200,
                        name_tag='fig', skip_nums=None, skip_rects=None):
    """版面级图片提取：用 pymupdf4llm 识别 picture 区域，再用 PyMuPDF 把整块区域
    渲染成一张图（矢量+位图一起合成），复合图不会被拆成碎片，并配对图注。
    未安装 pymupdf4llm 或解析失败时返回 []，由上层回退到基础位图提取。
    name_tag/skip_nums/skip_rects：在图注裁切之后补跑时用，改用 pic 前缀命名，
    并跳过已按图号裁出的图、以及落在已裁区域里的重复图区，只留下真正没图注的。"""
    try:
        import pymupdf4llm
    except ImportError:
        logger.info("pymupdf4llm 未安装，跳过版面级提取（建议 pip install pymupdf4llm 启用第一道防线）")
        return []

    try:
        chunks = pymupdf4llm.to_markdown(pdf_path, page_chunks=True, write_images=False)
    except Exception as e:
        logger.warning("pymupdf4llm 版面解析失败，回退基础提取：%s", e)
        return []

    try:
        doc = fitz.open(pdf_path)
    except Exception as e:
        logger.error("无法打开PDF文件: %s (%s)", pdf_path, e)
        return []

    figures = []
    try:
        for pidx, chunk in enumerate(chunks):
            if pidx >= len(doc):
                break
            page = doc[pidx]
            boxes = chunk.get("page_boxes") or []
            pics = [b for b in boxes if b.get("class") == "picture"]
            caps = [b for b in boxes if b.get("class") == "caption"]
            fig_no = 0
            for rect, caption in _merge_layout_pictures(page, pics, caps):
                if skip_nums and _caption_match(caption or '') in skip_nums:
                    continue          # 该图号已由图注裁切整幅裁出，别再塞碎片
                if _covered_by(rect, (skip_rects or {}).get(pidx + 1)):
                    continue          # 落在已裁图区内的重复图块
                fig_no += 1
                try:
                    pix = page.get_pixmap(clip=rect, dpi=dpi)
                except Exception as e:
                    logger.warning("  渲染图区失败 (page %d): %s", pidx + 1, e)
                    continue
                fname = f'{prefix}page{pidx + 1}_{name_tag}{fig_no}.png'
                fpath = os.path.join(output_dir, fname)
                pix.save(fpath)
                mark = is_publisher_mark(fpath, pix.width, pix.height, pidx + 1)
                if mark:
                    os.remove(fpath)
                    fig_no -= 1
                    print(f"  跳过首页{mark}")
                    continue
                fig = {
                    'page': pidx + 1,
                    'index': fig_no,
                    'filename': fname,
                    'path': f'images/{fname}',
                    'size': os.path.getsize(fpath),
                    'ext': 'png',
                    'source': 'layout-render',
                    'caption': caption,
                }
                fig['flags'] = _grade_figure(fig, _ink_ratio(fpath), None)
                figures.append(fig)
    finally:
        doc.close()

    return figures


def _merge_layout_pictures(page, pics, caps):
    """同一页、同一图注的 picture 框合成一个裁切框。

    pymupdf4llm 常把复合图拆成面板（Example2024 点云篇 Fig. 2 被拆成 6 块、
    Fig. 9 被拆成 12 块）。有图注的面板按图号合并；没配上图注的仍各自保留。
    """
    keyed, rest = {}, []
    for pb in pics:
        rect = fitz.Rect(pb["bbox"])
        if rect.width < 60 or rect.height < 60:
            continue
        rect = _grow_figure_rect(page, rect)
        caption = _match_caption(rect, caps, page)
        cid = _caption_id(caption or '')
        if cid is None:
            rest.append((rect, caption))
            continue
        if cid not in keyed:
            keyed[cid] = [rect, caption]
        else:
            keyed[cid][0] = keyed[cid][0] | rect
            if caption and not keyed[cid][1]:
                keyed[cid][1] = caption
    merged = [(r, c) for r, c in keyed.values()] + rest
    merged.sort(key=lambda item: (item[0].y0, item[0].x0))
    return merged


def _ink_ratio(path):
    """裁切图里非白像素的占比；读不出来返回 None。
    近乎全白说明裁错了位置（空白带、页边），是人眼一眼能看出、脚本以前看不出的毛病。"""
    try:
        from PIL import Image
        img = Image.open(path).convert('L')
    except Exception:
        return None
    w, h = img.size
    if w * h == 0:
        return None
    if w * h > 400_000:                      # 采样即可，别为质检拖慢抽图
        img = img.resize((w // 2 or 1, h // 2 or 1))
    hist = img.histogram()
    return sum(hist[:245]) / float(sum(hist) or 1)


def _grade_figure(fig, ink_ratio, has_graphic):
    """给一张裁切图打质检标记；无异常返回空列表。"""
    flags = []
    if ink_ratio is not None and ink_ratio < 0.004:
        flags.append('近乎空白')
    if has_graphic is False:
        flags.append('区内无图形墨迹（疑似正文误裁/图注是正文里的交叉引用）')
    if fig.get('source') == 'page-fallback':
        flags.append('整页兜底（含正文，建议人工裁切后替换）')
    return flags


def _ink_top(page, x0, x1, top, bottom):
    """给定裁切区间内，矢量图元与位图的最高点；区间内没有任何图形时返回 None。"""
    band = fitz.Rect(x0, top, x1, bottom)
    best = None
    try:
        items = [fitz.Rect(d['rect']) for d in page.get_drawings()]
        items += [fitz.Rect(i['bbox']) for i in page.get_image_info()]
    except Exception:
        return None
    for r in items:
        if r.width < 1 and r.height < 1:
            continue
        inter = r & band
        if inter.is_empty or inter.get_area() < 0.3 * r.get_area():
            continue
        best = inter.y0 if best is None else min(best, inter.y0)
    return best


def _covered_by(rect, boxes, ratio=0.6):
    """rect 是否已有 ratio 以上的面积落在 boxes 里的某一块内。"""
    area = rect.get_area()
    if not boxes or area <= 0:
        return False
    for box in boxes:
        inter = rect & fitz.Rect(box)
        if inter.get_area() >= ratio * area:
            return True
    return False


def _grow_figure_rect(page, rect, pad=3.0):
    """把图例、轴标题这类「图区自己的东西」并回裁切框。

    版面模型给的 picture 框常常偏紧：期刊图的图例多是矢量描出来的（不是文本
    块），框顶正好从图例中间穿过，渲染出来就是「图顶连同图例被切掉」。这里以
    图注、页眉页脚、通栏正文作硬边界，在边界内把横向落在图区、纵向紧贴或相交
    的矢量图元与短文本块并进来，越界的一概不碰，避免把邻图或正文吞进去。
    """
    try:
        blocks_raw = page.get_text('dict').get('blocks', [])
    except Exception:
        return rect

    page_w = page.rect.width
    cands, hard_top, hard_bottom = [], page.rect.y0, page.rect.y1
    for b in blocks_raw:
        if b.get('type') != 0:
            continue
        text = _block_text(b)
        if not text:
            continue
        r = fitz.Rect(b['bbox'])
        compact = ' '.join(text.split())
        blocking = (_is_header_footer(r, page, text)
                    or CAPTION_RE.match(compact) or BODY_CAPTION.match(compact)
                    or (r.width >= 0.62 * page_w and len(compact) >= 90)
                    or r.height > 72)
        if not blocking:
            cands.append(r)
            continue
        if min(r.x1, rect.x1) - max(r.x0, rect.x0) <= 0:
            continue                       # 横向不相干的块不构成边界
        if r.y1 <= rect.y0:
            hard_top = max(hard_top, r.y1)
        elif r.y0 >= rect.y1:
            hard_bottom = min(hard_bottom, r.y0)

    try:
        for d in page.get_drawings():
            r = fitz.Rect(d['rect'])
            if r.width >= 1 and r.height >= 1 and not (
                    r.width > 0.95 * page_w and r.height > 0.95 * page.rect.height):
                cands.append(r)             # 图例边框、坐标轴这类矢量图元
        for info in page.get_image_info():
            cands.append(fitz.Rect(info['bbox']))
    except Exception:
        pass

    grown = fitz.Rect(rect)
    up_limit = max(hard_top, rect.y0 - max(40.0, rect.height * 0.35))
    down_limit = min(hard_bottom, rect.y1 + max(24.0, rect.height * 0.20))
    for _ in range(4):                     # 多层图例/图元逐轮吸附
        changed = False
        for r in cands:
            if r.y0 < up_limit or r.y1 > down_limit:
                continue                   # 越过硬边界，不碰
            if min(r.x1, grown.x1) - max(r.x0, grown.x0) < 0.5 * r.width:
                continue                   # 横向不落在图区内
            gap_up, gap_down = grown.y0 - r.y1, r.y0 - grown.y1
            crossing = r.y0 < grown.y1 and r.y1 > grown.y0
            if not (crossing or 0 <= gap_up <= 20 or 0 <= gap_down <= 12):
                continue
            merged = grown | r
            if merged != grown:
                grown = merged
                changed = True
        if not changed:
            break
    grown.y0 = max(grown.y0 - pad, up_limit)
    grown.y1 = min(grown.y1 + pad, down_limit)
    return grown & page.rect


# Fig. 12 / Figure 12 / 图 12 / 表 1 / Fig. A.21 / 图 A.22
CAPTION_RE = re.compile(
    r'(?P<label>Fig(?:ure)?\.?|表|图)\s*(?:(?P<app>[A-Za-z])\s*\.\s*)?(?P<num>\d+)',
    re.I,
)
# 老扫描件 OCR 常把 Fig. 1/2/3 认成罗马字母（Fig. I. / Fig. II. / Fig. lll.）
CAPTION_ROMAN_RE = re.compile(r'(?:Fig(?:ure)?\.?)\s*([IVXl]{1,6})\s*[.:：]', re.I)
_ROMAN = {'i': 1, 'v': 5, 'x': 10}


def _roman_to_int(s):
    """OCR 容错：l 视作 i（Fig. ll. = Fig. II.）。非法组合返回 None。"""
    s = s.lower().replace('l', 'i')
    total, prev = 0, 0
    for ch in reversed(s):
        val = _ROMAN.get(ch)
        if val is None:
            return None
        total += val if val >= prev else -val
        prev = max(prev, val)
    return total if 0 < total <= 99 else None
BODY_CAPTION = re.compile(
    r'^\s*(?:Fig(?:ure)?\.?|图)\s*\d+[a-z]?\s+'
    r'(?:and\s+[a-z]\s+)?(?:shows?|illustrates?|presents?|depicts?|discusses?|显示|给出|表明)\b',
    re.I,
)
CAPTION_PREFIX_RE = re.compile(r'^(?:\(\s*[a-z]\s*\)\s*)+$', re.I)


def _block_text(block):
    return ''.join(
        span.get('text', '')
        for line in block.get('lines', [])
        for span in line.get('spans', [])
    ).strip()


def _caption_rest_ok(rest):
    """图注在图号之后应接句点/冒号/大写说明；'Fig. 12a plots…'、'Fig. 19(a-f) illustrates…' 是正文。"""
    rest = rest.strip()
    if not rest:
        return True
    rest = re.sub(
        r'^(\(\s*[a-z](?:\s*[-–—]\s*[a-z])?\s*\)\s*)+',
        '', rest, flags=re.I,
    ).strip()
    if not rest:
        return True
    ch = rest[0]
    if ch in '.。:：—–-':
        return True
    if '\u4e00' <= ch <= '\u9fff' or ch.isupper():
        return True
    return False


def _caption_id(text):
    """图注文本 → (附录字母或 '', 图号)；正文交叉引用返回 None。
    'In Fig. 12b, we…' / 'Fig. 12a plots…' 不是图注；'Fig. A.21. …' 是附录图。"""
    if not text or BODY_CAPTION.match(text):
        return None
    match = CAPTION_RE.search(text)
    if not match:
        m = CAPTION_ROMAN_RE.search(text)
        if m and m.start() <= 8:
            num = _roman_to_int(m.group(1))
            return ('', num) if num else None
        return None
    prefix = text[:match.start()].strip()
    if prefix and not CAPTION_PREFIX_RE.match(prefix):
        return None
    if not _caption_rest_ok(text[match.end():]):
        return None
    num = int(match.group('num'))
    if num > 99:
        return None
    app = (match.group('app') or '').upper()
    label = match.group('label')
    if label and label.startswith('表'):
        return ('表', num)
    return (app, num)


def _caption_match(text):
    """正文里的 'Figure 5 shows…' 不是图注；(a)(b) 与 Figure N 粘在同一块时仍算图注。
    图号 >99 视为误匹配（如「图 2020」实为年份），论文不会有上百张图。
    附录图 Fig. A.21 也返回 21，调用方若需区分附录应改用 _caption_id。"""
    cid = _caption_id(text)
    if cid is None or cid[0] == '表':
        return None
    return cid[1]


def _fig_tag(appendix, num):
    """文件名用的图号片段：12 → '12'；附录 A.21 → 'A21'。"""
    app = '' if not appendix or appendix == '表' else appendix
    return f'{app}{num}' if app else str(num)


def _is_header_footer(rect, page, text):
    if rect.y1 < page.rect.y0 + 70:
        return True
    if rect.y0 > page.rect.y1 - 68:
        return True
    stripped = text.strip()
    if re.match(r'^\d{2,5}$', stripped):
        return True
    if stripped.lower().startswith(('j. mt.', 'doi', 'http')):
        return True
    return False


def _is_stopper_text(text, rect, cap, x0=None, x1=None):
    """判断图注上方的某个文本块是不是「图区的上边界」。

    图内的图例（legend）也是文本块，字数常常轻松过百，早先只按字数判断，
    于是把上沿压到图例下方——图顶连同图例一起被切掉。正文是通栏排的、左边缘
    与栏左对齐，图例则多为居中或内缩，据此把两者分开。
    """
    if rect.y1 > cap.y0 - 2:
        return False
    compact = ' '.join(text.split())
    if compact.lower().startswith(('figure', 'fig.', 'table', '表', '图')):
        return True          # 上一张图的图注，无论宽窄都是硬边界
    if x0 is not None and x1 is not None:
        pad = 0.06 * (x1 - x0)
        if rect.x0 > x0 + pad and rect.x1 < x1 - pad:
            return False     # 两侧都内缩＝居中的图例/轴标题，不是正文边界
    if len(compact) >= 80:
        return True
    if rect.height > 48 and len(compact) >= 40:
        return True
    return False


def _iter_graphics(page):
    """页面上足够大的位图/矢量框，排除整页边框和小图标。"""
    page_w, page_h = page.rect.width, page.rect.height
    try:
        items = [fitz.Rect(info['bbox']) for info in page.get_image_info()]
        items += [fitz.Rect(d['rect']) for d in page.get_drawings()]
    except Exception:
        return []
    out = []
    for r in items:
        if r.width < 40 or r.height < 40:
            continue
        if r.width > 0.95 * page_w and r.height > 0.95 * page_h:
            continue
        out.append(r)
    return out


def _graphic_above_caption(page, cap, cut_y):
    """图注正上方、且与图注有横向重叠的那一块图。并排两栏图不会抢对方的图注。"""
    best, best_key = None, None
    for r in _iter_graphics(page):
        if r.y0 > cut_y - 2:
            continue
        if r.y1 < cut_y - 240:
            continue
        overlap = min(r.x1, cap.x1) - max(r.x0, cap.x0)
        if overlap <= 8:
            continue
        gap = cut_y - r.y1
        if gap < -8:
            continue
        key = (gap if gap >= 0 else 1e6, -r.get_area())
        if best_key is None or key < best_key:
            best_key, best = key, r
    return best


def _column_bounds(page, cap, cut_y=None):
    mid = page.rect.x0 + page.rect.width / 2
    left = page.rect.x0 + 50
    right = page.rect.x1 - 50
    if cap.width >= page.rect.width * 0.52:
        return 'full', left, right
    # 跨栏图的居中图注可能比半页还窄，但一定跨过版心中线；单栏图注不会。
    if cap.x0 < mid - 12 and cap.x1 > mid + 12:
        return 'full', left, right
    if cap.x0 < mid - 10:
        col, x0, x1 = 'left', left, mid - 6
    else:
        col, x0, x1 = 'right', mid + 6, right
    cap_y = cut_y if cut_y is not None else cap.y0
    graphic = _graphic_above_caption(page, cap, cap_y)
    # Frontiers 一类：图注左对齐挤在左栏，图本身居中跨栏。跟图走，不跟图注走。
    if graphic is not None and graphic.x0 < mid - 20 and graphic.x1 > mid + 20:
        return 'full', left, right
    return col, x0, x1


def _in_column(rect, col, page):
    if col == 'full':
        return True
    mid = page.rect.x0 + page.rect.width / 2
    if col == 'left':
        return rect.x0 < mid - 10
    return rect.x1 > mid + 10


def _figure_line_cut(block, num, appendix=''):
    """图注块常把 (a)(b)、坐标轴标题和 'Figure N …' 粘在同一 block。
    裁切下沿必须用 Figure/Fig/表/图 那一行的 y0，不能用整块 y0，否则会切掉 xlabel。"""
    appendix = (appendix or '').upper()
    for line in block.get('lines') or []:
        text = ''.join(span.get('text', '') for span in line.get('spans') or [])
        cid = _caption_id(text)
        if cid is None:
            continue
        app, n = ('' if cid[0] == '表' else cid[0]), cid[1]
        if n != num or app != appendix:
            continue
        if BODY_CAPTION.match(text.strip()):
            continue
        return fitz.Rect(line['bbox']).y0, ' '.join(text.split())
    return None, None


def extract_by_captions(pdf_path, output_dir, prefix='', dpi=160, only_nums=None, existing_names=None):
    """不依赖 pymupdf4llm：按页内 Figure/Fig/表/图 N 图注，在同一栏裁切其上方空隙。
    期刊矢量图、曲线、示意图用 get_images 几乎全漏，这条回退才能进文枢正文。
    必须按栏裁，禁止把双栏正文一起切进来。
    only_nums：只裁指定图号（版面级漏图的补漏模式）；existing_names：撞名时改挂 _clip 后缀。"""
    try:
        doc = fitz.open(pdf_path)
    except Exception as e:
        logger.error("无法打开PDF文件: %s (%s)", pdf_path, e)
        return []

    figures = []
    seen = set()
    expected = set()
    try:
        for pidx, page in enumerate(doc):
            raw_blocks = page.get_text('dict').get('blocks') or []
            text_blocks = []
            captions = []
            for block in raw_blocks:
                if block.get('type') != 0:
                    continue
                text = _block_text(block)
                if not text:
                    continue
                rect = fitz.Rect(block['bbox'])
                text_blocks.append((rect, text))
                cid = _caption_id(text)
                if cid is None:
                    continue
                appendix = '' if cid[0] == '表' else cid[0]
                num = cid[1]
                cut_y, line_text = _figure_line_cut(block, num, appendix=appendix)
                captions.append({
                    'num': num,
                    'appendix': appendix,
                    'rect': rect,
                    'cut_y': cut_y if cut_y is not None else rect.y0,
                    'text': (line_text or text)[:220],
                })
                expected.add((appendix, num))
            captions.sort(key=lambda item: (item['cut_y'], item['rect'].x0))
            for cap in captions:
                num = cap['num']
                appendix = cap.get('appendix') or ''
                if only_nums is not None and num not in only_nums:
                    continue
                key = (pidx + 1, appendix, num)
                if key in seen:
                    continue
                seen.add(key)
                col, x0, x1 = _column_bounds(page, cap['rect'], cap['cut_y'])
                # 上沿地板取「页眉下缘」而非固定 72pt：版心从 55pt 起的期刊里，
                # 一英寸地板会把图顶（往往正是图例）整条切掉。
                stop_y = page.rect.y0 + 30
                for rect, block_text in text_blocks:
                    if rect.y1 < page.rect.y0 + page.rect.height * 0.2 \
                            and _is_header_footer(rect, page, block_text):
                        stop_y = max(stop_y, rect.y1)
                for rect, block_text in text_blocks:
                    if _is_header_footer(rect, page, block_text):
                        continue
                    if not _in_column(rect, col, page):
                        continue
                    if abs(rect.y0 - cap['rect'].y0) < 1.5 and abs(rect.x0 - cap['rect'].x0) < 1.5:
                        continue
                    if _is_stopper_text(block_text, rect, cap['rect'], x0, x1):
                        stop_y = max(stop_y, rect.y1)
                bottom = cap['cut_y'] - 2
                top = min(stop_y + 4, bottom - 24)
                # 收紧上沿到图区真正的墨迹起点：正文与图之间常隔着一两行短句，
                # 短句字数够不上「正文块」阈值，靠它挡不住，只能按墨迹定位。
                ink = _ink_top(page, x0, x1, top, bottom)
                if ink is not None:
                    top = min(max(top, ink - 6), bottom - 24)
                clip = fitz.Rect(x0, top, x1, bottom)
                if clip.height < 64 or clip.width < 72:
                    logger.warning("  跳过过矮图区 page %d fig %d (h=%.1f)", pidx + 1, num, clip.height)
                    continue
                try:
                    pix = page.get_pixmap(clip=clip, dpi=dpi)
                except Exception as exc:
                    logger.warning("  图注裁切失败 page %d fig %d: %s", pidx + 1, num, exc)
                    continue
                tag = _fig_tag(appendix, num)
                fname = f'{prefix}page{pidx + 1}_fig{tag}.png'
                if existing_names and fname in existing_names:
                    fname = f'{prefix}page{pidx + 1}_fig{tag}_clip.png'
                fpath = os.path.join(output_dir, fname)
                pix.save(fpath)
                fig = {
                    'page': pidx + 1,
                    'index': num,
                    'appendix': appendix,
                    'filename': fname,
                    'path': f'images/{fname}',
                    'size': os.path.getsize(fpath),
                    'ext': 'png',
                    'source': 'caption-clip',
                    'caption': cap['text'],
                    'clip': (clip.x0, clip.y0, clip.x1, clip.y1),
                }
                fig['flags'] = _grade_figure(fig, _ink_ratio(fpath), ink is not None)
                figures.append(fig)
    finally:
        doc.close()

    got = {(fig.get('appendix') or '', fig['index']) for fig in figures}
    if expected and only_nums is None:
        missing = sorted(k for k in expected if k not in got)
        nums = [n for _, n in expected]
        miss_lbl = [f"{a or ''}{n}" for a, n in missing[:15]]
        print(
            f"  图注覆盖：识别 Figure {min(nums)}–{max(nums)}，"
            f"抽出 {len(figures)} 张"
            + (f"，未裁出：{miss_lbl}" if missing else "，识别号全裁出")
        )
    return figures


def scan_captions(pdf_path):
    """全 PDF 扫描图注行（与抽取路径无关的「期望集」）：[{kind,num,page,text}]。
    kind='表' 或 '图'（英文 Figure/Fig 归入 '图'；英文 Table 不裁、不进期望集）。
    同一 (kind,num) 只记首次出现页。"""
    try:
        doc = fitz.open(pdf_path)
    except Exception:
        return []
    out, seen = [], set()
    try:
        for pidx, page in enumerate(doc):
            for block in page.get_text('dict').get('blocks') or []:
                if block.get('type') != 0:
                    continue
                text = _block_text(block)
                cid = _caption_id(text)
                if cid is None:
                    continue
                if cid[0] == '表':
                    kind, appendix, num = '表', '', cid[1]
                else:
                    kind, appendix, num = '图', cid[0], cid[1]
                if (kind, appendix, num) in seen:
                    continue
                seen.add((kind, appendix, num))
                out.append({'kind': kind, 'num': num, 'appendix': appendix,
                            'page': pidx + 1,
                            'text': ' '.join(text.split())[:220]})
    finally:
        doc.close()
    return out


def coverage_check(captions, figures):
    """对照期望集与实际抽出的图，返回缺失的 caption 列表。
    caption-clip 的 index 即全局图号；layout-render 的图号从配对图注文本解析。
    任一图能给出图号即按图号精确对照（双图页漏一张也能查出来），
    全都给不出时才退化为「该页或邻页有没有抽出图」。"""
    fig_pages = {f.get('page') for f in figures if f.get('page')}
    fig_nums = set()
    for f in figures:
        if f.get('source') == 'caption-clip' and f.get('index') is not None:
            fig_nums.add((f.get('appendix') or '', f['index']))
        cid = _caption_id(f.get('caption') or '')
        if cid is not None and cid[0] != '表':
            fig_nums.add((cid[0], cid[1]))
    precise = bool(fig_nums)
    missing = []
    for cap in captions:
        if precise:
            ok = (cap.get('appendix') or '', cap['num']) in fig_nums
        else:
            ok = any(p in fig_pages for p in (cap['page'] - 1, cap['page'], cap['page'] + 1))
        if not ok:
            missing.append(cap)
    return missing


def rescue_missing(pdf_path, output_dir, prefix, missing, existing_names, dpi=160):
    """缺号兜底：先用图注裁切按图号补漏（裁出的是真图区）；
    仍裁不出的才把图注所在整页渲染成 PNG（宁可含正文，也绝不静默漏图）。
    整页产物标 source='page-fallback'，索引里会提示建议人工裁切。"""
    if not missing:
        return []
    rescued = list(extract_by_captions(
        pdf_path, output_dir, prefix=prefix,
        only_nums={c['num'] for c in missing}, existing_names=existing_names))
    if rescued:
        print(f"  裁切补漏：{len(rescued)} 张（图号 "
              + '、'.join(_fig_tag(f.get('appendix') or '', f['index']) for f in rescued) + "）")
    clipped_ids = {(f.get('appendix') or '', f['index']) for f in rescued}
    missing = [c for c in missing
               if (c.get('appendix') or '', c['num']) not in clipped_ids]
    if not missing:
        return rescued
    try:
        doc = fitz.open(pdf_path)
    except Exception:
        return rescued
    try:
        for cap in missing:
            page = doc[cap['page'] - 1]
            tag = _fig_tag(cap.get('appendix') or '', cap['num'])
            fname = f"{prefix}page{cap['page']}_fig{tag}.png"
            if fname in existing_names:
                fname = f"{prefix}page{cap['page']}_fig{tag}_full.png"
            fpath = os.path.join(output_dir, fname)
            try:
                page.get_pixmap(dpi=dpi).save(fpath)
            except Exception as exc:
                logger.warning("  整页兜底渲染失败 page %d: %s", cap['page'], exc)
                continue
            rescued.append({
                'page': cap['page'],
                'index': cap['num'],
                'appendix': cap.get('appendix') or '',
                'filename': fname,
                'path': f'images/{fname}',
                'size': os.path.getsize(fpath),
                'ext': 'png',
                'source': 'page-fallback',
                'caption': cap['text'],
            })
    finally:
        doc.close()
    return rescued


def _clear_prefix_images(output_dir, prefix):
    """重抽时清掉同前缀旧 png/jpeg，避免文枢图片页混进上次 get_images 碎片。"""
    if not prefix or not os.path.isdir(output_dir):
        return
    for name in os.listdir(output_dir):
        if not name.startswith(prefix):
            continue
        ext = os.path.splitext(name)[1].lower()
        if ext not in {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.tif', '.tiff'}:
            continue
        try:
            os.remove(os.path.join(output_dir, name))
        except OSError:
            pass


def extract_local_pdf_figures(pdf_path, output_dir, prefix='', no_layout=False,
                              prefer_layout=False):
    """本地 PDF 图片提取，最后对照全 PDF 图注扫描做覆盖检查，缺号一律整页渲染兜底
    —— 结构上保证不漏图。返回 (figures, coverage)。

    期刊 PDF 只要图注可解析，就以「图注锚定裁切」为主：它按图号命名、把跨栏复合图
    连同图例整幅裁下来；版面模型只用来补那些没有图注的图区（它常把复合图拆成面板，
    碎片一旦占住图号，正文就会挂上半幅图）。图注少于 3 条的文档（报告、幻灯）仍走
    版面级优先。prefer_layout 强制旧顺序；no_layout 完全跳过版面级。
    """
    _clear_prefix_images(output_dir, prefix)
    captions = scan_captions(pdf_path)
    caption_first = bool(captions) and len(captions) >= 3 and not prefer_layout

    figs = []
    if not no_layout and not caption_first:
        figs = extract_with_layout(pdf_path, output_dir, prefix=prefix)
        if figs:
            print(f"  版面级提取：{len(figs)} 个完整图区（含图注配对）")
    if not figs:
        print("  按图注裁切页面区域" if caption_first else "  回退：按图注裁切页面区域")
        figs = extract_by_captions(pdf_path, output_dir, prefix=prefix)
        if figs:
            print(f"  图注裁切：{len(figs)} 张")
        if figs and caption_first and not no_layout:
            clipped = {}
            for f in figs:
                if f.get('clip'):
                    clipped.setdefault(f['page'], []).append(f['clip'])
            extra = extract_with_layout(pdf_path, output_dir, prefix=prefix,
                                        name_tag='pic',
                                        skip_nums={f['index'] for f in figs
                                                   if not f.get('appendix')},
                                        skip_rects=clipped)
            if extra:
                print(f"  版面级补充无图注图区：{len(extra)} 张")
                figs.extend(extra)
    if not figs:
        print("  回退：基础位图提取 (get_images)")
        figs = extract_pdf_figures(pdf_path, output_dir, prefix=prefix)
        for f in figs:
            f.setdefault('source', 'pdf-extraction')

    missing = coverage_check(captions, figs)
    rescued = rescue_missing(pdf_path, output_dir, prefix, missing,
                             {f['filename'] for f in figs})
    figs.extend(rescued)
    still_missing = [c for c in missing
                     if not any(
                         r['index'] == c['num']
                         and r['page'] == c['page']
                         and (r.get('appendix') or '') == (c.get('appendix') or '')
                         for r in rescued)]
    coverage = {
        'captions': captions,
        'missingBefore': missing,
        'fallback': rescued,
        'stillMissing': still_missing,
    }
    if captions:
        label = lambda c: f"{c['kind']}{_fig_tag(c.get('appendix') or '', c['num'])}(p{c['page']})"
        pagefall = [r for r in rescued if r.get('source') == 'page-fallback']
        clipfall = [r for r in rescued if r.get('source') != 'page-fallback']
        print(f"  覆盖检查：图注 {len(captions)} 处"
              + (f"；裁切补漏 {len(clipfall)} 张" if clipfall else '')
              + (f"；整页兜底 {len(pagefall)} 张：" + '、'.join(r['filename'] for r in pagefall) if pagefall else '')
              + (f"；仍缺失：" + '、'.join(label(c) for c in still_missing) if still_missing else '；无缺失'))
    return figs, coverage


def main():
    # Windows UTF-8 兼容
    if sys.platform == 'win32':
        import io
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(message)s',
        datefmt='%H:%M:%S',
        stream=sys.stderr,
    )

    if len(sys.argv) < 4:
        print("Usage: python extract_images.py <paper_id> <output_dir> <index_file> [--prefix PREFIX]")
        print("  paper_id: arXiv ID (如: 2510.24701) 或本地PDF路径")
        print("  output_dir: 输出目录")
        print("  index_file: 索引文件路径")
        print("  --prefix: 图片文件名前缀（如 Kirkil2009_），避免不同论文图片重名")
        print("  --prefer-layout: 回到版面级优先（默认图注可解析时以图注裁切为主）")
        print("  --no-layout: 完全跳过版面级，只走图注裁切")
        sys.exit(1)

    paper_input = sys.argv[1]
    output_dir = sys.argv[2]
    index_file = sys.argv[3]

    # 解析 --prefix / --no-layout 参数
    prefix = ''
    no_layout = '--no-layout' in sys.argv
    prefer_layout = '--prefer-layout' in sys.argv
    for i, arg in enumerate(sys.argv):
        if arg == '--prefix' and i + 1 < len(sys.argv):
            prefix = sys.argv[i + 1]
            if not prefix.endswith('_'):
                prefix += '_'
            break

    os.makedirs(output_dir, exist_ok=True)

    is_pdf_file = os.path.isfile(paper_input)
    arxiv_id = None
    pdf_path = None

    if is_pdf_file:
        pdf_path = paper_input
        filename = os.path.basename(pdf_path)
        match = re.search(r'(\d{4}\.\d+)', filename)
        if match:
            arxiv_id = match.group(1)
            print(f"检测到arXiv ID: {arxiv_id}")
    else:
        arxiv_id = paper_input

    with tempfile.TemporaryDirectory() as temp_dir:
        all_figures = []

        # 步骤1: 尝试从arXiv源码包提取
        if arxiv_id:
            if extract_arxiv_source(arxiv_id, temp_dir):
                source_figures = find_figures_from_source(temp_dir)
                if source_figures:
                    print(f"\n从arXiv源码找到 {len(source_figures)} 个图片文件")
                    for fig in source_figures:
                        # 加前缀避免重名
                        prefixed_name = f'{prefix}{fig["filename"]}' if prefix else fig['filename']
                        output_file = os.path.join(output_dir, prefixed_name)
                        shutil.copy2(fig['path'], output_file)

                        all_figures.append({
                            'filename': prefixed_name,
                            'path': f'images/{prefixed_name}',
                            'size': os.path.getsize(output_file),
                            'ext': os.path.splitext(fig['filename'])[1][1:].lower(),
                            'source': fig['source']
                        })
                        print(f"  - {prefixed_name}")

        # 步骤2: 源码包图片不足时，从本地 PDF 提取（优先版面级区域渲染，回退基础位图）
        coverage = None
        if len(all_figures) < 3 and pdf_path:
            print(f"\n源码图片不足，改用本地 PDF 提取...")
            pdf_figures, coverage = extract_local_pdf_figures(
                pdf_path, output_dir, prefix=prefix, no_layout=no_layout,
                prefer_layout=prefer_layout)
            for fig in pdf_figures:
                all_figures.append(fig)

        # 步骤3: 检查源码包中的PDF图片文件并提取
        if arxiv_id and os.path.exists(temp_dir):
            for root, dirs, files in os.walk(temp_dir):
                for file in files:
                    if file.endswith('.pdf') and 'logo' not in file.lower() and file != f'{arxiv_id}.tar.gz':
                        pdf_fig_path = os.path.join(root, file)
                        try:
                            extracted = extract_from_pdf_figures(pdf_fig_path, output_dir, prefix=prefix)
                            for fig in extracted:
                                fig['source'] = 'pdf-figure'
                                all_figures.append(fig)
                        except Exception as e:
                            logger.warning("  跳过无法处理的PDF: %s (%s)", file, e)

    # 生成索引文件
    with open(index_file, 'w', encoding='utf-8') as f:
        f.write('# 图片索引\n\n')
        f.write(f'总计：{len(all_figures)} 张图片\n\n')

        if coverage is not None and coverage.get('captions'):
            label = lambda c: f"{c['kind']}{_fig_tag(c.get('appendix') or '', c['num'])}(p{c['page']})"
            fallback = coverage.get('fallback') or []
            still = coverage.get('stillMissing') or []
            f.write('## 覆盖检查\n')
            f.write(f"- 图注识别：{'、'.join(label(c) for c in coverage['captions'])}（共 {len(coverage['captions'])} 处）\n")
            f.write(f"- 覆盖缺失：{'、'.join(label(c) for c in still) if still else '无'}\n")
            pagefall = [fig for fig in fallback if fig.get('source') == 'page-fallback']
            if pagefall:
                f.write(f"- 整页兜底：{'、'.join(fig['filename'] for fig in pagefall)}（整页渲染含正文，建议人工裁切后替换）\n")
            f.write('\n')

        suspect = [fig for fig in all_figures if fig.get('flags')]
        if suspect:
            f.write('## 图质检查\n')
            for fig in suspect:
                f.write(f"- {fig['filename']}：{'；'.join(fig['flags'])}\n")
            f.write('\n')

        sources = {}
        for fig in all_figures:
            source = fig.get('source', 'unknown')
            if source not in sources:
                sources[source] = []
            sources[source].append(fig)

        for source, figs in sources.items():
            f.write(f'\n## 来源: {source}\n')
            for fig in figs:
                f.write(f'- 文件名：{fig["filename"]}\n')
                f.write(f'- 路径：{fig["path"]}\n')
                f.write(f'- 大小：{fig["size"] / 1024:.1f} KB\n')
                f.write(f'- 格式：{fig["ext"]}\n')
                if fig.get("caption"):
                    f.write(f'- 图注：{fig["caption"]}\n')
                if fig.get("flags"):
                    f.write(f'- 质检：{"；".join(fig["flags"])}\n')
                f.write('\n')

    print(f'\n成功提取 {len(all_figures)} 张图片')
    print(f'保存目录：{output_dir}')
    print(f'索引文件：{index_file}')
    print('\n图片列表：')
    for fig in all_figures:
        print(f'  - {fig["path"]} ({fig.get("source", "unknown")})')

    print('\nImage paths:')
    for fig in all_figures:
        print(fig["path"])

    # 机器可读的覆盖摘要（主代理据此判断是否要人工裁切/补图）
    if coverage is not None:
        summary = {
            'total': len(all_figures),
            'captions': len(coverage.get('captions') or []),
            'fallback': [fig['filename'] for fig in (coverage.get('fallback') or [])
                         if fig.get('source') == 'page-fallback'],
            'stillMissing': [f"{c['kind']}{_fig_tag(c.get('appendix') or '', c['num'])}(p{c['page']})"
                             for c in (coverage.get('stillMissing') or [])],
            'suspect': [{'file': fig['filename'], 'flags': fig['flags']}
                        for fig in all_figures if fig.get('flags')],
        }
        print('\nCOVERAGE ' + json.dumps(summary, ensure_ascii=False))


if __name__ == '__main__':
    main()
