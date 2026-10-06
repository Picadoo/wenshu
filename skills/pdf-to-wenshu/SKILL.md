---
name: pdf-to-wenshu
description: 维护文枢旧版入库流程的已有 job、存量论文修复及本地文献检索。新论文 PDF 入库、双语全文与学习笔记使用 paper-ingest，避免同时启动两套流程。
allowed-tools: Read, Write, Bash, Agent
---

# Skill: pdf-to-wenshu

## 入口选择

新论文入库使用 [paper-ingest](../paper-ingest/SKILL.md)，不再执行下面的旧版 prepare 流程。续跑已有旧版 `.job.json` 或用户明确指定旧流程时读取下文；不把旧产物重新抽取一遍。旧流程自动检查通过同样不能证明译文、表格和公式准确，必须对照原 PDF 核实本次修改涉及的内容。

**已入库条目的维护按原流程分流**：v2 条目回到其 `paper-ingest` 工作区，只修本次问题涉及的 `out/` 片段，复用原 PDF、清单和其他已完成阶段；不重跑旧 `ingest_prepare.py`，也不以重新入库作为修复前提。修后运行 `paper-ingest/scripts/verify.py --work <work>`，再按该技能受控更新、同步，并用 `wenshu-pro/scripts/web_lint.py --vault <vault> --paper <pid> --fail-on-warnings` 验收单篇。已有旧 job 则续跑对应旧流程的必要阶段。两类维护均保留原 pid/citekey、reading、个人笔记、批注、生词及活动日志；缺少原工作区时先定位原产物，不新建旧 job 覆盖现有论文。

**参考文献保留双语完整参考表**：中文正文末尾用 `## 参考文献`，正式英文正文末尾用 `## References`，两处各从同一份已逐条核对的 refs 数据复制一次，不让模型重写两遍。保留原文引用记号和对应条目锚点。`lint_cluster` 在正式集群中检查两侧缺表及英文未分节污染；内容阶段英文草稿可以尚未装配 References，但正式更新、同步前必须补齐。自动检查通过仍不能证明条目内容或编号准确，涉及参考文献的修改须对照原 PDF 核实。

把放进收件箱的 PDF 一条龙入库：DOI 权威增强 → 双语全文 → 深度分析+学习脚手架 → 全局术语库去重 → 参考文献互链 → **同步文枢前端**。

## 按需展开（本文件保持精简，用到哪份读哪份）

| 文件 | 什么时候读 |
| --- | --- |
| `references/pipeline.md` | 编排入口报错要手动逐条跑、或需要某个脚本的参数细节与坑位 |
| `references/prompts.md` | 主代理写 B 档分析，或查看 A/D/C 的完整规则来源时（步骤⑥） |
| `references/luna-a1-brief.md`（英文重排）/ `luna-a-brief.md`（中文翻译）/ `luna-d-brief.md` / `luna-c-brief.md` | 角色最小任务包；由 `build_agent_brief.py` 解析 job 后生成，不让子代理重读整套技能 |
| `references/topics.md` | 写 `Topics/` 方法专题、综述文档时 |
| `wenshu-pro/docs/content-contract.md` | Markdown 渲染契约，前端怎么解析以它为准 |

## 定位：一份数据，两个消费者

1. **文枢 Web（人读，唯一前端）**：`wenshu-pro` 论文详情页的 tabs——中文正文 / 英文正文 / 学习笔记 / 图片 / 原文 PDF，外加术语库页、生词本、阅读区。新论文默认走严格验收：核心产物齐全、确定性步骤全成功、`lint_cluster` 无错误、单篇 `web_lint --fail-on-warnings` 零警告且 sync-vault 完成，才允许标记 `finished`。旧 job 可显式 `--no-strict` 兼容。
2. **vault 文件层（AI 检索）**：`90_系统/_检索速览.md`（一次 Read 读完全库）、`_检索索引.md`（grep 方法名一击命中）、`content/<pid>.txt` 全文缓存、术语倒排、`_文献库.bib`、引文缺口榜/引用雷达。日后帮用户查文献、写综述全靠这层。

