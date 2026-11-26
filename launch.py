"""Run the original UI with the Rust accelerator in a separate local profile."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
UPSTREAM = ROOT / "upstream" / "src"
BINARY = ROOT / "target" / "release" / ("schoolhub-scan.exe" if os.name == "nt" else "schoolhub-scan")

def main():
    if not (UPSTREAM / "schoolhub_gui.py").is_file():
        raise SystemExit("Eseguire prima setup.py per preparare i sorgenti originali autorizzati.")
    sys.path.insert(0, str(UPSTREAM))
    import schoolhub_gui as gui
    from accelerator import install
    # Keep test profile and original SchoolHub data separate; do not auto-migrate.
    base = Path(gui.LOCAL_APPDATA) / "SchoolHubRust"
    gui.APP_DIR = str(base)
    gui.CONFIG_FILE = str(base / "config.json")
    gui.LOG_FILE = str(base / "schoolhub.log")
    gui.SYNC_STATE_FILE = str(base / "sync_state.json")
    gui.UPDATE_STAMP_FILE = str(base / "last_update_check.txt")
    gui.DEFAULT_REPO = str(base / "TempGit")
    gui.DEFAULT_WORKSPACE = str(base / "Workspaces" / "Scuola")
    # Do not modify the original Windows autorun entry or install upstream updates.
    def no_autorun(self, enabled):
        if enabled:
            self.write_log("Avvio automatico non disponibile nell'anteprima Rust.")
        return not enabled
    def no_update(self, silent=False):
        if not silent:
            gui.messagebox.showinfo("SchoolHub Rust", "Gli aggiornamenti dell'anteprima si installano dal repository del progetto.")
    gui.SchoolHub.set_windows_startup = no_autorun
    gui.SchoolHub.check_for_updates = no_update
    install(gui, BINARY)
    gui.main()

if __name__ == "__main__":
    main()
