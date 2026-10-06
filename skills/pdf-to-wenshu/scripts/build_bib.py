# -*- coding: utf-8 -*-
"""
build_bib.py —— 从全库 index frontmatter + 文献卡 导出 BibTeX(<VAULT>/_文献库.bib),
并把稳定 cite key 写回各 index frontmatter(citekey,差异即重盖、幂等),形成"笔记↔引用"闭环。
cite key = pid 前缀(作者年份,ASCII,对中文论文也稳) + 首个标题实词,冲突追加字母。
写论文直接 \\cite{citekey} / 指 Zotero(Better BibTeX)用此 .bib。
若存在 90_系统/_bib补丁.json(verify_bib.py 用 Crossref 核对产出),自动套用：
条目类型(@article/@inproceedings/…)、卷/期/页、年份——投稿级元数据。
手动:python build_bib.py --vault "<VAULT>"   入库收尾自动跑(见 SKILL.md 步骤⑩)。
"""
import os, re, glob, json, argparse

def fm_body(t):
    if t.startswith("---"):
        p = t.split("---", 2)
        if len(p) >= 3: return p[1], p[2]
    return "", t

def f1(pat, s, d=""):
    m = re.search(pat, s, re.M)
    return m.group(1).strip().strip('"').strip() if m else d

def authors_list(fm):
    m = re.search(r'^authors:\s*\n((?:[ \t]*-[ \t]*.+\n?)+)', fm, re.M)
    if not m: return []
    return [re.sub(r'^[ \t]*-[ \t]*', '', ln).strip().strip('"').strip()
            for ln in m.group(1).splitlines() if ln.strip()]

def clean_title(s):
    s = re.sub(r'<[^>]+>', '', s); s = re.sub(r'\s+', ' ', s).strip()
    return s

STOP = {"new","the","a","an","of","on","for","and","in","with","to","using","via","from","by","its","an"}
def cite_key(pid, en, used):
    base_seed = re.sub(r'[^A-Za-z0-9]', '', pid.split()[0]).lower() if pid.split() else "ref"
    word = ""
    for w in re.findall(r'[A-Za-z]+', en or ""):
        if len(w) >= 4 and w.lower() not in STOP: word = w.lower(); break
    base = (base_seed + word) or "ref"
    k = base; i = 0
    while k in used: i += 1; k = base + chr(ord('a') + i)
    used.add(k); return k

def build(vault):
    papers = os.path.join(vault, "Papers")
    sysdir = os.path.join(vault, "90_系统"); os.makedirs(sysdir, exist_ok=True)
    out = os.path.join(sysdir, "_文献库.bib")
    recs = []
    for mf in glob.glob(os.path.join(papers, "**", "*.md"), recursive=True):
        try: txt = open(mf, encoding="utf-8").read()
        except Exception: continue
        fm, body = fm_body(txt)
        if "noteType: index" not in fm and "p2o/paper" not in fm: continue
        pid = os.path.splitext(os.path.basename(mf))[0]
        au = authors_list(fm)
        translated = f1(r'^translatedTitle:\s*"?([^"\n]+)"?', fm)
        m = re.search(r'\*\*原题\*\*[：:]\s*(.*?)(?=\n[-*] \*\*|\n##|\Z)', body, re.S)
        en = clean_title(m.group(1)) if m else translated
        journal = f1(r'^journal:\s*"?([^"\n]+)"?', fm)
        vol = iss = pages = ""
        mj = re.search(r'\*\*期刊\*\*[：:]\s*(.+?)\s+(\d{4})(?:[，,]\s*([0-9]+)(?:\(([0-9A-Za-z]+)\))?(?:[：:]\s*([0-9]+[–\-—]?[0-9]*))?)?', body)
        if mj:
            if not journal: journal = mj.group(1).strip()
            vol, iss = (mj.group(3) or ""), (mj.group(4) or "")
            pages = (mj.group(5) or "").replace("–","--").replace("—","--").replace("-","--")
        recs.append(dict(mf=mf, fm=fm, txt=txt, pid=pid, au=au, en=en, journal=journal,
                         year=f1(r'^year:\s*"?([^"\n]+)"?', fm), doi=f1(r'^doi:\s*"?([^"\n]+)"?', fm),
                         vol=vol, iss=iss, pages=pages))
    recs.sort(key=lambda r: r["pid"].lower())
    # verify_bib.py 的 Crossref 核对补丁（按 DOI 键控；没有补丁文件则原样输出）
    patch_path = os.path.join(sysdir, "_bib补丁.json")
    patches = {}
    if os.path.isfile(patch_path):
        try: patches = json.load(open(patch_path, encoding="utf-8"))
        except Exception: patches = {}
    used = set(); entries = []; stamped = 0; n_patched = 0
    for r in recs:
        key = cite_key(r["pid"], r["en"], used)
        p = patches.get((r["doi"] or "").lower(), {})
        if p: n_patched += 1
        etype = p.get("entrytype", "article")
        vol   = p.get("volume", r["vol"])
        iss   = p.get("number", r["iss"])
        pages = p.get("pages",  r["pages"])
        year  = p.get("year",   r["year"])
        journal = r["journal"] or p.get("journal_full", "")
        jfield = "booktitle" if etype in ("inproceedings", "incollection") else \
                 ("school" if etype == "phdthesis" else "journal")
        fields = (['  author = {%s}' % " and ".join(r["au"])] if r["au"] else [])
        if r["en"]: fields.append('  title = {%s}' % r["en"])
        if journal: fields.append('  %s = {%s}' % (jfield, journal))
        if year: fields.append('  year = {%s}' % year)
        if vol: fields.append('  volume = {%s}' % vol)
        if iss: fields.append('  number = {%s}' % iss)
        if pages: fields.append('  pages = {%s}' % pages)
        if r["doi"]: fields.append('  doi = {%s}' % r["doi"])
        entries.append("@%s{%s,\n%s\n}" % (etype, key, ",\n".join(fields)))
        # 回填 citekey:差异即重盖
        cur = f1(r'^citekey:\s*"?([^"\n]+)"?', r["fm"])
        if cur != key:
            fm2 = re.sub(r'\n?^citekey:\s*"?[^"\n]*"?[ \t]*$', '', r["fm"], flags=re.M)  # 去旧
            ins = '\ncitekey: "%s"' % key
            nfm = re.sub(r'(^doi:\s*"?[^"\n]*"?[ \t]*$)', r'\1' + ins, fm2, count=1, flags=re.M)
            if nfm == fm2:
                nfm = re.sub(r'(^year:\s*"?[^"\n]*"?[ \t]*$)', r'\1' + ins, fm2, count=1, flags=re.M)
            if nfm != fm2:
                open(r["mf"], "w", encoding="utf-8").write("---" + nfm + "---" + r["txt"].split("---", 2)[2]); stamped += 1
    open(out, "w", encoding="utf-8").write("\n\n".join(entries) + "\n")
    return out, len(entries), stamped, n_patched

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--vault", default=r"G:\论文知识库"); a = ap.parse_args()
    out, n, st, np = build(a.vault)
    print("bib entries=%d  citekey (re)stamped=%d  crossref补丁=%d  -> _文献库.bib" % (n, st, np))
