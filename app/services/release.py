"""开发版一键推送客户版更新：打包、生成更新清单并上传 GitHub Release。"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

from ..core.paths import app_root

GITHUB_API = "https://api.github.com"
GITHUB_UPLOADS = "https://uploads.github.com"
DEFAULT_REPO = "MORRRRRK/finance-releases"
DEFAULT_CODE_REPO = "MORRRRRK/-"
DEV_TOP = {"财务软件.exe", "updater_helper.exe", "_internal"}
CUSTOMER_TOP = {
    "财务软件客户版.exe",
    "updater_helper.exe",
    "_internal",
    "edition.ini",
    "update_config.ini",
    "app_version.txt",
}
PRIVATE_PATTERNS = (
    "finance.db",
    "/data/",
    "/backups/",
    "/exports/",
    ".old_",
    "update_result.json",
)


def _find_source_root() -> Path:
    """向上查找包含 run.py 与 .venv 的项目目录，兼容源码运行和打包运行。"""
    start = app_root()
    for candidate in (start, *start.parents):
        if (
            (candidate / "run.py").exists()
            and (candidate / ".venv" / "Scripts" / "python.exe").exists()
        ):
            return candidate
    return app_root()


def _project_layout() -> tuple[Path, Path, Path, Path]:
    source_root = _find_source_root()
    dev_app = app_root()
    if not getattr(sys, "frozen", False):
        dev_app = source_root / "dist" / "财务软件"
    customer_app = source_root / "dist" / "财务软件客户版"
    releases_dir = source_root / "releases"
    return source_root, dev_app, customer_app, releases_dir


def customer_build_dir() -> Path:
    return _project_layout()[2]


def build_customer() -> None:
    """在项目目录执行 PyInstaller 构建客户版（无交互）。

    先构建到临时目录，再只替换程序文件（exe/_internal/updater_helper/配置），
    完全不动 data/backups/exports，客户版本地数据永远不会被构建清除。
    """
    source_root, _, _, _ = _project_layout()
    customer_app = source_root / "dist" / "财务软件客户版"
    new_app = source_root / "dist" / "财务软件客户版_new"
    if new_app.exists():
        shutil.rmtree(new_app)
    python_exe = source_root / ".venv" / "Scripts" / "python.exe"
    if not python_exe.exists():
        python_exe = Path(sys.executable)
    commands = [
        [
            str(python_exe),
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            "--onefile",
            "--console",
            "--name",
            "updater_helper",
            "tools\\updater_helper.py",
        ],
        [
            str(python_exe),
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            "--windowed",
            "--name",
            "财务软件客户版",
            "--icon",
            "app\\assets\\app_icon.ico",
            "--add-data",
            "app\\assets;app\\assets",
            "--add-data",
            "app\\web;app\\web",
            "--distpath",
            "dist\\财务软件客户版_new",
            "--workpath",
            "build\\customer_work",
            "run.py",
        ],
    ]
    for command in commands:
        result = subprocess.run(
            command,
            cwd=str(source_root),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode != 0:
            tail = (result.stdout or "")[-800:] + (result.stderr or "")[-800:]
            raise RuntimeError("客户版构建失败：\n" + tail)
    built = new_app / "财务软件客户版"
    if not built.exists():
        built = new_app
    (built / "edition.ini").write_text("customer\n", encoding="ascii")
    shutil.copy2(
        source_root / "dist" / "updater_helper.exe",
        built / "updater_helper.exe",
    )
    (built / "update_config.ini").write_text(
        "repo=MORRRRRK/finance-releases\n", encoding="ascii"
    )
    from .. import __version__
    (built / "app_version.txt").write_text(
        __version__, encoding="utf-8"
    )
    if not customer_app.exists():
        shutil.move(str(built), str(customer_app))
        shutil.rmtree(new_app, ignore_errors=True)
        return
    _stop_customer_processes(customer_app)
    _replace_customer_program(built, customer_app)
    shutil.rmtree(new_app)


def _replace_customer_program(new_app: Path, customer_app: Path) -> None:
    """用新构建的程序文件覆盖旧客户版，保留 data/backups/exports。"""
    for item in new_app.iterdir():
        target = customer_app / item.name
        if item.name == "_internal":
            old = customer_app / "_internal"
            if old.exists():
                shutil.rmtree(old)
            shutil.copytree(item, old)
        elif item.is_file():
            shutil.copy2(item, target)
        # data/backups/exports 等目录不复制，旧目录原样保留


def _stop_customer_processes(customer_app: Path) -> None:
    """关闭从指定客户版目录启动的进程，避免构建时文件被占用。"""
    subprocess.run(
        ["taskkill.exe", "/F", "/IM", "财务软件客户版.exe"],
        capture_output=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        check=False,
    )
    escaped = str(customer_app).replace("'", "''")
    command = (
        "Get-Process | Where-Object { $_.Path -like '"
        + escaped
        + "*' } | Stop-Process -Force -ErrorAction SilentlyContinue"
    )
    subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", command],
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        timeout=30,
        check=False,
    )
    time.sleep(1)


def _git(args: list[str], cwd: Path) -> tuple[int, str]:
    result = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return result.returncode, (result.stdout or "") + (result.stderr or "")


def push_source(
    version: str,
    notes: str,
    code_repo: str,
    token: str,
) -> None:
    """提交并推送当前源码到源码仓库。"""
    source_root = _find_source_root()
    if not (source_root / ".git").exists():
        raise RuntimeError("项目目录不是 Git 仓库，无法上传源码")
    code_repo = (code_repo or DEFAULT_CODE_REPO).strip().strip("/")
    message = f"feat: V{version} 更新"
    if notes.strip():
        message += f" {notes.strip()[:80]}"
    code, output = _git(["add", "-A"], source_root)
    if code != 0:
        raise RuntimeError("git add 失败：\n" + output)
    code, output = _git(["commit", "-m", message], source_root)
    if code not in (0, 1):
        raise RuntimeError("git commit 失败：\n" + output)
    code, output = _git(["rev-parse", "--abbrev-ref", "HEAD"], source_root)
    if code != 0:
        raise RuntimeError("无法获取当前分支：\n" + output)
    branch = output.strip() or "master"
    push_url = (
        f"https://x-access-token:{token}@github.com/{code_repo}.git"
    )
    code, output = _git(["push", push_url, f"{branch}:main"], source_root)
    if code != 0:
        raise RuntimeError("源码推送失败：\n" + output[-800:])


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _package_app(
    source_dir: Path, target: Path, allowed_top: set[str]
) -> Path:
    if not source_dir.exists():
        raise FileNotFoundError(f"找不到打包目录：{source_dir}")
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        target.unlink()
    count = 0
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
        for source in source_dir.rglob("*"):
            relative = source.relative_to(source_dir)
            top = relative.parts[0] if relative.parts else ""
            if top not in allowed_top or source.is_dir():
                continue
            zf.write(source, str(relative))
            count += 1
    if count == 0:
        target.unlink()
        raise RuntimeError(f"发布包为空：{target.name}")
    with zipfile.ZipFile(target) as zf:
        leaked = [
            name
            for name in zf.namelist()
            if any(pattern in name for pattern in PRIVATE_PATTERNS)
        ]
    if leaked:
        target.unlink()
        raise RuntimeError("发布包包含隐私数据，已终止：" + "、".join(leaked[:5]))
    return target


def package(version: str, customer_only: bool = False) -> dict[str, Path]:
    _, dev_app, customer_app, releases_dir = _project_layout()
    paths: dict[str, Path] = {}
    if not customer_only:
        paths["finance_app"] = _package_app(
            dev_app, releases_dir / f"finance-app-{version}.zip", DEV_TOP
        )
    version_file = customer_app / "app_version.txt"
    if version_file.exists():
        built_version = version_file.read_text(encoding="utf-8").strip()
        if built_version and built_version != version:
            raise RuntimeError(
                f"客户版构建版本为 {built_version}，发布版本写的是 {version}，请先同步 __version__ 再推送"
            )
    paths["customer_app"] = _package_app(
        customer_app,
        releases_dir / f"customer-app-{version}.zip",
        CUSTOMER_TOP,
    )
    return paths


def write_manifests(
    version: str,
    repo: str,
    notes: str,
    paths: dict[str, Path],
    customer_only: bool = False,
) -> None:
    _, _, _, releases_dir = _project_layout()
    if not customer_only:
        update = {
            "version": version,
            "url": (
                f"https://github.com/{repo}/releases/download/"
                f"v{version}/finance-app-{version}.zip"
            ),
            "sha256": _sha256(paths["finance_app"]),
            "min_app_version": "2.0.0",
            "notes": notes,
        }
        (releases_dir / "update.json").write_text(
            json.dumps(update, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    customer_update = {
        "version": version,
        "url": (
            f"https://github.com/{repo}/releases/download/"
            f"v{version}/customer-app-{version}.zip"
        ),
        "sha256": _sha256(paths["customer_app"]),
        "min_app_version": "2.0.0",
        "notes": notes,
    }
    (releases_dir / "customer_update.json").write_text(
        json.dumps(customer_update, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _headers(token: str, content_type: str = "application/json") -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "FinanceApp-Release-Pusher",
    }
    if content_type:
        headers["Content-Type"] = content_type
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _request(
    url: str,
    token: str,
    method: str = "GET",
    data: bytes | None = None,
    content_type: str = "application/json",
) -> dict:
    request = urllib.request.Request(
        url,
        data=data,
        headers=_headers(token, content_type),
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            body = response.read()
            return json.loads(body.decode("utf-8")) if body else {}
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="replace")[:300]
        except OSError:
            pass
        raise RuntimeError(f"GitHub 请求失败（HTTP {exc.code}）{detail}") from exc


def _get_or_create_release(
    token: str, repo: str, tag: str, notes: str
) -> dict:
    try:
        return _request(f"{GITHUB_API}/repos/{repo}/releases/tags/{tag}", token)
    except RuntimeError as exc:
        if "HTTP 404" not in str(exc):
            raise
    body = json.dumps(
        {
            "tag_name": tag,
            "name": tag,
            "body": notes,
            "draft": False,
            "prerelease": False,
        },
        ensure_ascii=False,
    ).encode("utf-8")
    return _request(
        f"{GITHUB_API}/repos/{repo}/releases",
        token,
        method="POST",
        data=body,
    )


def _upload_asset(
    token: str,
    repo: str,
    release_id: int,
    name: str,
    path: Path,
    content_type: str,
) -> None:
    assets = _request(
        f"{GITHUB_API}/repos/{repo}/releases/{release_id}/assets", token
    )
    for asset in assets:
        if asset.get("name") == name:
            _request(
                f"{GITHUB_API}/repos/{repo}/releases/assets/{asset['id']}",
                token,
                method="DELETE",
            )
            break
    url = (
        f"{GITHUB_UPLOADS}/repos/{repo}/releases/{release_id}/assets"
        f"?name={urllib.parse.quote(name)}"
    )
    _request(
        url,
        token,
        method="POST",
        data=path.read_bytes(),
        content_type=content_type,
    )


def publish(
    version: str,
    repo: str,
    token: str,
    notes: str,
    customer_only: bool = False,
    build_first: bool = False,
    code_repo: str = "",
) -> str:
    repo = (repo or DEFAULT_REPO).strip().strip("/")
    token = (token or "").strip()
    if not token:
        raise RuntimeError("未填写 GitHub Token，请在“设置”中填写")
    if build_first:
        build_customer()
    packaged = package(version, customer_only)
    write_manifests(version, repo, notes, packaged, customer_only)
    _, _, _, releases_dir = _project_layout()
    tag = f"v{version}"
    release = _get_or_create_release(token, repo, tag, notes)
    assets = []
    if not customer_only:
        assets.append(
            (f"finance-app-{version}.zip", releases_dir / f"finance-app-{version}.zip")
        )
        assets.append(("update.json", releases_dir / "update.json"))
    assets.append(
        (f"customer-app-{version}.zip", releases_dir / f"customer-app-{version}.zip")
    )
    assets.append(("customer_update.json", releases_dir / "customer_update.json"))
    for name, path in assets:
        _upload_asset(
            token,
            repo,
            int(release["id"]),
            name,
            path,
            "application/zip" if path.suffix == ".zip" else "application/json",
        )
    url = f"https://github.com/{repo}/releases/tag/{tag}"
    if code_repo:
        try:
            push_source(version, notes, code_repo, token)
        except RuntimeError as exc:
            raise RuntimeError(f"客户版已发布：{url}，但源码推送失败：{exc}")
    return url
