# Luna A1 最小任务简报 · 英文正文重排

这是已准备好的单篇**英文正文重排**任务，不是 `pdf-to-wenshu` 的编排任务。下面已包含完成任务所需的规则；不要再读取 `SKILL.md`、`references/prompts.md`、`pipeline.md` 或 `content-contract.md`。

**你在流水线里的位置**：你产出的英文正文是**中文翻译的骨架来源**——A2 中文档会照着你恢复的章节层级、公式编号和图表落位逐节翻译，只换文字、不再重建结构。所以结构错了会一路传染到中文，你这一档的层级必须是对的。

## 写权与输入

- 论文：`{{PAPER_ID}}`
- 只允许写：`{{ARTICLE_EN_PATH}}`
- 主要原料（PDF 机器 dump）：`{{SOURCE_PATH}}`
- **带上下标的 dump（行内公式就靠它）**：`{{RICH_SOURCE_PATH}}`
- 脚本已产的确定性草稿（起点，不是终点）：`{{DRAFT_PATH}}`
- 图索引：`{{IMAGE_INDEX_PATH}}`
- 表索引（**英文原表，逐格可用的直接搬，不要重敲数字**）：`{{TABLE_INDEX_PATH}}`
- 仅在公式/版面明显损坏时核对：`{{PDF_PATH}}`

不得修改中文正文、notes、terms、index、job、共享索引或前端文件。子代理的 final 会自动返回父代理；不要探测消息工具，也不要额外发送完成通知。

## 这一档存在的理由：确定性脚本恢复不出章节层级

双栏 PDF dump 里标题和正文本来就粘在一行：

```
2 Non-spherical representation based on poly-superquadric equation 2.1 Description
of the superquadric equation The superquadric equation is an effective method for…
```

脚本没有语义理解，拆不开这种行。脚本无法可靠恢复所有语义标题。**把它们拆成真标题，是你这一档最核心的产出。**

## 产出要求

> 完整清单见 `references/article-contract.md`（中英对称，共 17 项）。
> 下面是这一档最容易做错的几条，**严格程度与中文正文完全相同**——
> 英文正文是中文翻译的骨架来源，这边松一寸，中文侧就得自己重建一遍。

1. **章节层级忠实还原**：`## 2 Non-spherical representation…` / `### 2.1 Description of the superquadric equation`，编号照原文体例（JFM 式 `2.1`、附录 `A.1` 都保留）。**正文行里不得再残留「编号 + 标题词」**——验收会逐个揪出来。
2. **忠实原文措辞，不改写、不概括、不翻译**。这是原文重排，不是复述。
3. **`## Abstract` 必须是标题节**，禁止行内加粗 `**Abstract**` 照搬原刊排版。
3b. **`## Keywords` 也必须是标题节**，紧跟在摘要之后。期刊常把标签字母拉开排成
   `K E Y WO R D S`，抽文本时会原样带进来，还常粘着版权声明和期刊卷期——标签要归一、
   尾巴要剥干净，只留关键词本身。**原刊印了才写，没印就不许硬造**（与 Highlights 同一口径）。
   关键词格式与章节标题必须统一；原刊有关键词时不得省略。
4. **`## Highlights` 只在原刊真印了的时候写**。原刊没印就不许有——英文侧禁止提炼，提炼版归中文正文的 `## 亮点`。
5. **公式转 LaTeX**，块级 `$$…\tag{N}$$`，编号照原文。行内用 `$…$`。dump 里同一条公式的散字符残渣**必须删干净**，不要 LaTeX 和乱码并存。
5b. **行内公式照 `.rich.txt` 抄**。纯文本 dump 把 `C_D` 压成了 `CD`、`a_{p1}` 压成 `ap1`、`log^2` 压成 `log2`——上下标是 PDF 抽文本时丢的，不是原文没有。`.rich.txt` 是同一份 PDF 按字号与基线还原出来的，已经写成 `C_{D}`、`a_{p1}`、`\log^{2}(Re)`，你直接包上 `$…$` 即可，**不要自己猜哪个字母该是下标**。这一条是硬要求：上下标丢失时，读者看到的会是 `CD`、`Re`、`a1`。
6. **公式紧跟引出句**：正文说 `…is expressed as` 的下一段就该是那条公式，不要堆到几十行之后。
7. **图片原位内嵌** `![[文件名|700]]`，只用图索引里真实存在的文件名，下一段是**原文英文图注** `**Fig. N.** …`（要有实际说明文字，不能只有标签）。
   **一图一嵌，不要把切碎面板当成图组。** 图索引张数若明显多于 PDF 图注（例如图注少而碎片数量多），那是切图脚本把复合图拆成了面板，不是原文有 61 张图。此时：
   - 每条 `Fig. N` 只嵌一张整幅图，不要在同一图注前连续嵌 4 张以上；
   - **不要自己删图凑数**，先停手、在 note 里写「疑似多切图，需 reextract」，由父代理重抽后再嵌；
   - 图索引没有覆盖检查、或同一图注挂在多张碎片上，视为切图未完成，不是重排任务。
