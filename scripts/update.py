#!/usr/bin/env python3
"""Prepare a complete native TDLib update. Remote publication is opt-in."""

import argparse
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

from native_versions import ROOT, read_versions, tdlib_version

UPSTREAM = "https://github.com/tdlib/td.git"
RELEASE_REPO = "levochkaa/TDLibKit"
PLATFORMS = (
    "macos", "ios", "ios-simulator", "watchos", "watchos-simulator",
    "tvos", "tvos-simulator", "visionos", "visionos-simulator",
)
MANAGED_PATHS = (
    "versions.json", "Package.swift", "Native", "Sources/TDLibCxxBridge/Generated",
    "Sources/TDLibKitNative/Generated", "Documentation/TDLib-LICENSE.txt",
)


def run(*args, capture=False, cwd=None, env=None):
    command = [str(arg) for arg in args]
    print("+ " + shlex.join(command), flush=True)
    result = subprocess.run(command, cwd=cwd or ROOT, env=env, check=True, text=True,
                            stdout=subprocess.PIPE if capture else None)
    return result.stdout.strip() if capture else None


def resolve_ref(ref):
    if re.fullmatch(r"[0-9a-f]{40}", ref):
        return ref
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]*", ref):
        raise ValueError("--ref must be a branch, tag or full lowercase commit SHA")
    refs = run("git", "ls-remote", UPSTREAM, f"refs/heads/{ref}",
               f"refs/tags/{ref}", f"refs/tags/{ref}^{{}}", capture=True)
    matches = dict(line.split()[::-1] for line in refs.splitlines())
    branch = matches.get(f"refs/heads/{ref}")
    tag = matches.get(f"refs/tags/{ref}^{{}}", matches.get(f"refs/tags/{ref}"))
    if branch and tag and branch != tag:
        raise ValueError(f"Ambiguous upstream branch/tag: {ref}; use a full SHA")
    if not (branch or tag):
        raise ValueError(f"Upstream ref not found: {ref}")
    return branch or tag


def updated_manifest(manifest, url, checksum):
    manifest, urls = re.subn(
        r'url: "https://github\.com/levochkaa/TDLibKit/releases/download/[^\"]+/TdStatic\.xcframework\.zip"',
        f'url: "{url}"', manifest,
    )
    manifest, checksums = re.subn(r'checksum: "[0-9a-f]{64}"', f'checksum: "{checksum}"', manifest)
    if (urls, checksums) != (1, 1):
        raise ValueError("Expected exactly one TdStatic release URL and checksum in Package.swift")
    return manifest


def schema_delta(before, after):
    old = {item["name"]: item for item in before["declarations"]}
    new = {item["name"]: item for item in after["declarations"]}
    return {
        "added": sorted(new.keys() - old.keys()),
        "removed": sorted(old.keys() - new.keys()),
        "changed": sorted(name for name in old.keys() & new.keys() if old[name] != new[name]),
        "counts": after["counts"],
    }


def preflight(resume=False):
    for program in ("git", "python3", "cmake", "make", "xcrun", "xcodebuild",
                    "swift", "libtool", "lipo", "ditto", "xcodegen", "rg", "gperf"):
        if not shutil.which(program):
            raise ValueError(f"Missing required tool: {program}")
    dirty = run("git", "status", "--porcelain", "--", *MANAGED_PATHS, capture=True)
    if dirty and not resume:
        raise ValueError("Commit or stash changes to update-owned files before updating:\n" + dirty)
    td = ROOT / "Vendor/td"
    if (td / ".git").exists():
        dirty = run("git", "status", "--porcelain", cwd=td, capture=True)
        if dirty:
            raise ValueError("Vendor/td has local changes:\n" + dirty)


