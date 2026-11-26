"""Windows executable entry point. Original UI stays local and is never bundled."""
import base64
import difflib
import hashlib
import json
import os
import pathlib
import platform
import shutil
import struct
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
import urllib.request
import urllib.error
import urllib.parse
import uuid
import zipfile
import ctypes
from ctypes import wintypes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from accelerator import install, native_scan
from updater import dispatch_pending, stage_latest
from setup import REV, BASE, FILES, git_blob_id

BUNDLE = pathlib.Path(getattr(sys, "_MEIPASS", pathlib.Path(__file__).resolve().parent))
VERSION = (BUNDLE / "VERSION").read_text(encoding="utf-8").strip()
PROFILE = pathlib.Path(os.environ.get("LOCALAPPDATA", pathlib.Path.home())) / "SchoolHubRust"
UPDATES = PROFILE / "AppUpdates"
SOURCE = PROFILE / "OriginalUI" / REV
SCANNER = BUNDLE / "schoolhub-scan.exe"

def prepare_ui():
    missing = []
    for rel, expected in FILES.items():
        dest = SOURCE / rel
        if not dest.is_file() or git_blob_id(dest.read_bytes()) != expected:
            missing.append((rel, expected))
    if not missing:
        return True
    root = tk.Tk()
    root.withdraw()
    try:
        if not messagebox.askyesno(
            "SchoolHub Rust - Primo avvio",
            "L'interfaccia originale SchoolHub 2.6.7 appartiene al suo autore. "
            "Il suo repository non dichiara una licenza di riutilizzo.\n\n"
            "Confermi di avere il diritto di utilizzarla e vuoi scaricarne i sorgenti "
            "solo su questo computer?\n\nNon saranno inviati al repository SchoolHub Rust.",
            parent=root,
        ):
            return False
        for rel, expected in missing:
            request = urllib.request.Request(BASE + rel, headers={"User-Agent": "SchoolHubRust"})
            with urllib.request.urlopen(request, timeout=30) as response:
                data = response.read(2_000_000)
            if git_blob_id(data) != expected:
                raise RuntimeError(f"Integrità sorgente non verificata: {rel}")
            dest = SOURCE / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            fd, temp = tempfile.mkstemp(prefix=".source-", dir=dest.parent)
            try:
                with os.fdopen(fd, "wb") as f:
                    f.write(data)
                os.replace(temp, dest)
            finally:
                if os.path.exists(temp):
                    os.unlink(temp)
        return True
    finally:
        root.destroy()

def configure_gui(gui):
    gui.APP_DIR = str(PROFILE)
    gui.CONFIG_FILE = str(PROFILE / "config.json")
    gui.LOG_FILE = str(PROFILE / "schoolhub.log")
    gui.SYNC_STATE_FILE = str(PROFILE / "sync_state.json")
    gui.UPDATE_STAMP_FILE = str(PROFILE / "last_update_check.txt")
    gui.DEFAULT_REPO = str(PROFILE / "TempGit")
    gui.DEFAULT_WORKSPACE = str(PROFILE / "Workspaces" / "Scuola")
    def no_autorun(self, enabled):
        if enabled:
            self.write_log("Avvio automatico Windows non configurato dall'anteprima Rust.")
        return not enabled
    gui.SchoolHub.set_windows_startup = no_autorun

    def check_updates(self, silent=False):
        if self.update_check_running or not self.running:
            return
        self.update_check_running = True
        def worker():
            try:
                version = stage_latest(UPDATES, VERSION)
                if version:
                    message = f"Aggiornamento {version} scaricato e verificato. Si attiverà al prossimo avvio."
                    self.write_log(message)
                    self.root.after(0, lambda: messagebox.showinfo("SchoolHub Rust", message))
                elif not silent:
                    self.root.after(0, lambda: messagebox.showinfo("SchoolHub Rust", "Applicazione aggiornata."))
            except Exception as exc:
                self.write_log(f"Aggiornamento Rust non disponibile: {type(exc).__name__}")
                if not silent:
                    self.root.after(0, lambda: messagebox.showwarning("SchoolHub Rust", "Impossibile controllare gli aggiornamenti. Riprova."))
            finally:
                self.update_check_running = False
        threading.Thread(target=worker, daemon=True).start()
    gui.SchoolHub.check_for_updates = check_updates
    install(gui, SCANNER)

    original_init = gui.SchoolHub.__init__
    def init(self, root):
        original_init(self, root)
        root.title(f"SchoolHub Rust {VERSION}")
        # Startup check already scheduled by the original UI. Repeat every six hours.
        def periodic():
            if self.running:
                self.check_for_updates(silent=True)
                root.after(6 * 60 * 60 * 1000, periodic)
        root.after(6 * 60 * 60 * 1000, periodic)
    gui.SchoolHub.__init__ = init

def smoke(output):
    with tempfile.TemporaryDirectory() as d:
        path = pathlib.Path(d)
        (path / "sample").write_bytes(b"abc")
        actual = native_scan(path, SCANNER)
        key = AESGCM.generate_key(bit_length=256)
        cipher = AESGCM(key)
        nonce = b"\0" * 12
        encrypted = cipher.encrypt(nonce, b"smoke", None)
        assert cipher.decrypt(nonce, encrypted, None) == b"smoke"
        assert actual == {"sample": hashlib.sha256(b"abc").hexdigest()}
    pathlib.Path(output).write_text(json.dumps({"ok": True, "version": VERSION}), encoding="utf-8")

def main():
    if len(sys.argv) == 3 and sys.argv[1] == "--smoke":
        smoke(sys.argv[2])
        return
    PROFILE.mkdir(parents=True, exist_ok=True)
    if dispatch_pending(UPDATES, VERSION):
        return
    if not prepare_ui():
        return
    sys.path.insert(0, str(SOURCE / "src"))
    import schoolhub_gui as gui
    configure_gui(gui)
    gui.main()

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        if "--smoke" in sys.argv:
            raise
        PROFILE.mkdir(parents=True, exist_ok=True)
        with (PROFILE / "startup-error.log").open("a", encoding="utf-8") as log:
            log.write(traceback.format_exc() + "\n")
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("SchoolHub Rust", f"Avvio non riuscito: {exc}\nDettagli: {PROFILE / 'startup-error.log'}")
        root.destroy()
