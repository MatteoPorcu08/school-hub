import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from git_cache import SessionGitCache, CacheError
from accelerator import RemoteIndex, native_scan

class RemoteIndexTest(unittest.TestCase):
    def test_isolation_and_invalidation(self):
        cache = RemoteIndex()
        head = "a" * 40
        key = ("remote", "main", "user")
        original = {"a": "x"}
        cache.put(key, head, original)
        original["a"] = "y"
        hit = cache.get(key, head)
        self.assertEqual(hit, {"a": "x"})
        hit.clear()
        self.assertEqual(cache.get(key, head), {"a": "x"})
        self.assertIsNone(cache.get(key, "b" * 40))
        self.assertIsNone(cache.get(("remote", "other", "user"), head))
        self.assertIsNone(cache.get(key, ""))

class NativeTest(unittest.TestCase):
    def test_scan_matches_hashlib(self):
        import hashlib
        root = Path(__file__).resolve().parents[1]
        binary = root / "target" / "release" / ("schoolhub-scan.exe" if os.name == "nt" else "schoolhub-scan")
        if not binary.is_file():
            self.skipTest("cargo build --release required")
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            (base / "sub").mkdir()
            (base / "sub" / "è.txt").write_bytes(b"hello")
            (base / ".gitattributes").write_bytes(b"ignored")
            self.assertEqual(native_scan(base, binary), {"sub/è.txt": hashlib.sha256(b"hello").hexdigest()})
            (base / "sub" / "è.txt").write_bytes(b"world")
            self.assertEqual(native_scan(base, binary), {"sub/è.txt": hashlib.sha256(b"world").hexdigest()})
            with self.assertRaises(RuntimeError):
                native_scan(base / "missing", binary)

@unittest.skipUnless(shutil.which("git"), "git is required")
class IncrementalGitTest(unittest.TestCase):
    def test_incremental_checkout_and_missing_branch(self):
        calls = []
        def git(args, cwd, timeout=180):
            calls.append(args)
            result = subprocess.run(["git", *args], cwd=cwd, capture_output=True,
                                    text=True, encoding="utf-8", errors="replace", timeout=timeout)
            return result.returncode, result.stdout.strip(), result.stderr.strip()
        def run(args, cwd):
            code, out, err = git(args, cwd)
            self.assertEqual(code, 0, err)
            return out
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            src = root / "src"
            src.mkdir()
            run(["init", "-b", "main"], src)
            run(["config", "user.name", "Test"], src)
            run(["config", "user.email", "test@example.invalid"], src)
            (src / "a.txt").write_text("first", encoding="utf-8")
            run(["add", "."], src)
            run(["commit", "-m", "first"], src)
            run(["checkout", "-b", "school"], src)
            (src / "a.txt").write_text("school", encoding="utf-8")
            run(["commit", "-am", "second"], src)
            cache = SessionGitCache(root)
            try:
                remote = src.as_uri()
                dest1 = root / "checkout1"
                cache.checkout(git, remote, "school", dest1)
                self.assertEqual((dest1 / "a.txt").read_text(encoding="utf-8"), "school")
                self.assertEqual(run(["remote", "get-url", "origin"], dest1), remote)
                (src / "a.txt").write_text("updated", encoding="utf-8")
                run(["commit", "-am", "third"], src)
                dest2 = root / "checkout2"
                cache.checkout(git, remote, "school", dest2)
                self.assertEqual((dest2 / "a.txt").read_text(encoding="utf-8"), "updated")
                self.assertEqual(len(list(cache.root.iterdir())), 1)
                self.assertEqual((dest1 / "a.txt").read_text(encoding="utf-8"), "school")
                missing = root / "missing"
                with self.assertRaises(CacheError):
                    cache.checkout(git, remote, "nonexistent", missing)
                self.assertFalse(missing.exists())
            finally:
                cache.close()
                self.assertFalse(cache.root.exists())

if __name__ == "__main__":
    unittest.main()
