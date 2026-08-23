"""把开发版与客户版发布包上传到公开发布仓库。"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

GITHUB_API = "https://api.github.com"
GITHUB_UPLOADS = "https://uploads.github.com"
ROOT = Path(__file__).resolve().parents[1]
RELEASES_DIR = ROOT / "releases"


def _headers(token: str, content_type: str = "application/json") -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "FinanceApp-Release-Uploader",
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
        return _request(
            f"{GITHUB_API}/repos/{repo}/releases/tags/{tag}", token
        )
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
    token: str, repo: str, release_id: int, name: str, path: Path, content_type: str
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
    data = path.read_bytes()
    url = (
        f"{GITHUB_UPLOADS}/repos/{repo}/releases/{release_id}/assets"
        f"?name={urllib.parse.quote(name)}"
    )
    uploaded = _request(
        url,
        token,
        method="POST",
        data=data,
        content_type=content_type,
    )
    print(f"上传成功：{uploaded.get('name')}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True)
    parser.add_argument("--repo", default="MORRRRRK/finance-releases")
    parser.add_argument("--token", default=os.environ.get("GITHUB_TOKEN", ""))
    parser.add_argument("--notes", default="个人财务软件发布包")
    args = parser.parse_args()
    token = args.token or os.environ.get("GH_TOKEN", "")
    if not token:
        raise SystemExit("请设置 GITHUB_TOKEN 环境变量或 --token 参数")

    version = args.version
    tag = f"v{version}"
    assets = [
        (
            f"finance-app-{version}.zip",
            RELEASES_DIR / f"finance-app-{version}.zip",
            "application/zip",
        ),
        ("update.json", RELEASES_DIR / "update.json", "application/json"),
        (
            f"customer-app-{version}.zip",
            RELEASES_DIR / f"customer-app-{version}.zip",
            "application/zip",
        ),
        (
            "customer_update.json",
            RELEASES_DIR / "customer_update.json",
            "application/json",
        ),
    ]
    missing = [name for name, path, _ in assets if not path.exists()]
    if missing:
        raise SystemExit("缺少发布文件：" + "、".join(missing))

    release = _get_or_create_release(token, args.repo, tag, args.notes)
    for name, path, content_type in assets:
        _upload_asset(
            token, args.repo, int(release["id"]), name, path, content_type
        )
    print(f"发布完成：https://github.com/{args.repo}/releases/tag/{tag}")


if __name__ == "__main__":
    main()
