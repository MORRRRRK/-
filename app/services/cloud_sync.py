"""WebDAV 加密云同步：SQLite 数据库加密后上传到 WebDAV，支持手动与启动自动同步。"""
from __future__ import annotations

import base64
import os
import sqlite3
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

MAGIC = b"FINSYNC1"
PBKDF2_ITERATIONS = 200_000
REMOTE_NAME = "finance-encrypted.db"


class CloudSyncError(Exception):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


def derive_key(password: str, salt: bytes) -> bytes:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=PBKDF2_ITERATIONS,
    )
    return kdf.derive(password.encode("utf-8"))


def encrypt_bytes(plain: bytes, password: str) -> bytes:
    salt = os.urandom(16)
    nonce = os.urandom(12)
    key = derive_key(password, salt)
    ciphertext = AESGCM(key).encrypt(nonce, plain, None)
    return MAGIC + salt + nonce + ciphertext


def decrypt_bytes(blob: bytes, password: str) -> bytes:
    if not blob.startswith(MAGIC) or len(blob) < len(MAGIC) + 28:
        raise CloudSyncError("不是有效的加密同步文件")
    offset = len(MAGIC)
    salt = blob[offset : offset + 16]
    nonce = blob[offset + 16 : offset + 28]
    ciphertext = blob[offset + 28 :]
    key = derive_key(password, salt)
    try:
        return AESGCM(key).decrypt(nonce, ciphertext, None)
    except Exception:
        raise CloudSyncError("同步密码错误或文件已损坏")


def remote_url(base_url: str) -> str:
    base = (base_url or "").strip().rstrip("/")
    if not base:
        raise CloudSyncError("请先填写 WebDAV 地址")
    parts = urllib.parse.urlsplit(base)
    segments = [
        urllib.parse.quote(segment)
        for segment in parts.path.split("/")
        if segment
    ]
    if segments and segments[-1] == REMOTE_NAME:
        path = "/" + "/".join(segments)
    else:
        path = "/" + "/".join(segments) + "/" + REMOTE_NAME
    return urllib.parse.urlunsplit((parts.scheme, parts.netloc, path, "", ""))


