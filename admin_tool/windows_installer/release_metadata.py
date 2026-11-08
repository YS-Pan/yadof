"""Package administrator sources and evidence after successful MSI acceptance."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import runpy
import subprocess
import zipfile


ROOT = Path(__file__).resolve().parents[2]


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--acceptance", type=Path, required=True)
    parser.add_argument("--dist", type=Path, required=True)
    args = parser.parse_args()
    work, dist = args.acceptance.resolve(), args.dist.resolve()
    work.relative_to((ROOT / "temp").resolve())
    version = runpy.run_path(str(ROOT / "src/yadof/_version.py"))["__version__"]
    acceptance = json.loads((work / "acceptance.json").read_text(encoding="utf-8"))
    runtime = json.loads((work / "runtime-evidence.json").read_text(encoding="utf-8"))
    upgraded = json.loads((work / "after-upgrade/runtime-evidence.json").read_text(encoding="utf-8"))
    if acceptance["status"] != "passed" or runtime["yadof"] != version or upgraded["yadof"] != version:
        raise ValueError("Release requires successful same-version MSI acceptance")
    commit = os.environ.get("GITHUB_SHA") or subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    administrator = dist / f"yadof-admin-{version}.zip"
    with zipfile.ZipFile(administrator, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.write(ROOT / "admin_config.pyw", "admin_config.pyw")
        for path in sorted((ROOT / "admin_tool/cluster_config").glob("*")):
            if path.suffix in {".py", ".ps1", ".md"} and not path.name.startswith("test_"):
                archive.write(path, path.relative_to(ROOT).as_posix())
    report = {
        "version": version, "source_commit": commit, "status": "passed",
        "msi_acceptance": acceptance, "runtime": runtime, "after_upgrade": upgraded,
        "desktop_entries": [
            "yadof_tools/viewcost.pyw", "yadof_tools/viewtime.pyw",
            "yadof_tools/viewerror.pyw", "yadof_tools/surrogateviewer.pyw",
            "user_tools/aedt_parameters_gui.pyw",
        ],
    }
    report_path = dist / f"yadof-{version}-validation.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    checksums = "".join(f"{digest(path)}  {path.name}\n" for path in sorted(dist.iterdir()) if path.is_file() and path.name != "SHA256SUMS.txt")
    (dist / "SHA256SUMS.txt").write_text(checksums, encoding="utf-8")
    notes = f'''将 tools 分为 `yadof_tools` 和 `user_tools`。

- `yadof_tools` 顶层提供 `viewcost.pyw`、`viewtime.pyw`、`viewerror.pyw`、`surrogateviewer.pyw`；各工具的 Python 实现放入独立子目录。
- `user_tools/aedt_parameters_gui.pyw` 包含完整 AEDT 桌面界面，共用解析器单独保存。只导出 `OptimizationSetup1` 中 Include 勾选的变量，并在替换参数文件前保存原文件备份。
- 所有双击入口使用所属安装环境。主 GUI 的 tools 按钮打开分类目录，进度条旁显示按次清零、启停联动的总耗时。
- CLI 命令和参数保持不变。Python 工具导入路径更新到 `yadof.tools.yadof_tools` 和 `yadof.tools.user_tools.aedt_parameters`。

Windows x64 MSI 沿用已审计的 CPython 3.11.15 和依赖，重新生成当前模块布局的启动器。已通过隔离安装、GUI/依赖、通用任务、修复、同版本升级、卸载及数据保留验收。验证报告和 SHA-256 随资产发布。

源码提交：`{commit}`。
'''
    (work / "release-notes.md").write_text(notes, encoding="utf-8")
    print(f"Release metadata ready: {version}")


if __name__ == "__main__":
    main()
