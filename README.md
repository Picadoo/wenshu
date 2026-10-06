# 文枢 · Wenshu

读论文、看双语对照、核对原 PDF，把高亮、笔记和生词留在自己的文库里。

**[在线体验](https://picadoo.github.io/wenshu/)** · [导入自己的 PDF](docs/PDF_IMPORT.md) · [开发与桌面构建](docs/DEVELOPMENT.md)

## 先读一篇

打开在线体验，点击「开始读示例」，就能试用中文正文、英文原文、双语对照、公式、图片和原 PDF。高亮和个人笔记保存在你自己的浏览器里。

预览使用一篇明确采用 CC BY 4.0 的公开论文，不需要登录、API Key 或安装软件。论文译文、AI 学习笔记与个人笔记分别展示；原始来源和改编说明见 [示例署名](examples/README.md)。

## 在自己的电脑上运行

需要 **Node.js 20+** 和 **Python 3.10+**。

```sh
git clone https://github.com/Picadoo/wenshu.git
cd wenshu/app
npm ci
npm run dev
```

打开 `http://localhost:8080`，示例会自动准备好。阅读示例不需要配置 AI，也不用安装 PDF 处理依赖。

想整理自己的 PDF，继续看 [PDF 导入指南](docs/PDF_IMPORT.md)。目前 PDF 整理由 AI 辅助入库流程完成，网页负责阅读和笔记。

## 可以做什么

- 阅读完整中英文正文，切换双语对照、图片和原 PDF。
- 显示可编辑 LaTeX 公式、表格、引用与术语提示。
- 保存高亮、摘录、个人笔记、生词和阅读位置。
- 通过 PDF 入库技能生成正文、译文、图表与学习笔记。
- 构建 Windows 桌面版；按需要配置自己的同步后端。

## 项目结构

```text
app/        阅读客户端、桌面壳与可选后端
skills/     PDF 入库和论文文字技能
examples/   唯一公开示例及其署名
docs/       使用与开发指南
```

自己的文库放在根目录 `vault/`，处理材料放在 `_work/`。这两个目录、个人批注、密钥和生成的文库镜像默认不提交到 Git。

## 许可与致谢

项目代码采用 [AGPL-3.0](LICENSE)，第三方材料保留各自许可，见 [第三方声明](THIRD_PARTY_NOTICES.md)。示例论文及其译文改编采用 CC BY 4.0。

新人入口与静态试读的组织参考了 [EasyRead](https://github.com/Edwardxlai/easyread)。文枢使用自己的阅读器和入库实现。