> **Obsidian 已弃用（2026-08）**：闪卡（`cards.md` / 40_Flashcards / build_flashcards）、Dataview 仪表盘、关系图 MOC（regen_moc / _论文地图 / up: 层级）、PaperGraph（update_graph）已全部移除。**不要再生成这些东西**；旧库残留的 `p2o/*` 标签无害、不用清。
> **生词本是用户的**：生词由用户在文枢英文正文里自己双击添加。`90_系统/_web批注/`、`90_系统/_生词/`、`90_系统/_活动日志.jsonl`、`content/<pid>.我的笔记.md` 全是用户数据，**AI 不生成、不修改**（用户明确让你处理生词清单时只读）。

## 配置

```python
from pathlib import Path
import sys
SKILL_DIR  = Path(__file__).resolve().parents[1]     # scripts/ 中运行时的技能目录
sys.path.insert(0, str(SKILL_DIR.parent))
from shared.config import load_config
cfg        = load_config(SKILL_DIR / "config.json")
VAULT      = cfg["vault"]                             # 换库改这一行
WENSHU     = cfg.get("wenshu")                        # 文枢前端根目录；ingest_finish 用来 sync-vault
LANGUAGE   = cfg.get("language", "zh")
NOTE_MODE  = cfg.get("default_mode", "beginner")
SCRIPTS    = SKILL_DIR / "scripts"
PDF_DIR    = Path(VAULT) / "PDFs"
PAPERS_DIR = Path(VAULT) / "Papers"
```

- **领域自描述**：`Papers/` 下已有的文件夹就是领域（含 `大类/子类`）。归不进现有领域时据 concepts 起一个简洁中文领域名并**先向用户确认**，「其他」只留给确实无法归类的。
- 小白模式只影响学习卡/术语讲法；**正文翻译始终忠实**。

## 输出：每篇一个文件夹，外面只露 index

```
<VAULT>/Papers/
├── <大类>/<子类>/
│   ├── <pid>.md                       论文索引（noteType: index）；<pid>=「作者年份 中文短题」
│   └── <作者年份 英文全标题>/           论文文件夹用英文全名（严谨）
│       ├── content/<pid>.正文.md(中译) · <pid>.正文.en.md(英文重排) · <pid>.notes.md(学习卡+分析)
│       │          · <pid>.我的笔记.md(用户的，别动) · <pid>.pdf · <pid>.txt(全文缓存)
│       │          · <pid>.rich.txt(带上下标的 dump，英文侧行内公式的唯一原料)
│       │          · <pid>.tables.md(英文原表索引，抽表脚本产出，中英正文都从这儿取表)
│       └── images/<pid>_pageX_figY.png · <pid>.images.md
<VAULT>/Topics/<主题>/<文档名>.md        专题文档（noteType: topic，见 references/topics.md）
<VAULT>/30_Terms/  ├ _术语库总览.md（纯文本索引） └ 术语/(_registry.json + 各<术语>.md)
<VAULT>/90_系统/   检索速览/检索索引/_文献库.bib/引文缓存/缺口榜/质检报告/_ingest 工作区
```

- index frontmatter（Web 必填，缺失=web_lint 错误）：`translatedTitle / authors / year / domain / tags / status / reading`；建议 `journal / doi / quality_score / citekey`。`reading: 待读`（用户在文枢里改成 在读/已读/重读）。
- index 正文只留 Web 消费的块：`## 文献卡`、`## 科学问题`、`## 一句话总结`、`## 评分`（详情页顶部卡片取自这里）。
- 正文译文文件名 `<pid>.正文.md`（避免与 index 的 `<pid>.md` 撞 basename）。

## 已有旧 job 的完整流水线

主代理编排。**确定性步骤走脚本，禁止用模型手做**（DOI、抽图、**抽表**、公式对拷、清标记、参考文献、质检、文枢同步）。内容按能力拆分：**Luna Max 子代理**负责高吞吐的英文重排与中文全文翻译；**主代理**亲自负责 `notes.md`、`terms.json`、索引回填、跨库对比、综合评价与最终验收。分析不再转交子代理。

### 顺序是「先英后中」

**英文重排在前，中文翻译在后。** 英文正文是原文重排——章节层级、公式编号、图表落位都是原文的客观属性；中文是它的译文，直接继承这套骨架。

