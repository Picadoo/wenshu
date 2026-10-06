# 逐步流水线（①–⑪）

`ingest_prepare.py` / `ingest_finish.py` 是编排入口，正常入库只需这两条。**本文件是脚本失败时手动逐条跑的展开版**，以及各步骤的参数细节与坑位说明。

全程 UTF-8；subprocess 调脚本；读写 `encoding='utf-8'`；Windows stdout 先包 UTF-8。

## ① 扫描 + 指纹去重

```bash
python "<SCRIPTS>/scan_inbox.py" --vault "<VAULT>"
```
输出新论文 JSON（按 `sourceHash` 跳过已入库）。默认收件箱 `<VAULT>/PDFs`。

## ② DOI 增强

```bash
python "<SCRIPTS>/doi_enrich.py" --pdf "<pdf>" --out "<tmp>/meta.json"
```
产出标题/作者/期刊/卷期页/被引/OA/concepts/`suggestedId`/`suggestedFolder`/`detectedSourceLanguage`/`metadataSources`。无 DOI 自动降级 `["pdf"]`。

## ③ 定领域 + 定 pid/文件夹 + 译标题

- **领域**：先看 `Papers/` 下已有文件夹（含 `大类/子类`）→ 用 `concepts`/主题判断新论文能否归入已有领域；能就用现成的。**归不进=全新题材时，别丢「其他」**——据 concepts 起一个简洁中文领域名（可 `大类/子类`，如 `滑坡/易发性评估`），**先向用户确认**，确认后 `--domain` 直接用它（自动建新文件夹）。「其他」只留给确实无法归类的。
- **pid** = 「作者年份 中文短题」（可读，如 `Example2024 示例论文`；`--paper-id` 传它）；实在没有合适中文才退回 `meta.suggestedId` 英文 slug。
- **文件夹** = `meta.suggestedFolder`（作者年份 + 英文全标题）。
- 主代理把标题快速译中文作 `--translated-title`。

## ④ 生成集群 + 归档 PDF

```bash
python "<SCRIPTS>/generate_cluster.py" --paper-id "<meta.suggestedId>" --folder-name "<meta.suggestedFolder>" \
  --domain "<domain>" --pdf "<pdf>" --meta "<tmp>/meta.json" --vault "<VAULT>" \
  --translated-title "<中文标题>" --mode "<NOTE_MODE>" --archive move
```
建骨架：index 外露在子类层 `<pid>.md`，正文/notes/pdf 收进 `content/`，images 独立；归档 PDF 并把全文 dump 成 `content/<pid>.txt` 缓存（0 token，`--no-fulltext` 关）。`notes` 默认含 ✍️ 写作逻辑（`--no-writing-logic` 关）。返回 JSON 含 `notes.*`/`pdfPath`/`fulltextPath`/`contentDir`/`imagesDir`/`imageIndexPath`。

## ⑤ 提取图片

用归档后的 PDF（`ingest_prepare` 已做）：
```bash
python "<SCRIPTS>/extract_images.py" "<pdfPath>" "<imagesDir>" "<imageIndexPath>" --prefix "<pid>"
```

**优先级（2026-08-31 起以图注为主，与早期版本相反）**：全 PDF 扫到 **≥3 条图注**就走 **图注锚定裁切**为主路径 → 版面级（pymupdf4llm）降为**补无图注图区** → `get_images` 位图兜底。图注少于 3 条的文档（报告、幻灯、无图注扫描件）仍是版面级优先。

为什么倒过来：版面模型把跨栏复合图**拆成面板**，碎片一旦配上图注就占住了那个图号，覆盖检查以为「已覆盖」，正文于是挂上半幅图——Example2024 的 Fig 13 就这么只剩一半。图注路径按图号整幅裁，命名也确定（`page{页}_fig{图号}`），正文嵌入映射不再有歧义。

