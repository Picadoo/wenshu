# Luna D 最小任务简报

这是已生成英文草稿的局部校订任务，不是全文重建或技能编排。下面已包含所需规则；不要读取 `SKILL.md`、完整 `references/prompts.md`、`pipeline.md` 或 `content-contract.md`。

## 写权与输入

- 论文：`{{PAPER_ID}}`
- 只允许编辑草稿：`{{DRAFT_PATH}}`
- 通过严格验收后复制到：`{{ARTICLE_EN_PATH}}`
- 主要原料：`{{SOURCE_PATH}}`
- 图索引：`{{IMAGE_INDEX_PATH}}`
- 表索引：`{{TABLE_INDEX_PATH}}`
- 公式必要时核对：`{{PDF_PATH}}`

不得修改中文正文、notes、terms、index、job、共享索引或前端。不要探测消息工具；final 会自动返回父代理。

## 严格 lint 当前残留

```text
{{LINT_REPORT}}
```

## 任务边界

- 只修 lint 明细和草稿内 `TODO` 指向的残留，不通读或改写已经干净的正文。
- 不翻译、不摘要、不润色、不补写 Highlights；英文正文是忠实原文重排。
- 单位/作者信息只从全文第 1 页摘原文。缺图注只回全文找对应 Fig. 的原文英文图注。
- 已从中文正文对拷的 `$$...$$` 不动；只有 `<!-- TODO 式 (N) -->` 才核对对应 PDF 页。
- 已注入的英文原表不重建；只核对标为“需人工核对”的表或搬回 `## Unplaced tables` 下的表。
- 不手写 References，不加 wikilink 或中文注释。

## 收尾

只运行一次：

```powershell
python "{{LINT_SCRIPT}}" --vault "{{VAULT}}" --wenshu "{{WENSHU}}" --draft-dir "{{DRAFT_DIR}}" --only "{{PAPER_ID}}" --fail-on-warnings
```

只有退出码 0 且 `0 error / 0 warning` 时才把草稿复制到目标英文正文，并核对两文件哈希相同。不要再跑第二套全库 lint、`git status` 或重复复制。

最终回复只列实际修改、严格 lint 结果和目标路径。
