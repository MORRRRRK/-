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
GITHUB_WEB = "https://github.com"
DEFAULT_RELEASE_REPO = "MORRRRRK/finance-releases"


class UpdaterError(Exception):
    pass


def parse_version(text: str) -> tuple[int, ...]:
    parts = re.findall(r"\d+", text or "")
    return tuple(int(part) for part in parts[:3]) or (0, 0, 0)


def is_newer(remote: str, current: str) -> bool:
    return parse_version(remote) > parse_version(current)


def update_repo(conn) -> str:
    repo = repository.get_setting(conn, "update_repo", "").strip()
    if not repo:
        repo = update_config().get("repo", "")
    if not repo:
        repo = DEFAULT_RELEASE_REPO
    return repo


def update_token(conn) -> str:
    token = repository.get_setting(conn, "github_token", "").strip()
    if not token:
        token = update_config().get("token", "")
    return token


def update_config() -> dict[str, str]:
    """读取程序目录下的 update_config.ini（客户版免配置更新源）。"""
    path = paths.app_root() / "update_config.ini"
    if not path.exists():
        return {}
    config: dict[str, str] = {}
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                config[key.strip().lower()] = value.strip()
    except OSError:
        return {}
    return config


def _github_get(url: str, token: str = "", accept: str = "") -> dict:
    headers = {
        "Accept": accept or "application/vnd.github+json",
        "User-Agent": "FinanceApp-Updater",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise UpdaterError(f"GitHub 请求失败（HTTP {exc.code}）") from exc
    except urllib.error.URLError as exc:
        raise UpdaterError(f"网络连接失败：{exc.reason}") from exc
    except json.JSONDecodeError as exc:
        raise UpdaterError("GitHub 返回内容无法解析") from exc


def check_for_update(repo: str, token: str = "", customer: bool = False) -> dict:
    """返回最新版本信息；无新版本时返回 None。"""
    repo = repo.strip().strip("/")
    if not repo:
        raise UpdaterError("尚未配置 GitHub 更新仓库，请在“设置”中填写 owner/repo")
    manifest_name = "customer_update.json" if customer else "update.json"
    try:
        manifest = _github_get(
            f"{GITHUB_WEB}/{repo}/releases/latest/download/{manifest_name}",
            token,
            accept="application/octet-stream",
        )
        version = str(manifest.get("version") or "")
        update_url = str(manifest.get("url") or "")
        sha256 = str(manifest.get("sha256") or "")
        notes = str(manifest.get("notes") or "")
        if version and update_url and sha256:
            return {
                "version": version,
                "url": update_url,
                "sha256": sha256,
                "notes": notes,
                "current_version": __version__,
            }
    except UpdaterError:
        pass
    release = _github_get(f"{GITHUB_API}/repos/{repo}/releases/latest", token)
    tag = str(release.get("tag_name") or "").lstrip("v")
    version = tag or str(release.get("name") or "")
    update_url = ""
    zip_url = ""
    sha256 = ""
    notes = str(release.get("body") or "")
    zip_prefix = "customer-app-" if customer else "finance-app-"
    for asset in release.get("assets") or []:
        name = str(asset.get("name") or "")
        asset_url = str(
            asset.get("url") if token else asset.get("browser_download_url") or ""
        )
        if name == manifest_name:
            try:
                manifest = _github_get(
                    asset_url, token, accept="application/octet-stream"
                )
                version = str(manifest.get("version") or version)
                if not token:
                    update_url = str(manifest.get("url") or "")
                sha256 = str(manifest.get("sha256") or "")
                notes = str(manifest.get("notes") or notes)
            except Exception:
                pass
        elif name.startswith(zip_prefix) and name.endswith(".zip"):
            zip_url = asset_url
            if not update_url:
                update_url = asset_url
    if token and zip_url:
        update_url = zip_url
    if not update_url:
        raise UpdaterError("最新 Release 中没有找到客户版更新包")
    return {
        "version": version,
        "url": update_url,
        "sha256": sha256,
        "notes": notes,
        "current_version": __version__,
    }


def _download(url: str, target: Path, token: str = "") -> None:
    headers = {"User-Agent": "FinanceApp-Updater", "Accept": "application/octet-stream"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers)
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


def prepare_update(
    conn,
    update_info: dict,
    backup_dir: Path | None = None,
    token: str = "",
) -> tuple[Path, Path]:
    """下载并校验更新包，备份数据库，生成更新任务，返回 (任务文件, 助手副本)。"""
    temp_dir = Path(tempfile.gettempdir()) / "finance_app_update"
    temp_dir.mkdir(parents=True, exist_ok=True)
    version = update_info["version"]
    zip_path = temp_dir / f"finance-app-{version}.zip"
    if zip_path.exists():
        zip_path.unlink()
    _download(update_info["url"], zip_path, token)
    expected = update_info.get("sha256") or ""
    if expected:
        actual = _sha256(zip_path)
        if actual.lower() != expected.lower():
            raise UpdaterError("更新包校验失败（SHA-256 不匹配）")

    backup_target = backup_dir or paths.backups_dir()
    _backup_database(conn, backup_target)

    job = {
        "app_dir": str(paths.app_root()),
        "launcher": _launcher_name(),
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


def _launcher_name() -> str:
    app_dir = paths.app_root()
    for name in ("财务软件客户版.exe", "财务软件.exe"):
        if (app_dir / name).exists():
            return name
    return "财务软件.exe"


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
