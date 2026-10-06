# -*- coding: utf-8 -*-
"""文枢自建后端：认证、用户管理、笔记/生词同步、单篇分享、vault 静态资源鉴权。

接口契约：
  POST /api/auth/sign-in   {email,password} -> {accessToken, user}，并种 httpOnly 会话 cookie
  GET  /api/auth/me        Bearer 或 cookie -> {user}
  其余见各路由注释。

存储：SQLite 单文件（env WENSHU_DB，默认 ./wenshu.db）。
启动引导：users 表为空时用 WENSHU_ADMIN_EMAIL / WENSHU_ADMIN_PASSWORD 建管理员。
"""

from __future__ import annotations

import os
import json
import hashlib
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import unquote

import jwt
from fastapi import Cookie, Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ----------------------------------------------------------------------
# 配置

DB_PATH = Path(os.environ.get("WENSHU_DB", "wenshu.db"))
VAULT_DIR = Path(os.environ.get("WENSHU_VAULT_DIR", "../public/vault"))
COOKIE_SECURE = os.environ.get("WENSHU_COOKIE_SECURE", "0") == "1"
TOKEN_TTL_DAYS = 30

SESSION_COOKIE = "wenshu_session"
SHARE_COOKIE = "wenshu_share"

DEFAULT_ALLOWED_ORIGINS = (
    "http://localhost:8080", "http://127.0.0.1:8080",
    "http://tauri.localhost", "tauri://localhost",
)
ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.environ.get("WENSHU_ALLOWED_ORIGINS", ",".join(DEFAULT_ALLOWED_ORIGINS)).split(",")
    if origin.strip()
]
if "*" in ALLOWED_ORIGINS:
    raise RuntimeError("WENSHU_ALLOWED_ORIGINS 必须列出明确来源，不能对带凭据请求使用 *")

app = FastAPI(title="wenshu-api", docs_url=None, redoc_url=None)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)

# ----------------------------------------------------------------------
# 数据库


