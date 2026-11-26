"""Windows executable entry point. Original UI stays local and is never bundled."""
import base64
import difflib
import hashlib
import importlib.util
import math
import secrets
import errno
from datetime import datetime, timezone
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
from source_loader import REV, FILES, verified, prepare_sources
from workspace_binding import choose_binding, install_binding, make_binding

BUNDLE = pathlib.Path(getattr(sys, "_MEIPASS", pathlib.Path(__file__).resolve().parent))
VERSION = (BUNDLE / "VERSION").read_text(encoding="utf-8").strip()
PROFILE = pathlib.Path(os.environ.get("LOCALAPPDATA", pathlib.Path.home())) / "SchoolHubRust"
LEGACY = PROFILE.parent / "SchoolHub"
UPDATES = PROFILE / "AppUpdates"
SOURCE = PROFILE / "OriginalUI" / REV
SCANNER = BUNDLE / "schoolhub-scan.exe"

def prepare_ui(interactive=True):
    if all(verified(SOURCE / rel, digest) for rel, digest in FILES.items()):
        return True
    if not interactive:
        prepare_sources(SOURCE)
        return True
    root = tk.Tk()
    root.withdraw()
    try:
        if not messagebox.askyesno(
            "SchoolHub - Primo avvio",
            "L'interfaccia originale SchoolHub appartiene al suo autore. "
            "Il repository non dichiara una licenza di riutilizzo.\n\n"
            "Confermi di avere il diritto di utilizzarla e vuoi scaricarne i sorgenti "
            "solo su questo computer?",
            parent=root,
        ):
            return False
        root.title("SchoolHub - Preparazione")
        root.geometry("480x180")
        root.resizable(False, False)
        root.configure(bg="#0a1120")
        root.iconbitmap(str(BUNDLE / "schoolhub.ico"))
        tk.Label(root, text="SCHOOLHUB", font=("Segoe UI", 19, "bold"), fg="#eff6ff", bg="#0a1120").pack(pady=(22, 8))
        status = tk.Label(root, text="Verifica dei componenti...", fg="#76daff", bg="#0a1120")
        status.pack(pady=5)
        progress = ttk.Progressbar(root, mode="indeterminate", length=360)
        progress.pack(pady=12)
        progress.start(15)
        root.deiconify()
        root.update()
        def show(name):
            status.configure(text=f"Scaricamento: {pathlib.Path(name).name}")
            root.update()
        prepare_sources(SOURCE, show)
        return True
    finally:
        root.destroy()

