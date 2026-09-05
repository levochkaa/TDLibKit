import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import generate_native_schema as schema
import native_versions
import release
import update


class UpstreamTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        self.git("init", "-q", "-b", "master")
        self.git("config", "user.name", "Test")
        self.git("config", "user.email", "test@example.invalid")
        self.git("-c", "commit.gpgsign=false", "commit", "-qm", "Fixture", "--allow-empty")
        self.commit = self.git("rev-parse", "HEAD").strip()

    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.repo), *args], text=True)

    def resolve(self, ref):
        with patch.object(update, "UPSTREAM", str(self.repo)), contextlib.redirect_stdout(io.StringIO()):
            return update.resolve_ref(ref)

    def test_resolves_actual_branch_and_peeled_annotated_tag(self):
        self.git("-c", "tag.gpgsign=false", "tag", "-a", "v1", "-m", "Fixture tag")
        self.assertEqual(self.resolve("master"), self.commit)
        self.assertEqual(self.resolve("v1"), self.commit)

    def test_rejects_missing_and_ambiguous_refs(self):
        self.git("-c", "tag.gpgsign=false", "tag", "master")
        self.git("-c", "commit.gpgsign=false", "commit", "-qm", "Next", "--allow-empty")
        with self.assertRaisesRegex(ValueError, "Ambiguous"):
            self.resolve("master")
        with self.assertRaisesRegex(ValueError, "not found"):
            self.resolve("missing")


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.versions = native_versions.read_versions()
        self.manifest = (update.ROOT / "Package.swift").read_text()
        (self.root / "Package.swift").write_text(self.manifest)

    def invoke(self, *args, target=None):
        with patch.object(update, "ROOT", self.root), \
             patch.object(update, "read_versions", return_value=self.versions), \
             patch.object(update, "resolve_ref", return_value=target or self.versions["tdlib_commit"]), \
             patch.object(update, "preflight") as preflight, \
             patch.object(sys, "argv", ["update.py", *args]), \
             contextlib.redirect_stdout(io.StringIO()):
            result = update.main()
            preflight.assert_not_called()
            return result

    def test_current_revision_is_noop_even_with_local_edits(self):
        before = (self.root / "Package.swift").read_bytes()
        self.assertEqual(self.invoke(), 0)
        self.assertEqual(list(self.root.iterdir()), [self.root / "Package.swift"])
        self.assertEqual((self.root / "Package.swift").read_bytes(), before)

    def test_stable_binary_release_url_does_not_require_sha_in_its_tag(self):
        manifest = update.updated_manifest(
            self.manifest,
            "https://github.com/levochkaa/TDLibKit/releases/download/2.0.0/TdStatic.xcframework.zip",
            "a" * 64,
        )
        (self.root / "Package.swift").write_text(manifest)
        self.assertEqual(self.invoke(), 0)

    def test_check_reports_available_update_without_building_or_writing(self):
        self.assertEqual(self.invoke("--check", target="1" * 40), 2)
        self.assertEqual(self.invoke("--check"), 0)
        self.assertEqual(list(self.root.iterdir()), [self.root / "Package.swift"])

    def test_interrupted_update_cannot_report_already_current(self):
        state = self.root / ".build/tdlib-update" / self.versions["tdlib_commit"] / "in-progress"
        state.parent.mkdir(parents=True)
        state.touch()
        with self.assertRaisesRegex(ValueError, "incomplete"):
            self.invoke()

    def test_prepared_update_can_be_published_without_rebuilding(self):
        metadata = self.root / ".build/tdlib-update" / self.versions["tdlib_commit"] / "release.json"
        metadata.parent.mkdir(parents=True)
        metadata.write_text("{}")
        with patch.object(update, "run") as run:
            self.assertEqual(self.invoke(), 0)
            run.assert_not_called()
            self.assertEqual(self.invoke("--publish"), 0)
            run.assert_called_once_with(self.root / "scripts/release.py", metadata)

    def test_moved_source_pin_with_old_binary_cannot_report_current(self):
        self.versions["tdlib_commit"] = "2" * 40
        with self.assertRaisesRegex(ValueError, "incomplete"):
            self.invoke()

    def test_manifest_update_preserves_local_override_and_other_targets(self):
        url = "https://github.com/levochkaa/TDLibKit/releases/download/new/TdStatic.xcframework.zip"
        changed = update.updated_manifest(self.manifest, url, "a" * 64)
        self.assertIn(f'url: "{url}"', changed)
        self.assertIn('checksum: "' + "a" * 64 + '"', changed)
        self.assertIn('path: "Artifacts/TdStatic.xcframework"', changed)
        self.assertEqual(changed.split("let package =")[1], self.manifest.split("let package =")[1])
        with self.assertRaisesRegex(ValueError, "exactly one"):
            update.updated_manifest(self.manifest + self.manifest, url, "a" * 64)

    def test_schema_delta_includes_breaking_changes_even_when_counts_match(self):
        before = {"declarations": [{"name": "removed"}, {"name": "same", "fields": ["x"]}]}
        after = {"declarations": [{"name": "added"}, {"name": "same", "fields": ["y"]}], "counts": {}}
        self.assertEqual(update.schema_delta(before, after), {
            "added": ["added"], "removed": ["removed"], "changed": ["same"], "counts": {},
        })