- **图注裁切**：按栏找 Figure/Fig/表/图 N；下沿用「Figure N」那一行的 y0，避免 (a)(b)/xlabel 跟图注粘块时切掉坐标轴；矢量曲线靠这条；图号 >99 视为年份误匹配丢弃；OCR 把 Fig. 1 认成罗马字母 `Fig. I./ll.` 的老扫描件已容错换算。
- **上沿怎么定**（切顶的毛病都出在这）：页眉下缘定地板（**不是**固定 72pt——版心从 55pt 起的期刊会把图例整条切掉）→ 遇通栏正文块则压到其下方 → 最后按区内**矢量/位图墨迹起点**收紧。判「是不是正文」看两侧是否内缩：正文左缘与栏对齐，居中的图例、轴标题不算边界。
- **跨栏判定**：图注宽度 ≥52% 页宽，**或**图注跨过版心中线，**或图注正上方、且与图注有横向重叠的那一块图跨过版心中线**，即按通栏裁。跟图走、不跟图注走——Frontiers 把跨栏图的图注左对齐挤在左栏（Example2024 Fig.2/3）；并排两栏图（Fig.10/11）各跟自己的图注重叠，不会合成一张。
- **补图去重**：版面级补跑时改用 `pic` 前缀命名，并跳过 ① 已按图号裁出的图号 ② 有 60% 以上面积落在已裁区内的重复块。

**90 年代扫描版论文（带 OCR 文字层）可直接走全流程**：文字层供全文 dump/翻译，抽图按 OCR 图注坐标裁扫描图区，无文字层的哑扫描件才需要先 OCR（技能不内置）。重抽会清掉同 prefix 旧 png/jpeg。

- `--prefer-layout`：回到版面级优先（图注解析不可靠的文档用）。
- `--no-layout`：完全跳过版面级，只走图注裁切。

**首页出版社商标自动拦截**：刊头横幅（宽高比 ≥3.5）、侧边竖条（≤0.35）、出版社徽标/CrossMark 徽章（≤260×260）在**首页**一律不入库；另有 `assets/publisher_marks.json` 的 dHash 指纹名单兜底（汉明距离 ≤6 即判定）。**只在首页判定**——正文页里同样细长的图往往是真的流程图或色标条。图文摘要（graphical abstract）也常出现在首页且没有图注，几何粗筛与指纹都不命中就放行，宁可多留一张也不能吞掉图文摘要。新发现漏网商标时，把它的 dHash 补进名单即可。

**不漏图三道防线**（脚本内建，无须自己数）：
1. 抽完后全 PDF 扫一遍图注得「期望集」，与实际抽出**按图号精确对照**（layout 图的图号从配对图注解析；双图页漏一张也逃不掉）；
2. 漏号先**图注裁切补漏**（裁出真图区、与 layout 文件撞名自动挂 `_clip`），仍裁不出才**整页渲染兜底**（`source: page-fallback`，宁可含正文也绝不静默丢图，索引里标「建议人工裁切后替换」）；
3. 覆盖结果写进 `<pid>.images.md` 的「## 覆盖检查」段 + stdout 末尾 `COVERAGE {json}`，`lint_cluster` 读该段——覆盖缺失=错误、整页兜底=警告。

看到兜底图时：用 fitz 手动裁出图区替换同名文件即可转正（图注行 y0 定下沿）。

**图质检查（查「切歪了」，覆盖检查只查「漏没漏」）**：每张裁切图都过一遍非白像素占比与区内有无图形墨迹，异常写进 `<pid>.images.md` 的「## 图质检查」段和 `COVERAGE.suspect`：

| 标记 | 含义 | 怎么办 |
|---|---|---|
| 近乎空白 | 非白像素 <0.4%，裁到空白带/页边了 | 重抽；仍空白则人工裁 |
| 区内无图形墨迹 | 裁出来只有文字，多半图注是正文里的交叉引用（"…see Fig. 14）"）被误认成图注 | 确认后删掉该图与 images.md 条目 |
| 整页兜底 | 整页渲染，含正文 | 人工裁出图区替换同名文件 |

