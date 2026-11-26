import base64
import hashlib
import json
import os
from pathlib import Path
import tempfile
import urllib.request

REV = "513285580fbbade3568c8fd4fb3692ab891e4460"
BASE = f"https://raw.githubusercontent.com/MeloniMirko/SchoolHub/{REV}/.schoolhub-source-audit/"
BLOBS = "https://api.github.com/repos/MeloniMirko/SchoolHub/git/blobs/"
FILES = {
    "src/schoolhub_gui.py": "86da031e940421dadce88bafdaac82ce0a8ac17e",
    "src/workspace.py": "2af28754a957bdcac0fbd4ab05ca176fa82a15ad",
}
def git_blob_id(data):
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()

def verified(path, expected):
    try:
        return path.is_file() and git_blob_id(path.read_bytes()) == expected
    except OSError:
        return False

def fetch_source(relative, expected, opener=urllib.request.urlopen):
    errors = []
    for url, api in [(BASE + relative, False), (BLOBS + expected, True)]:
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "SchoolHubRust", "Accept": "application/vnd.github+json" if api else "*/*"})
            with opener(request, timeout=30) as response:
                raw = response.read(2_000_001)
            if len(raw) > 2_000_000:
                raise ValueError("File troppo grande")
            if api:
                blob = json.loads(raw)
                if blob.get("encoding") != "base64" or blob.get("sha") != expected:
                    raise ValueError("Blob GitHub non valido")
                raw = base64.b64decode("".join(blob["content"].split()), validate=True)
            if git_blob_id(raw) != expected:
                raise ValueError("Checksum Git non corrispondente")
            return raw
        except Exception as exc:
            errors.append(f"{'API' if api else 'raw'}: {type(exc).__name__}: {exc}")
    raise RuntimeError(f"Impossibile recuperare {relative}. " + "; ".join(errors))

def prepare_sources(root, progress=lambda name: None):
    for relative, expected in FILES.items():
        dest = Path(root) / relative
        if verified(dest, expected):
            continue
        progress(relative)
        data = fetch_source(relative, expected)
        dest.parent.mkdir(parents=True, exist_ok=True)
        fd, temp = tempfile.mkstemp(prefix=".source-", dir=dest.parent)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp, dest)
        finally:
            if os.path.exists(temp):
                os.unlink(temp)
