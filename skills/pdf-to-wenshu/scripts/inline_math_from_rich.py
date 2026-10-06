#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""拿 `<pid>.rich.txt` 把英文正文里裸着的数学符号包成行内公式。

## 原理

`<pid>.rich.txt` 与 `<pid>.txt` 是同一份 PDF、同一个抽取顺序，差别只在上下标有没有被
压平。所以 rich 里每出现一个 `C_{D}`，纯文本里对应位置就是 `CD`——把这两种形态配成对，
就得到**这篇论文自己的**符号映射表：`CD → C_D`、`ap1 → a_{p1}`、`v∞ → v_{\\infty}`。

判据全部来自 PDF，不读中文正文——「先英后中」之后英文先产出，那时没有中文稿可读。

## 为什么不能直接全文替换

正文经过连字符接回、页眉清理、公式注入、表格注入，跟 dump 已经不是逐行对应，
所以**不做位置对齐，只做符号级替换**：拿映射表在正文里按词边界找同样的裸 token。
代价是同名符号在不同上下文里若有歧义就会一刀切，因此下面几道闸都在压这个风险。

## 四道防误伤闸

1. **歧义丢弃**：同一个压平形态映射到多个 LaTeX 时，占比不到 80% 就整条不要
   （`Re2` 既可能是 `Re_2` 也可能是 `Re^2`，分不清就别猜）。
2. **普通词排除**：压平形态若在正文里大量以普通单词出现（`as`、`in`、`log`），一律不收。
3. **保护区**：已在 `$…$` / `$$…$$` / 代码围栏 / `[[wikilink]]` / HTML 注释 / Markdown
   标题里的内容一律不碰——否则会把已经正确的公式再包一层。