旧顺序（中文先行、脚本再把中文 LaTeX 搬进英文）留下的教训：**排版重建这件重活只发生在有子代理的那一侧**。双栏 dump 里标题和正文粘在一行，确定性脚本没有语义理解、拆不开，于是中文侧（有 Luna Max 通读）恢复出 38 个标题，英文侧（只有脚本）同一篇只有 3 个。改多少条 lint 都治不了，只能换顺序。

**别让模型重做脚本已经做完的事**——这是本技能最大的提速点，也是最容易复发的浪费：表格已抽在 `content/<pid>.tables.md`（英文原表，数字照搬只译表头），公式在中英之间按公式号自动对拷（同一条公式只转一次）。子代理只处理脚本明确标了 TODO 的残留。

**旧流程编排入口（仅适用已有旧 job 或用户明确指定旧流程）**：

```bash
python "<SCRIPTS>/ingest_prepare.py" --pdf "<pdf>" --domain "<大类/子类>" \
  --paper-id "<作者年份 中文短题>" --translated-title "<中文标题>" --archive copy

# ⑥a 英文侧先跑：脚本出确定性草稿 → A1 子代理在草稿上恢复章节层级
python "<SCRIPTS>/prep_article_en.py" --vault "<VAULT>" --only "<pid>" --promote-clean
python "<SCRIPTS>/build_agent_brief.py" --job "<job>" --role A1 \
  --draft "<_work/en-draft/<pid>.正文.en.md>"
# ⑥b 硬门禁：英文正文必须先过这一关，中文才有骨架可继承
python "<SCRIPTS>/lint_en_draft.py" --vault "<VAULT>" --draft-dir _work/en-draft \
  --only "<pid>" --fail-on-warnings
# ⑥c 英文过关后并行：Luna Max A 档(照英文骨架逐节译中文) + 主代理 B 档(notes+terms+回填索引)
#     按 job JSON 里的 notes.* / termsJson / imageIndexPath / tableIndexPath 填
# 长文且至少有 3 个 Luna 槽位、用户优先墙钟时，可把 A 改为章节并行：
python "<SCRIPTS>/luna_a_parts.py" prepare --job "<job>" --out-dir "<_work/a-parts/<pid>>" --parts 3
# 并发执行 manifest 里的每个 briefPath，全部返回后：
python "<SCRIPTS>/luna_a_parts.py" merge --manifest "<_work/a-parts/<pid>/manifest.json>"

python "<SCRIPTS>/ingest_finish.py" --job "<VAULT>/90_系统/_ingest/<pid>.job.json" --strict
```

**子代理启动协议（速度门禁）**：主代理已经读过本技能，A1/A/D/C 不再重复读 `SKILL.md`、完整 `prompts.md` 或 `content-contract.md`。先生成已解析路径、写权和验收命令的自包含任务包，再以 `fork_turns: none` 派发：

```bash
python "<SCRIPTS>/build_agent_brief.py" --job "<job>" --role A1 --draft "<_work/en-draft/<pid>.正文.en.md>"
python "<SCRIPTS>/build_agent_brief.py" --job "<job>" --role A
python "<SCRIPTS>/build_agent_brief.py" --job "<job>" --role D --draft "<_work/en-draft/<pid>.正文.en.md>"
# 仅已登记 cFallbackReason 时：
python "<SCRIPTS>/build_agent_brief.py" --job "<job>" --role C --draft "<C 档暂存输出>"
```

**A1 与 A 的分工不能混**：A1 只写 `.正文.en.md`、只管**结构**（章节层级、公式 LaTeX、图表落位、删页眉水印），忠实原文措辞不翻译；A 只写 `.正文.md`、照 A1 的骨架**逐节译**，公式连 `\tag{N}` 一起复制、图片位置照抄，**不要回去读 dump**——回读等于把 A1 的活重做一遍。`--promote-clean` 产出的草稿零 TODO 零警告时可直接晋级，此时 A1 也不必派。

D 命令会先跑严格草稿 lint；已经 `0 error / 0 warning` 时打印 `SKIP_D` 并以退出码 3 结束（表示无需该角色，不是处理失败），不得为了“再确认一次”启动子代理。任务包要求全文每个区间只读一次、避免并行大段读取造成截断复读，且子代理只做一次局部验收；final 会自动回到主代理，不再探测消息工具或额外发送完成通知。

