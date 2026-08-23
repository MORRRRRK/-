"""客户版在线更新服务：检查、下载、校验并启动独立更新助手。"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import sqlite3
import subprocess
import tempfile
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

from .. import __version__
from ..core import paths
from ..core import repository

GITHUB_API = "https://api.github.com"


class UpdaterError(Exception):
    pass


def parse_version(text: str) -> tuple[int, ...]:
    parts = re.findall(r"\d+", text or "")
    return tuple(int(part) for part in parts[:3]) or (0, 0, 0)


def is_newer(remote: str, current: str) -> bool:
    return parse_version(remote) > parse_version(current)


def update_repo(conn) -> str:
    return repository.get_setting(conn, "update_repo", "").strip()


def _github_get(url: str) -> dict:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "FinanceApp-Updater",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise UpdaterError(f"GitHub 请求失败（HTTP {exc.code}）") from exc
    except urllib.error.URLError as exc:
        raise UpdaterError(f"网络连接失败：{exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise UpdaterError("GitHub 返回内容无法解析") from exc


def check_for_update(repo: str) -> dict:
    """返回最新版本信息；无新版本时返回 None。"""
    repo = repo.strip().strip("/")
    if not repo:
        raise UpdaterError("尚未配置 GitHub 更新仓库，请在“设置”中填写 owner/repo")
    release = _github_get(f"{GITHUB_API}/repos/{repo}/releases/latest")
    tag = str(release.get("tag_name") or "").lstrip("v")
    version = tag or str(release.get("name") or "")
    update_url = ""
    sha256 = ""
    notes = str(release.get("body") or "")
    for asset in release.get("assets") or []:
        name = str(asset.get("name") or "")
        if name == "update.json":
            try:
                manifest = _github_get(str(asset.get("browser_download_url") or ""))
                version = str(manifest.get("version") or version)
                update_url = str(manifest.get("url") or "")
                sha256 = str(manifest.get("sha256") or "")
                notes = str(manifest.get("notes") or notes)
            except Exception:
                pass
        elif not update_url and name.startswith("finance-app-") and name.endswith(".zip"):
            update_url = str(asset.get("browser_download_url") or "")
    if not update_url:
        raise UpdaterError("最新 Release 中没有找到客户版更新包")
    return {
        "version": version,
        "url": update_url,
        "sha256": sha256,
        "notes": notes,
        "current_version": __version__,
    }


def _download(url: str, target: Path) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "FinanceApp-Updater"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response, target.open("wb") as out:
            shutil.copyfileobj(response, out, length=1024 * 1024)
    except urllib.error.HTTPError as exc:
        raise UpdaterError(f"下载失败（HTTP {exc.code}）") from exc
    except urllib.error.URLError as exc:
        raise UpdaterError(f"下载失败：{exc.reason}") from exc


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _backup_database(conn, backup_dir: Path) -> Path:
    backup_dir = Path(backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = backup_dir / f"pre_update_{stamp}.db"
    with sqlite3.connect(str(target)) as dest:
        conn.backup(dest)
    return target


def prepare_update(conn, update_info: dict, backup_dir: Path | None = None) -> tuple[Path, Path]:
    """下载并校验更新包，备份数据库，生成更新任务，返回 (任务文件, 助手副本)。"""
    temp_dir = Path(tempfile.gettempdir()) / "finance_app_update"
    temp_dir.mkdir(parents=True, exist_ok=True)
    version = update_info["version"]
    zip_path = temp_dir / f"finance-app-{version}.zip"
    if zip_path.exists():
        zip_path.unlink()
    _download(update_info["url"], zip_path)
    expected = update_info.get("sha256") or ""
    if expected:
        actual = _sha256(zip_path)
        if actual.lower() != expected.lower():
            raise UpdaterError("更新包校验失败（SHA-256 不匹配）")

    backup_target = backup_dir or paths.backups_dir()
    _backup_database(conn, backup_target)

    job = {
        "app_dir": str(paths.app_root()),
        "launcher": "财务软件.exe",
        "zip_path": str(zip_path),
        "new_version": version,
        "current_version": __version__,
        "data_dirs": ["data", "backups", "exports"],
    }
    job_path = temp_dir / "update_job.json"
    job_path.write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")

    helper_source = paths.app_root() / "updater_helper.exe"
    if not helper_source.exists():
        raise UpdaterError("缺少 updater_helper.exe，请重新安装完整版本")
    helper_copy = temp_dir / "updater_helper.exe"
    shutil.copy2(helper_source, helper_copy)
    return job_path, helper_copy


def launch_updater(job_path: Path, helper_copy: Path) -> None:
    try:
        subprocess.Popen(
            [str(helper_copy), str(job_path)],
            creationflags=getattr(subprocess, "DETACHED_PROCESS", 0)
            | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
            close_fds=True,
        )
    except OSError as exc:
        raise UpdaterError(f"无法启动更新助手：{exc}") from exc
