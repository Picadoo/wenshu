# 导入自己的 PDF

网页预览让你先体验阅读。整理自己的 PDF 需要在本机运行入库工具，并由具备原页核对能力的 AI 完成原文整理与翻译。

## 1. 准备工具

在仓库根目录安装 PDF 处理依赖：

```sh
python -m pip install -r skills/requirements.txt
```

前端已经执行过 `npm ci` 后，数学渲染资源也已准备好。选择你已安装、已登录的 AI CLI；默认配置从 PATH 使用 Codex，也可以在 `skills/paper-ingest/config.json` 选择其他 runner 和模型。仓库不提供模型账号或密钥。

配置中的相对路径按仓库根目录解析：`vault/` 存放文库，`_work/` 存放处理材料，`app/` 是阅读客户端。个人笔记、批注和生词不由入库工具改写。

## 2. 整理一篇论文

把 PDF 路径交给你的 AI 助手，明确请求：

> 按 `skills/paper-ingest/SKILL.md` 将这篇 PDF 导入文枢。先查重，核准完整原文、图表和公式，再生成完整中文译文与简洁学习笔记，通过检查后同步。保留原始 PDF。

普通 PDF 直接提取文字层。双栏顺序、公式、表格与裁图需要对照原页；扫描版需要先获得可靠文字层。自动检查通过并不等于内容已经准确。

如果希望先查看提取结果，可以在仓库根目录运行：

```sh
python skills/paper-ingest/scripts/extract.py --pdf "paper.pdf" --work "_work/Example2024"
```

接下来的原文核准、翻译和验收步骤见 [入库技能](../skills/paper-ingest/SKILL.md)。不要把 AI 学习笔记当作作者原文，也不要用摘要替代完整正文。

## 3. 打开文库

完成入库后，阅读镜像会同步到客户端。需要单独同步时：

```sh
cd app
npm run sync
npm run dev
```

刷新论文目录即可阅读。原 PDF 和正文保留在本机，个人数据与 AI 生成的学习材料分别存储。

分享论文前，确认它允许再分发和翻译。自己的全库、未公开稿件、批注、环境文件和 API Key 都不应上传到公开仓库。
