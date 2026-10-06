# -*- coding: utf-8 -*-
"""
build_index.py —— 生成全库"检索 digest"(_检索索引.md)。
每篇 index 一行:题 ｜ 一句话 ｜ 主题 ｜ 术语 ｜ 方法 ｜ 评分 ｜ 路径。
设计:文件小到 AI 能一次整篇读完做语义匹配;也可单文件 grep 方法名/术语精确命中。
- 术语列 = 30_Terms 倒排(子代理抽取的术语)。
- 方法列 = 扫每篇 notes+正文 命中的"方法/公式/模型名"白名单(根治"核心方法没被 termize 就搜不到":
  如 Example2024 的 Hölzer–Sommerfeld/反圆度 即使没进术语库,也能靠正文命中被搜到)。
入库收尾自动跑(见 SKILL.md)。手动:python build_index.py --vault "<VAULT>"
"""
import os, re, glob, argparse, datetime

# 方法/公式/模型 白名单:canonical 显示名 -> 命中子串(全小写匹配;用较长串避免误命中)
METHOD_MAP = {
 "Hölzer-Sommerfeld": ["hölzer", "holzer", "sommerfeld"],
 "Di Felice": ["di felice"],
 "Ganser": ["ganser"], "Haider-Levenspiel": ["haider"],
 "Wen-Yu": ["wen-yu", "wen and yu", "wen & yu"], "Ergun": ["ergun"],
 "Richardson-Zaki": ["richardson-zaki", "richardson and zaki"],
 "Schiller-Naumann": ["schiller-naumann", "schiller naumann"],
 "Clift-Gauvin": ["clift"], "Dioguardi": ["dioguardi"], "Bagheri": ["bagheri"],
 "inverse-circularity 反圆度": ["inverse circularity", "反圆度"],
 "Corey 形状因子": ["corey"], "Sneed-Folk": ["sneed"], "Zingg": ["zingg"],
 "Wadell": ["wadell"], "Krumbein": ["krumbein"], "Powers 圆度": ["powers"],
 "Shields": ["shields"], "Meyer-Peter-Müller": ["meyer-peter", "meyer peter"],
 "superquadric 超二次": ["superquadric", "super-quadric", "超二次", "superellipsoid", "超椭球", "poly-super"],
 "bonded-sphere 粘结球": ["bonded-sphere", "bonded sphere", "粘结球"],
 "multi-sphere 多球": ["multi-sphere", "multisphere", "多球"],
 "polyhedron 多面体": ["polyhedr", "多面体"],
 "IBM 浸没边界": ["immersed boundary", "浸没边界"],
 "LBM 格子玻尔兹曼": ["lattice boltzmann", "格子玻尔兹曼"],
 "DNS 直接数值模拟": ["direct numerical simulation"],
 "SPH 光滑粒子": ["smoothed particle"],
 "level-set/SDF": ["level-set", "level set", "signed distance", "符号距离场", "符号距离"],
 "point-cloud 点云": ["point cloud", "point-cloud", "点云曳力"],
 "YOLO": ["yolo"], "Hertz": ["hertz contact", "hertz-mindlin"], "GJK": ["gjk"],
 "endmember 端元": ["endmember", "端元"], "SfM 摄影测量": ["structure-from-motion", "structure from motion"],
 "Di Felice voidage": [],  # placeholder removed below if empty
}
METHOD_MAP = {k: v for k, v in METHOD_MAP.items() if v}

def fm_body(txt):
    if txt.startswith("---"):
        p = txt.split("---", 2)
        if len(p) >= 3: return p[1], p[2]
    return "", txt

def f1(pat, s, d=""):
    m = re.search(pat, s, re.M)
    return m.group(1).strip().strip('"').strip() if m else d

def rd(p):
    try: return open(p, encoding="utf-8").read()
    except Exception: return ""