4. **词边界**：前后不能紧邻字母数字，`CD` 不会从 `CDF` 里被抠出来。
"""
from __future__ import annotations

import argparse
import collections
import re
import sys
import unicodedata
from pathlib import Path

# Plane-1 数学字母符号区 + 类字母符号（ℝ ℕ ℓ …）。有些期刊的 PDF 把变量原样保留成
# `𝑝` `𝑁` `𝑷` `ℝ` 而不是 ASCII——实测 14 篇共 4470 处，词根只认 [A-Za-z] 时一个都匹配不上。
MATH_LETTER = '\U0001D400-\U0001D7FF\u2100-\u214F'
# `C_{D}`、`a_{p1}`、`Re^{−1/2}`、`v_{\infty}`、`𝑝_{𝑖}`：词根 + 一个或多个上下标组
RICH_TOKEN = re.compile(r'(?<![A-Za-z0-9])([A-Za-z%s][A-Za-z%s]{0,7})'
                        r'((?:[_^]\{[^}]{1,8}\})+)' % (MATH_LETTER, MATH_LETTER))
# 数学字母紧贴英文单词：`𝑝𝑖in the point cloud`、`𝑷is a finite set`、`𝑁points`
STUCK = re.compile(r'([%s])(?=[A-Za-z])|(?<=[A-Za-z])([%s])' % (MATH_LETTER, MATH_LETTER))
# 码位区间决定字体样式，NFKD 只能折出基字母、折不出样式
MATH_STYLE = ((0x1D400, 0x1D433, r'\mathbf{%s}'), (0x1D434, 0x1D467, '%s'),
              (0x1D468, 0x1D49B, r'\boldsymbol{%s}'), (0x1D49C, 0x1D4CF, r'\mathcal{%s}'),
              (0x1D4D0, 0x1D503, r'\boldsymbol{\mathcal{%s}}'),
              (0x1D504, 0x1D537, r'\mathfrak{%s}'), (0x1D538, 0x1D56B, r'\mathbb{%s}'),
              (0x1D56C, 0x1D59F, r'\boldsymbol{\mathfrak{%s}}'),
              (0x1D5A0, 0x1D5D3, r'\mathsf{%s}'), (0x1D5D4, 0x1D607, r'\boldsymbol{\mathsf{%s}}'),
              (0x1D670, 0x1D6A3, r'\mathtt{%s}'),
              (0x1D6A8, 0x1D6E1, r'\mathbf{%s}'), (0x1D6E2, 0x1D71B, '%s'),
              (0x1D71C, 0x1D755, r'\boldsymbol{%s}'), (0x1D7CE, 0x1D7FF, '%s'))
# 类字母符号区（U+2100–U+214F）没有整齐的码位分组，只能逐个列常用的
LETTERLIKE = {'ℝ': r'\mathbb{R}', 'ℕ': r'\mathbb{N}', 'ℤ': r'\mathbb{Z}',
              'ℚ': r'\mathbb{Q}', 'ℂ': r'\mathbb{C}', 'ℍ': r'\mathbb{H}',
              'ℙ': r'\mathbb{P}', 'ℓ': r'\ell', 'ℒ': r'\mathcal{L}',
              'ℱ': r'\mathcal{F}', 'ℬ': r'\mathcal{B}', 'ℰ': r'\mathcal{E}',
              'ℋ': r'\mathcal{H}', 'ℐ': r'\mathcal{I}', 'ℳ': r'\mathcal{M}',
              'ℛ': r'\mathcal{R}', '℘': r'\wp', 'ℏ': r'\hbar'}


def mathletter_to_tex(s: str) -> str:
    """`𝑝` → `p`、`𝑷` → `\\boldsymbol{P}`、`ℝ` → `\\mathbb{R}`。非数学字母原样返回。"""
    out = []
    for ch in s:
        if ch in LETTERLIKE:
            out.append(LETTERLIKE[ch])
            continue
        base = unicodedata.normalize('NFKD', ch)
        if base == ch or not base:
            out.append(ch)
            continue
        tpl = next((t for lo, hi, t in MATH_STYLE if lo <= ord(ch) <= hi), '%s')
        out.append(tpl % base)
    return ''.join(out)
SCRIPT_PART = re.compile(r'([_^])\{([^}]{1,8})\}')
TEX_TO_CHAR = {r'\infty': '∞', r'\alpha': 'α', r'\beta': 'β', r'\gamma': 'γ',
               r'\delta': 'δ', r'\epsilon': 'ε', r'\zeta': 'ζ', r'\eta': 'η',
               r'\theta': 'θ', r'\lambda': 'λ', r'\mu': 'μ', r'\nu': 'ν', r'\xi': 'ξ',
               r'\pi': 'π', r'\rho': 'ρ', r'\sigma': 'σ', r'\tau': 'τ', r'\phi': 'ϕ',
               r'\varphi': 'φ', r'\psi': 'ψ', r'\omega': 'ω'}
# 压平后会跟英文常用词撞车的词根，直接不收
STOP_BASE = {'log', 'exp', 'max', 'min', 'sin', 'cos', 'tan', 'as', 'at', 'in', 'is',
             'it', 'of', 'on', 'or', 'to', 'be', 'by', 'no', 'we', 'an', 'the', 'and',
             'for', 'are', 'can', 'all', 'one', 'two', 'has', 'not', 'but', 'was'}
MIN_HITS = 2            # 映射表里的一条至少要在 rich dump 出现两次，挡掉抽取噪声
DOMINANT = 0.8          # 歧义占比门槛


def to_plain(script_body: str) -> str:
    """上下标内容还原成纯文本 dump 里的样子：`\\infty` → `∞`。"""
    s = script_body
    for tex, ch in TEX_TO_CHAR.items():
        s = s.replace(tex, ch)
    return s.replace('\\', '')


def _kind(latex: str) -> str:
    """这条 LaTeX 的第一个上下标是 `_` 还是 `^`。"""
    m = SCRIPT_PART.search(latex)
    return m.group(1) if m else ''


def _root(latex: str) -> str:
    """词根部分。不能用 `[A-Za-z]+` 取——`\\mathbb{R}^{3}` 开头是反斜杠，取不到。"""
    m = SCRIPT_PART.search(latex)
    return latex[:m.start()] if m else latex


def build_symbol_map(rich: str) -> dict:
    """从 rich dump 提「压平形态 → LaTeX」映射表。歧义与低频项在这里就被丢掉。

    歧义有两种来源：一种是真歧义（`Re2` 既可能是 `Re_2` 也可能是 `Re^2`），
    另一种是基线判定的抖动——同一个系数偶尔被读成上标。后者可以靠**同族一致性**
    化解：`a_{1}` `a_{2}` `a_{5}` `a_{6}` 都是下标，那么占比只有 0.62 的 `a_{3}`
    显然也该是下标，而不是被整条丢掉、在正文里留下 `$a_{1}$ $a_{2}$ a3` 这种花脸。
    """
    cites = citation_map(rich)
    pairs: dict = collections.defaultdict(collections.Counter)
    for base, scripts in RICH_TOKEN.findall(rich):
        if base.lower() in STOP_BASE:
            continue
        if base + ''.join(b for _m, b in SCRIPT_PART.findall(scripts)) in cites:
            continue        # 引文号归 citation_map，别让它变成 `$Dhariwal^{65}$`
        flat = base + ''.join(to_plain(b) for _m, b in SCRIPT_PART.findall(scripts))
        if len(flat) < 2 or flat.lower() in STOP_BASE:
            continue
        # 词根/上下标里的数学字母要转成 LaTeX（`𝑝_{𝑖}` → `p_{i}`），
        # 但压平形态必须保留原字符——正文里躺着的就是 `𝑝𝑖`
        pairs[flat][mathletter_to_tex(base + scripts)] += 1

    # 先收下无歧义的，再用它们统计每个词根偏好哪种上下标
    out: dict = {}
    unsure: dict = {}
    for flat, cand in pairs.items():
        total = sum(cand.values())
        latex, n = cand.most_common(1)[0]
        if total < MIN_HITS:
            continue
        if n / total >= DOMINANT:
            out[flat] = latex
        else:
            unsure[flat] = cand

    pref: dict = collections.defaultdict(collections.Counter)
    for latex in out.values():
        pref[_root(latex)][_kind(latex)] += 1

    for flat, cand in unsure.items():
        base = _root(cand.most_common(1)[0][0])
        if base not in pref:
            continue
        want = pref[base].most_common(1)[0][0]
        same = [c for c in cand if _kind(c) == want]
        if len(same) == 1:
            out[flat] = same[0]
    return out


# `world^{1}`、`pressure^{2–5}`、`rheology.^{6–8}`：普通英文词 + 纯数字上标 = 引文号
# 词根放到 2 个字母：`al.68`（Druckrey et al.68）、`et al.70` 这种也是引文号
CITE_SUP = re.compile(r'(?<![A-Za-z0-9])([A-Za-z][A-Za-z]{1,}[.,;:)\]]?)'
                      r'\^\{(\d[\d,\u2013\u2014\-]{0,13})\}')


def citation_map(rich: str) -> dict:
    """从 rich dump 提「粘住的引文号 → `[N]`」映射表。

    正文里读到的是 `resource material in the world1`、`confining pressure2–5`、
    `rheology.6–8`——期刊用上标排引文号，抽纯文本时上标塌进词尾，引文号就成了单词的
    一部分。实测全库 443 处、涉及 42 篇，Example2024 一篇 25 处。

    这条**不能走符号表那条路**：`inline_math_from_rich` 有 `MIN_HITS = 2`
    （至少出现两次才收，用来挡抽取噪声），而「某个单词 + 某个引文号」的组合在全文
    只会出现一次，永远够不到阈值。对数学符号该有这道闸，对引文号则必须绕开。

    只认「≥3 个字母的普通词 + 纯数字上标」：`C^{2}` 这种单字母是数学，
    `Re^{-1/2}` 带负号斜杠也是数学，都不会被误当引文。
    """
    out = {}
    for word, num in CITE_SUP.findall(rich):
        if word.lower().rstrip('.,;:)]') in STOP_BASE:
            continue
        out[word + num] = '%s[%s]' % (word, num)
    return out


def drop_wordlike(smap: dict, rich: str) -> dict:
    """把「其实是英文单词」的条目剔掉。判据必须看 rich dump，不能看正文。

    拿正文当判据是自相矛盾的：正文里裸着的 `pa` 正是要替换的目标，
    却会因为「以小写形式反复出现」被当成英文单词剔掉（实测 `pa`、`Re_x` 全被误杀）。

    rich dump 保留了「带上下标」与「不带」的区别，所以能对账：
    某个形态若在 rich 里绝大多数时候是**光秃秃**出现的，那它就是普通词（`in`、`as`），
    真符号则绝大多数时候带着上下标。
    """
    out = {}
    for flat, latex in smap.items():
        marked = len(re.findall(r'(?<![A-Za-z0-9])%s(?![A-Za-z0-9])' % re.escape(latex), rich))
        bare = len(re.findall(r'(?<![A-Za-z0-9\\{])%s(?![A-Za-z0-9}])' % re.escape(flat), rich))
        if marked >= bare:
            out[flat] = latex
    return out


PROTECT = re.compile(
    r'```.*?```'                       # 代码围栏
    r'|\$\$.+?\$\$'                    # 块公式
    r'|(?<!\$)\$[^$\n]+\$'             # 已有的行内公式
    r'|!?\[\[[^\]]*\]\]'               # 图片内嵌与 wikilink
    r'|<!--.*?-->'                     # HTML 注释（TODO 工单）
    # 标题这条必须写 `[^\n]*` 而不是 `.*`：整个模式带 re.S，`.` 会吃掉换行，
    # 于是从第一个标题一路匹配到文末，整篇都成了保护区、一处也替换不了
    r'|^#{1,6} [^\n]*$',
    re.S | re.M)


ASCII_WORD = re.compile(r'[A-Za-z0-9]')
# 补空格只看字母：`𝑝𝑖in` 的 `in` 是被粘住的单词，而 `ℝ3` 的 `3` 是符号自己的一部分，
# 硬插空格会把 `ℝ³` 拆成「ℝ 和 3」两样东西
ASCII_ALPHA = re.compile(r'[A-Za-z]')
MATH_RUN = re.compile(r'[%s]+' % MATH_LETTER)


# 包裹时先吐占位符而不是 `$`，最后统一收口。
# 直接吐 `$` 的话，同一段里两处相邻替换会拼出 `$φ_{s}$$ρ_{s}$`——中间那对 `$$`
# 被当成块公式定界符，`lint_cluster` 立刻报「块公式未闭合」。而替换发生时看到的是
# 替换**前**的字符串，根本看不见上一处刚吐出的 `$`，所以只能等全部替换完再收口。
MARK = '\x00'


def _pad(neighbor: str) -> str:
    """邻居是英文字母时要补空格：`𝑝𝑖in` 里的 `in` 是被 PDF 抽文本粘上来的单词。"""
    return ' ' if ASCII_ALPHA.match(neighbor or ' ') else ''


def seal_marks(text: str) -> str:
    """占位符收口成 `$`，任何会拼出 `$$` 的地方都先塞一个空格。"""
    text = re.sub(r'%s(?=%s)' % (MARK, MARK), MARK + ' ', text)
    text = re.sub(r'(?<=\$)%s' % MARK, ' ' + MARK, text)
    text = re.sub(r'%s(?=\$)' % MARK, MARK + ' ', text)
    return text.replace(MARK, '$')


def wrap_bare_math(seg: str, hits: collections.Counter) -> str:
    """符号表没覆盖到的裸数学字母，也要包成行内公式并把粘住的空格补回来。

    `𝑝𝑖in the point cloud` / `𝑷is a finite set` / `ℝ3` 这类里，数学字母是变量、
    后面那截是英文单词，PDF 抽文本时两者之间的空格丢了。不补空格，读者看到的就是
    「公式和后面的字粘在一起」；不包 `$…$`，前端也不会按数学体渲染。
    """
    def rep(m):
        tok, i, j = m.group(0), m.start(), m.end()
        prev = seg[i - 1] if i else ''
        nxt = seg[j] if j < len(seg) else ''
        if prev == '{':
            return tok
        hits['(裸数学字母)'] += 1
        return '%s%s%s%s%s' % (_pad(prev), MARK, mathletter_to_tex(tok), MARK, _pad(nxt))
    return MATH_RUN.sub(rep, seg)


def apply_citations(seg: str, cites: dict, hits: collections.Counter) -> str:
    """把粘在词尾的引文号剥成 `[N]`。空表时原样返回。"""
    if not cites:
        return seg
    pat = re.compile(r'(?<![A-Za-z0-9])(%s)(?![A-Za-z0-9])'
                     % '|'.join(re.escape(k) for k in sorted(cites, key=len, reverse=True)))

    def rep(m):
        hits['(引文号)'] += 1
        return cites[m.group(1)]
    return pat.sub(rep, seg)


def wrap_inline(article: str, smap: dict, cites: dict = None):
    """按符号映射表把正文里的裸 token 包成 `$…$`，保护区内一律不碰。

    词边界不能只写 `(?![A-Za-z0-9])`：数学字母那批论文里 `𝑝𝑖in the point cloud`
    是**符号直接粘着单词**（PDF 抽文本时没有空格），一律拒绝就等于这 14 篇全放弃。
    所以改成：ASCII 词根要求两侧不是字母数字（`CD` 不从 `CDF` 里抠），
    数学字母词根允许紧贴单词，包裹时顺手把缺的空格补上。
    """
    cites = cites or {}
    # 符号表为空也不能提前退出：裸数学字母与引文号那两趟仍要跑，
    # 否则 14 篇 Unicode 数学字母论文里符号表恰好为空的那几篇会被整篇跳过
    pat = re.compile('(%s)' % '|'.join(re.escape(k) for k in
                                       sorted(smap, key=len, reverse=True))) if smap else None
    hits: collections.Counter = collections.Counter()

    def sub_plain(seg: str) -> str:
        if not seg:
            return seg
        seg = apply_citations(seg, cites, hits)
        if pat is None:
            return wrap_bare_math(seg, hits)

        def rep(m):
            tok, i, j = m.group(1), m.start(1), m.end(1)
            prev = seg[i - 1] if i else ''
            nxt = seg[j] if j < len(seg) else ''
            if prev == '\\':
                return tok
            # ASCII 收尾/起头的 token 必须守住词边界，否则 CD 会从 CDF 里被抠出来
            if ASCII_WORD.match(tok[0] or ' ') and ASCII_WORD.match(prev or ' '):
                return tok
            if ASCII_WORD.match(tok[-1] or ' ') and ASCII_WORD.match(nxt or ' '):
                return tok
            hits[tok] += 1
            return '%s%s%s%s%s' % (_pad(prev), MARK, smap[tok], MARK, _pad(nxt))

        seg = pat.sub(rep, seg)
        return wrap_bare_math(seg, hits)

    out, last = [], 0
    for m in PROTECT.finditer(article):
        out.append(sub_plain(article[last:m.start()]))
        out.append(m.group(0))
        last = m.end()
    out.append(sub_plain(article[last:]))

    return seal_marks(''.join(out)), hits


def process(article_path: Path, rich_path: Path):
    article = article_path.read_text(encoding='utf-8', errors='replace')
    rich = rich_path.read_text(encoding='utf-8', errors='replace')
    smap = drop_wordlike(build_symbol_map(rich), rich)
    new, hits = wrap_inline(article, smap, citation_map(rich))
    return new, smap, hits


def main() -> None:
    ap = argparse.ArgumentParser(description='用 rich dump 把英文正文的裸符号包成行内公式')
    ap.add_argument('--vault', required=True)
    ap.add_argument('--out', help='草稿目录；不给则原地改写（谨慎）')
    ap.add_argument('--only', help='只处理 pid 前缀匹配的')
    a = ap.parse_args()

    outdir = Path(a.out) if a.out else None
    if outdir:
        outdir.mkdir(parents=True, exist_ok=True)

    total_sym = total_hit = done = 0
    for en in sorted(Path(a.vault).rglob('content/*.正文.en.md')):
        pid = en.name[:-len('.正文.en.md')]
        if a.only and not pid.startswith(a.only):
            continue
        rich = en.with_name(pid + '.rich.txt')
        if not rich.is_file():
            print('%-44s 无 rich dump，跳过' % pid[:44])
            continue
        new, smap, hits = process(en, rich)
        n = sum(hits.values())
        total_sym += len(smap)
        total_hit += n
        done += 1
        (outdir / (pid + '.正文.en.md') if outdir else en).write_text(new, encoding='utf-8')
        top = '、'.join('%s→%s ×%d' % (k, smap.get(k, k), v) for k, v in hits.most_common(3))
        print('%-44s 符号表 %3d / 包裹 %4d 处  %s' % (pid[:44], len(smap), n, top[:60]))
    print('共 %d 篇，符号表合计 %d 条，包裹 %d 处 → %s'
          % (done, total_sym, total_hit, outdir or '原地'))


if __name__ == '__main__':
    main()
