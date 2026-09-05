#!/usr/bin/env python3
"""Shared source pins for the native build, generator and update command."""

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def read_versions(root=ROOT):
    versions = json.loads((root / "versions.json").read_text())
    for key in ("tdlib_commit", "tdlib_artifact_commit", "python_apple_support_commit"):
        if not re.fullmatch(r"[0-9a-f]{40}", versions[key]):
            raise ValueError(f"versions.json: {key} must be a full commit SHA")
    for key in ("tdlib_version", "openssl_version"):
        if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", versions[key]):
            raise ValueError(f"versions.json: invalid {key}")
    return versions


def tdlib_version(cmake):
    match = re.search(r"project\(TDLib VERSION ([0-9]+\.[0-9]+\.[0-9]+)\b", cmake)
    if not match:
        raise ValueError("Cannot read TDLib version from upstream CMakeLists.txt")
    return match[1]


def verify_source(root=ROOT):
    versions = read_versions(root)
    td = root / "Vendor/td"
    if not (td / ".git").exists():
        raise ValueError("Initialize Vendor/td with git submodule update --init Vendor/td")
    actual = subprocess.check_output(["git", "-C", str(td), "rev-parse", "HEAD"], text=True).strip()
    if actual != versions["tdlib_commit"]:
        raise ValueError(f"Vendor/td is {actual}, expected {versions['tdlib_commit']}")
    if tdlib_version((td / "CMakeLists.txt").read_text()) != versions["tdlib_version"]:
        raise ValueError("TDLib version differs from versions.json")
    dirty = subprocess.check_output(
        ["git", "-C", str(td), "status", "--porcelain", "--untracked-files=no"], text=True
    ).strip()
    if dirty:
        raise ValueError("Vendor/td has modified tracked source files")


if __name__ == "__main__":
    try:
        if sys.argv[1:] == ["--verify"]:
            verify_source()
        else:
            versions = read_versions()
            print(" ".join(versions[key] for key in sys.argv[1:]))
    except (ValueError, KeyError, OSError, subprocess.CalledProcessError) as error:
        sys.exit(f"error: {error}")
