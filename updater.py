"""Automatic staged updates from this project's GitHub Releases."""
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path

REPO = "MatteoPorcu08/school-hub"
API = f"https://api.github.com/repos/{REPO}/releases/latest"
MAX_SIZE = 200 * 1024 * 1024
DIGEST = re.compile(r"[0-9a-f]{64}")
VERSION_RE = re.compile(r"v?(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)")

def version_tuple(text):
    match = VERSION_RE.fullmatch(text)
    if not match:
        raise ValueError("Versione release non valida")
    return tuple(map(int, match.groups()))

def normalized_version(text):
    return ".".join(map(str, version_tuple(text)))

def sha256_file(path):
    with open(path, "rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()

def verified_url(url):
    parsed = urllib.parse.urlsplit(url)
    allowed = {"github.com", "api.github.com", "release-assets.githubusercontent.com", "objects.githubusercontent.com"}
    if parsed.scheme != "https" or parsed.hostname not in allowed or parsed.username or parsed.password or parsed.port:
        raise ValueError("URL aggiornamento non autorizzato")
    return url

class SecureRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return super().redirect_request(req, fp, code, msg, headers, verified_url(newurl))

def open_release(url, timeout=30):
    request = urllib.request.Request(verified_url(url), headers={
        "User-Agent": "SchoolHubRust-Updater",
        "Accept": "application/vnd.github+json" if url == API else "application/octet-stream",
    })
    return urllib.request.build_opener(SecureRedirect()).open(request, timeout=timeout)

def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=".update-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(value, fh)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)

def pending(base, current):
    try:
        marker = json.loads((base / "current.json").read_text(encoding="utf-8"))
        ver = normalized_version(marker["version"])
        digest = marker["sha256"]
        if version_tuple(ver) <= version_tuple(current) or not DIGEST.fullmatch(digest):
            return None
        exe = base / "versions" / ver / "SchoolHub.exe"
        if exe.is_file() and sha256_file(exe) == digest:
            return ver, exe
    except (OSError, ValueError, KeyError, TypeError):
        pass
    return None

def dispatch_pending(base, current):
    update = pending(base, current)
    if update is None:
        return False
    _, exe = update
    env = os.environ.copy()
    env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    subprocess.Popen([str(exe)], cwd=str(exe.parent), env=env)
    return True

def stage_latest(base, current, opener=open_release):
    with opener(API) as response:
        release = json.loads(response.read(2_000_000))
    if release.get("draft") or release.get("prerelease"):
        return None
    version = normalized_version(release["tag_name"])
    if version_tuple(version) <= version_tuple(current):
        return None
    existing = pending(base, current)
    if existing is not None and version_tuple(existing[0]) >= version_tuple(version):
        return existing[0]
    assets = {asset["name"]: asset for asset in release["assets"]}
    exe = assets["SchoolHub.exe"]
    checksum = assets["SchoolHub.exe.sha256"]
    expected_prefix = f"https://github.com/{REPO}/releases/download/{release['tag_name']}/"
    def asset_url(asset):
        url = asset["browser_download_url"]
        if url != expected_prefix + asset["name"]:
            raise ValueError("Asset release non corrispondente")
        return url
    size = exe["size"]
    if not isinstance(size, int) or not 1 <= size <= MAX_SIZE:
        raise ValueError("Dimensione aggiornamento non valida")
    with opener(asset_url(checksum)) as response:
        digest = response.read(1024).decode("ascii").strip().split()[0].lower()
    if not DIGEST.fullmatch(digest):
        raise ValueError("Checksum aggiornamento non valido")
    api_digest = exe.get("digest")
    if api_digest and api_digest != "sha256:" + digest:
        raise ValueError("Digest GitHub e checksum non corrispondenti")
    dest = base / "versions" / version / "SchoolHub.exe"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_file() and sha256_file(dest) == digest:
        atomic_json(base / "current.json", {"version": version, "sha256": digest})
        return version
    fd, temp = tempfile.mkstemp(prefix=".download-", dir=dest.parent)
    try:
        count = 0
        h = hashlib.sha256()
        with os.fdopen(fd, "wb") as stream, opener(asset_url(exe)) as response:
            while chunk := response.read(1024 * 1024):
                count += len(chunk)
                if count > size:
                    raise ValueError("Download superiore alla dimensione attesa")
                h.update(chunk)
                stream.write(chunk)
            stream.flush()
            os.fsync(stream.fileno())
        if count != size or h.hexdigest() != digest:
            raise ValueError("Aggiornamento incompleto o checksum errato")
        os.replace(temp, dest)
        atomic_json(base / "current.json", {"version": version, "sha256": digest})
        return version
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
