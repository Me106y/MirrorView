#!/usr/bin/env python3
import argparse
import os
import platform
import shutil
import subprocess
import tarfile
import textwrap
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DIST_DIR = ROOT / "dist"
BUILD_DIR = ROOT / "build"
RELEASE_DIR = ROOT / "release"


def run(cmd):
    print("+", " ".join(cmd))
    subprocess.run(cmd, check=True)


def detect_platform():
    system = platform.system().lower()
    machine = platform.machine().lower()

    if system.startswith("darwin"):
        platform_tag = "macos"
    elif system.startswith("win"):
        platform_tag = "windows"
    else:
        platform_tag = "linux"

    if machine in {"x86_64", "amd64"}:
        arch_tag = "x64"
    elif machine in {"arm64", "aarch64"}:
        arch_tag = "arm64"
    else:
        arch_tag = machine.replace(" ", "_")

    return platform_tag, arch_tag


def build_binary():
    onefile_name = "mirrorview-tui"
    sep = ";" if os.name == "nt" else ":"
    skill_dir = ROOT / "skills" / "CareerForge" / "skills"
    data_arg = f"{skill_dir}{sep}skills/CareerForge/skills"

    if DIST_DIR.exists():
        shutil.rmtree(DIST_DIR)
    if BUILD_DIR.exists():
        shutil.rmtree(BUILD_DIR)
    spec_file = ROOT / f"{onefile_name}.spec"
    if spec_file.exists():
        spec_file.unlink()

    cmd = [
        "pyinstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--console",
        "--name",
        onefile_name,
        "--collect-submodules",
        "server",
        "--collect-submodules",
        "client",
        "--collect-submodules",
        "tts_integration",
        "--collect-submodules",
        "utils",
        "--add-data",
        data_arg,
        str(ROOT / "client" / "tui_main.py"),
    ]
    run(cmd)

    binary = DIST_DIR / onefile_name
    if os.name == "nt":
        binary = binary.with_suffix(".exe")
    if not binary.exists():
        raise FileNotFoundError(f"Packaged binary not found: {binary}")
    return binary


def write_text(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def build_macos_bundle(stage_dir: Path, binary_path: Path):
    app_root = stage_dir / "MirrorView TUI.app" / "Contents"
    macos_dir = app_root / "MacOS"
    resources_dir = app_root / "Resources"
    macos_dir.mkdir(parents=True, exist_ok=True)
    resources_dir.mkdir(parents=True, exist_ok=True)

    bundled_bin = resources_dir / "mirrorview-tui"
    shutil.copy2(binary_path, bundled_bin)
    os.chmod(bundled_bin, 0o755)

    launcher = macos_dir / "MirrorView TUI"
    launcher_content = textwrap.dedent(
        """\
        #!/bin/bash
        set -e
        APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"
        BIN="$APP_DIR/Resources/mirrorview-tui"
        if [ ! -x "$BIN" ]; then
          osascript -e 'display alert "MirrorView TUI binary not found."'
          exit 1
        fi
        osascript <<EOF
        tell application "Terminal"
          activate
          do script quoted form of "$BIN"
        end tell
        EOF
        """
    )
    write_text(launcher, launcher_content)
    os.chmod(launcher, 0o755)

    info_plist = app_root / "Info.plist"
    plist_content = textwrap.dedent(
        """\
        <?xml version="1.0" encoding="UTF-8"?>
        <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
          "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
        <plist version="1.0">
          <dict>
            <key>CFBundleName</key>
            <string>MirrorView TUI</string>
            <key>CFBundleDisplayName</key>
            <string>MirrorView TUI</string>
            <key>CFBundleIdentifier</key>
            <string>com.mirrorview.tui</string>
            <key>CFBundleVersion</key>
            <string>1.0</string>
            <key>CFBundlePackageType</key>
            <string>APPL</string>
            <key>CFBundleExecutable</key>
            <string>MirrorView TUI</string>
            <key>LSMinimumSystemVersion</key>
            <string>11.0</string>
          </dict>
        </plist>
        """
    )
    write_text(info_plist, plist_content)


def build_linux_package(stage_dir: Path, binary_path: Path):
    target_bin = stage_dir / "mirrorview-tui"
    shutil.copy2(binary_path, target_bin)
    os.chmod(target_bin, 0o755)

    desktop = stage_dir / "MirrorView TUI.desktop"
    desktop_content = textwrap.dedent(
        """\
        [Desktop Entry]
        Version=1.0
        Type=Application
        Name=MirrorView TUI
        Comment=MirrorView CareerForge terminal UI
        Exec=__MIRRORVIEW_EXEC__
        Terminal=true
        Categories=Utility;Development;
        """
    )
    write_text(desktop, desktop_content)


def build_windows_package(stage_dir: Path, binary_path: Path):
    target_bin = stage_dir / "MirrorView TUI.exe"
    shutil.copy2(binary_path, target_bin)


def archive_stage(stage_dir: Path, asset_name: str, platform_tag: str):
    RELEASE_DIR.mkdir(parents=True, exist_ok=True)
    if platform_tag == "windows":
        archive_path = RELEASE_DIR / f"{asset_name}.zip"
        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for file_path in stage_dir.rglob("*"):
                if file_path.is_file():
                    zf.write(file_path, file_path.relative_to(stage_dir))
    else:
        archive_path = RELEASE_DIR / f"{asset_name}.tar.gz"
        with tarfile.open(archive_path, "w:gz") as tf:
            for file_path in stage_dir.rglob("*"):
                tf.add(file_path, arcname=file_path.relative_to(stage_dir))
    return archive_path


def main():
    parser = argparse.ArgumentParser(description="Build MirrorView TUI release artifact.")
    parser.add_argument("--version", required=True, help="Version tag without prefix, e.g. 1.2.0")
    args = parser.parse_args()

    platform_tag, arch_tag = detect_platform()
    asset_base = f"mirrorview-tui-{args.version}-{platform_tag}-{arch_tag}"
    stage_dir = RELEASE_DIR / asset_base
    if stage_dir.exists():
        shutil.rmtree(stage_dir)
    stage_dir.mkdir(parents=True, exist_ok=True)

    binary = build_binary()
    if platform_tag == "macos":
        build_macos_bundle(stage_dir, binary)
    elif platform_tag == "windows":
        build_windows_package(stage_dir, binary)
    else:
        build_linux_package(stage_dir, binary)

    readme = stage_dir / "README.txt"
    write_text(
        readme,
        textwrap.dedent(
            """\
            MirrorView TUI packaged release.

            Configuration:
            - Create ~/.mirrorview-tui/.env (or .env_tts) and set:
              DEEPSEEK_API_KEY=sk-xxxx

            Launch:
            - macOS: open "MirrorView TUI.app"
            - Windows: run "MirrorView TUI.exe"
            - Linux: run "./mirrorview-tui" or install desktop launcher
            """
        ),
    )

    archive = archive_stage(stage_dir, asset_base, platform_tag)
    print(str(archive))


if __name__ == "__main__":
    main()
