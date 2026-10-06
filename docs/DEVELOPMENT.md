# 开发与构建

## 客户端

```sh
cd app
npm ci
npm run dev
```

示例在首次运行时自动生成。代码与数据分离：`src/` 是客户端，`public/vault/` 是生成的阅读镜像，源示例在 `examples/vault/`。

本地网页和 Tauri 使用根路径。GitHub Pages 使用 `pages` 构建模式、`/wenshu/` 资源路径和 hash 路由；构建模式不改变工作台、阅读器、AI 配置或同步入口。GitHub Pages 自身只托管静态前端，使用者可按需配置自己的 AI 接口和同步服务器。发布时仅携带允许公开的示例，个人数据默认保存在使用者自己的本机。

```sh
npm run build
npm run build -- --mode pages
npm run test:markdown
```

## Windows 桌面版

额外需要 Rust、MSVC Build Tools 和 WebView2，安装包目标为 NSIS。

```sh
cd app
npm run tauri dev
npm run tauri build
```

桌面版内置示例。设置中分别选择个人笔记目录与同步后的阅读镜像目录；默认个人数据位于应用数据目录。文件读写限于已配置文库。

## PDF 流程与可选后端

- `skills/paper-ingest/`：提取、核原稿、裁图、翻译、笔记与验收。
- `skills/paper-writing/`：论文文字技能，保留上游归因及许可。
- `app/server/`：自托管认证、个人数据同步和单篇分享，运行方式见 [后端说明](../app/server/README.md)。

内容格式见 [内容契约](../app/docs/content-contract.md)。公开客户端支持同篇双语对照；跨论文并排、用户删除和密码重置界面尚未接入。桌面与生产分享需要实际部署验收。

## 检查与发布

只运行与修改直接相关的检查。入库工具的现有测试：

```sh
python -m unittest discover -s skills/paper-ingest/tests
```

GitHub Pages 的构建入口为 `.github/workflows/pages.yml`。它先检查源文件的公开边界，再从唯一示例生成镜像并部署；不使用私人文库或模型密钥。

发布源码前：

```sh
git add .
python scripts/check-public-tree.py
```

该检查只报告文件路径与规则，不打印疑似密钥，但不能替代人工内容核查。不要强制提交 `vault/`、`_work/`、`.env`、数据库或生成的完整文库。
