"""PyInstaller helper - bundles LexiArbiter into a macOS .app distribution.

Usage (on a macOS machine, in your venv):

    pip install pyinstaller
    python build_mac.py

The output is `dist/LexiArbiter.app/`，內部結構（macOS 的 one-dir = .app 資料夾）：

    LexiArbiter.app/
      Contents/
        MacOS/
          LexiArbiter         ← 執行檔
          configs/            ← 與執行檔同層，讓 app_root() 找得到
          assets/
          _internal/          ← PyInstaller 依賴
        Resources/
          LexiArbiter_icon.icns
        Info.plist

打包流程末端會跑 ad-hoc codesign，讓 Apple Silicon 能執行（arm64 強制要求簽名），
再用 `ditto` 壓成 zip — `ditto` 比 `zip` 更可靠地保留 macOS metadata（包括
codesign signature 與 bundle 結構）。

注意：本腳本只能在 macOS 上跑（仰賴 codesign / ditto）。Windows 端打包請用
`build_exe.py`。
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
DIST = HERE / "dist"
APP_NAME = "LexiArbiter"
BUNDLE_ID = "com.lexiarbiter.app"
ARCH = "arm64"


def main():
    if sys.platform != "darwin":
        print("build_mac.py 只能在 macOS 上執行；Windows 請改用 build_exe.py。",
              file=sys.stderr)
        sys.exit(1)

    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("找不到 PyInstaller，請先 `pip install pyinstaller` 後再執行。",
              file=sys.stderr)
        sys.exit(1)

    icon_path = HERE / "assets" / "LexiArbiter_icon.icns"
    if not icon_path.exists():
        print(f"找不到 icon 檔：{icon_path}，將以 PyInstaller 預設 icon 打包。\n"
              "（在 GitHub Actions 中此檔由 workflow 從 png 動態產生。本機打包前\n"
              "請先用 sips + iconutil 把 LexiArbiter_icon.png 轉成 .icns。）",
              file=sys.stderr)

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", APP_NAME,
        "--noconfirm",
        "--clean",
        "--windowed",                       # macOS 上會自動生成 .app bundle
        "--osx-bundle-identifier", BUNDLE_ID,
        str(HERE / "main.py"),
    ]
    if icon_path.exists():
        cmd[-1:-1] = ["--icon", str(icon_path)]
    print("執行：", " ".join(cmd))
    subprocess.check_call(cmd, cwd=HERE)

    app_path = DIST / f"{APP_NAME}.app"
    if not app_path.exists():
        print(f"打包失敗：找不到 {app_path}", file=sys.stderr)
        sys.exit(1)

    # 把 configs/ 與 assets/ 放到 .app/Contents/MacOS/ 之下，與執行檔同層。
    # 這樣 lexiarbiter.core.config.app_root() 取 Path(sys.executable).parent
    # 才能正確找到 configs/，與 Windows onedir 行為一致。
    macos_dir = app_path / "Contents" / "MacOS"

    def _sync_tree(src: Path, dst: Path, label: str) -> None:
        if not src.exists():
            print(f"找不到來源資料夾：{src}，略過 {label} 複製。", file=sys.stderr)
            return
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(src, dst)
        print(f"已將 {label} 複製到 {dst}")

    _sync_tree(HERE / "configs", macos_dir / "configs", "configs/")
    _sync_tree(HERE / "assets", macos_dir / "assets", "assets/")

    # Ad-hoc codesign：免費、不需 Apple Developer 帳號，能讓 Apple Silicon
    # 接受啟動。Gatekeeper 仍會擋（quarantine flag），使用者首次開啟需跑
    # `xattr -dr com.apple.quarantine` —— 已在 README 寫明。
    # --deep 是為了一併簽 .app 內部所有 dylib / framework。
    print("執行 ad-hoc codesign...")
    subprocess.check_call([
        "codesign", "--force", "--deep", "--sign", "-",
        str(app_path),
    ])
    subprocess.check_call(["codesign", "--verify", "--verbose", str(app_path)])

    # 用 ditto 壓 zip：比 `zip` 指令更完整保留 macOS metadata 與簽名。
    zip_path = DIST / f"{APP_NAME}-macos-{ARCH}.zip"
    if zip_path.exists():
        zip_path.unlink()
    subprocess.check_call([
        "ditto", "-c", "-k", "--keepParent", str(app_path), str(zip_path),
    ])

    print(f"\n打包完成：{app_path}")
    print(f"Release zip：{zip_path}")


if __name__ == "__main__":
    main()