`lint_cluster` 只在**正文真的引用了**这张图时报警告——未引用的可疑图不打扰。自动覆盖检查仍不能证明裁图完整，应看核对图。

**抽完先看一眼总览图**（脚本能查漏、查不出「切歪」，那只有看）：

```bash
python "<SCRIPTS>/contact_sheet.py" "<clusterDir>"            # 正文引用的图，按出现顺序
python "<SCRIPTS>/contact_sheet.py" "<clusterDir>" --all      # images/ 全部（审无图注新图）
python "<SCRIPTS>/contact_sheet.py" "<clusterDir>" --flagged  # 只看图质检查标了问题的
```

默认输出 `images/_总览.png`。一屏就能看出谁顶部被切、谁只剩半幅面板、谁是碎片——比逐张点开快一个数量级。

**重抽已入库论文**（换抽取算法后批量刷新旧论文）：
```bash
python "<SCRIPTS>/reextract_images.py" "<clusterDir>" [--prefer-layout] [--no-layout] [--dry-run]
```
自动：重抽 → 解析新 `<pid>.images.md` 图注建「图键→新文件名」表 → 按旧正文里每个嵌入下方的图注编号把 正文/正文.en/notes 的嵌入改写到新名（旧图组多张映射到同一新图自动去重）。

**报告必须人工收尾**：⚠️ 无图注新图＝逐张看图（用 `contact_sheet.py --all` 一次看完）——出版社商标/封面→删（同步 images.md 条目与总计）、复合图拆出的面板→连续嵌入共享一条图注（图组）、与已配对图同内容→删重复；⚠️ 未映射旧嵌入＝人工找新名或补裁。收尾必跑 fix_article + lint_cluster + sync-vault 验收。

**改了裁切规则要跑回归**，别只看手上这一篇：把若干 PDF 用新旧两套规则各抽一遍到临时目录、出两张总览图对照。回归应覆盖已经确认存在问题的代表版式，避免无必要的全库重抽。

**改完算法要全库盘一遍**，把该重抽的旧论文挑出来：

```bash
python "<SCRIPTS>/audit_images.py" --vault "<VAULT>"          # 全库，几十秒
python "<SCRIPTS>/audit_images.py" --vault "<VAULT>" --paper <pid子串> --all
```

它**回 PDF 重扫图注**跟磁盘、正文对账，不看 images.md 的历史结论——`lint_cluster` 读的是那次抽图当时写下的覆盖结果，算法改进后旧论文不会自动复查，漏的图就一直漏着。有疑似漏图时退出码 1。

## ⑤b 提取表格（`ingest_prepare` 已自动跑）

```bash
python "<SCRIPTS>/extract_tables.py" "<pdfPath>" "<contentDir>/<pid>.tables.md" --pid "<pid>"
```

为什么要有这一步：PDF 机器 dump 会把表格打散成一列一列的碎字符，表体数字整段丢失，于是**同一批数字被 AI 手工重建两遍**（中文正文一遍、英文正文一遍）。而 `pymupdf4llm` 的版面模型本来就能把表格解析成 Markdown（技能早已依赖它做版面级抽图），只是从没拿它抽过表。

抽出来的是**英文原表**：英文正文原样注入（`prep_article_en.py` 自动做），中文正文只需把表头/行标签译成中文、表体数字照搬。

**抽不干净的如实标注、不猜**：合并单元格、行列数对不上都打「需人工核对」并保留原始 `<br>`。宁可标出来，也不静默编一张看着整齐的假表。文末有覆盖检查段（抽到哪些表号 / 正文提到却没抽到哪些），stdout 末行 `TABLE_COVERAGE {json}` 供编排判定，`ingest_prepare` 把它写进 job 的 `tableCoverage`。

**抽表失败不阻断入库**：综述、纯图文论文本来就没表；`pymupdf4llm` 没装同理——退回「译者照 PDF 手搓」的老路，慢但不断。

