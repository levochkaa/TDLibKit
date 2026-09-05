#!/usr/bin/env python3
"""Build and run an external consumer using an exact semantic version."""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from native_versions import ROOT, read_versions


def run(*args, cwd, env):
    subprocess.run([str(arg) for arg in args], cwd=cwd, env=env, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", help="Published Git URL; otherwise test a tagged snapshot of this working tree")
    args = parser.parse_args()
    versions = read_versions()
    version = versions["package"]
    env = dict(os.environ)
    env.pop("TDLIBKIT_USE_LOCAL_TDSTATIC", None)
    with tempfile.TemporaryDirectory(prefix="tdlibkit-semver-") as directory:
        temporary = Path(directory)
        url = args.url
        if not url:
            snapshot = temporary / "TDLibKit"
            snapshot.mkdir()
            shutil.copyfile(ROOT / "Package.swift", snapshot / "Package.swift")
            for name in ("Sources", "Tests"):
                shutil.copytree(ROOT / name, snapshot / name)
            run("git", "init", "-q", snapshot, cwd=temporary, env=env)
            run("git", "add", ".", cwd=snapshot, env=env)
            run("git", "-c", "user.name=Codex", "-c", "user.email=noreply@openai.com",
                "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null", "commit", "-qm",
                "test(package): snapshot semantic version consumer\n\nCo-authored-by: Codex <noreply@openai.com>",
                cwd=snapshot, env=env)
            run("git", "-c", "tag.gpgsign=false", "tag", version, cwd=snapshot, env=env)
            url = snapshot.as_uri()
        consumer = temporary / "Consumer"
        source = consumer / "Sources/SemverSmoke"
        source.mkdir(parents=True)
        (consumer / "Package.swift").write_text(f'''// swift-tools-version: 6.0
import PackageDescription
let package = Package(
    name: "SemverSmoke",
    platforms: [.macOS(.v12)],
    dependencies: [.package(url: {json.dumps(url)}, exact: {json.dumps(version)})],
    targets: [.executableTarget(
        name: "SemverSmoke",
        dependencies: [.product(name: "TDLibKitShared", package: "TDLibKit")],
        swiftSettings: [.interoperabilityMode(.Cxx)]
    )]
)
''')
        (source / "Smoke.swift").write_text('''import TDLibKit

@main struct SemverSmoke {
    static func main() async throws {
        let manager = TDLibClientManager()
        let client = try await manager.createClient()
        try await client.executeSetLogVerbosityLevel(0)
        let result = try await client.send(TDNativeRequests.getOption(name: "version"))
        guard case .optionValueString(let version) = result else {
            fatalError("Expected a native TDLib version response")
        }
        print("Native TDLib version: \\(version.value)")
        try await client.close()
        await manager.shutdown()
    }
}
''')
        run("swift", "run", "--jobs", "2", "SemverSmoke", cwd=consumer, env=env)
        resolved = json.loads((consumer / "Package.resolved").read_text())
        pin = next(item for item in resolved["pins"] if item["identity"] == "tdlibkit")
        if pin["state"].get("version") != version:
            raise RuntimeError(f"Expected exact {version}, resolved {pin['state']}")
        print(f"Semantic-version consumer passed: {version}, revision {pin['state']['revision']}")


if __name__ == "__main__":
    main()