**章节并行 A 是降墙钟的可选模式，不是默认省 token 路径**。仅在清洁全文较长（经验阈值约 1000 行）、可同时占用 3 个 Luna 槽位且用户明确更在意等待时间时启用；否则仍派一个 A。`luna_a_parts.py` 只按编号章节边界切连续片段，每个子代理写独立 `.zh.md`，写后不自验，由父代理统一 merge。PDF 双栏 dump 会让相邻片段看到上一栏的图表；merge 按首次出现者保留、去掉重复图表、规范编号标题层级，并以 job/索引的全量图表数、公式配对、H1/亮点/摘要/TODO 作门禁，失败时不覆盖正文。并行减少等待不等于减少总开销；必须分别记录墙钟时间与所有代理的累计时间。

**公式只转一次，方向随顺序走**：新流程下 A1 在英文侧把公式转成 `$$…\tag{N}$$`，A 档中文侧连 `\tag` 一起复制过去。存量论文（中文侧已有 LaTeX、英文侧没有）仍由 `prep_article_en.py` 反向对拷补齐，两条路共用同一套公式号锚点。

这条不再靠自觉：`lint_cluster` 会比对两侧公式数，**中文有 ≥3 条带号 LaTeX 而英文一条块公式都没有 = 错误**（落差过半 = 警告）。文字 dump 的散字符不能替代可编辑公式；严格验收应检查中英公式对应，并对照原页确认含义。

**章节层级同样有硬门禁**：`check_heading_recovery` 会揪出「正文里残留编号章节名」和「平均一万多字符才一个标题」两种情况并判**错误**。这是「先英后中」的验收关口——A1 没把层级建出来，A 档就没有骨架可继承，旧病立刻复发。

`--promote-clean` 是严格快通道：草稿只有在 **0 TODO + `lint_en_draft --fail-on-warnings` 0 错误/0 警告** 时才直接替换英文占位骨架并跳过 D 档；否则原样留在 `_work/en-draft/`，把 lint 明细交给 D 档只修残留。已有人工英文正文永不自动覆盖。

**C 档默认禁用**。只有确定性草稿整体失效（如 dump 无分页标记、双栏顺序完全不可用、解析器直接失败），主代理才可先用 `ingest_stage.py allow-c-fallback --reason "<具体失效证据>"` 把理由写入 job，再派 C 档从零重建；不得因“D 档还有几条 TODO”启用 C，也不得让 C 与 A 并行抢跑。

`ingest_finish` 的顺序（每一步为什么在这个位置，见 `references/pipeline.md`）：

update_terms（**先**！术语表回填靠标记定位）→ strip_markers → delink_unresolved → **fix_article**（确定性纠错，机械格式问题全自动修）→ build_refs `--inline` → build_index / build_bib（**citekey 回填必须先于质检**，否则 lint 报「缺 citekey」假警告）→ lint_cluster → **`wenshu-pro/scripts/sync-vault.py`**（含 web_lint）

任一侧 lint 有 E 则退出码 1，**不得宣称入库完成**。

**执行角色固定**：A1/A/D/C 使用适合相应任务且宿主可用的模型，并以最小任务包派发；源稿、公式、表格、裁图核准与 B 档深度分析由主代理或具备原页核对能力的较强模型负责。具体模型在配置中选择。全程 UTF-8。

**耗时必须可审计**：`ingest_prepare` 与 `ingest_finish` 自动把确定性子步骤耗时写进 job 的 `timing.prepare/finish`。主代理在派发/收回 A、B、D 角色时，用 `ingest_stage.py start|finish --stage lunaA|mainAnalysis|prepEnglish|lunaD` 记录内容阶段；并行 A 额外以最早子代理 `started_at` 到最晚 `completed_at` 作为墙钟，以各会话 `duration_ms` 之和作为总 agent 时间，不能拿脚本秒数或只报最快分片。先看 job 的分段时间，再判断慢在 PDF 解析、翻译、分析、英文校订还是 Web 同步。

**引用边保鲜**：新论文入库后，老论文引它的地方不会自动长出 `📥` 链——收尾再跑一次 `build_refs.py --vault "<VAULT>" --all --no-crossref`（纯缓存+库内重匹配，不联网、秒级）。

