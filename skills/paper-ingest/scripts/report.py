#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
report.py — 把 paper-ingest 的设计 + 实测成果渲染成一页 HTML（数据全部从工作区 / 库里现取，可反复重生成）。

    python report.py --work-root _work/lite --vault vault-lite [--vault vault] --out 技能流程-paper-ingest.html

取数：<work>/{meta,stats,timing,verify}.json，<vault>/90_系统/_ingest/*.lite.json（finish 之后才有：webLint / sync）。
"""
from __future__ import annotations

import argparse
import html
import io
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from shared.config import load_config as load_skill_config  # noqa: E402

HERE = Path(__file__).resolve().parent


def utf8() -> None:
    if sys.platform == "win32":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


def rd_json(p: Path) -> dict:
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def esc(v) -> str:
    return html.escape(str(v if v is not None else ""))


def code_lines(paths: list[Path]) -> tuple[int, int]:
    n = 0
    for p in paths:
        if p.exists():
            n += sum(1 for _ in p.read_text(encoding="utf-8", errors="replace").splitlines())
    return len([p for p in paths if p.exists()]), n


REJECT_LABEL = {"regex": "正则凑数", "condensed": "英文缩写 3 倍", "copied_old": "复用作废产物", "filler": "码位填充 + 集中堆放", "disconnected": "断网挂死"}


def attempts(work_root: Path, key: str) -> list[dict]:
    """_work/lite/_rejected/<Key>/<round…_原因>/ 里的作废尝试（目录名尾巴就是原因）。"""
    base = work_root / "_rejected" / key
    if not base.exists():
        return []
    out = []
    for d in sorted(p for p in base.iterdir() if p.is_dir()):
        t, v = rd_json(d / "timing.json"), rd_json(d / "verify.json")
        label = next((lab for suf, lab in REJECT_LABEL.items() if d.name.endswith(suf)), d.name)
        secs = t.get("seconds") or sum(float(r.get("seconds") or 0) for r in t.get("rounds", []))
        out.append({"name": d.name, "label": label, "effort": t.get("effort") or "—", "secs": secs or None,
                    "started": (t.get("started_at") or "")[11:16], "verify": v})
    return out


def collect(work_root: Path, vaults: list[Path]) -> list[dict]:
    lites: dict[str, dict] = {}
    for v in vaults:
        for p in (v / "90_系统" / "_ingest").glob("*.lite.json"):
            d = rd_json(p)
            key = (d.get("extract") or {}).get("key") or ""
            if key:
                lites[key] = d | {"_vault": v.name}
    rows = []
    for w in sorted(p for p in work_root.iterdir() if p.is_dir() and not p.name.startswith("_")):
        stats = rd_json(w / "stats.json")
        if not stats:
            continue
        meta = rd_json(w / "meta.json")
        fields = rd_json(w / "out" / "fields.json")
        if not meta.get("title") or meta.get("title") == Path(str(meta.get("pdf") or "")).stem:
            meta["title"] = fields.get("title") or fields.get("translatedTitle") or meta.get("title") or w.name
        row = {"name": w.name, "meta": meta, "stats": stats, "timing": rd_json(w / "timing.json"),
               "verify": rd_json(w / "verify.json"), "lite": lites.get(stats.get("key") or w.name) or lites.get(w.name) or {},
               "out": sorted(p.name for p in (w / "out").glob("*") if p.is_file() and not p.name.startswith("_")),
               "attempts": attempts(work_root, w.name)}
        rows.append(row)
    return rows


def publisher(meta: dict) -> str:
    pub = meta.get("publisher") or ""
    if pub:
        return pub.replace("Elsevier BV", "Elsevier").replace("Springer Science and Business Media LLC", "Springer")
    return "中文期刊" if meta.get("lang") == "zh" else "—"


def fmt_secs(s) -> str:
    try:
        s = float(s)
    except Exception:
        return "—"
    return f"{s:.0f} s" if s < 90 else f"{s / 60:.1f} min"


def badge(ok: bool | None, yes="通过", no="未过", none_="未跑") -> str:
    if ok is None:
        return f'<span class="badge b-mute">{none_}</span>'
    return f'<span class="badge {"b-ok" if ok else "b-bad"}">{yes if ok else no}</span>'


def render(rows: list[dict], cfg: dict) -> str:
    scripts = ["extract.py", "layout.py", "figtools.py", "run_agent.py", "verify.py", "finish.py", "report.py"]
    nscripts, nlines = code_lines([HERE / s for s in scripts])
    agent = cfg.get("agent", {})
    runner = agent.get("runner", "codex")
    model = agent.get("model") or (agent.get("models") or {}).get(runner, "")
    ran = [r for r in rows if r["timing"].get("rounds")]
    finished = [r for r in rows if r["lite"]]

    # ---- 抽取表
    ext_rows = []
    for r in rows:
        s, m = r["stats"], r["meta"]
        exp = s.get("expected") or {}
        figs = s.get("figures") or {}
        ext_rows.append(
            f"<tr><td><b>{esc(r['name'])}</b><span class='sub2'>{esc((m.get('title') or '')[:70])}</span></td>"
            f"<td>{esc(publisher(m))}</td><td class='num'>{esc(s.get('pages'))}</td>"
            f"<td class='num'>{figs.get('extracted', 0)}/{len(exp.get('figures', []))}</td>"
            f"<td class='num'>{s.get('equationsMarked', 0)}/{len(exp.get('equations', []))}</td>"
            f"<td class='num'>{len(exp.get('tables', []))}</td><td class='num'>{s.get('refs', 0)}</td>"
            f"<td class='num'>{s.get('regroupedPages', 0)}</td><td class='num'>{fmt_secs(s.get('totalSeconds'))}</td></tr>")

    # ---- 子代理表
    run_rows = []
    for r in ran:
        t, v, lite = r["timing"], r["verify"], r["lite"]
        rounds = t.get("rounds", [])
        per = "<br>".join(f"第 {x['round']} 轮 {fmt_secs(x['seconds'])} · rc={esc(x['rc'])} · verify {x['verify']['errors']} err / {x['verify']['warnings']} warn" for x in rounds)
        counts = v.get("counts") or {}
        fig, eq, tab = counts.get("figures") or {}, counts.get("equations") or {}, counts.get("tables") or {}
        exp = r["stats"].get("expected") or {}
        lines = counts.get("lines") or {}
        wl = (lite.get("summary") or {}).get("webLint") or {}
        run_rows.append(
            f"<tr><td><b>{esc(r['name'])}</b><span class='sub2'>{esc(t.get('runner'))} · {esc(t.get('model') or '默认模型')} · effort={esc(t.get('effort') or '默认')}</span></td>"
            f"<td>{per or '—'}</td><td class='num'>{fmt_secs(t.get('seconds'))}</td>"
            f"<td class='num'>图 {fig.get('zhEmbedded', 0)}/{len(exp.get('figures', []))}<br>式 {eq.get('zhTagged', 0)}/{len(exp.get('equations', []))}<br>表 {tab.get('zhBuilt', 0)}/{len(exp.get('tables', []))}</td>"
            f"<td class='num'>en {lines.get('en', 0)}<br>zh {lines.get('zh', 0)}<br>notes {lines.get('notes', 0)}</td>"
            f"<td>{badge(v.get('ok'))}<span class='sub2'>{len(v.get('errors', []))} err / {len(v.get('warnings', []))} warn</span></td>"
            f"<td>{badge(None if not wl else wl.get('rc') == 0, '0 错 0 警', 'rc=' + str(wl.get('rc')))}"
            f"{('<span class=sub2>' + esc((lite.get('summary') or {}).get('pid', '')) + '</span>') if lite else ''}</td></tr>")

    # ---- verify 明细（最近一次）
    detail = []
    for r in ran:
        v = r["verify"]
        items = [f"<li class='bad'>{esc(e)}</li>" for e in v.get("errors", [])] + [f"<li class='warn'>{esc(w)}</li>" for w in v.get("warnings", [])]
        detail.append(f"<div class='card'><h4>{esc(r['name'])} · verify {badge(v.get('ok'))}</h4>"
                      + (f"<ul class='vlist'>{''.join(items)}</ul>" if items else "<p>errors / warnings 均为空。</p>") + "</div>")

    # ---- 状态表：每篇现在到哪一步（含作废尝试、进行中的子代理）
    status_rows = []
    for r in rows:
        s, t, v, lite = r["stats"], r["timing"], r["verify"], r["lite"]
        exp = s.get("expected") or {}
        figs = s.get("figures") or {}
        ext = (f"图 {figs.get('extracted', 0)}/{len(exp.get('figures', []))} · 式 {s.get('equationsMarked', 0)}/{len(exp.get('equations', []))}"
               f" · 表 {len(exp.get('tables', []))} · {fmt_secs(s.get('totalSeconds'))}")
        tries = [f"<span class='badge b-bad'>✗</span> {esc(a['effort'])} · {fmt_secs(a['secs']) if a['secs'] else '—'} · {esc(a['label'])}" for a in r["attempts"]]
        rounds = t.get("rounds", [])
        if rounds:
            last = rounds[-1]
            okb = last["verify"]["errors"] == 0
            tries.append(f"<span class='badge {'b-ok' if okb else 'b-bad'}'>{'✓' if okb else '✗'}</span> {esc(t.get('effort'))} · {fmt_secs(t.get('seconds'))} · {len(rounds)} 轮 · rc={esc(last['rc'])}")
        elif t:
            tries.append(f"<span class='badge b-warn'>⏳</span> {esc(t.get('effort'))} · 进行中（{esc((t.get('started_at') or '')[11:16])} 起）")
        if lite:
            wl_rc = ((lite.get("summary") or {}).get("webLint") or {}).get("rc")
            if wl_rc == 0:
                state, cls = "已入库 · 前端质检 0 错 0 警", "b-ok"
            else:
                state, cls = "已装配 · 前端质检有警告，等修复轮重装", "b-warn"
        elif t and not rounds:
            state, cls = "子代理进行中", "b-warn"
        elif r["attempts"] and not rounds:
            state, cls = f"{len(r['attempts'])} 次作废，待重派", "b-bad"
        elif rounds:
            state, cls = ("过 verify，待 finish" if v.get("ok") else "verify 未过"), ("b-ok" if v.get("ok") else "b-bad")
        else:
            state, cls = "仅抽取，未派子代理", "b-mute"
        status_rows.append(
            f"<tr><td><b>{esc(r['name'])}</b><span class='sub2'>{esc(publisher(r['meta']))} · {esc(s.get('pages'))} 页 · {'中文' if r['meta'].get('lang') == 'zh' else '英文'}</span></td>"
            f"<td class='mono' style='font-size:12.5px'>{ext}</td><td style='font-size:12.5px'>{'<br>'.join(tries) or '—'}</td>"
            f"<td>{badge(v.get('ok') if v else None)}</td><td><span class='badge {cls}'>{state}</span></td></tr>")

    # ---- 大白话实例：每篇已入库的论文，从 PDF 到集群实际拿到了什么
    example_cards = []
    for r in finished:
        s, t, lite = r["stats"], r["timing"], r["lite"]
        sm = lite.get("summary") or {}
        lt = lite.get("timing") or t
        cnt = ((sm.get("verify") or {}).get("counts") or {})
        lines = cnt.get("lines") or {}
        exp = s.get("expected") or {}
        folder = (sm.get("folder") or "").replace("\\", "/")
        folder_short = folder.split("/Papers/")[-1] if "/Papers/" in folder else folder
        wl = (sm.get("webLint") or {}).get("rc")
        example_cards.append(
            f"<div class='card'><h4>{esc(r['name'])} <span class='sub2' style='display:inline;margin:0 0 0 6px'>{esc(publisher(r['meta']))} · {esc(s.get('pages'))} 页 · {'中文刊' if r['meta'].get('lang') == 'zh' else '英文刊'}</span></h4>"
            f"<p><b>丢进去</b>：1 个 PDF。<b>脚本</b> {fmt_secs(s.get('totalSeconds'))} 拆完；<b>AI</b> {esc(lt.get('runner'))}·{esc(lt.get('model'))} 用 {fmt_secs(lt.get('seconds'))}（{len(lt.get('rounds') or [])} 轮）写完；<b>装配</b> {sm.get('finishSeconds', 0)} s。</p>"
            f"<p style='margin-top:6px'><b>拿到</b>：中文正文 {lines.get('zh', 0)} 行 · 英文正文 {lines.get('en', 0)} 行 · 学习卡 {lines.get('notes', 0)} 行 · 术语 {cnt.get('terms', 0)} 条 · 整幅图 {sm.get('images', 0)} 张 · 参考文献 {sm.get('refs', 0)} 条；"
            f"图 {len(exp.get('figures', []))} / 公式 {len(exp.get('equations', []))} / 表 {len(exp.get('tables', []))} 逐号核对齐全；前端质检 {badge(None if wl is None else wl == 0, '0 错 0 警', '有警告')}。</p>"
            f"<p style='margin-top:6px' class='mono'>→ Papers/{esc(folder_short)}/</p></div>")

    gen = datetime.now().strftime("%Y-%m-%d %H:%M")
    ok_runs = sum(1 for r in ran if r["verify"].get("ok"))
    lint_ok = sum(1 for r in finished if ((r["lite"].get("summary") or {}).get("webLint") or {}).get("rc") == 0)
    total_figs = sum(len((r["stats"].get("expected") or {}).get("figures", [])) for r in rows)
    total_eqs = sum(len((r["stats"].get("expected") or {}).get("equations", [])) for r in rows)
    found_figs = sum((r["stats"].get("figures") or {}).get("extracted", 0) for r in rows)
    marked_eqs = sum(r["stats"].get("equationsMarked", 0) for r in rows)
    extract_secs = sum(float(r["stats"].get("totalSeconds") or 0) for r in rows)

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>paper-ingest · 文枢极简入库：设计与实测</title>
<style>
:root{{--bg:#0f1115;--panel:#161a21;--panel2:#1c212a;--line:#2a313d;--tx:#e6e9ef;--tx2:#9aa4b2;--tx3:#6b7480;
--script:#3b82f6;--script-bg:rgba(59,130,246,.12);--ai:#a855f7;--ai-bg:rgba(168,85,247,.12);--gate:#10b981;--gate-bg:rgba(16,185,129,.12);
--warn:#f59e0b;--warn-bg:rgba(245,158,11,.12);--bad:#ef4444;--bad-bg:rgba(239,68,68,.12)}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--tx);font:15px/1.75 -apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;-webkit-font-smoothing:antialiased}}
code,.mono{{font-family:"SFMono-Regular",Consolas,"Cascadia Mono",monospace;font-size:.88em}}
.wrap{{max-width:1180px;margin:0 auto;padding:56px 28px 96px}}
header{{margin-bottom:48px}} h1{{font-size:30px;letter-spacing:-.4px;margin:0 0 10px}}
.sub{{color:var(--tx2);font-size:15px;max-width:800px}} .sub b{{color:var(--tx)}}
.meta{{margin-top:18px;display:flex;gap:10px;flex-wrap:wrap}}
.pill{{padding:5px 12px;border-radius:999px;font-size:12.5px;border:1px solid var(--line);background:var(--panel);color:var(--tx2)}} .pill b{{color:var(--tx);font-weight:600}}
h2{{font-size:19px;margin:56px 0 8px;padding-bottom:10px;border-bottom:1px solid var(--line);letter-spacing:-.2px}} h2 .num{{color:var(--tx3);font-weight:400;margin-right:10px}}
.lead{{color:var(--tx2);margin:0 0 24px;font-size:14.5px}} .lead b{{color:var(--tx)}}
.legend{{display:flex;gap:20px;flex-wrap:wrap;margin:22px 0 8px}} .lg{{display:flex;align-items:center;gap:8px;font-size:13px;color:var(--tx2)}} .dot{{width:11px;height:11px;border-radius:3px;flex:none}}
.stage{{border:1px solid var(--line);border-radius:14px;background:var(--panel);margin-bottom:14px;overflow:hidden}}
.stage-hd{{display:flex;align-items:center;gap:14px;padding:15px 20px;background:var(--panel2);border-bottom:1px solid var(--line)}}
.stage-no{{width:28px;height:28px;border-radius:8px;flex:none;display:grid;place-items:center;font-size:13px;font-weight:700}}
.stage-hd h3{{margin:0;font-size:15.5px;font-weight:600}} .stage-hd .tag{{margin-left:auto;font-size:12px;color:var(--tx3)}} .stage-bd{{padding:18px 20px}}
.steps{{display:flex;flex-direction:column;gap:10px}}
.step{{display:grid;grid-template-columns:170px 1fr;gap:16px;align-items:start;padding:12px 14px;border-radius:10px;background:var(--panel2);border-left:3px solid transparent}}
.step.s-script{{border-left-color:var(--script)}} .step.s-ai{{border-left-color:var(--ai)}} .step.s-gate{{border-left-color:var(--gate)}}
.step .k{{font-size:13px;color:var(--tx2);font-weight:600;padding-top:1px}} .step .k .cmd{{display:block;color:var(--script);font-size:12px;font-weight:400;margin-top:3px;word-break:break-all}}
.step.s-ai .k .cmd{{color:var(--ai)}} .step.s-gate .k .cmd{{color:var(--gate)}}
.step .v{{font-size:13.5px;color:var(--tx2)}} .step .v b{{color:var(--tx);font-weight:600}} .step .v .note{{display:block;margin-top:6px;color:var(--tx3);font-size:12.5px}}
table{{width:100%;border-collapse:collapse;margin:16px 0;font-size:13.5px}}
th,td{{padding:10px 13px;text-align:left;border-bottom:1px solid var(--line);vertical-align:top}}
th{{color:var(--tx3);font-weight:600;font-size:12.5px;letter-spacing:.3px;background:var(--panel)}} td b{{color:var(--tx)}}
tbody tr:hover{{background:var(--panel)}} td.num{{text-align:right;font-family:"SFMono-Regular",Consolas,monospace;color:var(--tx);white-space:nowrap}}
.sub2{{display:block;color:var(--tx3);font-size:12px;font-weight:400;margin-top:3px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:14px;margin:18px 0}}
.card{{border:1px solid var(--line);border-radius:12px;padding:16px 18px;background:var(--panel)}}
.card h4{{margin:0 0 8px;font-size:14px;display:flex;align-items:center;gap:8px}} .card p{{margin:0;font-size:13px;color:var(--tx2)}}
.card .big{{font-size:26px;font-weight:700;color:var(--tx);letter-spacing:-.5px;line-height:1.2}} .card .unit{{font-size:12.5px;color:var(--tx3);margin-left:5px;font-weight:400}}
.badge{{display:inline-block;padding:2px 9px;border-radius:6px;font-size:11.5px;font-weight:600;white-space:nowrap}}
.b-ok{{background:var(--gate-bg);color:var(--gate)}} .b-warn{{background:var(--warn-bg);color:var(--warn)}} .b-bad{{background:var(--bad-bg);color:var(--bad)}}
.b-script{{background:var(--script-bg);color:var(--script)}} .b-ai{{background:var(--ai-bg);color:var(--ai)}} .b-mute{{background:var(--panel2);color:var(--tx3)}}
pre{{background:#0b0d11;border:1px solid var(--line);border-radius:10px;padding:15px 18px;overflow-x:auto;margin:16px 0;font-family:"SFMono-Regular",Consolas,"Cascadia Mono",monospace;font-size:12.5px;line-height:1.8;color:var(--tx2)}}
pre .c{{color:var(--tx3)}} pre .g{{color:var(--gate)}} pre .p{{color:var(--ai)}} pre .b{{color:var(--script)}}
.pit{{display:grid;grid-template-columns:auto 1fr auto;gap:14px;align-items:start;padding:13px 16px;border:1px solid var(--line);border-radius:10px;background:var(--panel);margin-bottom:9px}}
.pit .n{{width:26px;height:26px;border-radius:7px;display:grid;place-items:center;font-size:12px;font-weight:700;background:var(--panel2);color:var(--tx2)}}
.pit .t{{font-size:13.5px}} .pit .t b{{color:var(--tx)}} .pit .t span{{display:block;color:var(--tx3);font-size:12.5px;margin-top:4px}}
.pit .r{{font-family:Consolas,monospace;font-size:12.5px;white-space:nowrap;color:var(--gate)}}
.callout{{border:1px solid var(--line);border-left:3px solid var(--warn);border-radius:0 10px 10px 0;background:var(--warn-bg);padding:14px 18px;margin:20px 0;font-size:13.5px;color:var(--tx2)}}
.callout b{{color:var(--tx)}} .callout.good{{border-left-color:var(--gate);background:var(--gate-bg)}} .callout.ai{{border-left-color:var(--ai);background:var(--ai-bg)}}
.vlist{{margin:6px 0 0;padding-left:18px;font-size:12.5px;color:var(--tx2)}} .vlist li.bad{{color:var(--bad)}} .vlist li.warn{{color:var(--warn)}}
.cmp{{display:grid;grid-template-columns:1fr 1fr;gap:14px}} @media(max-width:720px){{.cmp{{grid-template-columns:1fr}} .step{{grid-template-columns:1fr;gap:8px}} .wrap{{padding:36px 18px 64px}}}}
footer{{margin-top:64px;padding-top:20px;border-top:1px solid var(--line);color:var(--tx3);font-size:12.5px}}
</style>
</head>
<body><div class="wrap">

<header>
  <h1>paper-ingest · 一篇论文 PDF 怎么进「文枢」</h1>
  <p class="sub">重做的目标只有三条：<b>更小</b>（一份任务书、{nscripts} 个脚本、{nlines:,} 行，替代原来 9 份互相矛盾的规则文档和 43 个脚本 1.15 万行）、
  <b>更快</b>（脚本部分 3–35 s/篇，其余时间全部花在 AI 读论文本身）、
  <b>不漏不错</b>（图、公式、表按 PDF 文本数出来的清单逐号对账，过不了确定性闸门不许入库）。
  AI 子代理宿主可插拔：codex / claude / grok / kimi 任选，模型 ID 写在配置里。</p>
  <div class="meta">
    <span class="pill">入口 <b>.agents/skills/paper-ingest/</b></span>
    <span class="pill">脚本 <b>{nscripts} 个 · {nlines:,} 行</b></span>
    <span class="pill">子代理 <b>{esc(runner)} · {esc(model or '默认模型')} · effort={esc(agent.get('effort') or '默认')}</b></span>
    <span class="pill">并发上限 <b>{esc(agent.get('maxParallel', 2))} 个子代理</b></span>
    <span class="pill">验证集 <b>{len(rows)} 篇抽取 · {len(ran)} 篇全流程</b></span>
  </div>
</header>

<h2><span class="num">00</span>这个技能做什么（先说人话）</h2>
<p class="lead"><b>丢进去一个论文 PDF，出来一套能直接在「文枢」里读的东西</b>：中文全译正文、英文清洁正文、学习卡、术语、索引页、整幅图。
人只敲三条命令；中间<b>不亲自翻译、不亲自转公式</b>——读论文这件事整个交给一个命令行 AI，脚本只干确定性的活，再用脚本核对 AI 交的作业。</p>
<div class="cmp">
  <div class="card"><h4><span class="badge b-script">输入</span>一个 PDF</h4><p>任何出版社、中英文都行。不需要事先整理，扫描件除外。</p></div>
  <div class="card"><h4><span class="badge b-gate">输出</span>一个论文集群文件夹</h4><p><code>Papers/领域/子类/&lt;作者年份 短题&gt;/</code>：<b>正文.md</b>（中文全译，公式 LaTeX、图原位嵌入、表格、重点公式【说明】、末尾参考文献）· <b>正文.en.md</b>（英文原文清洁重排）· <b>notes.md</b>（学习卡：要点/问答/深度分析/写作逻辑）· <b>images/</b>（整幅裁图）· 索引页（TL;DR、评分、主题）· 术语进 <code>30_Terms/术语/</code>。</p></div>
</div>
<table><thead><tr><th style="width:120px">三步</th><th style="width:130px">谁干</th><th>干什么（人话）</th><th style="width:200px">拿到什么</th><th style="width:170px">多久</th></tr></thead><tbody>
<tr><td><b>① 拆 PDF</b><span class="sub2">extract.py</span></td><td><span class="badge b-script">脚本</span></td><td>查题名作者期刊（DOI → Crossref）；把每张图<b>整幅</b>裁出来并配上图注；把正文按阅读顺序抄成一份草稿（双栏、页眉页脚、断词都处理掉）；切出参考文献；每页渲染成图片；<b>数清这篇 PDF 里有几张图、几条公式、几张表</b>；最后把「你要做什么、交什么、怎么自检」写成一份任务书 brief.md。</td><td>一个工作区文件夹：meta.json · images/ · pages/*.png · en.draft.md · refs.md · brief.md</td><td class="num">3–35 s</td></tr>
<tr><td><b>② 读论文、写内容</b><span class="sub2">run_agent.py</span></td><td><span class="badge b-ai">一个命令行 AI</span><span class="sub2">codex / claude / grok / kimi 任选</span></td><td>拿着任务书和每页图片，像人一样干活：核对每张图裁得对不对（不对就重裁）→ 把英文草稿修成干净的<b>原文重排版</b>（不改写、不缩写）→ <b>逐段翻成中文</b>，公式照页面图转 LaTeX、表格照图重建、图注译成中文 → 写学习卡 → 列 8–20 条术语 → 填索引字段 → 自己跑一遍校验，直到没有错误。</td><td>out/ 五个文件：en.md · zh.md · notes.md · terms.json · fields.json</td><td class="num">10 页中文刊 22 min<br>6 页英文刊 11 min<br>26 页英文刊 80 min+（未成）</td></tr>
<tr><td><b>③ 查作业、装进库</b><span class="sub2">verify.py + finish.py</span></td><td><span class="badge b-gate">脚本</span></td><td><b>先查</b>：图/公式/表按第 ① 步数出来的清单<b>逐号</b>对——缺一个就打回；再查英文是不是原文、中文是不是逐段真译（不是概括、不是机器填充）、公式图表有没有放回原文位置、格式合不合前端契约。<b>不过</b>：把错误清单原样发回 AI 再改一轮（默认最多 2 轮）。<b>过了</b>：装成集群、合并术语库、跑前端质检，零错零警才算入库。</td><td>集群文件夹 + <code>90_系统/_ingest/&lt;pid&gt;.lite.json</code>（每步耗时、核对计数）</td><td class="num">秒级</td></tr>
</tbody></table>
{('<p class="lead" style="margin-top:20px">已经这样走完全程、进了测试库 vault-lite 的论文：</p><div class="grid">' + ''.join(example_cards) + '</div>') if example_cards else ''}
<div class="callout ai"><b>为什么这么分工</b>：PDF 版式千差万别，脚本改英文正文改不好、裁图也常裁歪——所以「判断」的活（章节层级、公式、译文、笔记）全交给 AI，它手里有每页的渲染图；但 AI 会偷懒、会糊弄，所以「核对」的活（数清有几张图几条公式、逐号对账、看译文是不是人话）全交给脚本，AI 的自述一个字都不信。哪一步出了什么问题、怎么补的，见 07。</div>

<h2><span class="num">01</span>现在到哪一步（{gen} 生成，数据现取）</h2>
<p class="lead">下表只展示当前传入工作区的运行结果；抽取与格式检查通过不能证明原稿或译文准确。</p>
<table><thead><tr><th>论文</th><th>① 抽取（自动裁出 / 应有）</th><th>② 子代理尝试</th><th>verify</th><th>状态</th></tr></thead>
<tbody>{''.join(status_rows)}</tbody></table>

<h2><span class="num">02</span>先看结论</h2>
<div class="grid">
  <div class="card"><h4>抽取：图</h4><div class="big">{found_figs}<span class="unit">/ {total_figs} 张自动裁出</span></div><p>{len(rows)} 篇 PDF，应有图数按 PDF 文本重新数；差额由子代理照页面图补裁，verify 逐号核对。</p></div>
  <div class="card"><h4>抽取：公式</h4><div class="big">{marked_eqs}<span class="unit">/ {total_eqs} 条定位到页</span></div><p>脚本只负责「第几页有第 (N) 式」，LaTeX 全部由 AI 照页面图转写；漏号由 verify 兜底。</p></div>
  <div class="card"><h4>脚本总耗时</h4><div class="big">{fmt_secs(extract_secs)}<span class="unit">/ {len(rows)} 篇</span></div><p>含 Crossref 查询与逐页渲染。旧版 pymupdf4llm 单篇 32 s 还把双栏整页当表格。</p></div>
  <div class="card"><h4>全流程</h4><div class="big">{ok_runs}<span class="unit">/ {len(ran)} 篇过 verify</span></div><p>{lint_ok}/{len(finished)} 篇 finish 后前端质检 0 错 0 警。子代理每轮起止时间都记在 timing.json。</p></div>
</div>

<h2><span class="num">03</span>三步流水线：确定性的活给脚本，判断的活给一个 AI</h2>
<p class="lead">主代理只敲三条命令，中间不亲自翻译、不亲自转公式。<b>格式权威只有前端的 content-contract.md</b>，本技能不另立规则。</p>
<div class="legend">
  <span class="lg"><span class="dot" style="background:var(--script)"></span>脚本（确定性）</span>
  <span class="lg"><span class="dot" style="background:var(--ai)"></span>AI 子代理（判断）</span>
  <span class="lg"><span class="dot" style="background:var(--gate)"></span>确定性闸门（不过不许往下走）</span>
</div>

<div class="stage">
  <div class="stage-hd"><span class="stage-no" style="background:var(--script-bg);color:var(--script)">1</span><h3>抽取：PDF → 结构化工作区</h3><span class="tag">3–35 s/篇 · extract.py + layout.py</span></div>
  <div class="stage-bd"><div class="steps">
    <div class="step s-script"><div class="k">元数据<span class="cmd">首页 DOI → Crossref</span></div><div class="v">题名/作者/年份/期刊/卷期页 用 Crossref 权威数据；无 DOI 按题名查；再退回首页最大字号。<span class="note">中文期刊 DOI 多不在 Crossref → 题名/作者由子代理从 p1 补进 fields.json。</span></div></div>
    <div class="step s-script"><div class="k">整幅图<span class="cmd">栅格框 ∪ 矢量簇 → 按图注配对 → 裁 2.2×</span></div><div class="v">图注识别做到<b>行级</b>：正文段和图注粘成一块时在图注行切开；Wiley 拉开的 <code>F I G U R E 1 0</code> / <code>TA B L E 2</code> 先合并；每词一行的老 PDF 先按基线重组行、按行距重组块。<span class="note">配不到图区时取图注上方空当（标 gap-fallback）。抽完自动出 images/_sheet.png 总览。</span></div></div>
    <div class="step s-script"><div class="k">阅读顺序草稿<span class="cmd">span 级版面还原（不用 pymupdf4llm）</span></div><div class="v">行样式切段、双栏切带、页眉页脚按跨页重复去；编号公式行标 <code>&lt;!--EQ (N) pP--&gt;</code>（含 Elsevier 独占一行的 <code>(N)</code> 和中文刊的全角 <code>（N）</code>）；无线表留 <code>&lt;!--TABLE N pP--&gt;</code>。<span class="note">草稿只是脚手架——子代理手里有每页渲染图，草稿不对就照图重建。</span></div></div>
    <div class="step s-script"><div class="k">应有清单<span class="cmd">verify.expected_from_pdf</span></div><div class="v">从 fulltext.txt 直接数：行首 <code>Fig./FIGURE/图 N</code>、行尾或独占行的 <code>(N)</code> 且相邻行有数学符号、<code>Table/表 N</code>；编号连续 → min..max。<b>写进 brief.md，子代理知道要交多少张图多少条公式。</b></div></div>
    <div class="step s-script"><div class="k">任务书<span class="cmd">brief.md（自包含）</span></div><div class="v">路径、格式契约、应有清单、输出清单、裁图工具用法、自检命令，一份 8 KB 文本。子代理<b>不需要读任何技能文档</b>，换宿主也不用改。</div></div>
  </div></div>
</div>

<div class="stage">
  <div class="stage-hd"><span class="stage-no" style="background:var(--ai-bg);color:var(--ai)">2</span><h3>内容：一个命令行 AI 子代理照页面图写</h3><span class="tag">时间主要花在这里 · run_agent.py</span></div>
  <div class="stage-bd"><div class="steps">
    <div class="step s-ai"><div class="k">宿主可插拔<span class="cmd">config.json → agent.runner / models</span></div><div class="v">
      <table style="margin:6px 0"><thead><tr><th>runner</th><th>无头命令模板（run_agent.py RUNNERS，config 可覆盖/新增）</th><th>实测</th></tr></thead><tbody>
      <tr><td><code>codex</code></td><td><code>codex exec -C &lt;work&gt; -s workspace-write -m &lt;model&gt; -c model_reasoning_effort=&lt;effort&gt; -o &lt;last&gt; -</code></td><td><span class="badge b-ok">可看图可写文件</span></td></tr>
      <tr><td><code>claude</code></td><td><code>claude -p --model &lt;model&gt; --dangerously-skip-permissions --add-dir &lt;work&gt;</code></td><td><span class="badge b-warn">需自行配置并认证</span></td></tr>
      <tr><td><code>grok</code></td><td><code>agent --prompt-file &lt;brief&gt; --cwd &lt;work&gt; --permission-mode bypassPermissions -m &lt;model&gt;</code></td><td><span class="badge b-warn">无头模式挂起</span></td></tr>
      <tr><td><code>kimi</code></td><td><code>kimi -p &lt;brief&gt; -y -m &lt;model&gt; --add-dir &lt;work&gt;</code></td><td><span class="badge b-mute">未测</span></td></tr>
      </tbody></table>
      <span class="note">宿主必须能看本地 PNG、能写文件、能跑 python——公式和表格全靠看 pages/pP.png。</span></div></div>
    <div class="step s-ai"><div class="k">子代理做什么<span class="cmd">brief.md → out/</span></div><div class="v">核图（总览图 + 补裁）→ en.md 英文重排 → zh.md 逐节全译 → notes.md 学习卡/深度分析/写作逻辑 → terms.json 8–20 条术语 → fields.json 索引字段 → <b>自己跑 verify.py 直到 errors 为空</b>。</div></div>
    <div class="step s-gate"><div class="k">自动复核<span class="cmd">verify() → 不过再派一轮</span></div><div class="v">run_agent 收回后立刻跑 verify；有 error 就把 errors 拼成修复任务书再派一轮（默认最多 2 轮），每轮起止/耗时/退出码/verify 计数记进 timing.json。</div></div>
  </div></div>
</div>

<div class="stage">
  <div class="stage-hd"><span class="stage-no" style="background:var(--gate-bg);color:var(--gate)">3</span><h3>装配 + 质检 + 同步</h3><span class="tag">秒级 · finish.py</span></div>
  <div class="stage-bd"><div class="steps">
    <div class="step s-gate"><div class="k">闸门<span class="cmd">verify.py</span></div><div class="v">有 error 直接退出不装配（<code>--force</code> 只给人工兜底）。</div></div>
    <div class="step s-script"><div class="k">装配集群<span class="cmd">out/ → Papers/领域/子类/&lt;pid&gt;/</span></div><div class="v">pid = 作者年份 + 中文短题；正文.md / 正文.en.md / notes.md / images.md / PDF / txt / 索引页；图片前缀改成 pid；参考文献拼到中文正文末尾（英文 tab 由前端自动挂）。</div></div>
    <div class="step s-script"><div class="k">术语库<span class="cmd">30_Terms/术语/_registry.json</span></div><div class="v">同名归一去重、合并别名与用法；正文里指向不存在笔记的 <code>[[wikilink]]</code> 全部拆成纯文本。</div></div>
    <div class="step s-gate"><div class="k">前端质检 + 同步<span class="cmd">web_lint.py --fail-on-warnings · sync-vault.py</span></div><div class="v">零错误零警告才算入库完成；抽取计数 / verify 计数 / 子代理每轮耗时写进 <code>90_系统/_ingest/&lt;pid&gt;.lite.json</code>，本页就从那里取数。</div></div>
  </div></div>
</div>

<h2><span class="num">04</span>图和公式怎么保证一个不漏</h2>
<p class="lead">不信草稿、不信子代理的自述，<b>信 PDF 文本</b>。应有清单在抽取时数好写进任务书；产出回来逐号对账；号不齐就打回去。</p>
<pre><span class="c"># verify.py 的对账口径（有 error → 退出码 1 → finish 拒收）</span>
图    每个应有编号 N：zh.md 有 <span class="g">**图 N.**</span>（en.md 有 <span class="g">**Fig. N.**</span>）且上方紧跟 <span class="g">![[文件|700]]</span>；文件必须真实存在于 images/；核对用的 _sheet.png 不许嵌
公式  每个应有编号 N：en.md / zh.md 都有 <span class="g">\\tag{{N}}</span>；$$ 成对、花括号配对；不许残留 &lt;!--EQ--&gt; 标记和 PDF 私有区乱码
表    每个应有编号 N：<span class="g">**Table N.** / **表 N.**</span> 后面紧跟以 | 开头的 Markdown 表体；不许残留 &lt;!--TABLE--&gt;
结构  en 首行 # 题名、有 ## Abstract、无中文；zh 有 ## 亮点 / ## 摘要、中文比例、编号章节与 en 一一对应、原刊无 Highlights 必须带【说明】行
忠实  en 每段能在 PDF 原文里找到、字数 ≥ 草稿 70%；zh 每节是英文的 15%–100%、每段有标点有常用字不是码位填充、图注是中文、没有「其余各节略」
位置  每条公式上方能找到草稿里引出它的那段话；zh 的公式/图/表与 en 同一编号章节；不许 ## Equations / ## 公式 这类堆放节；不许空章节
表格  表格行里不等号写 <span class="g">\\lt</span> / <span class="g">\\gt</span>、不许裸 &lt; &gt; 和 &lt;br&gt;（与前端 web_lint 同口径；Example2024 第一版就是在这里被前端质检拦下的）
文件  notes.md 骨架标题齐全；terms.json 8–20 条；fields.json shortTitle ≤14 字无标点、中文刊必填 firstAuthorPinyin
放行  PDF 确实没有某号 → 子代理看过页面图后写 out/verify_overrides.json 登记原因，报告里可审计</pre>

<p class="lead">这道闸门先拿脚本自己体检，当场抓出三处「以为全对、其实漏了」——都是旧流程里靠人眼绝对看不出来的：</p>
<div class="pit"><span class="n">1</span><div class="t"><b>Wiley 把图注数字也拉开：<code>F I G U R E 1 0</code></b><span>旧 despace 只合字母，「1 0」读成 1 → Example2024 实际 25 张图只认出 12 张；<code>TA B L E 2</code> 一张表都没认出。修：合并标签后紧随的拉开数字。</span></div><span class="r">12 → 25 / 25</span></div>
<div class="pit"><span class="n">2</span><div class="t"><b>老 Particuology 每词一行，图注粘在上一段里</b><span>Example2024 只认出 15/17（Fig. 1、Fig. 4 起头的块不是以 Fig. 开头）。修：按「行数≈词数」判畸形页 → 按基线重组行、按行距重组块；所有 PDF 的块都在图注行处切开。</span></div><span class="r">15 → 17 / 17</span></div>
<div class="pit"><span class="n">3</span><div class="t"><b>Elsevier 公式号 <code>(9)</code> 独占一块，被当成页眉页脚删了</b><span>数字归一后变 <code>(#)</code>，多页重复 → 「跨页重复即页眉页脚」规则把它删掉 → Example2024 40 条公式只标 30 条；中文刊全角 <code>（3）</code> 一条不认。修：独占的编号块升级上一段为公式、排除出重复检测、接受全角括号。</span></div><span class="r">30 → 40 / 40</span></div>

<h2><span class="num">05</span>验证集：{len(rows)} 篇不同出版社的 PDF，抽取结果</h2>
<p class="lead">「图」列 = 脚本自动裁出 / PDF 文本里数出的应有数；「公式」列 = 定位到页的 / 应有数。差额不是丢了，是留给子代理照页面图补，verify 逐号盯。</p>
<table><thead><tr><th>论文</th><th>出版社</th><th>页</th><th>图</th><th>公式</th><th>表</th><th>参考文献</th><th>重组页</th><th>脚本耗时</th></tr></thead>
<tbody>{''.join(ext_rows)}</tbody></table>

<h2><span class="num">06</span>全流程实测：子代理 → verify → finish → 前端质检</h2>
<p class="lead">每篇一个子代理，同时最多 {esc(agent.get('maxParallel', 2))} 个；主代理只派发、看 verify、收尾。</p>
{('<table><thead><tr><th>论文 · 宿主</th><th>轮次</th><th>子代理总耗时</th><th>对账（zh）</th><th>产出行数</th><th>verify</th><th>web_lint</th></tr></thead><tbody>' + ''.join(run_rows) + '</tbody></table>') if run_rows else '<div class="callout">还没有跑完的子代理记录（run_agent.py 会把每轮写进 timing.json）。</div>'}
{('<div class="grid">' + ''.join(detail) + '</div>') if detail else ''}

<h2><span class="num">07</span>检查的边界</h2>
<p>正文必须忠实、完整。数量、字数、公式渲染与受保护 token 的检查不能替代原 PDF 核对；失败产物不能标记为已发布。</p>

<h2><span class="num">08</span>已知边界</h2>
<div class="grid">
  <div class="card"><h4>抽取</h4><p>图注不以 Fig./Figure/图 开头的认不到；与正文同字号同粗细的标题识别不到；无线表常抽不出（留标记给子代理）；数学字体私有码位仍是乱码（子代理照图转写）。</p></div>
  <div class="card"><h4>应有清单</h4><p>行首的正文句「Fig. 3 shows…」靠动词表排除，漏排的会多要一张图——子代理确认后用 verify_overrides.json 登记即可，报告里可审计。</p></div>
  <div class="card"><h4>子代理</h4><p>宿主必须能看图；选择可用且已经认证的 CLI；具体模型由配置或 CLI 默认值决定。Codex 会自动发现 .agents/skills 里的旧技能，brief 已明确禁止读取。CLI 断网后会静默挂住，run_agent 按「日志 10 分钟不长」判挂死终止再派修复轮。</p></div>
  <div class="card"><h4>「不错」只能部分确定性</h4><p>公式转写、译文忠实度没有确定性判据；verify 能保证结构、数量、位置和「不是填充」，内容质量靠模型 + 人工抽查（看 images.md 与正文对图）。长论文可按连续章节处理，任何未完成部分都须明确报告。</p></div>
</div>

<footer>由 <code>skills/paper-ingest/scripts/report.py</code> 于 {gen} 生成 · 数据来源 _work/lite/*/{{stats,timing,verify}}.json 与 vault/90_系统/_ingest/*.lite.json</footer>
</div></body></html>
"""


def main() -> None:
    utf8()
    ap = argparse.ArgumentParser()
    ap.add_argument("--work-root", required=True)
    ap.add_argument("--vault", action="append", default=[])
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    cfg = load_skill_config(HERE.parent / "config.json")
    rows = collect(Path(a.work_root).resolve(), [Path(v).resolve() for v in a.vault])
    out = Path(a.out).resolve()
    out.write_text(render(rows, cfg), encoding="utf-8")
    print(f"{out} ({out.stat().st_size:,} bytes, {len(rows)} papers)")


if __name__ == "__main__":
    main()
