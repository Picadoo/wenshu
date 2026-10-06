# 文枢 · Wenshu

本地科研文献库：整理 PDF，阅读中英文全文，查看图表与公式，保存笔记、高亮和生词。提供 React 网页客户端、Tauri 桌面壳、AI 辅助入库技能与可选自托管 API。

公开版保留自研的数据和阅读逻辑，并使用独立实现的界面。仓库仅带一篇 CC BY 4.0 示例论文；个人文库、批注、阅读记录和密钥均不属于发布内容。

## 快速开始

需要 Node.js 20+、Python 3.10+。Python 命令若在你的系统中为 `python3`，相应替换。

```sh
python -m pip install -r skills/requirements.txt
cd wenshu-pro
npm ci
npm run sample
npm run dev
```

访问 `http://localhost:8080`。示例生成的目录和镜像被 Git 忽略；仓库中的原始示例位于 `examples/vault/`。

## 桌面版

当前安装包目标为 Windows（NSIS）。额外需要 Rust、MSVC Build Tools 和 WebView2。

```sh
cd wenshu-pro
npm run sample
npm run tauri dev
# 生成安装包
npm run tauri build
```

桌面版内置示例。设置中可以分别选择个人笔记目录与同步后的阅读镜像目录；自有文库无需嵌入程序。公开版使用独立应用标识 `com.wenshu.opensource`，个人数据默认保存在应用数据目录。

## 导入自己的论文

将私人文库放在仓库根目录的 `vault/`，工作材料放在 `_work/`。两者均被 Git 忽略。先阅读 [入库技能](skills/paper-ingest/SKILL.md)，按需要配置 `skills/paper-ingest/config.json` 与旧流程配置。相对路径均按仓库根目录解析；AI CLI 和模型由使用者自行配置，仓库不提供 API Key。

流程为：查重 → 提取文字与页面图 → 核准原文、公式、表格和裁图 → 锁定内容翻译与学习笔记 → 验收 → 同步。普通 PDF 使用文字层，扫描版需要额外处理。自动检查通过并不代表语义准确，尤其要复核公式和定量结论。

```sh
cd wenshu-pro
npm run sync
```

原 PDF 保留。笔记、批注和生词属于使用者，AI 入库流程不应改写这些数据。可选 API 的运行方式见 [server/README.md](wenshu-pro/server/README.md)；写作技能见 [skills/README.md](skills/README.md)。

## 目录

| 目录 | 职责 |
| --- | --- |
| `wenshu-pro/src/` | 文库索引、Markdown/LaTeX 阅读、个人阅读数据 |
| `wenshu-pro/src-tauri/` | 桌面窗口、文库资源协议、本地数据读写 |
| `wenshu-pro/server/` | 可选自托管账号与个人数据 API |
| `skills/paper-ingest/` | 当前 PDF 入库流程 |
| `skills/pdf-to-wenshu/` | 旧版任务维护与检索 |
| `skills/paper-writing/` | 带来源归因的论文文字技能 |
| `examples/vault/` | 唯一公开示例 |

内容格式见 [content-contract.md](wenshu-pro/docs/content-contract.md)。

## 验证与发布边界

```sh
cd wenshu-pro
npm run build
npm run test:markdown
cd ..
python -m unittest discover -s skills/paper-ingest/tests
python -m unittest discover -s skills/pdf-to-wenshu/tests
git add .
python scripts/check-public-tree.py
```

发布检查只检查 Git 暂存范围，报告路径与规则，不打印疑似密钥。它不能识别所有秘密；发布前仍需检查实际暂存文件。不要强制添加 `.env`、私人 `vault/`、数据库、工作记录、构建产物或生成的全库目录。分享自己处理的论文前，还需确认其再分发和翻译授权。

## 许可

项目代码采用 [AGPL-3.0-only](LICENSE)。PDF 入库依赖 PyMuPDF 的开源版本，其许可为 AGPL；若有不同许可需求，请先确认相关依赖授权。其他第三方组件保留各自许可证，见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

示例论文采用 CC BY 4.0，不受本项目代码许可证替代；原文作者署名、出处和译文改编说明见 [examples/README.md](examples/README.md)。

