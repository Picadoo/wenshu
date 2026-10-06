# 公开示例论文

仓库仅附带这一篇公开论文，用于展示双语阅读、原 PDF、公式、图表、学习笔记和术语。示例不包含个人批注、个人笔记、阅读进度或活动记录。

## 原始来源与署名

- **题名：** The Basset–Boussinesq history force: its neglect, validity, and recent numerical developments
- **作者：** Divya Jaganathan; S. Ganga Prasath; Rama Govindarajan; Vishal Vasan
- **原刊：** Frontiers in Physics, Volume 11, Article 1167338, 22 May 2023
- **DOI：** [10.3389/fphy.2023.1167338](https://doi.org/10.3389/fphy.2023.1167338)
- **官方全文：** [Frontiers article](https://www.frontiersin.org/journals/physics/articles/10.3389/fphy.2023.1167338/full)
- **官方 PDF：** [Frontiers PDF](https://www.frontiersin.org/journals/physics/articles/10.3389/fphy.2023.1167338/pdf)
- **原文许可：** [Creative Commons Attribution 4.0 International (CC BY 4.0)](https://creativecommons.org/licenses/by/4.0/)
- **版权：** © 2023 Jaganathan, Prasath, Govindarajan and Vasan.

原 PDF 首页明示 CC BY，PDF 中的许可链接指向 CC BY 4.0。作者与原刊署名及出版声明保留；示例论文不适用仓库代码的许可。

## 改编说明

英文 Markdown 是 PDF 的文字与公式转写；图 1 由原 PDF 裁切，用于软件中的图像浏览；中文正文是 AI 辅助译文和排版改编，**不是作者提供的中文原作**。学习笔记和术语说明是根据本篇内容重新整理的 AI 辅助概括，也不是作者原文。上述转写、翻译与概括不改变原始 PDF，科学内容以作者原刊为准。

图 1 的原图注注明其示意构思源于 Bentwich and Miloh（1978）以及 Sano（1981）；这一署名和原参考文献保留。原文图注与表 1 未标示另行转载许可或独立第三方版权例外。示例中的论文文字、译文改编和图 1 按 CC BY 4.0 使用，并保留来源与改编说明。

## 示例文件

- `examples/vault/Papers/示例/流体力学/`：新建的中性索引与唯一论文集群。
- 集群 `content/`：原 PDF、英文 Markdown、中文 Markdown和重新整理的学习笔记。
- 集群 `images/`：图 1 的 PNG 与 WebP 浏览副本。
- `examples/vault/30_Terms/术语/`：仅四个与本篇直接相关的示例术语。

同步产物位于 `app/public/vault/`；目录计数为 1，专题为空，个人活动为空。示例数据可按原文许可再分发，使用时仍需保留原作者、原刊、DOI、许可链接和改编说明。

运行 `npm run sample` 从 `examples/vault` 生成公开示例镜像。根目录 `vault/`、生成镜像与构建兜底数据不纳入 Git；用户自己的文库放在根 `vault/`。
