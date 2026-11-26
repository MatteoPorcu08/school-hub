import hashlib
import tempfile
import unittest
from pathlib import Path
from workspace_binding import make_binding, state_path, apply_folder_changes, validate_folder

def hashes(path):
    return {f.relative_to(path).as_posix(): hashlib.sha256(f.read_bytes()).hexdigest()
            for f in Path(path).rglob("*") if f.is_file()}

class BindingTest(unittest.TestCase):
    def test_existing_folder_unchanged(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            selected = base / "SchoolHub"
            selected.mkdir()
            (selected / "lesson.txt").write_text("notes")
            original = {"workspace_path": str(selected), "remote": "https://github.com/test/data", "branch": "main"}
            result = make_binding(base / "profile", base / "legacy", selected, original)
            self.assertEqual(result["workspace_path"], str(selected.resolve()))
            self.assertEqual(result["workspace_mode"], "folder")
            self.assertEqual(result["remote"], original["remote"])
            self.assertEqual((selected / "lesson.txt").read_text(), "notes")
            self.assertFalse(result["auto_sync"])
            self.assertNotEqual(state_path(base / "profile", result), state_path(base / "profile", {**result, "branch":"other"}))

    def test_preserve_existing_vault(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            workspace = base / "work"
            workspace.mkdir()
            vault = base / "vault"
            (vault / "files").mkdir(parents=True)
            (vault / "vault.json").write_text("{}")
            result = make_binding(base / "profile", base / "legacy", workspace, {"workspace_path": str(workspace), "vault_path": str(vault)})
            self.assertEqual(result["workspace_mode"], "vault")
            self.assertEqual(result["vault_path"], str(vault.resolve()))
            self.assertTrue(vault.exists())

    def test_download_preserves_backup_and_existing_files(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            local, merged = base / "local", base / "merged"
            local.mkdir(); merged.mkdir()
            for path, content in ((local/"same","same"),(local/"change","old"),(local/"delete","old"),(merged/"same","same"),(merged/"change","new"),(merged/"add","new")):
                path.write_text(content)
            backup = apply_folder_changes(local, merged, ["change","delete","add"], base/"profile", hashes)
            self.assertEqual(hashes(local), hashes(merged))
            self.assertEqual((backup/"change").read_text(), "old")
            self.assertEqual((backup/"delete").read_text(), "old")

    def test_different_tree_refuses_to_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            local, merged = base/"local", base/"merged"
            local.mkdir(); merged.mkdir()
            (local/"new-local").write_text("do not delete")
            (merged/"incoming").write_text("remote")
            with self.assertRaises(ValueError):
                apply_folder_changes(local, merged, ["incoming"], base/"profile", hashes)
            self.assertEqual((local/"new-local").read_text(), "do not delete")
            self.assertFalse((local/"incoming").exists())

    def test_reject_profile_root(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            with self.assertRaises(ValueError):
                validate_folder(base, base/"profile", base/"legacy")
