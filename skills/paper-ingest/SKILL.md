---
name: paper-ingest
description: 将论文 PDF 入库文枢，生成忠实的双语全文、图表公式、学习笔记与术语，核对并同步；查重后复用已有条目，v2 维护只修相关片段。旧版 job 续跑使用 pdf-to-wenshu。
allowed-tools: Read, Write, Bash
---

# paper-ingest · 文枢入库

产出忠实、可读的论文全文、图表、笔记与术语。默认以减少重复处理为提速方式：正常文字复用抽取，易错内容核对原页。较强模型核准源稿，翻译模型仅翻译锁定稿。配置路径由 `skills/shared/config.py` 统一按仓库根解析；保留整个 `skills/` 目录。路径取 `config.json`，正式库为 `vault/`，正文格式遵循 `wenshu-pro/docs/content-contract.md`。

## 1 查重与抽取

先在 `wenshu-pro/public/vault/catalog.json` 按 DOI 查重；无 DOI 核对原题、作者、年份。已入库直接复用，不重新下载、抽取或翻译；用户要求修复才进入局部维护。`finish.py` 也会阻止已有 pid/DOI 的重复装配。

新论文运行：
```bash
python skills/paper-ingest/scripts/extract.py --pdf "<file.pdf>" --work "_work/lite/<Key>" --vault "<V>" --key <Key>
```
先核首页版本、真实摘要和末页/参考起止，确认来源完整，区分出版版、预印本和网页打印件。抽取缺字或疑似扫描页才处理该页；当前脚本不带自动 OCR，必要时用已有 `pdftotext` 辅助，不给正常 PDF 同时跑多套提取器。

## 2 一次整理并核准源稿

读一次 `brief.md`，沿连续章节使用 `columns.md`；`fulltext.txt` 仅用于异常页兜底。看原页结构与跨栏/跨页衔接，同时整理正文与 `out/layout.json`，普通文字直接复用原句，不逐字重抄。乱码、乱序、疑似漏段才扩大对应片段核查，禁止脚本猜语义、生成译文或凑字数。

必须核对的易错内容：
- 原题、作者、单位、真实摘要、原刊 Keywords/Highlights、完整章节与附录。中文原刊直接整理 `zh.md`，不要求英文全文。
- 实际核准为专栏导言且原刊无摘要时，`meta.documentType=editorial`，完整保留导言，不编造摘要；普通研究论文仍要求真实摘要。
- 所有公式的上下标、正负号、分母、指数、log/ln；表格数字、单位、脚注。公式可编辑并放在引出段落后，保留完整原号（含 `2.1`、`A1`）。看不清放大该区域，不猜填。
- `refs.md` 逐条对参考页核对一次：原刊号、条目身份、边界、首末条及总数。数字制不去重或重编号，原刊重复条目保留；作者年份制防误合/误拆。致谢等后置事项不混入末条。finish 将同一清单复制到两正文末尾。

`layout.json` 保存 `headings`（level/title/page）、`figures`（num/page/完整原文 caption）、`tables`（num/page/title）、`equations`（完整 num/page）及 `notes`。正则粗数只提醒；确实跳号才在 `verify_overrides.json` 登记类别、编号和原因。原刊数值矛盾忠实保留，在笔记说明。

```bash
python skills/paper-ingest/scripts/cutfigs.py --work "_work/lite/<Key>" --embed
# 看已有 images/_review_figN.png，一次核对原页画框与实际裁图。
python skills/paper-ingest/scripts/figtools.py review --work "_work/lite/<Key>" --num N --note "pP 全部子图、轴、图例完整且图号对应"
python skills/paper-ingest/scripts/translation.py review-source --work "_work/lite/<Key>" --note "已核对原页结构、公式、表格及参考；疑点及页码…"
```
只修坏图：`figtools.py crop --work … --page P --num N --box x0,y0,x1,y1`；像素框按 `stats.renderDpi`（旧区默认100），pt 框加 `--unit pt`。重裁后重新查看/确认并 embed；正确裁图不重裁，已有核对图不重复 compare。`figcut.json` 保存 sourcePage、pt bbox、精确 file 与 reviewed/reviewNote；重裁会撤销确认。

