#!/usr/bin/env python3
"""Publish a committed update.py candidate as one immutable package tag and release."""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from native_versions import ROOT, package_version, read_versions
from update import ASSET, RELEASE_REPO, asset_url, run

REMOTE = f"https://github.com/{RELEASE_REPO}.git"


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def remote_tag_commit(tag):
    refs = run("git", "ls-remote", "--tags", REMOTE, f"refs/tags/{tag}", f"refs/tags/{tag}^{{}}", capture=True)
    matches = dict(line.split()[::-1] for line in (refs or "").splitlines())
    return matches.get(f"refs/tags/{tag}^{{}}", matches.get(f"refs/tags/{tag}"))


def release_notes(versions, tag, checksum, metadata):
    commit = versions["tdlib_commit"]
    lines = [
        f"TDLibKit {versions['package']} over the native C++ API of TDLib {versions['tdlib_version']} "
        f"([`{commit[:8]}`](https://github.com/tdlib/td/commit/{commit})).",
        "",
        "```swift",
        f'.package(url: "https://github.com/{RELEASE_REPO}.git", exact: "{tag}")',
        "```",
        "",
    ]
    delta_path = metadata.resolve().parent / "schema-delta.json"
    if delta_path.exists():
        delta = json.loads(delta_path.read_text())
        lines.append(f"TL schema since the previous pin: {len(delta['added'])} added, "
                     f"{len(delta['removed'])} removed, {len(delta['changed'])} changed declarations.")
        for kind in ("added", "removed", "changed"):
            if delta[kind]:
                lines.append(f"- {kind.capitalize()}: " + ", ".join(f"`{name}`" for name in delta[kind]))
        lines.append("")
    lines.append(f"SHA-256 of `{ASSET}`: `{checksum}`")
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("metadata", type=Path, help="release.json produced by scripts/update.py")
    args = parser.parse_args()
    if (args.metadata.resolve().parent / "in-progress").exists():
        raise ValueError("Candidate preparation has not finished")
    release = json.loads(args.metadata.read_text())
    versions = read_versions()
    asset = Path(release["asset"])
    if release["repo"] != RELEASE_REPO or asset.name != ASSET:
        raise ValueError("Unexpected release repository or asset name")
    checksum = sha256(asset)
    tag = package_version(versions)
    url = asset_url(tag)
    if (release["checksum"], release["tag"], release["url"], release["tdlib_commit"]) != (
            checksum, tag, url, versions["tdlib_commit"]):
        raise ValueError("Release metadata is stale or the candidate archive changed")
    manifest = (ROOT / "Package.swift").read_text()
    if f'url: "{url}"' not in manifest or f'checksum: "{checksum}"' not in manifest:
        raise ValueError("Package.swift no longer matches the verified candidate")
    # The tag must contain exactly the verified sources, so only a clean, committed HEAD is published.
    dirty = run("git", "status", "--porcelain", "--untracked-files=no", capture=True, cwd=ROOT)
    if dirty:
        raise ValueError("Commit the prepared update before publishing:\n" + dirty)
    commit = run("git", "rev-parse", "HEAD", capture=True, cwd=ROOT)
    run("gh", "auth", "status")
    tagged = remote_tag_commit(tag)
    if tagged not in (None, commit):
        raise ValueError(f"{tag} already points to {tagged}, not HEAD {commit}")
    # A failed API request must not be interpreted as a missing release.
    releases = json.loads(run("gh", "api", "--paginate", "--slurp",
                             f"repos/{RELEASE_REPO}/releases?per_page=100", capture=True))
    existing = next((item for page in releases for item in page if item["tag_name"] == tag), None)
    if existing is not None and (existing["draft"] or tagged is None):
        raise ValueError("A draft or untagged release already occupies this tag; inspect it before publishing")
    if tagged is None:
        # Tag pushes do not trigger CI. Push the branch after the binary is downloadable.
        run("git", "push", REMOTE, f"{commit}:refs/tags/{tag}", cwd=ROOT)
    if existing is None:
        notes = args.metadata.resolve().parent / "release-notes.md"
        notes.write_text(release_notes(versions, tag, checksum, args.metadata))
        run("gh", "release", "create", tag, asset, "--repo", RELEASE_REPO, "--verify-tag",
            "--title", f"TDLibKit {tag}", "--notes-file", notes, "--latest")
    # Read back the actual download, including on a retry after partial network failure.
    with tempfile.TemporaryDirectory(prefix="tdlibkit-release-") as directory:
        run("gh", "release", "download", tag, "--repo", RELEASE_REPO,
            "--pattern", asset.name, "--dir", directory)
        if sha256(Path(directory) / asset.name) != checksum:
            raise ValueError("Published asset checksum mismatch; existing assets were not replaced")
    # An external package resolves the exact remote tag, downloads its binary and runs TDLib.
    env = dict(os.environ)
    env.pop("TDLIBKIT_USE_LOCAL_TDSTATIC", None)
    run(ROOT / "scripts/check-semver.py", "--url", REMOTE, env=env)
    print(f"Published {tag}: {url}")
    print(f"Push the branch containing {commit}; this script does not move branches.")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, OSError, subprocess.CalledProcessError) as error:
        sys.exit(f"Publication stopped: {error}")