def _request(
    method: str,
    url: str,
    username: str,
    password: str,
    data: bytes | None = None,
    timeout: int = 60,
    extra_headers: dict[str, str] | None = None,
) -> bytes:
    token = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
    headers = {
        "Authorization": f"Basic {token}",
        "User-Agent": "FinanceApp-CloudSync",
        "Accept": "*/*",
    }
    if data is not None:
        headers["Content-Type"] = "application/octet-stream"
    if extra_headers:
        headers.update(extra_headers)
    request = urllib.request.Request(
        url,
        data=data,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.read()
    except urllib.error.HTTPError as exc:
        raise CloudSyncError(
            f"WebDAV 请求失败（{method} {url}，HTTP {exc.code}）", exc.code
        ) from exc
    except urllib.error.URLError as exc:
        raise CloudSyncError(f"网络连接失败：{exc.reason}") from exc


def _remote_exists(url: str, username: str, password: str) -> bool:
    try:
        _request(
            "PROPFIND",
            url,
            username,
            password,
            extra_headers={"Depth": "0"},
        )
        return True
    except CloudSyncError as exc:
        if exc.status_code == 404:
            return False
        if exc.status_code in (401, 403):
            raise
        if exc.status_code in (405, 501):
            try:
                _request("GET", url, username, password)
                return True
            except CloudSyncError as get_exc:
                if get_exc.status_code == 404:
                    return False
                raise
        raise


def _download_remote(url: str, username: str, password: str) -> bytes:
    try:
        return _request("GET", url, username, password)
    except CloudSyncError as exc:
        if exc.status_code == 404:
            raise CloudSyncError("云端没有找到同步文件") from exc
        raise


def _upload_remote(url: str, username: str, password: str, data: bytes) -> None:
    _ensure_remote_path(url, username, password)
    try:
        _request("PUT", url, username, password, data)
        return
    except CloudSyncError as exc:
        if exc.status_code not in (404, 409, 405, 412):
            raise
    folder = url.rsplit("/", 1)[0] + "/"
    try:
        _request("MKCOL", folder, username, password)
    except CloudSyncError:
        pass
    _request("PUT", url, username, password, data)


def _ensure_remote_path(url: str, username: str, password: str) -> None:
    """按需创建 WebDAV 路径中的每一级目录，避免 PUT 返回 404。"""
    parts = urllib.parse.urlsplit(url)
    segments = [
        urllib.parse.unquote(segment)
        for segment in parts.path.split("/")
        if segment
    ]
    if not segments:
        return
    dirs = segments[:-1]
    base = f"{parts.scheme}://{parts.netloc}"
    for index in range(1, len(dirs) + 1):
        encoded = [
            urllib.parse.quote(segment) for segment in dirs[:index]
        ]
        folder = base + "/" + "/".join(encoded) + "/"
        try:
            _request("MKCOL", folder, username, password, timeout=30)
        except CloudSyncError:
            pass


def test_connection(base_url: str, username: str, password: str) -> str:
    folder = (base_url or "").strip().rstrip("/") + "/"
    try:
        _request(
            "PROPFIND",
            folder,
            username,
            password,
            timeout=30,
            extra_headers={"Depth": "0"},
        )
        return "连接成功"
    except CloudSyncError as exc:
        if exc.status_code == 404:
            return "连接成功（目录不存在，首次同步会自动创建）"
        if exc.status_code in (401, 403):
            raise CloudSyncError("账号或密码错误，请检查 WebDAV 凭据", exc.status_code)
        if exc.status_code in (405, 501):
            try:
                _request("HEAD", folder, username, password, timeout=30)
                return "连接成功"
            except CloudSyncError as head_exc:
                if head_exc.status_code == 404:
                    return "连接成功（目录不存在，首次同步会自动创建）"
                if head_exc.status_code in (401, 403):
                    raise CloudSyncError(
                        "账号或密码错误，请检查 WebDAV 凭据", head_exc.status_code
                    )
                raise
        raise


def _backup_db_to_temp(db_path: Path) -> Path:
    handle = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    target = Path(handle.name)
    handle.close()
    source = sqlite3.connect(str(db_path))
    dest = sqlite3.connect(str(target))
    try:
        source.backup(dest)
    finally:
        dest.close()
        source.close()
    return target


def _update_sync_settings(db_path: Path, **values: str) -> None:
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)"
        )
        for key, value in values.items():
            conn.execute(
                "INSERT INTO settings(key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )
        conn.commit()
    finally:
        conn.close()


def _get_sync_setting(db_path: Path, key: str) -> str:
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)"
        )
        row = conn.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ).fetchone()
        return str(row[0]) if row else ""
    finally:
        conn.close()


def push_sync(
    db_path: Path,
    base_url: str,
    username: str,
    password: str,
    sync_password: str,
    backup_dir: Path,
) -> dict:
    if len(sync_password) < 8:
        raise CloudSyncError("同步密码至少 8 位，用于加密云端数据")
    url = remote_url(base_url)
    plain_path = _backup_db_to_temp(db_path)
    try:
        plain = plain_path.read_bytes()
        encrypted = encrypt_bytes(plain, sync_password)
        conflict_path = None
        conflict_saved = False
        if _remote_exists(url, username, password):
            if not _get_sync_setting(db_path, "cloud_sync_last_time"):
                backup_dir = Path(backup_dir)
                backup_dir.mkdir(parents=True, exist_ok=True)
                stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                conflict_path = backup_dir / f"cloud_conflict_{stamp}.enc"
                conflict_path.write_bytes(_download_remote(url, username, password))
                conflict_saved = True
        _upload_remote(url, username, password, encrypted)
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        _update_sync_settings(
            db_path,
            cloud_sync_last_time=now,
            cloud_sync_last_status="同步成功",
            cloud_sync_last_error="",
        )
        return {
            "conflict_saved": conflict_saved,
            "conflict_path": str(conflict_path) if conflict_path else "",
            "message": "同步成功",
        }
    finally:
        plain_path.unlink(missing_ok=True)


def pull_sync(
    db_path: Path,
    base_url: str,
    username: str,
    password: str,
    sync_password: str,
) -> Path:
    url = remote_url(base_url)
    encrypted = _download_remote(url, username, password)
    plain = decrypt_bytes(encrypted, sync_password)
    target = Path(tempfile.gettempdir()) / f"finance_restore_{int(time.time() * 1000)}.db"
    target.write_bytes(plain)
    conn = sqlite3.connect(str(target))
    try:
        check = conn.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        conn.close()
    if str(check).lower() != "ok":
        raise CloudSyncError("云端文件校验失败，未执行恢复")
    return target
