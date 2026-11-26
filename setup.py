"""Fetch only the pinned upstream source files locally, validate Git blob IDs, build Rust."""
import hashlib
import pathlib
import subprocess
import sys
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent
REV = "513285580fbbade3568c8fd4fb3692ab891e4460"
BASE = f"https://raw.githubusercontent.com/MeloniMirko/SchoolHub/{REV}/.schoolhub-source-audit/"
FILES = {
    "src/schoolhub_gui.py": "86da031e940421dadce88bafdaac82ce0a8ac17e",
    "src/workspace.py": "2af28754a957bdcac0fbd4ab05ca176fa82a15ad",
    "intro.tcl": "b19bfc74d9953f81a49b6d0c17646c6d14946e95",
}

def git_blob_id(data):
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii") + data).hexdigest()

def main():
    if "--authorized" not in sys.argv:
        raise SystemExit("Il codice originale non dichiara una licenza. Procedi soltanto se hai diritto a utilizzarlo: python setup.py --authorized")
    for relative, expected in FILES.items():
        dest = ROOT / "upstream" / relative
        if dest.is_file() and git_blob_id(dest.read_bytes()) == expected:
            continue
        request = urllib.request.Request(BASE + relative, headers={"User-Agent": "SchoolHubRust-dev"})
        with urllib.request.urlopen(request, timeout=30) as response:
            data = response.read(2_000_000)
        if git_blob_id(data) != expected:
            raise RuntimeError(f"Integrità sorgente non verificata: {relative}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
    subprocess.run([sys.executable, "-m", "pip", "install", "-r", str(ROOT / "requirements.txt")], check=True)
    subprocess.run(["cargo", "build", "--release"], cwd=ROOT, check=True)
    print("Preparazione completata. Avvia con: python launch.py")

if __name__ == "__main__":
    main()