def load_original():
    def load(name, file):
        spec = importlib.util.spec_from_file_location(name, file)
        if spec is None or spec.loader is None:
            raise ImportError(f"Impossibile caricare {name}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
        return module
    load("workspace", SOURCE / "src" / "workspace.py")
    return load("schoolhub_gui", SOURCE / "src" / "schoolhub_gui.py")

def configure_gui(gui):
    gui.APP_DIR = str(PROFILE)
    gui.CONFIG_FILE = str(PROFILE / "config.json")
    gui.LOG_FILE = str(PROFILE / "schoolhub.log")
    gui.SYNC_STATE_FILE = str(PROFILE / "sync_state.json")
    gui.UPDATE_STAMP_FILE = str(PROFILE / "last_update_check.txt")
    gui.DEFAULT_REPO = str(PROFILE / "TempGit")
    gui.DEFAULT_WORKSPACE = str(PROFILE / "Workspaces" / "Scuola")
    gui.RELEASE_API = "https://api.github.com/repos/MatteoPorcu08/school-hub/releases/latest"
    gui.RELEASES_API = "https://api.github.com/repos/MatteoPorcu08/school-hub/releases"
    original_resource_path = gui.resource_path
    def resource_path(name):
        if name == "schoolhub_icon.png":
            return str(BUNDLE / "schoolhub_icon.png")
        return original_resource_path(name)
    gui.resource_path = resource_path
    # Idempotent responsive sizing: Tk can repeatedly emit Configure when
    # a widget is reconfigured with its existing value. Avoid idle-event loops.
    def responsive_wraps(self, available_width=None):
        if not self.widget_alive(getattr(self, "content", None)):
            return
        cap = max(240, int(available_width or max(320, self.content.winfo_width())) - 70)
        stack = [self.content]
        while stack:
            parent = stack.pop()
            for widget in parent.winfo_children():
                stack.append(widget)
                if isinstance(widget, tk.Label):
                    try:
                        current = int(float(widget.cget("wraplength") or 0))
                    except (ValueError, TypeError, tk.TclError):
                        continue
                    if current <= 0:
                        continue
                    if not hasattr(widget, "_schoolhub_wrap_base"):
                        widget._schoolhub_wrap_base = current
                    target = min(widget._schoolhub_wrap_base, cap)
                    if current != target:
                        widget.configure(wraplength=target)
    gui.SchoolHub._apply_responsive_wraps = responsive_wraps
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
                    self.root.after(0, lambda: messagebox.showinfo("SchoolHub", message))
                elif not silent:
                    self.root.after(0, lambda: messagebox.showinfo("SchoolHub", "Applicazione aggiornata."))
            except Exception as exc:
                self.write_log(f"Aggiornamento non disponibile: {type(exc).__name__}: {exc}")
                if not silent:
                    self.root.after(0, lambda detail=str(exc): messagebox.showwarning("SchoolHub", f"Impossibile controllare gli aggiornamenti.\n\n{detail}\n\nConsulta le release GitHub."))
            finally:
                self.update_check_running = False
        threading.Thread(target=worker, daemon=True).start()
    gui.SchoolHub.check_for_updates = check_updates
    install(gui, SCANNER)
    gui.APP_VERSION = VERSION
    install_binding(gui, PROFILE, LEGACY)

    # Prefer the private bundled runtime; never require system Git.
    original_git = gui.bundled_git_info
    def bundled_only():
        exe, env, bundled = original_git()
        if not bundled:
            raise RuntimeError("Runtime di sincronizzazione integrato mancante. Reinstalla SchoolHub.")
        return exe, env, bundled
    gui.bundled_git_info = bundled_only

    original_init = gui.SchoolHub.__init__
    def init(self, root):
        original_init(self, root)
        root.title(f"SchoolHub {VERSION}")
        root.iconbitmap(str(BUNDLE / "schoolhub.ico"))
        self.logo_subtitle.configure(text="SECURE SCHOOL WORKSPACE")
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

def ui_smoke(output):
    global PROFILE, UPDATES, SOURCE, LEGACY
    trace_path = pathlib.Path(output + ".trace")
    def mark(stage):
        with trace_path.open("a", encoding="utf-8") as trace:
            trace.write(stage + "\n")
            trace.flush()
    mark("start")
    with tempfile.TemporaryDirectory(prefix="schoolhub-ui-test-") as d:
        PROFILE = pathlib.Path(d) / "optimized"
        LEGACY = pathlib.Path(d) / "original"
        UPDATES = PROFILE / "AppUpdates"
        SOURCE = PROFILE / "OriginalUI" / REV
        mark("prepare original source")
        prepare_ui(interactive=False)
        mark("load original modules")
        gui = load_original()
        configure_gui(gui)
        mark("configured")
        selected = LEGACY / "Workspaces" / "Scuola"
        selected.mkdir(parents=True)
        (selected / "existing.txt").write_text("existing", encoding="utf-8")
        mark("bind existing folder")
        config = make_binding(PROFILE, LEGACY, selected, {})
        config["onboarding_complete"] = True
        config["auto_sync"] = False
        gui.save_config(config)
        mark("create Tk")
        root = tk.Tk()
        try:
            root.withdraw()
            mark("construct app")
            app = gui.SchoolHub(root)
            mark("app constructed")
            actual = pathlib.Path(app.workspace.get_unlocked_path())
            mark(f"workspace expected={selected} actual={actual} mode={app.config.get('workspace_mode')}")
            assert actual.samefile(selected), f"Wrong workspace: {actual} != {selected}"
            assert (actual / "existing.txt").read_text(encoding="utf-8") == "existing"
            mark("existing folder verified")
            git_exe, git_env, bundled = gui.bundled_git_info()
            assert bundled and pathlib.Path(git_exe).is_relative_to(BUNDLE)
            for args in (["--version"], ["credential-manager", "--version"], ["lfs", "version"], ["credential-manager", "github", "login", "--help"]):
                mark("runtime " + " ".join(args))
                result = subprocess.run([git_exe, *args], env=git_env, capture_output=True, timeout=30, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                if result.returncode:
                    raise RuntimeError(f"Runtime integrato: {args}: {result.stderr.decode('utf-8', 'replace')}")
                if args[-1] == "--help":
                    help_text = (result.stdout + result.stderr).decode("utf-8", "replace")
                    assert "--web" in help_text and "--force" in help_text
            for page in ("Home", "Sync", "Workspace", "Attività", "Impostazioni"):
                mark("navigate " + page)
                app.navigate(page)
                root.update_idletasks()
                mark("rendered " + page)
            app.running = False
            mark("all pages rendered")
            assert root.title() == f"SchoolHub {VERSION}"
            assert gui.resource_path("schoolhub_icon.png")
        except BaseException:
            mark(traceback.format_exc())
            raise
        finally:
            mark("destroy Tk")
            root.destroy()
    mark("finished")
    pathlib.Path(output).write_text(json.dumps({"ok": True, "version": VERSION, "ui": True}), encoding="utf-8")

def main():
    if len(sys.argv) == 3 and sys.argv[1] == "--smoke":
        smoke(sys.argv[2])
        return
    if len(sys.argv) == 3 and sys.argv[1] == "--ui-smoke":
        ui_smoke(sys.argv[2])
        return
    PROFILE.mkdir(parents=True, exist_ok=True)
    if dispatch_pending(UPDATES, VERSION):
        return
    if not prepare_ui():
        return
    gui = load_original()
    configure_gui(gui)
    if not choose_binding(gui, PROFILE, LEGACY):
        return
    gui.main()

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        if "--smoke" in sys.argv or "--ui-smoke" in sys.argv:
            if len(sys.argv) == 3:
                pathlib.Path(sys.argv[2]).write_text(json.dumps({"ok": False, "error": traceback.format_exc()}), encoding="utf-8")
            # Windowed PyInstaller shows a blocking modal on unhandled errors.
            # Return a real exit code to the test runner instead.
            sys.exit(1)
        PROFILE.mkdir(parents=True, exist_ok=True)
        with (PROFILE / "startup-error.log").open("a", encoding="utf-8") as log:
            log.write(traceback.format_exc() + "\n")
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("SchoolHub", f"Avvio non riuscito: {exc}\nDettagli: {PROFILE / 'startup-error.log'}")
        root.destroy()
