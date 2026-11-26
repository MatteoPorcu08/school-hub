"""Explicit workspace binding. Never migrate, move or erase an existing folder on startup."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import tempfile
import uuid
from datetime import datetime

BINDING_VERSION = 1

def read_config(path):
    if not path.is_file():
        return {}
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError(f"Configurazione non valida: {path}")
    nested = data.get("vaults", {})
    if isinstance(nested, dict) and isinstance(nested.get("Scuola"), dict):
        data = {**data, **nested["Scuola"]}
    return data

def is_reparse(path):
    try:
        info = path.lstat()
        return path.is_symlink() or bool(getattr(info, "st_file_attributes", 0) & 0x400)
    except FileNotFoundError:
        return False

def contains(parent, child):
    return child == parent or child.is_relative_to(parent)

def validate_folder(path, profile, legacy, allow_missing=False):
    path = Path(path).expanduser()
    if not path.is_absolute():
        raise ValueError("Selezionare un percorso assoluto.")
    if is_reparse(path):
        raise ValueError("Selezionare una cartella reale, non un collegamento.")
    path = path.resolve()
    profile, legacy = Path(profile).resolve(), Path(legacy).resolve()
    if path == Path(path.anchor) or contains(path, profile) or contains(path, legacy):
        raise ValueError("Selezionare solo la cartella dei documenti, non un disco o l'intero profilo applicativo.")
    # Existing app data must never become part of the synced file tree.
    for base in (profile, legacy):
        if contains(base, path) and not contains(base / "Workspaces", path) and path != base / "Workspace":
            raise ValueError("La cartella scelta contiene dati interni di SchoolHub.")
    if (path.exists() and not path.is_dir()) or (not allow_missing and not path.is_dir()):
        raise ValueError("Cartella documenti non disponibile.")
    if (path / "vault.json").exists() or (path / "config.json").exists() and (path / "Vaults").exists():
        raise ValueError("Selezionare la cartella dei documenti, non quella dei dati dell'app.")
    return path

def identity(workspace, remote, branch):
    obj = [os.path.normcase(str(Path(workspace).resolve())), str(remote).rstrip("/").removesuffix(".git").lower(), str(branch)]
    return hashlib.sha256(json.dumps(obj, ensure_ascii=False).encode("utf-8")).hexdigest()

def state_path(profile, config):
    return Path(profile) / "SyncState" / (identity(config["workspace_path"], config.get("remote", ""), config.get("branch", "master")) + ".json")

def make_binding(profile, legacy, selected, source, create=False):
    selected = validate_folder(selected, profile, legacy, allow_missing=create)
    source = dict(source)
    raw_old = source.get("workspace_path")
    same = bool(raw_old and Path(raw_old).resolve() == selected)
    if raw_old and not same and selected.exists() and Path(raw_old).exists():
        same = selected.samefile(raw_old)
    # A vault is reused ONLY when it is associated with this exact workspace.
    candidates = []
    if same and source.get("vault_path"):
        candidates.append(Path(source["vault_path"]))
    candidates.append(Path(str(selected) + ".vault"))
    if selected == Path(legacy).resolve() / "Workspaces" / "Scuola":
        candidates.append(Path(legacy) / "Vaults" / "Scuola.vault")
    existing = [p for p in candidates if p.exists()]
    vault = existing[0].resolve() if existing else None
    if vault is not None:
        if contains(selected, vault) or contains(vault, selected):
            raise ValueError("Il Vault e i documenti devono essere in cartelle separate.")
        if not (vault / "vault.json").is_file() or not (vault / "files").is_dir():
            raise ValueError(f"Vault non valido: {vault}. Nessun file verrà modificato.")
    if not selected.exists():
        if not create:
            raise ValueError("Cartella non disponibile.")
        selected.mkdir(parents=True, exist_ok=False)
    result = {
        "version": 7,
        "binding_version": BINDING_VERSION,
        "workspace_path": str(selected),
        "workspace_mode": "vault" if vault else "folder",
        "vault_path": str(vault or Path(profile) / "Vaults" / "Unused.vault"),
        "remote": source.get("remote", "") if same else "",
        "branch": source.get("branch", "master") if same else "master",
        "github_user": source.get("github_user", "") if same else "",
        "interval": max(30, min(86400, int(source.get("interval", 300)))),
        "auto_sync": False,
        "auto_start": False,
        "onboarding_complete": bool(same and source.get("remote")),
        "device_id": uuid.uuid4().hex,
        "device_name": source.get("device_name", "") or "",
        "update_channel": "stable",
    }
    result["sync_state_file"] = str(state_path(profile, result))
    return result

def choose_binding(gui, profile, legacy):
    profile, legacy = Path(profile), Path(legacy)
    current = read_config(profile / "config.json")
    if current.get("binding_version") == BINDING_VERSION:
        validate_folder(current["workspace_path"], profile, legacy)
        return True
    original = read_config(legacy / "config.json")
    # Prefer the original saved path, then the existing optimized profile.
    source = original if original.get("workspace_path") else current
    default = legacy / "Workspaces" / "Scuola"
    candidate = Path(source["workspace_path"]) if source.get("workspace_path") else default
    root = gui.tk.Tk()
    root.withdraw()
    try:
        use = None
        if candidate.is_dir() or source.get("vault_path") and Path(source["vault_path"]).is_dir():
            answer = gui.messagebox.askyesnocancel("SchoolHub — Cartella di lavoro",
                f"Vuoi usare la cartella già configurata?\n\n{candidate}\n\n"
                "Sì: usa questa cartella senza spostare i file.\nNo: seleziona un'altra cartella.\nAnnulla: esci senza modifiche.", parent=root)
            if answer is None:
                return False
            if answer:
                use = candidate
        else:
            answer = gui.messagebox.askyesnocancel("SchoolHub — Cartella di lavoro",
                f"Vuoi scegliere la cartella SchoolHub già presente sul disco?\n\n"
                f"Sì: seleziona i documenti esistenti.\nNo: crea la cartella originale predefinita:\n{default}\nAnnulla: esci.", parent=root)
            if answer is None:
                return False
            if not answer:
                use = default
        if use is None:
            name = gui.filedialog.askdirectory(title="Seleziona la cartella SchoolHub con i tuoi documenti",
                                              initialdir=str(candidate.parent if candidate.parent.is_dir() else Path.home()), parent=root)
            if not name:
                return False
            use = Path(name)
        # Match either original or prior optimized profile exactly to keep its remote.
        matched = next((c for c in (original, current) if c.get("workspace_path") and Path(c["workspace_path"]).resolve() == use.resolve()), {})
        selected = make_binding(profile, legacy, use, matched, create=(use == default or bool(matched.get("vault_path"))))
        if selected["workspace_mode"] == "folder":
            if not gui.messagebox.askyesno("SchoolHub — Cartella normale",
                f"Sincronizzerò direttamente:\n{use}\n\nI documenti rimarranno leggibili sul disco. "
                "Non verrà creato un Vault cifrato. Le modifiche e le cancellazioni remote saranno sincronizzate; "
                "le copie sostituite verranno conservate nei backup locali. Usare un repository dati privato.\n\nContinuare?", parent=root):
                return False
        # The previous configuration remains available if a user needs to recover it.
        config_path = profile / "config.json"
        if config_path.is_file():
            backup = profile / ("config.before-binding-" + uuid.uuid4().hex[:8] + ".json")
            shutil.copy2(config_path, backup)
        gui.save_config(selected)
        return True
    finally:
        root.destroy()

class FolderWorkspace:
    """A normal folder, intentionally not a Vault. Never materializes or erases it."""
    def __init__(self, path, vault, error_type):
        self.workspace_path = Path(path)
        self.vault_path = Path(vault)
        self.error_type = error_type
        self.last_warning = None
    @property
    def exists(self):
        return self.workspace_path.is_dir() and not is_reparse(self.workspace_path)
    @property
    def is_unlocked(self):
        return self.exists
    @property
    def has_plaintext(self):
        return self.exists
    def ensure_materialized(self):
        if not self.exists:
            raise self.error_type("La cartella SchoolHub non è disponibile. Nessun file modificato.")
    def get_unlocked_path(self):
        self.ensure_materialized()
        return str(self.workspace_path)

def safe_path(root, relative):
    if not isinstance(relative, str) or "\\" in relative:
        raise ValueError("Percorso non valido")
    parts = relative.split("/")
    if any(not p or p in (".", "..") or ":" in p or p.casefold() == ".git" for p in parts):
        raise ValueError("Percorso non valido")
    root = Path(root)
    path = root
    if is_reparse(path):
        raise ValueError("Collegamento non supportato")
    for p in parts:
        path = path / p
        if is_reparse(path):
            raise ValueError(f"Collegamento non supportato: {relative}")
    return path

def backup_files(profile, root, paths, hash_tree):
    """Keep local originals of files about to be replaced, not in synced root."""
    paths = sorted(set(paths))
    if not paths:
        return None
    base = Path(profile) / "Backups" / "FolderRecovery"
    base.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".pending-", dir=base))
    try:
        expected = {}
        original = hash_tree(root)
        for rel in paths:
            src = safe_path(root, rel)
            if src.is_file():
                dest = safe_path(staging, rel)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest)
                expected[rel] = original[rel]
            elif src.exists() and not src.is_dir():
                raise ValueError(f"Elemento non supportato: {rel}")
        if hash_tree(staging) != expected or hash_tree(root) != original:
            raise ValueError("I file sono cambiati durante il backup.")
        if not expected:
            shutil.rmtree(staging)
            return None
        dest = base / ("Recovery-" + datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:8])
        os.replace(staging, dest)
        return dest
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise

def apply_folder_changes(root, source, paths, profile, hash_tree):
    root, source = Path(root), Path(source)
    local, remote = hash_tree(root), hash_tree(source)
    paths = sorted(set(paths))
    # Refuse file-directory replacements instead of recursively deleting any tree.
    for rel in paths:
        dst, src = safe_path(root, rel), safe_path(source, rel)
        if rel in remote:
            if dst.is_dir() or any(p.is_file() for p in dst.parents if p != root and contains(root,p)):
                raise ValueError(f"Conflitto file/cartella: {rel}. Rinominare manualmente.")
            if not src.is_file():
                raise ValueError(f"Sorgente non valida: {rel}")
        elif dst.is_dir():
            raise ValueError(f"Conflitto file/cartella: {rel}. Rinominare manualmente.")
    proposed = dict(local)
    for rel in paths:
        if rel in remote:
            proposed[rel] = remote[rel]
        else:
            proposed.pop(rel, None)
    if proposed != remote:
        raise ValueError("La cartella è cambiata durante la sincronizzazione; nessun file modificato.")
    recovery = backup_files(profile, root, paths, hash_tree)
    if hash_tree(root) != local:
        raise ValueError("La cartella è cambiata dopo il backup; riprovare.")
    for rel in paths:
        dst, src = safe_path(root, rel), safe_path(source, rel)
        if rel in remote:
            dst.parent.mkdir(parents=True, exist_ok=True)
            fd, temp = tempfile.mkstemp(prefix=".schoolhub-", dir=dst.parent)
            os.close(fd)
            try:
                shutil.copy2(src, temp)
                os.replace(temp, dst)
            finally:
                if os.path.exists(temp):
                    os.unlink(temp)
        elif dst.is_file():
            dst.unlink()
    if hash_tree(root) != remote:
        raise ValueError("Verifica finale dei file non riuscita. Le copie precedenti restano nei backup.")
    return recovery

def install_binding(gui, profile, legacy):
    cls = gui.SchoolHub
    old_load = cls._load_active_vault
    old_state_load = cls._load_sync_state
    old_state_save = cls._save_sync_state
    old_persist = cls._persist_sync_tree
    old_recovery = cls._create_conflict_recovery
    old_workspace = cls.show_workspace
    old_close = cls.close
    old_assert = cls._assert_remote_private

    def normalize(self):
        if self.config.get("binding_version") != BINDING_VERSION:
            raise gui.WorkspaceError("Cartella non configurata. Riavvia SchoolHub.")
        validate_folder(self.config["workspace_path"], profile, legacy)
        if self.config.get("workspace_mode") not in ("folder", "vault"):
            raise gui.WorkspaceError("Modalità Workspace non valida.")
        self.config.setdefault("device_id", uuid.uuid4().hex)
        self.config["device_name"] = self.config.get("device_name") or "Dispositivo " + self.config["device_id"][:6].upper()
        self.config["sync_state_file"] = str(state_path(profile, self.config))
        gui.save_config(self.config)

    def load(self):
        old_load(self)
        if self.config["workspace_mode"] == "folder":
            self.workspace = FolderWorkspace(self.workspace_path, self.vault_path, gui.WorkspaceError)

    def scoped(self):
        cfg = {"workspace_path": self.workspace_path, "remote": self.remote, "branch": self.branch}
        self.sync_state_file = str(state_path(profile, cfg))

    def load_state(self):
        scoped(self)
        return old_state_load(self)

    def save_state(self, files):
        scoped(self)
        return old_state_save(self, files)

    def persist(self, source, password, temp_root, remote_paths=None):
        if isinstance(self.workspace, FolderWorkspace):
            self.workspace.ensure_materialized()
            recovery = apply_folder_changes(self.workspace_path, source, remote_paths or [], profile, self._hash_tree)
            if recovery:
                self.write_log("✓ Copie precedenti conservate: " + str(recovery))
            return
        return old_persist(self, source, password, temp_root, remote_paths)

    def recover(self, source, local_files, password):
        if not isinstance(self.workspace, FolderWorkspace):
            return old_recovery(self, source, local_files, password)
        recovery = backup_files(profile, source, list(local_files), self._hash_tree)
        self._last_conflict_recovery = str(recovery) if recovery else None
        if recovery:
            self.write_log("✓ Backup locale dei conflitti (non cifrato): " + str(recovery))
        return recovery

    def show(self):
        if not isinstance(self.workspace, FolderWorkspace):
            return old_workspace(self)
        self.clear_content()
        self.section_title("Workspace", "La tua cartella SchoolHub, sincronizzata direttamente con GitHub.")
        card = gui.tk.Frame(self.content, bg=gui.PANEL, highlightbackground=gui.BORDER, highlightthickness=1)
        card.pack(fill="x", pady=15)
        gui.tk.Label(card, text="CARTELLA LOCALE", fg=gui.GREEN, bg=gui.PANEL, font=("Segoe UI", 16, "bold")).pack(pady=(24,8))
        gui.tk.Label(card, text=self.workspace_path, fg=gui.TEXT, bg=gui.PANEL, font=("Consolas", 10), wraplength=540).pack(padx=16,pady=8)
        gui.tk.Label(card, text="I documenti rimangono leggibili. Nessun Vault obbligatorio.\nI file sostituiti vengono conservati nei backup locali.", fg=gui.MUTED, bg=gui.PANEL, justify="center").pack(pady=12)
        for name, command in (("APRI CARTELLA", self.open_workspace), ("SINCRONIZZA", self.start_sync)):
            gui.tk.Button(card, text=name, command=command, bg=gui.BLUE, fg="white", bd=0, padx=20, pady=10).pack(pady=6)
        gui.tk.Label(card, text="Repository dati: " + (self.remote or "non configurato"), fg=gui.MUTED, bg=gui.PANEL, wraplength=540).pack(pady=(12,24))

    def close(self):
        if not isinstance(self.workspace, FolderWorkspace) or self.sync_running or self.workspace_busy:
            return old_close(self)
        self.running = False
        if self.auto_sync_job is not None:
            self.root.after_cancel(self.auto_sync_job)
        self.root.destroy()

    def assert_remote(self):
        if (self.remote or "").lower().rstrip("/").removesuffix(".git") == "https://github.com/matteoporcu08/school-hub":
            raise gui.WorkspaceError("Questo repository contiene il codice dell'app, non i documenti. Seleziona un repository dati privato separato.")
        return old_assert(self)

    cls._ensure_vault_config = normalize
    cls._load_active_vault = load
    cls._load_sync_state = load_state
    cls._save_sync_state = save_state
    cls._persist_sync_tree = persist
    cls._create_conflict_recovery = recover
    cls.show_workspace = show
    cls.close = close
    cls._assert_remote_private = assert_remote