8. **表格从表索引取**，标注「逐格可用」的原样搬进来；只有版面模型没抽出表体时才照 PDF 补。
8b. **符号表 / 命名表必须用 Markdown 表格**，不能排成普通正文。原刊的 `Nomenclature` / `List of symbols` / `Notations` 是符号–释义对照，写成 `| Symbol | Description |`（有量纲再加一列 Dimensions）。`Greek letters` / `Subscripts` 可以分表，但每张都得是表。禁止 `$A$ Bottom area, m$^2$` 这种一段一行（符号表压成段落会丢失结构）。
9. **删干净页眉页脚、水印、通讯地址**。dump 常把 `* Author name email@x State Key Laboratory…` 插进句子中间，要把被截断的句子接回去。
10. **`## References` 必须是标题节，一条一行**。原刊的文献表抽出来常常是跑马文字——没有标题、揉进上一段、和 `O RC I D` 粘在一起、一行挤好几条。要做的是**拆条 + 补标题**，不是删掉。文内引用写成 `word[N]`，**不许粘在词尾**（`world1`、`pressure2–5` 是坏的）。不加 `[[wikilink]]`、不加中文注释、不加译者按语。
10b. **后置事项各自成节**：`## Author Contributions` / `## Acknowledgments` / `## Conflict of Interest Statement` / `## Data Availability Statement`。期刊把这些标签的字母拉开排（`AU T H O R C O N T R I B U T I O N S`），抽文本时原样留在正文里，要归一成标题。
10c. **版权与下载水印一律删净**：`OA articles are governed by the applicable Creative Commons License`、`10969853, 2024, 16, Downloaded from https://onlinelibrary.wiley.com/…` 这类整串。
11. 题名块：H1 写英文全标题，其后一段加粗作者、一段裸文本单位、一段期刊信息。**作者行不要写 `^{单位号}`**。
12. **附录属于全文**：超长附录可按连续章节另派任务，但未完成时必须明确报告不完整，不能用 Deferred 占位宣称全文入库完成。

## 读取与写入预算

1. 先各读一次脚本草稿、图索引、表索引。草稿已经做完了机械活（连字符接回、页眉清理、表格注入、软连字符），**你的活是在它基础上恢复结构**，不要从零重写。
2. 统计 dump 行数，按章节顺序每次读取不超过 400 行。每个区间只读一次；不要把多个大区间并行塞进同一次工具调用，输出截断后也不要整段重读。
3. 只有某条公式在 dump 里明显损坏时，才读 PDF 对应的一两页；不要通读 PDF。
4. 尽量一次写完整篇；如输出过长，按连续章节分 2--3 次追加，不要先写半篇再反复改写已完成的章节。

## 验收（只跑这一条，不要跑全库 lint 或 Web 同步）

```
python "{{LINT_SCRIPT}}" --vault "{{VAULT}}" --wenshu "{{WENSHU}}" --draft-dir "{{DRAFT_DIR}}" --only "{{PAPER_ID}}" --fail-on-warnings
```

必须 0 error。特别会被揪住的三条：**章节层级没恢复**（正文里残留编号章节名，或平均一万多字符才一个标题）、**`## Abstract` 不是标题节**、**原刊没印却写了 `## Highlights`**。

最终回复只报告目标路径、行数、标题数、公式/图/表数量、TODO 数，以及仍需父代理处理的真实问题。