def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db() -> None:
    conn = db()
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS users (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          email TEXT NOT NULL UNIQUE,
          display_name TEXT NOT NULL DEFAULT '',
          role TEXT NOT NULL DEFAULT 'reader',
          pass_salt BLOB NOT NULL,
          pass_hash BLOB NOT NULL,
          disabled INTEGER NOT NULL DEFAULT 0,
          created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS notes (
          user_id INTEGER NOT NULL,
          slug TEXT NOT NULL,
          data TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          PRIMARY KEY (user_id, slug)
        );
        CREATE TABLE IF NOT EXISTS kv (
          user_id INTEGER NOT NULL,
          key TEXT NOT NULL,
          data TEXT NOT NULL,
          updated_at TEXT NOT NULL,
          PRIMARY KEY (user_id, key)
        );
        CREATE TABLE IF NOT EXISTS shares (
          token TEXT PRIMARY KEY,
          slug TEXT NOT NULL,
          created_by INTEGER NOT NULL,
          created_at TEXT NOT NULL,
          expires_at TEXT,
          revoked INTEGER NOT NULL DEFAULT 0
        );
        """
    )
    conn.commit()
    conn.close()


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def meta_get(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
    return row["value"] if row else None


def jwt_secret() -> str:
    """JWT signing requires an explicitly configured deployment secret."""
    secret = os.environ.get("WENSHU_JWT_SECRET", "").strip()
    if not secret:
        raise RuntimeError("需要设置 WENSHU_JWT_SECRET，不能使用默认签名密钥")
    return secret


# ----------------------------------------------------------------------
# 密码与令牌


def hash_password(password: str, salt: bytes | None = None) -> tuple[bytes, bytes]:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1)
    return salt, digest


def verify_password(password: str, salt: bytes, expected: bytes) -> bool:
    _, digest = hash_password(password, salt)
    return secrets.compare_digest(digest, expected)


def issue_token(user: sqlite3.Row) -> str:
    payload = {
        "sub": str(user["id"]),
        "email": user["email"],
        "exp": datetime.now(timezone.utc) + timedelta(days=TOKEN_TTL_DAYS),
    }
    return jwt.encode(payload, jwt_secret(), algorithm="HS256")


def decode_token(token: str) -> dict[str, Any] | None:
    try:
        return jwt.decode(token, jwt_secret(), algorithms=["HS256"])
    except jwt.PyJWTError:
        return None


def user_json(user: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": str(user["id"]),
        "email": user["email"],
        "displayName": user["display_name"] or user["email"].split("@")[0],
        "role": user["role"],
        "disabled": bool(user["disabled"]),
        "createdAt": user["created_at"],
    }


def bootstrap_admin() -> None:
    conn = db()
    count = conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]
    if count == 0:
        email = os.environ.get("WENSHU_ADMIN_EMAIL", "").strip().lower()
        password = os.environ.get("WENSHU_ADMIN_PASSWORD", "").strip()
        if not email or not password:
            conn.close()
            raise RuntimeError("首次启动需要设置 WENSHU_ADMIN_EMAIL 和 WENSHU_ADMIN_PASSWORD")
        if len(password) < 6:
            conn.close()
            raise RuntimeError("管理员密码至少 6 位")
        salt, digest = hash_password(password)
        conn.execute(
            "INSERT INTO users (email, display_name, role, pass_salt, pass_hash, created_at)"
            " VALUES (?, ?, 'admin', ?, ?, ?)",
            (email, "管理员", salt, digest, now_iso()),
        )
        conn.commit()
        # Credentials are never written to logs.
    conn.close()


# ----------------------------------------------------------------------
# 依赖


def get_user(
    authorization: str | None = Header(default=None),
    session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> sqlite3.Row:
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:]
    elif session:
        token = session
    payload = decode_token(token) if token else None
    if not payload:
        raise HTTPException(status_code=401, detail="未登录或登录已过期")
    conn = db()
    user = conn.execute("SELECT * FROM users WHERE id=?", (int(payload["sub"]),)).fetchone()
    conn.close()
    if not user or user["disabled"]:
        raise HTTPException(status_code=401, detail="账号不存在或已停用")
    return user


def get_admin(user: sqlite3.Row = Depends(get_user)) -> sqlite3.Row:
    if user["role"] != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=TOKEN_TTL_DAYS * 86400,
        httponly=True,
        samesite="lax",
        secure=COOKIE_SECURE,
        path="/",
    )


# ----------------------------------------------------------------------
# 认证


class SignInBody(BaseModel):
    email: str
    password: str


@app.post("/api/auth/sign-in")
def sign_in(body: SignInBody, response: Response):
    conn = db()
    user = conn.execute("SELECT * FROM users WHERE email=?", (body.email.strip().lower(),)).fetchone()
    conn.close()
    if not user or user["disabled"] or not verify_password(body.password, user["pass_salt"], user["pass_hash"]):
        raise HTTPException(status_code=401, detail="邮箱或密码不正确")
    token = issue_token(user)
    set_session_cookie(response, token)
    return {"accessToken": token, "user": user_json(user)}


@app.post("/api/auth/sign-out")
def sign_out(response: Response):
    response.delete_cookie(SESSION_COOKIE, path="/")
    return {"ok": True}


@app.get("/api/auth/me")
def me(user: sqlite3.Row = Depends(get_user)):
    return {"user": user_json(user)}


class ChangePasswordBody(BaseModel):
    oldPassword: str
    newPassword: str


@app.post("/api/auth/change-password")
def change_password(body: ChangePasswordBody, user: sqlite3.Row = Depends(get_user)):
    if not verify_password(body.oldPassword, user["pass_salt"], user["pass_hash"]):
        raise HTTPException(status_code=400, detail="原密码不正确")
    if len(body.newPassword) < 6:
        raise HTTPException(status_code=400, detail="新密码至少 6 位")
    salt, digest = hash_password(body.newPassword)
    conn = db()
    conn.execute("UPDATE users SET pass_salt=?, pass_hash=? WHERE id=?", (salt, digest, user["id"]))
    conn.commit()
    conn.close()
    return {"ok": True}


# ----------------------------------------------------------------------
# 用户管理（管理员）


class CreateUserBody(BaseModel):
    email: str
    password: str
    displayName: str = ""
    role: str = "reader"


class PatchUserBody(BaseModel):
    password: str | None = None
    displayName: str | None = None
    role: str | None = None
    disabled: bool | None = None


@app.get("/api/users")
def list_users(_: sqlite3.Row = Depends(get_admin)):
    conn = db()
    rows = conn.execute("SELECT * FROM users ORDER BY id").fetchall()
    conn.close()
    return {"users": [user_json(row) for row in rows]}


@app.post("/api/users")
def create_user(body: CreateUserBody, _: sqlite3.Row = Depends(get_admin)):
    email = body.email.strip().lower()
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="邮箱格式不正确")
    if len(body.password) < 6:
        raise HTTPException(status_code=400, detail="密码至少 6 位")
    if body.role not in ("admin", "reader"):
        raise HTTPException(status_code=400, detail="角色只能是 admin 或 reader")
    salt, digest = hash_password(body.password)
    conn = db()
    try:
        conn.execute(
            "INSERT INTO users (email, display_name, role, pass_salt, pass_hash, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (email, body.displayName.strip(), body.role, salt, digest, now_iso()),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        raise HTTPException(status_code=400, detail="该邮箱已存在")
    user = conn.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
    conn.close()
    return {"user": user_json(user)}


@app.patch("/api/users/{uid}")
def patch_user(uid: int, body: PatchUserBody, admin: sqlite3.Row = Depends(get_admin)):
    conn = db()
    user = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    if not user:
        conn.close()
        raise HTTPException(status_code=404, detail="用户不存在")
    if body.password is not None:
        if len(body.password) < 6:
            conn.close()
            raise HTTPException(status_code=400, detail="密码至少 6 位")
        salt, digest = hash_password(body.password)
        conn.execute("UPDATE users SET pass_salt=?, pass_hash=? WHERE id=?", (salt, digest, uid))
    if body.displayName is not None:
        conn.execute("UPDATE users SET display_name=? WHERE id=?", (body.displayName.strip(), uid))
    if body.role is not None:
        if body.role not in ("admin", "reader"):
            conn.close()
            raise HTTPException(status_code=400, detail="角色只能是 admin 或 reader")
        if uid == admin["id"]:
            conn.close()
            raise HTTPException(status_code=400, detail="不能修改自己的角色")
        conn.execute("UPDATE users SET role=? WHERE id=?", (body.role, uid))
    if body.disabled is not None:
        if uid == admin["id"]:
            conn.close()
            raise HTTPException(status_code=400, detail="不能停用自己")
        conn.execute("UPDATE users SET disabled=? WHERE id=?", (1 if body.disabled else 0, uid))
    conn.commit()
    user = conn.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
    conn.close()
    return {"user": user_json(user)}


@app.delete("/api/users/{uid}")
def delete_user(uid: int, admin: sqlite3.Row = Depends(get_admin)):
    if uid == admin["id"]:
        raise HTTPException(status_code=400, detail="不能删除自己")
    conn = db()
    conn.execute("DELETE FROM users WHERE id=?", (uid,))
    conn.execute("DELETE FROM notes WHERE user_id=?", (uid,))
    conn.execute("DELETE FROM kv WHERE user_id=?", (uid,))
    conn.commit()
    conn.close()
    return {"ok": True}


# ----------------------------------------------------------------------
# 笔记 / KV 同步（按用户隔离）


@app.get("/api/notes")
def list_notes(user: sqlite3.Row = Depends(get_user)):
    """登录后一次拉全量：新设备立即看到所有论文的星标/笔记。"""
    conn = db()
    rows = conn.execute("SELECT slug, data, updated_at FROM notes WHERE user_id=?", (user["id"],)).fetchall()
    conn.close()
    return {
        "notes": {
            row["slug"]: {"data": json.loads(row["data"]), "updatedAt": row["updated_at"]} for row in rows
        }
    }


@app.get("/api/notes/{slug}")
def get_notes(slug: str, user: sqlite3.Row = Depends(get_user)):
    conn = db()
    row = conn.execute(
        "SELECT data, updated_at FROM notes WHERE user_id=? AND slug=?", (user["id"], slug)
    ).fetchone()
    conn.close()
    if not row:
        return {"data": None}
    return {"data": json.loads(row["data"]), "updatedAt": row["updated_at"]}


@app.put("/api/notes/{slug}")
async def put_notes(slug: str, request: Request, user: sqlite3.Row = Depends(get_user)):
    data = await request.json()
    conn = db()
    conn.execute(
        "INSERT INTO notes (user_id, slug, data, updated_at) VALUES (?, ?, ?, ?)"
        " ON CONFLICT(user_id, slug) DO UPDATE SET data=excluded.data, updated_at=excluded.updated_at",
        (user["id"], slug, json.dumps(data, ensure_ascii=False), now_iso()),
    )
    conn.commit()
    conn.close()
    return {"ok": True}


@app.get("/api/kv/{key}")
def get_kv(key: str, user: sqlite3.Row = Depends(get_user)):
    conn = db()
    row = conn.execute(
        "SELECT data, updated_at FROM kv WHERE user_id=? AND key=?", (user["id"], key)
    ).fetchone()
    conn.close()
    if not row:
        return {"data": None}
    return {"data": json.loads(row["data"]), "updatedAt": row["updated_at"]}


@app.put("/api/kv/{key}")
async def put_kv(key: str, request: Request, user: sqlite3.Row = Depends(get_user)):
    data = await request.json()
    conn = db()
    conn.execute(
        "INSERT INTO kv (user_id, key, data, updated_at) VALUES (?, ?, ?, ?)"
        " ON CONFLICT(user_id, key) DO UPDATE SET data=excluded.data, updated_at=excluded.updated_at",
        (user["id"], key, json.dumps(data, ensure_ascii=False), now_iso()),
    )
    conn.commit()
    conn.close()
    return {"ok": True}


# ----------------------------------------------------------------------
# 单篇分享


def load_catalog() -> list[dict[str, Any]]:
    path = VAULT_DIR / "catalog.json"
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("papers", [])
    except (OSError, json.JSONDecodeError):
        return []


def share_row_json(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "token": row["token"],
        "slug": row["slug"],
        "createdAt": row["created_at"],
        "expiresAt": row["expires_at"],
        "revoked": bool(row["revoked"]),
    }


def share_valid(row: sqlite3.Row | None) -> bool:
    if not row or row["revoked"]:
        return False
    if row["expires_at"] and row["expires_at"] < now_iso():
        return False
    return True


class CreateShareBody(BaseModel):
    slug: str
    days: int | None = None  # None = 永久；7 / 30 等


@app.get("/api/shares")
def list_shares(user: sqlite3.Row = Depends(get_user)):
    conn = db()
    rows = conn.execute(
        "SELECT * FROM shares WHERE created_by=? AND revoked=0 ORDER BY created_at DESC", (user["id"],)
    ).fetchall()
    conn.close()
    return {"shares": [share_row_json(row) for row in rows]}


@app.post("/api/shares")
def create_share(body: CreateShareBody, user: sqlite3.Row = Depends(get_user)):
    papers = load_catalog()
    if not any(p.get("slug") == body.slug for p in papers):
        raise HTTPException(status_code=404, detail="论文不存在")
    token = secrets.token_urlsafe(12)
    expires_at = None
    if body.days:
        expires_at = (datetime.now(timezone.utc) + timedelta(days=body.days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    conn = db()
    conn.execute(
        "INSERT INTO shares (token, slug, created_by, created_at, expires_at) VALUES (?, ?, ?, ?, ?)",
        (token, body.slug, user["id"], now_iso(), expires_at),
    )
    conn.commit()
    conn.close()
    return {"share": {"token": token, "slug": body.slug, "createdAt": now_iso(), "expiresAt": expires_at, "revoked": False}}


@app.delete("/api/shares/{token}")
def revoke_share(token: str, user: sqlite3.Row = Depends(get_user)):
    conn = db()
    conn.execute("UPDATE shares SET revoked=1 WHERE token=? AND created_by=?", (token, user["id"]))
    conn.commit()
    conn.close()
    return {"ok": True}


@app.get("/api/share/{token}/meta")
def share_meta(token: str, response: Response):
    """分享访客入口：校验 token、返回该篇论文的目录数据，并种分享 cookie 供静态资源鉴权。"""
    conn = db()
    row = conn.execute("SELECT * FROM shares WHERE token=?", (token,)).fetchone()
    conn.close()
    if not share_valid(row):
        raise HTTPException(status_code=410, detail="分享链接不存在或已失效")
    paper = next((p for p in load_catalog() if p.get("slug") == row["slug"]), None)
    if not paper:
        raise HTTPException(status_code=410, detail="论文已下架")
    response.set_cookie(
        SHARE_COOKIE,
        token,
        max_age=7 * 86400,
        httponly=True,
        samesite="lax",
        secure=COOKIE_SECURE,
        path="/",
    )
    return {"paper": paper, "expiresAt": row["expires_at"]}


# ----------------------------------------------------------------------
# vault 静态资源鉴权（nginx auth_request）


@app.get("/api/authz")
def authz(
    x_original_uri: str | None = Header(default=None),
    session: str | None = Cookie(default=None, alias=SESSION_COOKIE),
    share: str | None = Cookie(default=None, alias=SHARE_COOKIE),
):
    """登录用户放行全部 vault；分享 cookie 只放行对应论文目录。"""
    if session and decode_token(session):
        return Response(status_code=204)
    if share and x_original_uri:
        conn = db()
        row = conn.execute("SELECT * FROM shares WHERE token=?", (share,)).fetchone()
        conn.close()
        if share_valid(row):
            uri = unquote(x_original_uri.split("?")[0])
            if uri.startswith(f"/vault/papers/{row['slug']}/"):
                return Response(status_code=204)
    raise HTTPException(status_code=401, detail="无权访问")


# ----------------------------------------------------------------------

# Validate the secret before creating or opening the database.
jwt_secret()
init_db()
bootstrap_admin()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8787)
