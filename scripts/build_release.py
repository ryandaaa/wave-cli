#!/usr/bin/env python3
"""
Cross-Platform Standalone Binary Builder & Packager for WAVE-CLI
Used by GitHub Actions CD pipeline and local release builds.
"""

import sys
import os
import shutil
import subprocess
import hashlib
import tarfile
import zipfile
import platform


def detect_target() -> str:
    system = platform.system().lower()
    machine = platform.machine().lower()

    if machine in ("x86_64", "amd64"):
        arch = "x86_64"
    elif machine in ("arm64", "aarch64"):
        arch = "arm64"
    else:
        arch = machine

    if system == "linux":
        return f"linux-{arch}"
    elif system == "darwin":
        return f"macos-{arch}"
    elif system == "windows":
        return f"windows-{arch}"
    return f"{system}-{arch}"


def main():
    target = sys.argv[1] if len(sys.argv) > 1 else detect_target()
    print(f"=== Building WAVE-CLI Standalone Binary for [{target}] ===")

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.chdir(project_root)

    # 1. Clean previous build artifacts
    for dir_name in ("build", "dist"):
        if os.path.exists(dir_name):
            shutil.rmtree(dir_name, ignore_errors=True)
    if os.path.exists("wave.spec"):
        try:
            os.unlink("wave.spec")
        except OSError:
            pass

    # 2. Determine separator and PyInstaller arguments
    sep = ";" if sys.platform == "win32" else ":"
    tcss_src = os.path.join("wave", "tui", "styles", "wave.tcss")
    tcss_dst = os.path.join("wave", "tui", "styles")
    tcss_path = f"{tcss_src}{sep}{tcss_dst}"

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", "wave",
        "--onefile",
        "--clean",
        "--noconfirm",
        f"--add-data={tcss_path}",
        "--collect-data", "textual",
        "--collect-data", "rich",
        "main.py"
    ]

    print(f"Running: {' '.join(cmd)}")
    subprocess.check_call(cmd)

    # 3. Locate compiled executable
    exe_name = "wave.exe" if sys.platform == "win32" else "wave"
    exe_path = os.path.join(project_root, "dist", exe_name)

    if not os.path.exists(exe_path):
        print(f"Error: Executable not found at {exe_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Build succeeded! Testing executable: {exe_path} --version")
    subprocess.check_call([exe_path, "--version"])

    # 4. Package into release archive
    dist_dir = os.path.join(project_root, "dist")
    if sys.platform == "win32":
        archive_name = f"wave-{target}.zip"
        archive_path = os.path.join(dist_dir, archive_name)
        with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(exe_path, arcname=exe_name)
    else:
        archive_name = f"wave-{target}.tar.gz"
        archive_path = os.path.join(dist_dir, archive_name)
        with tarfile.open(archive_path, "w:gz") as tf:
            tf.add(exe_path, arcname=exe_name)

    # 5. Generate SHA256 checksum
    with open(archive_path, "rb") as af:
        sha256 = hashlib.sha256(af.read()).hexdigest()

    checksum_file = f"{archive_path}.sha256"
    with open(checksum_file, "w") as cf:
        cf.write(f"{sha256}  {archive_name}\n")

    print("\n=======================================================")
    print(f"Release Archive: {archive_path}")
    print(f"SHA256 Checksum: {sha256}")
    print("=======================================================")


if __name__ == "__main__":
    main()