## 多子代理并行（单篇长文可选 / 批量返工）

单篇默认仍由一个 Luna Max 写翻译、主代理写分析；满足上面的长文与槽位门槛时，A 可通过 `luna_a_parts.py` 按独立分片并行，只有父代理 merge 写最终正文。**跨篇批量作业**（一次校订几十篇英文正文、批量补图注）走任务板，规则只有两条：

1. **写权按 pid 与角色切分**：Luna Max 只写自己认领那篇的 `正文.md` / `正文.en.md`；主代理独占 `notes.md`、`terms.json` 与 `<pid>.md`。共享产物——`30_Terms/术语/_registry.json`、`90_系统/` 下的 `_检索速览.md` / `_检索索引.md` / `_文献库.bib` / `_质检报告.md`、`wenshu-pro` 的 `public/vault` 与 `generated-catalog.ts`——**只有主代理串行写**。
2. **调度走任务板，别在 prompt 里写死分片**：`scripts/workboard.py` 提供原子认领 + 租约回收（已用 8 进程并发压测，零重复派发）。写死「你做第 1-5 篇」的话，子代理一死那几篇就静默丢了；任务板会在租约到期后把活自动回收给别人。

```bash
python "<SCRIPTS>/workboard.py" --vault "<VAULT>" init   --task <任务名> --items-file <pid 清单>
python "<SCRIPTS>/workboard.py" --vault "<VAULT>" claim  --task <任务名> --agent <名字> --n 3
python "<SCRIPTS>/workboard.py" --vault "<VAULT>" report --task <任务名> --agent <名字> --item "<pid>" --status done
python "<SCRIPTS>/workboard.py" --vault "<VAULT>" status --task <任务名>
```

**主代理集成验收**（A/B/D 都就绪后再跑）：vault 必须 0 错误，Web 必须 0 错误且 0 警告；**不要跑全库、更不要加 `--report`**（会覆盖全库共享报告）。Luna Max 在 A/B 并行期间只验自己文件的完整性，不因主代理尚未完成 notes/index 而提前跑整篇质检：

```bash
python "<SCRIPTS>/lint_cluster.py"     --vault "<VAULT>" --paper "<pid>"
python "<WENSHU>/scripts/web_lint.py"  --vault "<VAULT>" --paper "<pid>" --fail-on-warnings
```

产出物先落在暂存区（如 `_work/en-draft/`）时，**先在暂存位置验、过了再搬进集群**——别拿 vault 当试错场：

```bash
python "<SCRIPTS>/lint_en_draft.py" --draft-dir _work/en-draft --only "<pid>" --fail-on-warnings
```

**收尾仍然串行**：所有角色就绪后，主代理运行 `ingest_finish.py --strict`；跨篇批量维护完成后再统一跑全库 `lint_cluster --report`。角色提示词与完整规则见 `references/prompts.md` §0 与 D 档。

## 重要规则

- **要用户下载文献时，直接给「可点击的完整网址」，绝不丢 DOI 号让用户复制粘贴**：凡需用户自行获取的文献（付费墙 / 无合法 OA / 脚本下载失败），一律提供可直接点击进站的 URL——首选 `https://doi.org/<DOI>`，并附出版商页面完整链接；**每篇一行、必带 `https://` 前缀**。**严禁**只给一个裸 DOI 字符串、或让用户把号粘进某个网站。

- **检索协议——帮用户查文献先用两层检索 digest，别盲 grep 全文**（均由 `build_index.py` 生成、入库收尾自动重建）：
  1. **模糊/语义**查 → 整篇 Read 轻量版 `90_系统/_检索速览.md`（题｜一句话｜主题｜评分｜→路径，~9k token 一次读完即全局）做匹配；
  2. **方法/公式/术语名**（如 Hölzer–Sommerfeld、Shields、Sneed–Folk、超二次）→ grep 全字段版 `90_系统/_检索索引.md`，命中按行尾「→ 路径」开对应 index；
  3. **概念→论文** 用 `30_Terms/<术语>.md` 的 `papers:` 倒排。

  **只有要核对原文细节，才去读那一篇的 `.txt`/notes——不要一上来盲 grep 整库**（噪声大、多轮、漏模糊查询）。库涨到几百篇、速览一次读不下时，再按大类切片或加向量层。