def build_matrix(env, xcode, jobs):
    native = ROOT / "scripts/tdlib-native.sh"
    build = ROOT / ".build/tdlib-native"
    ssl = build / "openssl-pinned"
    ssl_intel = build / "openssl-pinned-x86_64"
    run(native, "openssl", "--platform", "all", "--output-root", ssl, "--xcode", xcode, env=env)
    run(native, "openssl", "--platform", "ios-simulator", "--arch", "x86_64",
        "--output-root", ssl_intel, "--xcode", xcode, env=env)
    products = build / "update-products"
    archives = {}
    for platform, arch in [(p, "arm64") for p in PLATFORMS] + [("ios-simulator", "x86_64")]:
        archive = products / f"{platform}-{arch}/libTdStatic.a"
        run(native, "build", "--platform", platform, "--arch", arch,
            "--configuration", "Release", "--optimization", "oz", "--lto", "off",
            "--openssl", (ssl if arch == "arm64" else ssl_intel) / platform,
            "--jobs", jobs, "--skip-generate", "--output", archive, env=env)
        archives[platform, arch] = archive
    simulator = products / "ios-simulator-universal/libTdStatic.a"
    run(native, "universal", "--output", simulator, archives["ios-simulator", "arm64"],
        archives["ios-simulator", "x86_64"], env=env)
    arguments = []
    for platform in PLATFORMS:
        arguments.extend([f"--{platform}", simulator if platform == "ios-simulator"
                          else archives[platform, "arm64"]])
    run(native, "xcframework", *arguments, env=env)