`review` / `review-source` 只能在实际原页核对后使用。源审核检查 KaTeX 并保存正文/清单快照，修改会使确认失效；能渲染和数量正确都不能证明抄对。尚有无法辨认的内容就不宣称已核准。

## 3 并行翻译与简洁笔记

源稿核准后，同时最多 2 个内容子代理（含无头 CLI）：一个翻译，另一个按 `analysis-brief.md` 写 notes/terms/fields。任务只给负责内容和路径，不加载整段历史或重复核全篇。共享术语、索引和发布由主代理串行写。

```bash
python skills/paper-ingest/scripts/run_agent.py --work "_work/lite/<Key>" --stage translate
```
默认沿用 config 的 runner/model（默认 Codex CLI / CLI 已配置的模型），翻译 low 推理；Codex 接收纯文本锁定稿和只读符号释义，不读写文件或处理 PDF。`run_agent.py` 已自动 prepare、merge、check；成功后不要重复执行。原生翻译代理使用 `translation.py prepare/merge/check`，只写 `translation/zh.locked.md`。

保护公式、图片、代码、参考和表格数据；token 必须恰好一次且保持顺序，失败不覆盖旧中文。摘要、方法适用条件和定量结论重点核对译文的数字、否定、比较与因果，普通叙述抽查；末尾不再重复全文逐句通读。保护检查不能证明翻译语义准确。

中文正文必须逐段完整翻译英文源稿，保留正文引文、推导、适用条件、讨论及附录；段落内部也不能概括、摘译或删句。检查时普通叙述抽查不改变全文翻译要求。“简洁”只约束学习笔记，提速依靠复用和减少重复操作。缺完整译文的存量条目不能作为全文完成交付；补齐内容后再报告。

笔记保留既有骨架，默认 3–5 条摘要要点、4–6 个问答、8–10 个核心术语；每小节简洁、有本文依据，数字与关键结论注明章节/图表/页码。作者结论与建议分开，公式解释放 notes，不补造正文公式。原刊无 Highlights 时分析任务写纯文字 `out/highlights.md` 并显式标明 AI 提炼；如它在自动合并之后才完成，只再 merge 一次插入，不重翻全文。

## 4 一次发布与交付

```bash
python skills/paper-ingest/scripts/finish.py --work "_work/lite/<Key>" --vault "<V>" --wenshu "<W>"
```
finish 已执行 verify、单篇严格 web_lint（零错误零警告）和同步，不再单独原样重复。只有 `status=ready` 且三项成功才报告完成；失败只修报错的内容，必要源稿修改重新核准后再运行，不能使用 `--force` 绕过。`--no-sync` 或 `assembled` 不等于正式完成。

不同论文生成相同 citekey 时，finish 在写库前阻止冲突；只给新条目设置独立 `fields.citekey`（小写字母数字、下划线或连字符），保留既有条目的标识与阅读链接，不改作者或题名来规避冲突。

使用既有服务打开 `http://127.0.0.1:8080<readingPath>` 并确认题名/内容；批量交付只开优先篇。文件面板 `queued` 不能视为显示成功。原 PDF、pid/citekey、reading、个人笔记、批注、生词和活动日志保留。

## 局部维护

已有 v2 条目复用 `_work/lite/<Key>/`，只改对应片段并受控更新正式生成文件，不重跑整篇抽取、术语合并或 finish。必要时翻译用 `--stage translate --repair-only`；源文改变后不可复用过期锁定稿，重新核准并 prepare，正确内容不循环重写。工作区图片前缀是 Key，正式库为 pid，按已有映射复制。没有工作区先定位原产物；只有旧 `.job.json` 续跑使用 [pdf-to-wenshu](../pdf-to-wenshu/SKILL.md)，不同时开两套流程。

改过哪个阶段就核对受影响内容；严格单篇检查通过后同步用 `--no-lint`，不重复全库检查、重建引用或计算额外哈希。Windows 显式 UTF-8，后台进程隐藏启动并记录 PID，结束只清理本次资源，保留既有阅读服务。依赖沿用现有工具，不新增框架、配置或 OCR 服务。
