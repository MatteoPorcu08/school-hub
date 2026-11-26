import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from updater import API, REPO, pending, stage_latest, version_tuple

class UpdaterTest(unittest.TestCase):
    def fixture(self, body=b"new-exe", download=None, version="v0.2.1"):
        digest = hashlib.sha256(body).hexdigest()
        prefix = f"https://github.com/{REPO}/releases/download/{version}/"
        release = {
            "tag_name": version, "draft": False, "prerelease": False,
            "assets": [
                {"name": "SchoolHub.exe", "size": len(body), "digest": "sha256:" + digest,
                 "browser_download_url": prefix + "SchoolHub.exe"},
                {"name": "SchoolHub.exe.sha256", "size": 64,
                 "browser_download_url": prefix + "SchoolHub.exe.sha256"}
            ]
        }
        def open_fake(url):
            data = {API: json.dumps(release).encode(), prefix + "SchoolHub.exe": body if download is None else download,
                    prefix + "SchoolHub.exe.sha256": digest.encode()}
            return io.BytesIO(data[url])
        return open_fake

    def test_stage_and_detect(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            self.assertEqual(stage_latest(base, "0.2.0", self.fixture()), "0.2.1")
            version, exe = pending(base, "0.2.0")
            self.assertEqual(version, "0.2.1")
            self.assertEqual(exe.read_bytes(), b"new-exe")
            self.assertIsNone(pending(base, "0.2.1"))
            exe.write_bytes(b"tampered")
            self.assertIsNone(pending(base, "0.2.0"))

    def test_invalid_download_preserves_state(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            with self.assertRaises(ValueError):
                stage_latest(base, "0.2.0", self.fixture(download=b"bad-exe"))
            self.assertFalse((base / "current.json").exists())

    def test_no_downgrade(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(stage_latest(Path(d), "0.3.0", self.fixture()))
        self.assertGreater(version_tuple("v0.10.0"), version_tuple("0.2.0"))
