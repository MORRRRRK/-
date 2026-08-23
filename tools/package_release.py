"""打包客户版发布包并生成 update.json。"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "dist" / "财务软件"
RELEASE_DIR = ROOT / "releases"
ALLOWED_TOP = {"财务软件.exe", "updater_helper.exe", "_internal"}
PRIVATE_PATTERNS = ("finance.db", "/data/", "/backups/", "/exports/", ".old_", "update_result.json")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def package(version: str) -> Path:
    if not APP_DIR.exists():
        raise SystemExit(f"找不到打包目录：{APP_DIR}")
    if not (APP_DIR / "财务软件.exe").exists() or not (APP_DIR / "_internal").exists():
        raise SystemExit("打包目录缺少 财务软件.exe 或 _internal")
    RELEASE_DIR.mkdir(parents=True, exist_ok=True)
    target = RELEASE_DIR / f"finance-app-{version}.zip"
    if target.exists():
        target.unlink()
    included = 0
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
        for source in APP_DIR.rglob("*"):
            relative = source.relative_to(APP_DIR)
            top = relative.parts[0] if relative.parts else ""
            if top not in ALLOWED_TOP:
                continue
            if source.is_dir():
                continue
            zf.write(source, str(relative))
            included += 1
    if included == 0:
        target.unlink()
        raise SystemExit("发布包为空，打包失败")
    with zipfile.ZipFile(target) as zf:
        names = zf.namelist()
    leaked = [
        name
        for name in names
        if any(pattern in name for pattern in PRIVATE_PATTERNS)
    ]
    if leaked:
        target.unlink()
        raise SystemExit("发布包包含隐私数据，已终止：\n" + "\n".join(leaked[:20]))
    return target


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    parser.add_argument("--repo", required=True, help="GitHub owner/repo")
    parser.add_argument("--tag", required=True, help="Release tag，如 v2.4.0")
    parser.add_argument("--notes", default="")
    args = parser.parse_args()

    zip_path = package(args.version)
    update = {
        "version": args.version,
        "url": (
            f"https://github.com/{args.repo}/releases/download/"
            f"{args.tag}/finance-app-{args.version}.zip"
        ),
        "sha256": sha256_file(zip_path),
        "min_app_version": "2.0.0",
        "notes": args.notes,
    }
    (RELEASE_DIR / "update.json").write_text(
        json.dumps(update, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print("发布包：", zip_path)
    print("update.json：", RELEASE_DIR / "update.json")


if __name__ == "__main__":
    main()
