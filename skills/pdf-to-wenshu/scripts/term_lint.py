# -*- coding: utf-8 -*-
"""
term_lint.py —— 扫 _registry.json，按"显著词签名"+字符串相似度找近重复术语,
输出候选清单 <VAULT>/_术语去重候选.md(仅提示,不自动合并;合并见 SKILL.md 的去重姿势)。
防 H-S×2 / Di Felice×4 这类重复复发。手动:python term_lint.py --vault "<VAULT>"
"""
import os, re, json, argparse, difflib

STOP = set("""drag model method correction correlation coefficient function equation number scheme
approach theory force index analysis modeling modelling simulation based new the a an of on for and
with to using via from particle particles flow shape effect general formula law ratio
曳力 模型 方法 系数 修正 关联式 公式 数 法 效应 分析 模拟 颗粒 形状 流 的 与 法则 指数 函数 模型法""".split())

def norm(s):
    s = s.lower()
    for a, b in [("ö","o"),("ü","u"),("é","e"),("á","a"),("è","e"),("ä","a")]: s = s.replace(a, b)
    return s

def sig(term):
    toks = re.split(r'[\s\-_/(),.|]+', norm(term))
    keep = [t for t in toks if len(t) >= 3 and t not in STOP and not t.isdigit()]
    # 中文按 2-gram 兜底(短中文词)
    for t in toks:
        if len(t) >= 2 and re.search(r'[一-鿿]', t) and t not in STOP: keep.append(t)
    return frozenset(keep)

def build(vault):
    reg = json.load(open(os.path.join(vault, "30_Terms", "术语", "_registry.json"), encoding="utf-8"))
    items = [(k, e.get("term",""), e.get("note",""), len(e.get("usages",[]))) for k, e in reg.items()]
    # 1) 按签名分组
    groups = {}
    for k, term, note, nu in items:
        s = sig(term)
        if s: groups.setdefault(s, []).append((term, note, nu))
    sig_dups = [g for g in groups.values() if len(g) >= 2]
    # 2) 字符串相似度(catch 签名没抓到的拼写变体)
    seen_pairs = set(); ratio_dups = []
    terms = [(term, note, nu) for _, term, note, nu in items]
    for i in range(len(terms)):
        for j in range(i+1, len(terms)):
            a, b = terms[i][0], terms[j][0]
            if abs(len(a)-len(b)) > 8: continue
            r = difflib.SequenceMatcher(None, norm(a), norm(b)).ratio()
            if r >= 0.86:
                key = tuple(sorted([a, b]))
                if key not in seen_pairs:
                    seen_pairs.add(key); ratio_dups.append((r, terms[i], terms[j]))
    # 写报告
    L = ["# 🧹 术语去重候选（term_lint 自动生成 · 仅提示，需人工确认再合并）", "",
         "> 共 %d 术语；签名重复组 %d；相似对 %d。合并姿势见 SKILL.md（registry 合并 usages/aliases + 删冗余 note + 全库 `[[变体]]`→`[[规范]]` remap + update_terms --rebuild）。" % (len(items), len(sig_dups), len(ratio_dups)), ""]
    if sig_dups:
        L.append("## A. 同义签名组（最可能是重复）")
        for g in sorted(sig_dups, key=lambda g:-len(g)):
            L.append("- " + " ｜ ".join("**%s**(%s, %d篇)" % (t, n, u) for t, n, u in sorted(g, key=lambda x:-x[2])))
    if ratio_dups:
        L.append("\n## B. 高相似词对（拼写/命名变体）")
        for r, x, y in sorted(ratio_dups, key=lambda z:-z[0]):
            L.append("- %.2f ｜ **%s**(%d篇) ↔ **%s**(%d篇)" % (r, x[0], x[2], y[0], y[2]))
    if not sig_dups and not ratio_dups:
        L.append("✅ 未发现明显重复候选。")
    sysdir = os.path.join(vault, "90_系统"); os.makedirs(sysdir, exist_ok=True)
    out = os.path.join(sysdir, "_术语去重候选.md")
    open(out, "w", encoding="utf-8").write("\n".join(L) + "\n")
    return out, len(items), len(sig_dups), len(ratio_dups)

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--vault", default=r"G:\论文知识库"); a = ap.parse_args()
    out, n, sd, rd = build(a.vault)
    print("terms=%d  sig_dup_groups=%d  ratio_pairs=%d  -> _术语去重候选.md" % (n, sd, rd))