def validate_candidate(env, output):
    run(ROOT / "scripts/check-native.sh", env=env)
    run("swift", "test", "--scratch-path", output / "swift-tests", env=env)
    # This compiles and links the real iOS host against the candidate, and measures it.
    host = ROOT / "Benchmarks/SizeHost"
    run("xcodegen", "generate", "--spec", host / "project.yml", "--project", host, env=env)
    archive = output / "SizeHost.xcarchive"
    run("xcodebuild", "-project", host / "TDLibKitSizeHost.xcodeproj", "-scheme", "TDLibKitSizeHost",
        "-configuration", "Release", "-sdk", "iphoneos", "-destination", "generic/platform=iOS",
        "-derivedDataPath", output / "DerivedData", "-archivePath", archive, "archive",
        "CODE_SIGNING_ALLOWED=NO", "CODE_SIGNING_REQUIRED=NO", "ONLY_ACTIVE_ARCH=YES",
        "ARCHS=arm64", "SKIP_INSTALL=NO", env=env)
    run(ROOT / "scripts/check-size.sh", archive / "Products/Applications/TDLibKitSizeHost.app", env=env)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ref", default="master", help="Upstream branch, tag or full SHA (default: master)")
    parser.add_argument("--check", action="store_true", help="Only compare upstream; exit 2 if an update exists")
    parser.add_argument("--rebuild", action="store_true", help="Rebuild even when already current")
    parser.add_argument("--resume", action="store_true", help="Resume a stopped preparation, keeping reviewed local edits")
    parser.add_argument("--publish", action="store_true", help="Also publish the verified binary GitHub release")
    parser.add_argument("--jobs", type=int, default=8)
    parser.add_argument("--xcode", type=Path, help="Xcode.app; defaults to DEVELOPER_DIR / xcode-select")
    args = parser.parse_args()
    if args.jobs < 1:
        parser.error("--jobs must be positive")
    if args.check and (args.rebuild or args.publish or args.resume):
        parser.error("--check cannot be combined with --rebuild, --resume or --publish")

    versions = read_versions()
    commit = resolve_ref(args.ref)
    output = ROOT / ".build/tdlib-update" / commit
    in_progress = output / "in-progress"
    if args.resume and not in_progress.exists():
        raise ValueError("No stopped preparation for this SHA; use --ref with its original commit")
    current = commit == versions["tdlib_commit"]
    print(f"Pinned:   TDLib {versions['tdlib_version']} ({versions['tdlib_commit']})")
    print(f"Upstream: {commit}")
    if args.check:
        print("Already up to date." if current else "TDLib update available.")
        return 0 if current else 2
    if in_progress.exists() and not (args.resume or args.check):
        raise ValueError(f"Preparation is incomplete. Review the diff and use --resume --ref {commit}.")
    if current and not (args.rebuild or args.resume):
        # A failed preparation may have moved the source pin, but not the binary pin.
        if commit != versions["tdlib_artifact_commit"]:
            raise ValueError("Source update is incomplete. Review the diff and rerun with --rebuild.")
        metadata = output / "release.json"
        if metadata.exists():
            if args.publish:
                run(ROOT / "scripts/release.py", metadata)
            else:
                print(f"Already prepared: {metadata}. Use --publish to publish/verify the binary release.")
            return 0
        print("Already up to date; no files changed and no build/publication needed.")
        return 0

    preflight(resume=args.resume)
    env = dict(os.environ, TDLIBKIT_USE_LOCAL_TDSTATIC="1")
    developer = str(args.xcode / "Contents/Developer") if args.xcode else env.get("DEVELOPER_DIR")
    developer = developer or run("xcode-select", "-p", capture=True)
    xcode = Path(developer).parent.parent
    if not (xcode / "Contents/Developer").is_dir():
        raise ValueError("A full Xcode installation is required")
    env["DEVELOPER_DIR"] = str(xcode / "Contents/Developer")
    output.mkdir(parents=True, exist_ok=True)
    if not args.resume:
        # Preserve the original schema/pins across a resumed preparation.
        (output / "previous-versions.json").write_text(json.dumps(versions, indent=4) + "\n")
        shutil.copyfile(ROOT / "Native/Generated/schema.json", output / "previous-schema.json")
    before = json.loads((output / "previous-schema.json").read_text())
    in_progress.touch()
    if not (ROOT / "Vendor/td/.git").exists():
        run("git", "submodule", "update", "--init", "Vendor/td")
    td = ROOT / "Vendor/td"
    run("git", "fetch", "--depth", "1", UPSTREAM, commit, cwd=td)
    run("git", "checkout", "--detach", commit, cwd=td)
    versions.update(tdlib_commit=commit, tdlib_version=tdlib_version((td / "CMakeLists.txt").read_text()))
    (ROOT / "versions.json").write_text(json.dumps(versions, indent=4) + "\n")
    run(ROOT / "scripts/tdlib-native.sh", "generate", env=env)
    run(ROOT / "scripts/generate_native_schema.py", env=env)
    after = json.loads((ROOT / "Native/Generated/schema.json").read_text())
    delta = schema_delta(before, after)
    (output / "schema-delta.json").write_text(json.dumps(delta, indent=2) + "\n")
    print(f"Schema: +{len(delta['added'])} -{len(delta['removed'])} changed={len(delta['changed'])}")
    shutil.copyfile(td / "LICENSE_1_0.txt", ROOT / "Documentation/TDLib-LICENSE.txt")
    build_matrix(env, xcode, args.jobs)
    validate_candidate(env, output)

    asset = output / "TdStatic.xcframework.zip"
    if asset.exists():
        asset.unlink()
    run("ditto", "-c", "-k", "--sequesterRsrc", "--keepParent", ROOT / "Artifacts/TdStatic.xcframework", asset)
    checksum = run("swift", "package", "compute-checksum", asset, capture=True)
    # A content suffix permits a new immutable asset if the same TD commit is rebuilt.
    tag = f"tdstatic-{versions['tdlib_version']}-{commit[:8]}-{checksum[:12]}"
    url = f"https://github.com/{RELEASE_REPO}/releases/download/{tag}/{asset.name}"
    manifest = ROOT / "Package.swift"
    manifest.write_text(updated_manifest(manifest.read_text(), url, checksum))
    versions["tdlib_artifact_commit"] = commit
    (ROOT / "versions.json").write_text(json.dumps(versions, indent=4) + "\n")
    release = dict(repo=RELEASE_REPO, tag=tag, url=url, checksum=checksum,
                   asset=str(asset), tdlib_commit=commit, tdlib_version=versions["tdlib_version"])
    metadata = output / "release.json"
    metadata.write_text(json.dumps(release, indent=2) + "\n")
    run("git", "diff", "--check")
    in_progress.unlink()
    print(f"Prepared TDLib {versions['tdlib_version']}: {metadata}")
    if args.publish:
        run(ROOT / "scripts/release.py", metadata)
    else:
        print("Binary is local. Package.swift now points to its pending release URL.")
        print("Local builds: TDLIBKIT_USE_LOCAL_TDSTATIC=1 swift test")
        print(f"Publish when ready: ./scripts/release.py {shlex.quote(str(metadata))}")
    print("Review and commit the source changes before pushing the package. No source commit or push was made.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        sys.exit(f"Update stopped: {error}\nReview the working diff; failed preparation is not a completed update.")
