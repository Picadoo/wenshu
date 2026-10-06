# -*- coding: utf-8 -*-
"""Upsert the administrator from explicit environment variables."""

from __future__ import annotations

import os
import sys

from app import db, hash_password, now_iso


def main() -> None:
    email = (os.environ.get("WENSHU_ADMIN_EMAIL") or "").strip().lower()
    password = (os.environ.get("WENSHU_ADMIN_PASSWORD") or "").strip()
    name = os.environ.get("WENSHU_ADMIN_NAME") or "管理员"
    if not email or not password:
        sys.exit("需要 WENSHU_ADMIN_EMAIL 和 WENSHU_ADMIN_PASSWORD")
    if len(password) < 6:
        sys.exit("密码至少 6 位")

    salt, digest = hash_password(password)
    conn = db()
    row = conn.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
    if row:
        conn.execute(
            "UPDATE users SET pass_salt=?, pass_hash=?, role='admin', disabled=0, display_name=? WHERE email=?",
            (salt, digest, name, email),
        )
        action = "updated"
    else:
        conn.execute(
            "INSERT INTO users (email, display_name, role, pass_salt, pass_hash, created_at)"
            " VALUES (?, ?, 'admin', ?, ?, ?)",
            (email, name, salt, digest, now_iso()),
        )
        action = "created"
    conn.commit()
    conn.close()
    print(f"admin {action}: {email}")


if __name__ == "__main__":
    main()