- **数学字母被抽成谚文字形，是确定性可修的，别当"PDF 就这样"放过**：Springer 系 PDF 抽文本会丢 Plane-1 高位，把数学字母符号 U+1D400–U+1D7FF 整体减 0x10000 落进谚文区——正文里看到的 `휌lnxlnylnz` 其实是 `ρ·ln_x·ln_y·ln_z`，`퐗` 是粗体 **X**。还原是纯算术（码位 +0x10000 再 NFKC 折平），无需猜测：`prep_article_en` 生成草稿时自动洗、`fix_article` 修库内既有文稿、`lint_cluster` 把残留判为错误。判据只有一份（`lint_cluster.restore_math_glyphs`），三处 import 复用。**整篇混有真韩文时自动整篇让开**并降级成警告——宁可留乱码报警，也不能把韩文改成希腊字母。

- **英文侧的原料只能来自 PDF，不许读中文正文**：「先英后中」之后英文正文先产出，那一刻**根本没有中文稿**——任何「从中文正文取符号表/取表格/取结构」的做法都会把依赖方向倒回去，增量流水线上直接跑不通。存量返工也照此办理，否则会长出两套互不相同的路径。

- **行内公式丢失是抽文本方式造成的，不是原文没有**：`page.get_text()` 纯文本模式只返回字符、丢掉字号与基线，于是 `C_D` 压成 `CD`、`a_{p1}` 压成 `ap1`、`log^2` 压成 `log2`；行内上下标缺失会影响可读性与语义。`get_text('dict')` 能拿到每个 span 的字号与基线 y——下标字号更小、基线更低，上标更小更高，`extract_rich_text.py` 据此另产 `<pid>.rich.txt`（直接写成 `C_{D}`、`a_{p1}`、`\log^{2}(Re)`，A1 抄起来就是行内公式）。**阈值按篇自取**——正文字号各篇不同，不能使用单一固定字号。之所以另存而不改 `.txt`：`.txt` 有四个消费者（`build_refs` 找参考文献、`prep_article_en` 刨正文、`src_has_highlights` 判原刊亮点、检索层全文缓存），参考文献里的卷期号也常是上标，直接改格式很可能打乱匹配。

- **Read 误报加密的兜底**：Read 报某 PDF "password-protected" 但 fitz `needs_pass=0` 时＝Read 解析器不耐受、非真加密。主代理：fitz `insert_pdf` 重建干净副本再 `--archive`；全文走 `content/<pid>.txt` 缓存；公式/表格用 fitz `get_pixmap(Matrix(2.3,2.3))≈165dpi` 把每页渲染成 PNG 放临时区，子代理 Read PNG 而非 PDF。

- **收件箱安全**：处理期间用户可能继续往 `PDFs/` 丢新论文。任何「清收件箱」只能按**确切文件名**删你这次处理过的那一篇原件，**绝不批量/glob 删**；删用户文件前先核对它确实是你刚归档过的那篇。

- **命名严谨**：文件夹=`suggestedFolder`（作者年份+全标题），文件=`suggestedId`（完整关键词、不从词中间截断）。**PowerShell 里别用 `$pid` 变量**（只读自动变量=进程号，会把文件名写错）。**pid 就是论文互链 `[[pid]]` 的目标名，改名要全库同步**（用 `restructure.py`）。

- **渲染契约要点**（完整版见 `wenshu-pro/docs/content-contract.md`）：图片 `![[name.png|700]]`；列表/正文用别名 `[[file|名]]`；**表格里的链接用 `[[base]] 名`，别用 `[[a\|b]]`**（转义竖线易断链）；frontmatter 双引号；**表格/列表前空行 +「：」引出**（忌行尾「——」顶表格）；表格内数学不等号用 `\lt`/`\gt`、不用裸 `<`/`>`；**H1 之后、`## 亮点` 之前禁止出现引用块**（会把整段正文卷进「说明」卡片）。

