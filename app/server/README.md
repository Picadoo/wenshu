# 可选 API

本地阅读与入库不必启动 API。此后端提供认证、用户管理、个人笔记与生词同步、分享和静态资源鉴权，数据存于自己的 SQLite 数据库。

```sh
python -m pip install -r requirements.txt
```

从本目录启动。必须通过进程环境设置 `WENSHU_JWT_SECRET`，首次启动还需 `WENSHU_ADMIN_EMAIL` 与 `WENSHU_ADMIN_PASSWORD`。JWT 密钥应使用足够长的随机值；管理员密码不写入日志。配置字段见 `.env.example`，代码不会自动读取该文件。

```sh
python -m uvicorn app:app --host 127.0.0.1 --port 8787
```

默认数据库是当前目录的 `wenshu.db`，镜像目录是 `../public/vault`。需要修改时设置 `WENSHU_DB`、`WENSHU_VAULT_DIR`；HTTPS 部署设置 `WENSHU_COOKIE_SECURE=1`。

默认允许 `http://localhost:8080`、`http://127.0.0.1:8080` 以及桌面应用的 `http://tauri.localhost`、`tauri://localhost` 发起带凭据请求。前端设置中可填写 `http://127.0.0.1:8787`。部署到自己的域名时，通过 `WENSHU_ALLOWED_ORIGINS` 指定逗号分隔的完整前端来源；不接受 `*`。Tauri 改用 HTTPS scheme 时也须相应设置其来源。

数据库、个人笔记、生词、会话、分享 token 与环境文件均不应提交到公开仓库。本包不含任何现有部署地址或数据库。

生产分享阅读采用同域部署：前端提供 `/share/<token>` 路由，反向代理将 `/api/` 转给此 API，并将 `/vault/` 指向同步镜像。API 的 `/api/authz` 验证登录或单篇分享 cookie，代理应据此保护文库静态文件；API 本身不直接托管全文。不要将私人全库的 catalog、terms、正文和图片作为无需鉴权的静态站点发布。
