# 文枢 AI 技能

- [paper-ingest](paper-ingest/SKILL.md)：把 PDF 整理成双语全文、图表、学习笔记与术语，再发布到文库。
- [paper-writing](paper-writing/SKILL.md)：起草、重组、润色和翻译论文文字；归因与许可证保留在技能目录中。

## 准备环境

需要 Python 3.10+、Node.js，以及能读取文件和查看原页图片的 AI 宿主。先安装依赖：

```sh
python -m pip install -r skills/requirements.txt
```

按根目录 README 安装客户端依赖。核准含公式的源稿需要客户端的 KaTeX 资源。自动翻译还需要已安装、认证且在 PATH 中的 Codex CLI；也可以在 `paper-ingest/config.json` 选择其他 runner。空模型配置沿用 CLI 默认模型。

`paper-ingest/config.json` 的路径相对于仓库根解析。保留 `skills/shared/`，它负责解析配置；也可配置自己的绝对路径。

## 导入第一篇论文

让 AI 使用 [paper-ingest](paper-ingest/SKILL.md)，提供 PDF 路径和希望保存的文库目录。工作区是中间产物，正式文库默认是 `vault/`。

```sh
python skills/paper-ingest/scripts/extract.py --pdf "paper.pdf" --work "_work/Example2024" --vault "vault" --key Example2024
```

这一步生成文本、原页图片和任务书，不会直接发布论文。接着按任务书核准源稿、裁图、翻译、生成笔记，最后运行 `finish.py`。脚本不内置 OCR；扫描版需要先获得可靠文字层。格式检查不能代替原页与翻译内容核对。

共享示例只位于 `examples/vault/`。客户端的 `npm run sample` 生成示例阅读镜像，不写入私人 `vault/`。私人文库、入库工作区、阅读记录、数据库和密钥配置都保留在本地。

## 测试

```sh
python -m unittest discover -s skills/paper-ingest/tests
```