**改了抽表规则要全库刷一遍**（老论文不会自动复查）：

```bash
python "<SCRIPTS>/extract_tables.py" --scan "<VAULT>/Papers"           # 只补缺的
python "<SCRIPTS>/extract_tables.py" --scan "<VAULT>/Papers" --force   # 规则改了，全部重抽
```

收尾会打一行总账（共几张表、逐格可用几张、需核对几张、正文提到却没抽到几张）。**「正文提到却没抽到」是最该盯的一栏**——常见漏抽版式包括：① pymupdf4llm 见大号字就渲成标题，表题变成 `###### **Table 2**`，标签正则被 `#` 前缀挡在门外；② Springer 系把表题排进表格**首列**，版面模型于是把它折进 (0,0) 格（`|**Table 3**Mass-based size<br>fractions…|Case|…`），根本不成行。

## ⑥ 内容角色填充（**两拍，翻译与分析分权**）

**⑥a 并行**（写不同文件不冲突）：
- Luna Max 翻译档（A 档，`gpt-5.6-luna` / `max`）→ `<pid>.正文.md`
- 主代理分析档（B 档）→ `<pid>.notes.md` + `terms.json` + 回填索引 `<pid>.md`

派 A 前先运行 `build_agent_brief.py --job <job> --role A`，把生成的最小任务包交给 `fork_turns: none` 的子代理。子代理不得再加载完整技能/提示词/前端契约；全文按顺序分段且每个区间只读一次，避免大段并行输出截断后的复读。

**长文可选章节并行 A**：清洁全文约 1000 行以上、至少能同时派 3 个 Luna，且用户优先等待时间而非总 token 时，改用：

```bash
python "<SCRIPTS>/luna_a_parts.py" prepare --job "<job>" --out-dir "<_work/a-parts/<pid>>" --parts 3
# fork_turns:none 并发执行 manifest.parts[*].briefPath；每个代理只写自己的 outputPath
python "<SCRIPTS>/luna_a_parts.py" merge --manifest "<_work/a-parts/<pid>/manifest.json>"
```

子代理读完局部源文与图表索引后直接写一次，不做 `Test-Path`、重读、统计或局部 lint；父代理统一 merge。merge 会先备份目标，按首次出现者确定性去掉双栏 dump 在章节边界造成的重复图表，规范编号标题层级，并检查全量图表、公式配对、TODO、H1、亮点和摘要；失败时不覆盖目标。并行只用于缩短等待时间，不应视为节约总开销。

**⑥b A 档完成后**（英文源论文才有这一拍；`detectedSourceLanguage==zh` 时 generate_cluster 不建 `.正文.en.md`，整拍跳过）：

```bash
python "<SCRIPTS>/prep_article_en.py" --vault "<VAULT>" --only "<pid>" --promote-clean
```

→ 若输出显示“严格晋级入库”，直接跳过 D；否则再派 **Luna Max 英文草稿校订档（D 档）**，只按 TODO 与严格 lint 明细修补 `_work/en-draft/<pid>.正文.en.md` 后入库。

派 D 前运行 `build_agent_brief.py --job <job> --role D --draft <草稿>`。它会重跑严格草稿 lint 并把残留写进任务包；若已 `0 error / 0 warning` 则打印 `SKIP_D` 并以退出码 3 拒绝生成任务，不能启动 D 做重复验收。

**为什么英文侧要等中文侧，而不是三个一起并行**：公式与语言无关，同一条公式转两遍 LaTeX 是纯返工。脚本按公式号把 A 档已转好的 `$$…$$` **原样搬进英文草稿**（`--no-transplant` 可关），表格则直接注入 ⑤b 抽出的英文原表。正确的公式与表格可由脚本复用，但残留 TODO 仍须逐项处理。

代价是英文侧从「与 A 并行」变成「跟在 A 后面」，但换来的是 D 档的活缩到接近于零——而原来的 C 档要从 dump 从零重写整篇、还要自己啃 14 条乱码公式和 6 张碎表。**总时长与总 token 都是降的。**