class SchemaFailureTests(unittest.TestCase):
    def test_new_syntax_and_unknown_type_fail_with_source_context(self):
        with self.assertRaisesRegex(ValueError, "td_api.tl:1"):
            schema.parse_declarations("thing flags:# x:flags.0?int32 = Thing;", {"thing": 1})
        declarations = schema.parse_declarations("thing x:FutureType = Thing;", {"thing": 1})
        with self.assertRaisesRegex(ValueError, "FutureType"):
            schema.build_document(b"fixture", declarations)

    def test_unsupported_vector_does_not_partially_overwrite_generated_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            tl = root / "td_api.tl"
            header = root / "td_api.h"
            tl.write_text("thing x:vector<vector<int32>> = Thing;\n")
            header.write_text("class thing final : public Thing { static const std::int32_t ID = 1; };")
            args = ["generate_native_schema.py"]
            outputs = []
            for name in ("output", "access-output", "swift-output", "factory-output"):
                path = root / name
                path.write_text("original\n")
                args.extend([f"--{name}", str(path)])
                outputs.append(path)
            with patch.object(schema, "TL_PATH", tl), patch.object(schema, "HEADER_PATH", header), \
                 patch.object(schema, "verify_source"), patch.object(sys, "argv", args):
                with self.assertRaisesRegex(ValueError, "nested object vectors"):
                    schema.main()
            self.assertTrue(all(path.read_text() == "original\n" for path in outputs))


