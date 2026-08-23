"""独立更新助手：替换程序文件并保留用户数据。"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from pathlib import Path


def _write_result(path: Path, data: dict) -> None:
    try:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass


def main() -> int:
    if len(sys.argv) < 2:
        print("缺少更新任务文件")
        return 1
    job_path = Path(sys.argv[1])
    try:
        job = json.loads(job_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print("无法读取更新任务：", exc)
        return 1

    app_dir = Path(job["app_dir"])
    launcher = app_dir / job["launcher"]
    internal = app_dir / "_internal"
    zip_path = Path(job["zip_path"])
    version = job.get("new_version", "unknown")
    data_dirs = [name for name in job.get("data_dirs", []) if name]
    result_path = app_dir / "update_result.json"

    time.sleep(2)
    old_dir = app_dir / f".old_{version}"
    try:
        old_dir.mkdir(parents=True, exist_ok=True)
        if launcher.exists():
            shutil.move(str(launcher), str(old_dir / launcher.name))
        if internal.exists():
            shutil.move(str(internal), str(old_dir / internal.name))

        shutil.unpack_archive(str(zip_path), str(app_dir))
        for name in data_dirs:
            (app_dir / name).mkdir(parents=True, exist_ok=True)

        new_launcher = app_dir / job["launcher"]
        if not new_launcher.exists():
            raise RuntimeError("更新包中没有找到程序启动文件")
        _write_result(result_path, {"success": True, "version": version})
        subprocess.Popen([str(new_launcher)], cwd=str(app_dir))
        shutil.rmtree(old_dir, ignore_errors=True)
        return 0
    except Exception as exc:
        try:
            if not launcher.exists() and (old_dir / launcher.name).exists():
                shutil.move(str(old_dir / launcher.name), str(launcher))
            if not internal.exists() and (old_dir / internal.name).exists():
                shutil.move(str(old_dir / internal.name), str(internal))
        except OSError:
            pass
        _write_result(result_path, {"success": False, "error": str(exc), "version": version})
        print("更新失败：", exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
