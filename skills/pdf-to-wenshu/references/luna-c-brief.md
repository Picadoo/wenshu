# Luna C 异常兜底简报

这是确定性英文草稿整体失效后的异常重建任务。下面已包含所需规则；不要读取 `SKILL.md`、完整 `references/prompts.md`、`pipeline.md` 或 `content-contract.md`。

## 已登记的启用理由

`{{C_FALLBACK_REASON}}`

## 写权与输入

- 论文：`{{PAPER_ID}}`
- 只允许写草稿：`{{DRAFT_PATH}}`
- 主要原料：`{{SOURCE_PATH}}`
- 图索引：`{{IMAGE_INDEX_PATH}}`
- 表索引：`{{TABLE_INDEX_PATH}}`
- 公式必要时核对：`{{PDF_PATH}}`

不得修改中文正文、notes、terms、index、job、共享索引或前端。final 会自动返回父代理，不要额外发消息。

## 产出边界

- 按原文真实结构重排英文，不翻译、不摘要、不润色；原刊没有 Highlights 就不添加。
- 图按图索引原位嵌入并紧跟原文英文图注；表格直接取表索引的英文原表。
- 公式转 LaTeX；只在全文损坏的对应页读取 PDF，不逐页通读。
- 不手写 References，不添加 wikilink 或中文注释。
- 全文按顺序每次读取不超过 400 行，每个区间只读一次；不要并行读取多个大区间造成截断复读。
- 尽量一次写完，最多按连续章节分 2--3 次追加；最后只跑一次严格草稿 lint。

最终回复只报告目标路径、结构统计、严格 lint 结果和无法恢复的源材料问题。