class PreparationTests(unittest.TestCase):
    def test_failed_build_preserves_binary_pin_and_resume_finishes_original_delta(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            td = root / "Vendor/td"
            (td / ".git").mkdir(parents=True)
            (td / "CMakeLists.txt").write_text("project(TDLib VERSION 1.8.68 LANGUAGES CXX C)")
            (td / "LICENSE_1_0.txt").write_text("Fixture license")
            (root / "Documentation").mkdir()
            schema_path = root / "Native/Generated/schema.json"
            schema_path.parent.mkdir(parents=True)
            schema_path.write_text('{"declarations": [], "counts": {}}')
            versions = native_versions.read_versions()
            (root / "versions.json").write_text(json.dumps(versions))
            manifest = root / "Package.swift"
            original_manifest = (update.ROOT / "Package.swift").read_text()
            manifest.write_text(original_manifest)
            xcode = root / "Xcode.app"
            (xcode / "Contents/Developer").mkdir(parents=True)
            target = "3" * 40
            output = root / ".build/tdlib-update" / target
            calls = []

            def run(*args, **kwargs):
                args = list(map(str, args))
                calls.append(args)
                if args[0].endswith("generate_native_schema.py"):
                    schema_path.write_text('{"declarations": [{"name": "newObject"}], "counts": {}}')
                if args[:3] == ["swift", "package", "compute-checksum"]:
                    return "a" * 64

            common = ["update.py", "--ref", target, "--xcode", str(xcode)]
            with patch.object(update, "ROOT", root), \
                 patch.object(update, "read_versions", side_effect=lambda: native_versions.read_versions(root)), \
                 patch.object(update, "resolve_ref", return_value=target), \
                 patch.object(update, "preflight"), patch.object(update, "run", side_effect=run), \
                 patch.object(update, "build_matrix") as build, \
                 patch.object(update, "validate_candidate") as validate, \
                 contextlib.redirect_stdout(io.StringIO()):
                build.side_effect = subprocess.CalledProcessError(1, "native-build")
                with patch.object(sys, "argv", common + ["--publish"]):
                    with self.assertRaises(subprocess.CalledProcessError):
                        update.main()
                validate.assert_not_called()
                self.assertEqual(manifest.read_text(), original_manifest)
                self.assertTrue((output / "in-progress").exists())
                self.assertFalse((output / "release.json").exists())
                self.assertFalse(any(call[0].endswith("release.py") for call in calls))

                build.side_effect = None
                with patch.object(sys, "argv", common + ["--resume"]):
                    self.assertEqual(update.main(), 0)
                validate.assert_called_once()
                self.assertFalse((output / "in-progress").exists())
                self.assertEqual(json.loads((output / "schema-delta.json").read_text())["added"], ["newObject"])
                self.assertIn('checksum: "' + "a" * 64 + '"', manifest.read_text())
                self.assertEqual(json.loads((output / "release.json").read_text())["tdlib_commit"], target)
                self.assertFalse(any(call[0].endswith("release.py") for call in calls))


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.asset = self.root / "TdStatic.xcframework.zip"
        self.asset.write_bytes(b"verified fixture archive")
        self.versions = native_versions.read_versions()
        self.checksum = release.sha256(self.asset)
        tag = f"tdstatic-{self.versions['tdlib_version']}-{self.versions['tdlib_commit'][:8]}-{self.checksum[:12]}"
        self.record = dict(repo=update.RELEASE_REPO, tag=tag, checksum=self.checksum,
                           tdlib_commit=self.versions["tdlib_commit"], asset=str(self.asset),
                           url=f"https://github.com/{update.RELEASE_REPO}/releases/download/{tag}/{self.asset.name}")
        self.metadata = self.root / "release.json"
        self.metadata.write_text(json.dumps(self.record))
        manifest = (update.ROOT / "Package.swift").read_text()
        (self.root / "Package.swift").write_text(update.updated_manifest(manifest, self.record["url"], self.checksum))

    def invoke(self, run):
        with patch.object(release, "ROOT", self.root), \
             patch.object(release, "read_versions", return_value=self.versions), \
             patch.object(release, "run", side_effect=run), \
             patch.object(sys, "argv", ["release.py", str(self.metadata)]), \
             contextlib.redirect_stdout(io.StringIO()):
            release.main()

    def test_changed_archive_is_rejected_before_contacting_github(self):
        self.asset.write_bytes(b"unverified replacement")
        calls = []
        with self.assertRaisesRegex(ValueError, "archive changed"):
            self.invoke(lambda *args, **kwargs: calls.append(args))
        self.assertEqual(calls, [])

    def test_api_failure_is_not_treated_as_absent_release(self):
        calls = []

        def run(*args, **kwargs):
            calls.append(args)
            if args[:2] == ("gh", "api"):
                raise subprocess.CalledProcessError(1, "gh api")

        with self.assertRaises(subprocess.CalledProcessError):
            self.invoke(run)
        self.assertFalse(any(args[:3] == ("gh", "release", "create") for args in calls))

    def test_existing_asset_is_read_back_without_overwrite_and_checksum_mismatch_fails(self):
        calls = []

        def run(*args, **kwargs):
            calls.append(args)
            if args[:2] == ("gh", "api"):
                return json.dumps([[{"tag_name": self.record["tag"], "draft": False}]])
            if args[:3] == ("gh", "release", "download"):
                (Path(args[-1]) / self.asset.name).write_bytes(b"wrong remote bytes")

        with self.assertRaisesRegex(ValueError, "checksum mismatch"):
            self.invoke(run)
        self.assertFalse(any(args[:3] == ("gh", "release", "create") for args in calls))


class ArtifactFailureTests(unittest.TestCase):
    def test_native_verifier_rejects_empty_artifact_and_mismatched_headers(self):
        if sys.platform != "darwin":
            self.skipTest("Native archive verification runs on macOS")
        with tempfile.TemporaryDirectory() as directory:
            artifact = Path(directory)
            command = [str(update.ROOT / "scripts/tdlib-native.sh"), "verify", "--artifact", directory]
            empty = subprocess.run(command, text=True, capture_output=True)
            self.assertNotEqual(empty.returncode, 0)
            self.assertIn("no static libraries", empty.stderr)
            (artifact / "libTdStatic.a").touch()
            mismatched = subprocess.run(command, text=True, capture_output=True)
            self.assertNotEqual(mismatched.returncode, 0)
            self.assertIn("headers differ", mismatched.stderr)


if __name__ == "__main__":
    unittest.main()