从零写英文（C 档）不是普通分支。只有脚本崩溃、无分页标记、双栏读取顺序整体不可恢复等“草稿整体不可用”时，主代理才可先把具体证据写入 job，再派 C：

```bash
python "<SCRIPTS>/ingest_stage.py" --job "<job>" allow-c-fallback --reason "<具体失效证据>"
```

job 的 `englishWorkflow.cFallbackReason` 为空时禁止 C；几条 TODO 或 warning 必须走 D，不得让 C 与 A 并行。

内容阶段耗时也写回同一 job：

```bash
python "<SCRIPTS>/ingest_stage.py" --job "<job>" start  --stage lunaA
python "<SCRIPTS>/ingest_stage.py" --job "<job>" finish --stage lunaA
# 同理：mainAnalysis / prepEnglish / lunaD
```

`ingest_prepare` / `ingest_finish` 的确定性子步骤会自动写 `timing.prepare/finish`。复盘并行角色时另读真实子代理会话：墙钟 = 最早 `started_at` 到最晚 `completed_at`，总计算 = 各 `duration_ms` 之和。复盘速度时以这些记录为准。

Prompt 模板见 `references/prompts.md`。

## ⑦ 术语库对账（串行！）

```bash
python "<SCRIPTS>/update_terms.py" --terms "<tmp>/<pid>.terms.json" \
  --paper-id "<pid>" --vault "<VAULT>" --notes-note "<notes.notes>"
```
查重入库 + 再生术语笔记/总览 + 回填 notes 术语表。批量多篇此步**一篇一篇串行**（registry 不并发写）。回填靠 notes 里的 `<!--TERMS_START-->` / `<!--TERMS_END-->` 标记定位，标记缺失则回填不上。

## ⑧ 回填索引

**主代理在 B 档直接回填**（prompts.md B 档第 4 条）：替换 index 里 `<!--SCI_Q-->`/`<!--TLDR-->`/`<!--SCORE-->` 三处，改 frontmatter `status: analyzed`、`quality_score`，并把 `topics` 每个写成 `tags` 里的 `主题/<词>`（喂文枢标签墙与搜索——主题标签 = 跨大类按主题找论文，取自作者关键词归一的中文词表）。

主代理在完成分析后自检 `{sciQuestion,tldr,score,topics}` 与 index 实际内容一致；占位文字仍在时不得进入收尾。

> 为什么由主代理直接写：分析结论与索引卡片来自同一判断过程，转交会增加漏填和语义漂移。`<pid>.md` 由主代理独占，Luna Max 的 A/C/D 档不碰，并行也不会打架。

## ⑨ 收尾清理 + 参考文献 + 质检

```bash
python "<SCRIPTS>/strip_markers.py" "<index>" "<article>" "<articleEn>" "<notes>"
python "<SCRIPTS>/delink_unresolved.py" "<VAULT>" "<notes>"
python "<SCRIPTS>/build_refs.py" --vault "<VAULT>" --article "<article>" --inline
python "<SCRIPTS>/fix_article.py" --vault "<VAULT>" [--paper "<pid>"] [--dry-run]
python "<SCRIPTS>/lint_cluster.py" --vault "<VAULT>" --paper "<pid>"
```

