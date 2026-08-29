"""打包客户版安装程序（C# 自解压安装器，嵌入无隐私数据的客户版压缩包）。"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "dist" / "财务软件客户版"
RELEASE_DIR = ROOT / "releases"
ALLOWED_TOP = {
    "财务软件客户版.exe",
    "updater_helper.exe",
    "_internal",
    "edition.ini",
    "update_config.ini",
}
CSC = Path(
    r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe"
)


def make_zip(version: str) -> Path:
    if not APP_DIR.exists():
        raise SystemExit(f"请先运行 build_customer.bat：{APP_DIR}")
    if not (APP_DIR / "edition.ini").exists():
        (APP_DIR / "edition.ini").write_text("customer\n", encoding="ascii")
    RELEASE_DIR.mkdir(parents=True, exist_ok=True)
    target = RELEASE_DIR / f"customer-app-{version}.zip"
    if target.exists():
        target.unlink()
    count = 0
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
        for source in APP_DIR.rglob("*"):
            relative = source.relative_to(APP_DIR)
            top = relative.parts[0] if relative.parts else ""
            if top not in ALLOWED_TOP or source.is_dir():
                continue
            zf.write(source, str(relative))
            count += 1
    if count == 0:
        target.unlink()
        raise SystemExit("客户版压缩包为空")
    with zipfile.ZipFile(target) as zf:
        names = zf.namelist()
    leaked = [n for n in names if any(
        p in n for p in ("finance.db", "/data/", "/backups/", "/exports/", ".old_")
    )]
    if leaked:
        target.unlink()
        raise SystemExit("客户版压缩包包含隐私数据：\n" + "\n".join(leaked[:20]))
    return target


def build(version: str, desktop: Path, repo: str = "MORRRRRK/finance-releases") -> Path:
    zip_path = make_zip(version)
    digest = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    update = {
        "version": version,
        "url": (
            f"https://github.com/{repo}/releases/download/"
            f"v{version}/customer-app-{version}.zip"
        ),
        "sha256": digest,
        "min_app_version": "2.0.0",
        "notes": f"V{version} 更新",
    }
    (RELEASE_DIR / "customer_update.json").write_text(
        json.dumps(update, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    source_cs = ROOT / "tools" / "setup_customer.cs"
    temp_cs = RELEASE_DIR / "setup_customer.cs"
    temp_cs.write_bytes(source_cs.read_bytes())
    output = desktop / "个人财务软件客户版安装程序.exe"
    command = [
        str(CSC),
        "/nologo",
        "/target:winexe",
        f"/out:{output}",
        f"/resource:{zip_path},customer.zip",
        "/r:System.Windows.Forms.dll",
        str(temp_cs),
    ]
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if result.returncode != 0 or not output.exists():
        raise SystemExit("安装程序编译失败：\n" + result.stdout + result.stderr)
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", default="2.4.0")
    parser.add_argument(
        "--repo",
        default="MORRRRRK/finance-releases",
        help="GitHub owner/repo",
    )
    parser.add_argument(
        "--desktop",
        default="D:/Desktop",
        help="安装程序输出目录",
    )
    args = parser.parse_args()
    desktop = Path(args.desktop)
    desktop.mkdir(parents=True, exist_ok=True)
    output = build(args.version, desktop, args.repo)
    print("客户版安装程序：", output)


if __name__ == "__main__":
    main()
