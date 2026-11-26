"""Original SchoolHub UI adapter; disk object caching is opt-in."""
import os
import re
import subprocess
import tempfile
import threading
from git_cache import SessionGitCache, CacheError
from pathlib import Path

ROOT = Path(__file__).resolve().parent
HEX = re.compile(r"[0-9a-f]{64}")
HEAD = re.compile(r"[0-9a-f]{40}|[0-9a-f]{64}")

def native_scan(root, binary, error_type=RuntimeError):
    import json
    root = Path(root)
    try:
        workers = max(1, min(8, int(os.environ.get("SCHOOLHUB_SCAN_WORKERS", "4"))))
        result = subprocess.run(
            [str(binary), "scan", os.path.abspath(root), str(workers)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        if result.returncode:
            raise error_type(result.stderr.decode("utf-8", "replace").strip() or "Scansione Rust fallita")
        files = json.loads(result.stdout)
        if not isinstance(files, dict) or any(
            not isinstance(k, str) or not isinstance(v, str) or not HEX.fullmatch(v)
            for k, v in files.items()
        ):
            raise error_type("Risposta non valida del motore Rust")
        return files
    except (OSError, ValueError) as exc:
        raise error_type(f"Motore Rust: {exc}") from exc

class RemoteIndex:
    """One immutable-by-copy manifest per app session, keyed by remote, branch, identity and commit."""
    def __init__(self):
        self._lock = threading.Lock()
        self._entry = None

    def get(self, key, head):
        if not head:
            return None
        with self._lock:
            if self._entry and self._entry[:2] == (key, head):
                return dict(self._entry[2])
        return None

    def put(self, key, head, files):
        if HEAD.fullmatch(head or ""):
            with self._lock:
                self._entry = (key, head, dict(files))

def install(module, binary):
    """Apply narrowly scoped changes to pinned SchoolHub 2.6.7 before creating the UI."""
    if module.APP_VERSION != "2.6.7":
        raise RuntimeError("Versione dell'interfaccia non supportata")
    binary = Path(binary).resolve()
    if not binary.is_file():
        raise FileNotFoundError(f"Compilare prima il motore Rust: {binary}")
    cls = module.SchoolHub
    if getattr(cls, "_rust_acceleration_installed", False):
        raise RuntimeError("Adattatore già installato")
    original_clone = cls._clone_remote
    original_sync = cls.sync_worker
    index = RemoteIndex()
    git_cache = SessionGitCache.from_environment()

    def scan(root):
        return native_scan(root, binary, module.WorkspaceError)

    def clone_selected(self, destination):
        # Directly clone the configured branch, not the default branch followed
        # by a second fetch. Keep upstream recovery for empty repositories.
        branch = str(self.branch or module.DEFAULT_BRANCH).strip() or module.DEFAULT_BRANCH
        remote = self._git_remote_for_auth()
        parent = os.path.dirname(os.path.abspath(destination))
        os.makedirs(parent, exist_ok=True)
        if os.path.lexists(destination):
            return original_clone(self, destination)
        if git_cache is not None:
            try:
                git_cache.checkout(self.git, remote, branch, destination, getattr(self, "github_user", ""))
                return
            except CacheError:
                # Never use the cached old commit after a failed fetch.
                if os.path.lexists(destination):
                    raise module.WorkspaceError("Impossibile rimuovere un checkout temporaneo incompleto")
                self.write_log("Cache Git non utilizzabile: ripiego sul clone diretto.")
        code, out, err = self.git(
            ["clone", "--depth", "1", "--no-tags", "--single-branch",
             "--branch", branch, "--", remote, destination], cwd=parent)
        if code == 0:
            branch_code, checked_out, _ = self.git(["symbolic-ref", "--short", "HEAD"], cwd=destination)
            if branch_code != 0 or checked_out != branch:
                raise module.WorkspaceError("Il riferimento selezionato non è un branch Git valido")
            self.git(["config", "credential.useHttpPath", "true"], cwd=destination)
            return
        # Git normally removes failed clones itself. Never delete an unexpected
        # nonempty directory or bypass an authentication/network failure.
        if os.path.isdir(destination) and not os.path.islink(destination) and not os.listdir(destination):
            os.rmdir(destination)
        if os.path.lexists(destination):
            raise module.WorkspaceError(err or out or "Clone non riuscito")
        detail = (out + "\n" + err).lower()
        if "remote branch" in detail and ("not found" in detail or "not exist" in detail):
            return original_clone(self, destination)
        raise module.WorkspaceError(err or out or "Clone non riuscito")

    def key_for(self):
        return (self.remote, str(self.branch or module.DEFAULT_BRANCH), getattr(self, "github_user", ""))

    def remote_head(self):
        # Match upstream's permitted remotes, including local fixtures in development.
        if not self.remote:
            raise module.WorkspaceError("Repository non configurato")
        is_local = not getattr(module.sys, "frozen", False) and os.path.exists(self.remote)
        if not is_local and not self._github_repo_parts():
            raise module.WorkspaceError("Repository GitHub HTTPS richiesto")
        head = self._current_remote_data_head()
        if head and not HEAD.fullmatch(head):
            raise module.WorkspaceError("Commit remoto non valido")
        return head

    def remote_manifest(self):
        key = key_for(self)
        head = remote_head(self)
        if key_for(self) != key:
            raise module.WorkspaceError("Configurazione GitHub modificata durante il controllo")
        hit = index.get(key, head)
        if hit is not None:
            return hit
        self._assert_remote_private()
        with tempfile.TemporaryDirectory(prefix="schoolhub-rust-status-") as temp:
            checkout = os.path.join(temp, "repo")
            self._clone_remote(checkout)
            files = scan(checkout)
            code, actual, _ = self.git(["rev-parse", "HEAD"], cwd=checkout)
            # Do not cache an unborn branch or a snapshot of a different commit.
            if key_for(self) != key:
                raise module.WorkspaceError("Configurazione GitHub modificata durante il controllo")
            if code == 0 and actual == head:
                index.put(key, actual, files)
            return files

    def get_status(self):
        if not self.git_enabled or not self.remote:
            return None, None, "GitHub non configurato: SchoolHub funziona in locale."
        if not self.workspace.exists:
            return None, None, "Workspace cifrato non trovato."
        if not self.workspace.is_unlocked:
            return None, None, "Workspace bloccato: sbloccalo per controllare lo stato."
        try:
            local = scan(self.workspace.get_unlocked_path())
            remote = remote_manifest(self)
            self._last_status_local_fingerprint = self._tree_fingerprint(local)
            self._last_status_remote_fingerprint = self._tree_fingerprint(remote)
            state = self._load_sync_state()
            base = state.get("files", {}) if state is not None else {}
            if local == remote:
                self.last_conflicts = []
                if state is None or base != remote:
                    self._save_sync_state(remote)
                return 0, 0, False
            outgoing, incoming, conflicts = self._classify_changes(base, local, remote)
            self.last_conflicts = conflicts
            return len(outgoing) + len(conflicts), len(incoming) + len(conflicts), bool(outgoing or incoming or conflicts)
        except Exception as exc:
            return None, None, str(exc)

    def remote_fingerprint(self):
        if not self.remote:
            return ""
        return self._tree_fingerprint(remote_manifest(self))

    def sync_worker(self, password=None):
        # Fast no-op only for a previously verified manifest at the current
        # remote commit. Any uncertainty/change takes the complete upstream path.
        try:
            if self.workspace.is_unlocked and self.git_enabled and self.remote:
                key = key_for(self)
                head = remote_head(self)
                cached = index.get(key, head)
                if cached is not None and scan(self.workspace.get_unlocked_path()) == cached:
                    if remote_head(self) == head and key_for(self) == key and scan(self.workspace.get_unlocked_path()) == cached:
                        state = self._load_sync_state()
                        if state is None or state.get("files") != cached:
                            self._save_sync_state(cached)
                        self.last_conflicts = []
                        self.write_log("✓ Nessuna modifica: sincronizzazione rapida (commit e SHA-256 verificati).")
                        self.progress_update(100, "Completato", "Tutto aggiornato")
                        self.finish_status("SINCRONIZZATO", module.GREEN, "Tutto aggiornato")
                        threading.Thread(target=self._publish_device_status_quiet, args=("updated", 0, 0), daemon=True).start()
                        self.sync_running = False
                        self.close_progress()
                        if self.running:
                            self.root.after(0, self.refresh_status)
                        return
        except Exception:
            # Do not report a successful sync when a validation failed.
            pass
        return original_sync(self, password)

    cls._hash_tree = staticmethod(scan)
    cls._clone_remote = clone_selected
    cls.get_status = get_status
    cls._remote_content_fingerprint = remote_fingerprint
    cls.sync_worker = sync_worker
    cls._rust_acceleration_installed = True
