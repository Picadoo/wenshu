# 文枢技能与入库工具

新论文使用 `paper-ingest`。`pdf-to-wenshu` 只用于旧 job 续跑、存量维护与检索；`paper-writing` 处理论文文字，第三方归因和许可证保留在该目录。

需要 Python 3.10 或更新版本、Node.js，以及具备对应任务能力的 AI 宿主。安装 Python 依赖：

```sh
python -m pip install -r skills/requirements.txt
```

在 `wenshu-pro/` 安装前端依赖并准备数学渲染资源后，才能核准含公式的源稿。无头翻译另需已安装、已认证且在 PATH 中的 Codex CLI；也可以在 `paper-ingest/config.json` 选择其他 runner。空模型配置沿用 CLI 默认模型。

`vault`、`wenshu` 和 `work` 在两个技能的 `config.json` 中相对于仓库根解析，不受运行目录影响。保留整个 `skills/` 目录，包括 `shared/`；绝对路径也可用于自己的库。

```sh
python skills/paper-ingest/scripts/extract.py --pdf "paper.pdf" --work "_work/lite/Example2024" --vault "vault" --key Example2024
```

然后按 `paper-ingest/SKILL.md` 整理与核准原稿、裁图、翻译并验收。脚本不内置 OCR；扫描版需要先获得可靠文字层。源稿审核需要具备原页视觉核对能力，翻译模型只处理锁定文本。检查通过不能替代内容核对。

示例源库位于 `examples/vault/`；前端的 `npm run sample` 只生成该示例的阅读镜像，不写入你的私人 `vault/`。私人文库、入库工作区、阅读记录、API 数据库和配置密钥应保留在本地。

旧版可选功能使用 `pdf-to-wenshu/requirements-optional.txt` 的依赖；参考文献格式化另需 pandoc。不要为新论文同时启动两套流程。

已有测试：

```sh
python -m unittest discover -s skills/paper-ingest/tests
python -m unittest discover -s skills/pdf-to-wenshu/tests
```