- `strip_markers`：去构造标记。`articleEn` = generate_cluster 返回的 `notes.articleEn`；中文母语论文无此文件则不传。
- `delink_unresolved`：清掉子代理给未入库论文/生造术语加的悬空 `[[ ]]`（Web 会把悬空链接降级纯文本并告警）。
- `build_refs`（**确定性脚本、零 token**）：从 `content/<pid>.txt` 提取原文 References → 解析条目（`[N]` 序号与 author-year 两种体裁；剔页眉/页码/混入图注）→ 条目挂链接（印了 DOI 直接链，没印走 Crossref 反查，严校验：年份+一作+卷页/标题重合度，宁缺勿滥，瞬时网络失败不缓存）→ **已入库论文自动 `📥 [[pid]]` 互链**（前端渲染成「引用」徽标）→ 写进正文末尾 `<!--REFS_AUTO-->` 标记区（幂等，重跑替换）。
  - `--inline` 仅对 `[N]` 体裁把正文引用改成同文件跳转 `[[#^ref-N|N]]`——**文枢显示为可点击的「作者+年份」，不是数字上标**，悬浮预览文献条目、点击跳参考文献。支持 `[N]`、`[N,M]`、`[N-M]` 区间（区间只链两个端点，避免整段挤满徽标）。**严禁外面再包方括号**（`[[[…]]]` 嵌套是历史 bug，web_lint 会警告；表格行/公式/代码块/已有链接自动跳过——表格里禁竖线别名）。`式 (N)` / `Eq. (N)` 前缀的数字有护栏、不会被误链成引用。
  - 写前自动备份到 `%TEMP%/build_refs_backups/`。Crossref 结果缓存 `90_系统/_引文DOI缓存.json`（可手改纠错；缓存查询不受断网开关影响）。断网用 `--no-crossref`。批量回填 `--all`。已有手写参考文献章时默认 `skip-existing` 不动它，确认要换成带锚点的自动版用 `--force`。
