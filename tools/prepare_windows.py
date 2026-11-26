"""Extract the existing SchoolHub icon and acquire pinned Windows sync runtimes."""
import base64
import concurrent.futures
import hashlib
import io
import os
from pathlib import Path
import shutil
import tarfile
import tempfile
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = "https://raw.githubusercontent.com/MeloniMirko/SchoolHub/513285580fbbade3568c8fd4fb3692ab891e4460/.schoolhub-v2.2/"
ARCHIVE_SHA256 = "11a25bb9e4b54868a2754b15d3c665b5384fb24cc06946a3fb0f29af6f135ba8"
RUNTIMES = [
    ("git", "https://github.com/git-for-windows/git/releases/download/v2.56.1.windows.1/MinGit-2.56.1-64-bit.zip",
     "4a92850b6e917da4fd010669b614b55dccf5b0ec333a534cc4be4700dfefdafd"),
    ("gcm", "https://github.com/git-ecosystem/git-credential-manager/releases/download/v3.0.2/gcm-win-x64-3.0.2.zip",
     "9d2bef6e42a37654ea7ef33172bbcf1b6a1df6191fcf6a57dfbf39e1cbc27a0f"),
    ("lfs", "https://github.com/git-lfs/git-lfs/releases/download/v3.8.1/git-lfs-windows-amd64-v3.8.1.zip",
     "5bb771c12b3dacc535e912d0270a010c209d4da2e63819c5918e3547c2defed9"),
]

def get(url, maximum):
    request = urllib.request.Request(url, headers={"User-Agent": "SchoolHub-Build"})
    last = None
    for _ in range(3):
        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                data = response.read(maximum + 1)
            if len(data) > maximum:
                raise ValueError("Download too large")
            return data
        except Exception as exc:
            last = exc
    raise RuntimeError(f"Unable to download {url}") from last

def logo():
    from PIL import Image
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        chunks = list(pool.map(lambda i: get(UPSTREAM + f"source.part{i:02d}", 20000).strip(), range(31)))
    data = base64.b64decode(b"".join(chunks), validate=True)
    if hashlib.sha256(data).hexdigest() != ARCHIVE_SHA256:
        raise ValueError("Original source archive SHA-256 mismatch")
    out = ROOT / "assets"
    out.mkdir(exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:xz") as archive:
        for name in ("schoolhub_icon.png", "schoolhub.ico"):
            matches = [m for m in archive.getmembers() if m.isfile() and Path(m.name).name.lower() == name.lower()]
            if len(matches) != 1:
                raise ValueError(f"Expected exactly one original {name}, found {[m.name for m in matches]}")
            member = matches[0]
            if member.size > 5_000_000:
                raise ValueError("Icon too large")
            contents = archive.extractfile(member).read()
            with Image.open(io.BytesIO(contents)) as image:
                image.verify()
            (out / name).write_bytes(contents)
            print(f"Original icon: {member.name} SHA-256 {hashlib.sha256(contents).hexdigest()}")
    # Deliberately never extract or redistribute the source archive.

def safe_extract(archive, dest):
    for member in archive.infolist():
        target = (dest / member.filename).resolve()
        if not target.is_relative_to(dest.resolve()):
            raise ValueError("Invalid archive path")
    archive.extractall(dest)

def runtime(item):
    name, url, expected = item
    data = get(url, 100_000_000)
    if hashlib.sha256(data).hexdigest() != expected:
        raise ValueError(f"{name} checksum mismatch")
    dest = ROOT / "vendor" / name
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        safe_extract(archive, dest)
    if name == "lfs":
        paths = list(dest.rglob("git-lfs.exe"))
        if len(paths) != 1:
            raise ValueError("LFS binary not found uniquely")
        if paths[0].parent != dest:
            shutil.copy2(paths[0], dest / "git-lfs.exe")
    required = {"git": dest / "cmd/git.exe", "gcm": dest / "git-credential-manager.exe", "lfs": dest / "git-lfs.exe"}[name]
    if not required.is_file():
        raise FileNotFoundError(required)
    print(f"Verified bundled {name}: {required.name}")

if __name__ == "__main__":
    logo()
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        list(pool.map(runtime, RUNTIMES))