- 编码：subprocess 调脚本；读写 `encoding='utf-8'`；Windows stdout 先包 UTF-8。
- 去重靠 `sourceHash`，幂等。术语库对账**串行**，registry 不并发写。术语稳定命名以便查重。
- 术语库总览随每次入库**从 registry 全量再生**；手动改库/换模板后 `update_terms.py --vault "<VAULT>" --rebuild` 刷新。
- 原文不另存为笔记：归档 PDF 即原文；机器复用看 `content/<pid>.txt`。
- 构造标记 `<!--…-->` 仅用于填充定位，收尾 `strip_markers.py` 去掉。
- 图策略：正文原位忠实全量；notes 只挑关键图。诚实：公式/表格能可靠转写就转，否则留图兜底；无 DOI 标 `["pdf"]`。
- **抽完图必须看一眼总览图**：`contact_sheet.py "<clusterDir>"` 出 `images/_总览.png`，一屏核对。覆盖检查只能查「漏没漏」，查不出「切歪了」——顶部被切掉图例、跨栏图只剩半幅、复合图裁成碎片，这三类**全部通过 lint 却是废图**，只有看才发现。脚本侧已加图质检查（近乎空白 / 区内无图形墨迹）兜住最明显的两类，其余靠这一眼。
- **改过抽图算法就全库盘一遍**：`audit_images.py --vault "<VAULT>"` 回 PDF 重扫图注对账，找出算法改进前入库、至今仍漏图的旧论文（`lint_cluster` 读的是当年写下的覆盖结论，不会自动复查）。
- token 最耗在 Luna Max 的全文翻译；长输出本身仍需生成，但启动规则、重复全文读取和英文从零重建都不应再占时间。主代理分析/学习卡是核心，不下放、不压缩。
- **验收口径诚实标注**：只有实际执行 `ingest_prepare.py --pdf <原始PDF>` 起跑的测试，才叫“完整 PDF 工作流/端到端评测”。复用既有 `.txt/.tables.md/.images.md` 的测试只能叫“部分内容角色评测”，不得拿它宣称验证了 PDF 抽取或总耗时。

## 依赖（自包含）

- Python3 + PyMuPDF(fitz) + requests + Pillow + **pymupdf4llm**（版面级抽图第一道防线，也是 `extract_tables.py` 抽表的唯一依赖；缺失时 `pip install pymupdf4llm`，装不上也能降级运行——抽图退回图注裁切，抽表退回译者手搓）。`format_refs.py` 需 pandoc（缺失时脚本会给安装指引）。
- 换机先安装依赖并配置 CLI：脚本对 `90_系统/` 等目录自动建目录（空库可跑）；`SKILL_DIR` 以**本文件实际所在目录**为准。联网项：doi_enrich/verify_bib 用 Crossref，citation_radar 用 OpenAlex，CSL 样式下载带国内可达镜像——均可离线降级（`--no-crossref`/跳过）。
- **脚本全部随技能自带**于 `<SKILL_DIR>/scripts/`：编排入口 `ingest_prepare.py` / `ingest_finish.py`；另有 `scan_inbox · doi_enrich · generate_cluster · extract_images · extract_tables · reextract_images · contact_sheet · audit_images · update_terms · strip_markers · delink_unresolved · fix_article · build_refs · build_citation_gaps · citation_radar · lint_cluster · verify_bib · format_refs · restructure · move_cluster · check_links · fix_glossary_links · cache_fulltext · build_index · build_bib · term_lint · topic_lint`；内容计时/C 档门禁用 `ingest_stage`，A/D/C 最小任务包用 `build_agent_brief`，单篇长文 A 的独立分片与原子合并用 `luna_a_parts`；批量作业另有 `prep_article_en`（英文正文草稿生成，把 dump 的机械活确定性做掉；`--redo-list <文件>` 才会覆盖已有英文正文，**防止误删人工校订过的版本**；`--promote-clean` 仅严格零警告时晋级）、`lint_en_draft`（草稿**入库前**质检，口径同 web_lint；`--fail-on-warnings` 用于严格晋级；`--list-out <路径>` 让 Python 直接写 UTF-8 清单，绕开 PowerShell 重定向把 UTF-8 当 GBK 解的坑）与 `workboard`（多子代理任务板）。`<SKILL_DIR>/assets/publisher_marks.json` 是首页出版社商标的指纹名单。保留整个 `skills/` 目录（包括 `shared/`）；前端目录须包含质检、同步与数学渲染资源。
- 配置：`<skill>/config.json`（`vault` + `wenshu`）。子代理与主代理同模型家族。