- **引用边保鲜**：新论文入库后，老论文引它的地方不会自动长出 `📥` 链——收尾再跑一次 `build_refs.py --vault "<VAULT>" --all --no-crossref`（纯缓存+库内重匹配，不联网、秒级，只有产生新互链的文件才被改写）。
- `fix_article`（**确定性纠错**，lint 之前先跑）：机械格式问题全自动修（H1 后缀/「要点」标题/三层括号/图片名与宽度/表格空行与裸 `<>`/连续空行/被误链成引用的公式号/**英文正文里原刊没印的 `## Highlights` 整节**），幂等、写前备份 `%TEMP%/fix_article_backups/`；`$$` 奇数、缺图注、通俗摘要只报告。ingest_finish 已内置。
- `lint_cluster`（**vault 侧质检**）：占位符/构造标记残留、图片嵌入指向不存在文件、抽图覆盖缺失（E）/整页兜底（W）/正文引用了裁切可疑的图（W，读 images.md「## 图质检查」段）、`$$` 未闭合、缺参考文献、表格裸 `<`/`>`、H1 后缀、前置块、说明块吞正文、公式号被链成引用、残留 `cards.md`……**有错误必须修完再收工**。全库体检去掉 `--paper`，加 `--report` 写 `90_系统/_质检报告.md`；退出码非 0 = 有错误。
- **英文正文 Highlights 按 txt 双向校验**：拿同集群 `<pid>.txt` 当事实源——原刊印了（Elsevier 的 `Highlights`／AGU 的 `Key Points`，均只认独立成行的标题）而英文正文没有 = 警告；原刊没印却写了 = **错误**（英文侧是原文重排，禁提炼；要点归中文正文 `## 亮点`）。旧口径「原文无则从 Abstract 提炼」曾诱导出 18 篇冒充原文的自撰要点，已作废。

## ⑩ 重建 AI 检索层 + 同步文枢

每次增删/改名后都跑；`ingest_finish` 已做。

```bash
python "<SCRIPTS>/build_index.py" --vault "<VAULT>"
python "<SCRIPTS>/build_bib.py" --vault "<VAULT>"
python "<WENSHU>/scripts/sync-vault.py" --vault "<VAULT>"
python "<SCRIPTS>/build_citation_gaps.py" --vault "<VAULT>"
```

- `build_index`：重建**两层检索 digest**——轻量版 `90_系统/_检索速览.md`（每篇一行：题｜一句话｜主题｜评分｜→路径，供 AI 一次 Read 读完全库做语义匹配）；全字段版 `_检索索引.md`（多了术语/方法名列，供单文件 grep 方法名一击命中）。
- `build_bib`：重建 BibTeX 文献库 `90_系统/_文献库.bib` + 回填稳定 `citekey`（=pid 前缀+标题实词）到各 index frontmatter。citekey 同时是文枢 slug/分享链接的来源；差异即重盖、幂等；自动套用 `_bib补丁.json`。**citekey 回填必须先于质检**，否则 lint 报「缺 citekey」假警告。
- `sync-vault`：把集群拷进 `wenshu-pro/public/vault/` 并重写 `generated-catalog.ts`；自动调用 `web_lint.py` 按 `docs/content-contract.md` 验收——正文 H1 不加「（中文翻译）」；Highlights→`## 亮点`（禁「要点」）；英文禁 `## Key Points` / 通俗摘要 / 作者 `^{1}`；英文源论文必有 `.正文.en.md`；图后紧跟图注段。
- `build_citation_gaps`：重建**引文缺口榜** `90_系统/_引文缺口榜.md`——全库参考文献汇总去重，被 **≥3 篇**共引而未入库的排成阅读/下载队列，领域必修课自动浮出；零联网、秒级。写综述加 `--under "大类/子类"` 或 `--seeds "pid1,pid2"` + `--min-count 2` 出主题榜 `_引文缺口榜_<范围>.md`，成稿后可做漏引审计。

### 按需工具（非每次入库）

- **投稿级引用**：`verify_bib.py --vault "<VAULT>"`（元数据核对：全库 DOI 逐条比 Crossref——条目类型/卷/期/页/年自动补丁进 `_bib补丁.json`，标题对不上=DOI 挂错者只报不改 → `_bib核对报告.md` 的 ⚠️ 档人工过）；`format_refs.py --style gbt7714|elsevier-num|agu|… --keys "k1,k2"`（按期刊格式出参考文献列表：pandoc citeproc + CSL 官方样式约一万种，首次自动下载缓存 `90_系统/_csl样式/`，`--list-styles` 看别名）。Word 长期写作走 Zotero，用户说明书在 `<VAULT>/90_系统/_Zotero对接说明.md`。
- **引用雷达**（前向追踪）：`citation_radar.py --vault "<VAULT>" --under "<大类/子类>"`——OpenAlex 查「谁在引用库内种子论文」，默认近 3 年、命中 ≥2 篇种子上榜、已入库自动排除 → `90_系统/_引用雷达_<范围>.md`，综述「最新进展」取材处；与缺口榜（向后滚雪球）互为镜像。DOI→OpenAlex ID 缓存于 `90_系统/_openalex缓存.json`。
- **术语卫生检查**：`term_lint.py --vault "<VAULT>"` 扫近重复术语 → `90_系统/_术语去重候选.md`（**仅提示**；人工挑确属重复的再合并，**务必排除反义/不同概念**：如 resolved↔unresolved、prolate↔oblate、Reynolds↔particle-Reynolds）。
- **改分类**（AI 分错领域/后期调整）：`move_cluster.py --vault "<VAULT>" --pid "<pid>" --new-domain "大类/子类"`——pid/citekey 不变，互链与分享链接不受影响；收尾重跑 build_index + build_bib + sync-vault。
- **改 pid**：`restructure.py`（pid 就是论文互链 `[[pid]]` 的目标名，改名要全库同步）。

> 📦 系统/工具文件统一放 `<VAULT>/90_系统/`，绝不丢库根。`_检索速览.md`/`_检索索引.md` 输出纯文本标题 + 行尾 `→ 路径`（定位靠路径不靠双链）。

## ⑪ 清理临时文件

`meta.json` / `terms.json` 可留在 `90_系统/_ingest/` 备查，保留集群与 PDF。

**绝不盲删收件箱**：`--archive move` 已把处理过的原件移走；唯一可能残留是「受保护原件（那篇归档的是解密副本）」——只按**确切文件名**删它**那一个**，**严禁 `glob("*.pdf")` 删整个收件箱**（处理期间用户随时会往里加新论文，盲删会误删未处理的论文）。