def build(vault):
    papers = os.path.join(vault, "Papers")
    termsd = os.path.join(vault, "30_Terms", "术语")
    sysdir = os.path.join(vault, "90_系统"); os.makedirs(sysdir, exist_ok=True)
    out = os.path.join(sysdir, "_检索索引.md")

    # 术语倒排
    paper_terms = {}
    for tf in glob.glob(os.path.join(termsd, "*.md")):
        fm, _ = fm_body(rd(tf))
        term = f1(r'^term:\s*"?([^"\n]+)"?', fm); zh = f1(r'^zhName:\s*"?([^"\n]*)"?', fm)
        label = term + (("(" + zh + ")") if (zh and zh != term) else "")
        for pid in re.findall(r'\[\[([^\]]+)\]\]', fm):
            paper_terms.setdefault(pid.strip(), []).append(label or term)

    # 一次遍历:收 index + 按 pid 收 notes/正文 路径
    index_items = []; notes_by, art_by = {}, {}
    for root, _, files in os.walk(papers):
        for fn in files:
            if not fn.endswith(".md"): continue
            full = os.path.join(root, fn); base = fn[:-3]
            if base.endswith(".notes"): notes_by[base[:-6]] = full
            elif base.endswith(".正文"): art_by[base[:-3]] = full
            else:
                txt = rd(full); fm, body = fm_body(txt)
                if "noteType: index" in fm or "p2o/paper" in fm: index_items.append((base, fm, body))

    rows = []
    for pid, fm, body in index_items:
        domain = f1(r'^domain:\s*"?([^"\n]+)"?', fm, "(未分类)")
        score = f1(r'^quality_score:\s*"?([^"\n]+)"?', fm)
        topics = re.findall(r'主题/([^\s"]+)', fm)
        en = f1(r'\*\*原题\*\*[：:]\s*(.+)', body)
        tl = re.search(r'##\s*📝[^\n]*\n+([^\n<]+)', body)
        tldr = tl.group(1).strip() if tl else ""
        if tldr.startswith("（") or tldr.startswith("("): tldr = ""
        # 方法扫描(notes + 正文)
        scan = (rd(notes_by.get(pid, "")) + "\n" + rd(art_by.get(pid, ""))).lower()
        methods = [name for name, subs in METHOD_MAP.items() if any(s in scan for s in subs)]
        rows.append(dict(pid=pid, domain=domain, score=score, topics=topics, en=en, tldr=tldr,
                         terms=paper_terms.get(pid, []), methods=methods,
                         rel=os.path.relpath([f for f in [notes_by.get(pid), art_by.get(pid)] if f][0] if (notes_by.get(pid) or art_by.get(pid)) else "", vault)))
        # 路径用 index 自身更稳:
        rows[-1]["rel"] = None

    # index 路径(重新定位:index 文件名=pid.md,在 Papers 下)
    idx_path = {}
    for root, _, files in os.walk(papers):
        for fn in files:
            if fn.endswith(".md"):
                idx_path.setdefault(fn[:-3], os.path.join(root, fn))
    for r in rows:
        p = idx_path.get(r["pid"], "")
        r["rel"] = os.path.relpath(p, vault).replace("\\", "/") if p else r["pid"]

    rows.sort(key=lambda r: (r["domain"], r["pid"]))
    L = ["# 🔎 库检索索引（AI 快速检索用 · 自动生成，勿手改）", "",
         "> **用法**：① 语义/模糊查 → 先读轻量版 `_检索速览.md`（一次 Read 装得下）；② 本文件是**全字段版**，用来 grep 方法名/术语/主题（如 Hölzer、Shields、超二次），命中后按行尾「→ 路径」打开对应 index。",
         "> 字段：**题** ｜ 一句话 ｜ 主题 ｜ 术语 ｜ 方法（扫正文/笔记命中的模型·公式名）｜ ⭐评分 ｜ → 路径（**故意不用 wiki 双链**：否则本文件会连向全库每篇→关系图超级枢纽；定位用行尾路径）",
         "> 共 %d 篇 · 生成 %s" % (len(rows), datetime.date.today().isoformat()), ""]
    cur = None
    for r in rows:
        if r["domain"] != cur: cur = r["domain"]; L.append("\n## " + cur)
        seg = ["**%s**" % r["pid"]]  # 纯文本标题，不用 [[ ]]：避免这一个文件连向全库 100 篇=关系图超级枢纽冲垮分专题布局；定位靠行尾「→ 路径」
        if r["tldr"]: seg.append(r["tldr"])
        if r["topics"]: seg.append("主题:" + " ".join(r["topics"][:8]))
        if r["terms"]: seg.append("术语:" + ", ".join(r["terms"][:14]))
        if r["methods"]: seg.append("方法:" + ", ".join(r["methods"]))
        if r["en"]: seg.append("EN:" + r["en"][:90])
        if r["score"]: seg.append("⭐" + r["score"])
        seg.append("→ " + r["rel"])
        L.append("- " + " ｜ ".join(seg))
    open(out, "w", encoding="utf-8").write("\n".join(L) + "\n")

    # 轻量版速览：题｜一句话｜主题｜⭐｜路径。给 AI「一次 Read 读完全库」做语义匹配用；
    # 全字段版(检索索引)留给 grep 精确命中。两层由同一数据源生成，永远同步。
    out2 = os.path.join(sysdir, "_检索速览.md")
    S = ["# ⚡ 库检索速览（AI 一次读完全库用 · 自动生成，勿手改）", "",
         "> 轻量版 digest：每篇一行=题｜一句话｜主题｜⭐｜→路径。**语义/模糊找论文先整篇读我**；",
         "> 要按方法名/术语名精确 grep（Hölzer、Shields、超二次…）用全字段版 `_检索索引.md`。",
         "> 共 %d 篇 · 生成 %s" % (len(rows), datetime.date.today().isoformat()), ""]
    cur = None
    for r in rows:
        if r["domain"] != cur: cur = r["domain"]; S.append("\n## " + cur)
        seg = ["**%s**" % r["pid"]]
        if r["tldr"]: seg.append(r["tldr"])
        if r["topics"]: seg.append("主题:" + " ".join(r["topics"][:6]))
        if r["score"]: seg.append("⭐" + r["score"])
        seg.append("→ " + r["rel"])
        S.append("- " + " ｜ ".join(seg))
    open(out2, "w", encoding="utf-8").write("\n".join(S) + "\n")

    nm = sum(1 for r in rows if r["methods"])
    return out, len(rows), sum(1 for r in rows if r["terms"]), nm, os.path.getsize(out), os.path.getsize(out2)

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--vault", default=r"G:\论文知识库"); a = ap.parse_args()
    out, n, nt, nm, sz, sz2 = build(a.vault)
    print("papers=%d  with_terms=%d  with_methods=%d  索引=%d bytes (~%dk tok)  速览=%d bytes (~%dk tok)"
          % (n, nt, nm, sz, sz // 4 // 1000, sz2, sz2 // 4 // 1000))
