---
name: paper-ingest
description: 将论文 PDF 整理成忠实的双语全文、图表公式、学习笔记与术语，核对后发布到文枢文库。
allowed-tools: Read, Write, Bash
---

# PDF 入库

将一篇 PDF 整理成可阅读、可追溯的文库条目。原文整理与源页核对由具备视觉能力的主代理负责；翻译代理只处理核准后的锁定文本。内容格式遵循 [文库格式契约](../../app/docs/content-contract.md)，路径配置位于 `config.json`，相对路径按仓库根解析。

## 1. 查重并抽取

先在客户端生成的 `public/vault/catalog.json` 按 DOI 查重；没有 DOI 时核对原题、作者、年份。已存在则打开已有条目，避免重复导入。

从仓库根运行：

```sh
python skills/paper-ingest/scripts/extract.py --pdf "paper.pdf" --work "_work/Example2024" --vault "vault" --key Example2024
```

先核首页版本、真实摘要和末页，确认来源完整，区分出版版、预印本与网页打印件。`columns.md` 是主要正文原料，`fulltext.txt` 只用于异常片段；`pages/` 提供原页核对。脚本直接读取文字层，不含自动 OCR；扫描版需要先获得可靠文字层。

## 2. 整理并核准原稿

读取工作区的 `brief.md`，复用抽取原句，对照原页恢复双栏顺序、跨页衔接和章节层级，生成 `out/en.md` 与 `out/layout.json`。中文原刊只整理 `out/zh.md`，不编造英文全文。

必须核对题名、作者、单位、原刊摘要、Keywords/Highlights、全部章节与附录；原刊没有摘要的专栏导言不补造摘要。正文逐句完整保留，解释与建议写入笔记。

- 公式用可编辑 LaTeX，核对上下标、正负号、分母、指数和 log/ln，保留原刊编号。
- 表格用 Markdown，核对每个数字、单位与脚注。
- `refs.md` 对照参考页核对身份、边界、编号和总数；保留原刊重复条目。发布时中英文共用同一参考清单。
- `layout.json` 记录 headings（level/title/page）、figures（num/page/完整 caption）、tables（num/page/title）、equations（num/page）及 notes。图表公式编号保留章节号与附录字母。正则数量只作提示。

按核准清单裁图：

```sh
python skills/paper-ingest/scripts/cutfigs.py --work "_work/Example2024" --embed
```

查看生成的原页画框与裁图，确认子图、轴、图例、色条齐全。只重裁有问题的图：

```sh
python skills/paper-ingest/scripts/figtools.py crop --work "_work/Example2024" --page 5 --num 3 --box x0,y0,x1,y1 --unit pt
python skills/paper-ingest/scripts/figtools.py review --work "_work/Example2024" --num 3 --note "已对照第5页确认子图、轴与图例完整"
python skills/paper-ingest/scripts/cutfigs.py --work "_work/Example2024" --embed
python skills/paper-ingest/scripts/translation.py review-source --work "_work/Example2024" --note "已核对原页结构、公式、表格及参考条目"
```

`review` 和 `review-source` 只能在实际视觉核对后执行。源审核保存正文与清单快照并检查公式渲染；修改源文或重裁会使对应确认失效。看不清的内容先报告，不猜填或宣称已完成。

## 3. 翻译与学习笔记

英文原刊的源稿核准后运行：

```sh
python skills/paper-ingest/scripts/run_agent.py --work "_work/Example2024"
```

runner/model 取配置，默认 Codex CLI 的已配置模型与 low 推理。工具自动 prepare、merge、check；失败只修报错内容。也可由宿主翻译代理使用 `translation.py prepare/merge/check`，只写 `translation/zh.locked.md`。

公式、图片、代码、参考和表格数据被保护为 token，必须恰好一次且保持顺序。中文逐段完整翻译，不概括、删句或补造正文。重点核对摘要、方法条件、定量结论中的数字、否定、比较与因果，普通叙述抽查。token 检查不能证明语义准确。

翻译期间可由另一个内容代理按 `analysis-brief.md` 生成 `out/notes.md`、`terms.json`、`fields.json`，同时最多两个内容任务。默认 3–5 条摘要要点、4–6 个问答、8–10 个核心术语；数字和结论注明原文章节、图表或页码，作者结论与自己的建议分开。原刊无 Highlights 时可写明标注 AI 提炼的 `out/highlights.md`。共享术语与发布由主代理串行处理。

## 4. 检查并发布

```sh
python skills/paper-ingest/scripts/finish.py --work "_work/Example2024" --vault "vault" --wenshu "app"
```

该命令检查正文、单篇阅读格式并同步文库。只有 `status=ready` 且 verify、严格 web_lint 和同步成功才报告发布完成；`assembled` 或 `--no-sync` 不代表完成。数量、快照和结构正确不代替原页核对。

若 citekey 冲突，仅给新论文设置独立 `fields.citekey`，保留已有阅读链接。打开客户端确认题名、双语正文、图表与原 PDF 可访问。个人笔记、批注、生词和活动日志不得覆盖。
