#!/usr/bin/env python3
"""Publish a verified update.py candidate without overwriting existing assets."""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from native_versions import ROOT, read_versions
from update import RELEASE_REPO, run


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("metadata", type=Path, help="release.json produced by scripts/update.py")
    args = parser.parse_args()
    if (args.metadata.resolve().parent / "in-progress").exists():
        raise ValueError("Candidate preparation has not finished")
    release = json.loads(args.metadata.read_text())
    versions = read_versions()
    asset = Path(release["asset"])
    if release["repo"] != RELEASE_REPO or asset.name != "TdStatic.xcframework.zip":
        raise ValueError("Unexpected release repository or asset name")
    checksum = sha256(asset)
    tag = f"tdstatic-{versions['tdlib_version']}-{versions['tdlib_commit'][:8]}-{checksum[:12]}"
    url = f"https://github.com/{RELEASE_REPO}/releases/download/{tag}/{asset.name}"
    if (release["checksum"], release["tag"], release["url"], release["tdlib_commit"]) != (
            checksum, tag, url, versions["tdlib_commit"]):
        raise ValueError("Release metadata is stale or the candidate archive changed")
    manifest = (ROOT / "Package.swift").read_text()
    if f'url: "{url}"' not in manifest or f'checksum: "{checksum}"' not in manifest:
        raise ValueError("Package.swift no longer matches the verified candidate")
    run("git", "diff", "--check")
    run("gh", "auth", "status")
    # A failed API request must not be interpreted as a missing release.
    releases = json.loads(run("gh", "api", "--paginate", "--slurp",
                             f"repos/{RELEASE_REPO}/releases?per_page=100", capture=True))
    existing = next((item for page in releases for item in page if item["tag_name"] == tag), None)
    if existing is None:
        notes = args.metadata.resolve().parent / "release-notes.md"
        notes.write_text(
            f"Native static TDLib {versions['tdlib_version']} binary for TDLibKit 2.\n\n"
            f"TDLib source: https://github.com/tdlib/td/commit/{versions['tdlib_commit']}\n\n"
            f"SHA-256: `{checksum}`\n"
        )
        run("gh", "release", "create", tag, asset, "--repo", RELEASE_REPO,
            "--title", tag, "--notes-file", notes, "--latest=false")
    elif existing["draft"]:
        raise ValueError("A draft already occupies this release tag; inspect it before publishing")
    # Read back the actual download, including on a retry after partial network failure.
    with tempfile.TemporaryDirectory(prefix="tdlibkit-release-") as directory:
        run("gh", "release", "download", tag, "--repo", RELEASE_REPO,
            "--pattern", asset.name, "--dir", directory)
        if sha256(Path(directory) / asset.name) != checksum:
            raise ValueError("Published asset checksum mismatch; existing assets were not replaced")
    env = dict(os.environ)
    env.pop("TDLIBKIT_USE_LOCAL_TDSTATIC", None)
    with tempfile.TemporaryDirectory(prefix="tdlibkit-published-") as directory:
        run("swift", "package", "--scratch-path", directory, "resolve", env=env)
    print(f"Published and resolved from Package.swift: {url}")
    print("Source changes still need review, commit and push.")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, OSError, subprocess.CalledProcessError) as error:
        sys.exit(f"Publication stopped: {error}")
