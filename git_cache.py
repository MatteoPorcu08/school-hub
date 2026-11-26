"""Opt-in session cache: incremental Git fetch plus shared LFS objects.

Contains plaintext Git objects. Only enable on a directory the user explicitly
selects on an encrypted volume. No remote writes, no force push, no stale fallback.
"""
import atexit
import hashlib
import json
import os
import stat
import shutil
import tempfile
import threading
from pathlib import Path

def remove_tree(path):
    def retry(func, name, exc_info):
        os.chmod(name, stat.S_IREAD | stat.S_IWRITE | stat.S_IEXEC)
        func(name)
    if os.path.isdir(path) and not os.path.islink(path):
        shutil.rmtree(path, onerror=retry)

class CacheError(RuntimeError):
    pass

class SessionGitCache:
    def __init__(self, base):
        base = Path(base).resolve(strict=True)
        if not base.is_dir():
            raise ValueError("Cache Git: selezionare una cartella su volume cifrato")
        self.root = Path(tempfile.mkdtemp(prefix="schoolhub-git-session-", dir=base))
        self._lock = threading.Lock()
        atexit.register(self.close)

    @classmethod
    def from_environment(cls):
        base = os.environ.get("SCHOOLHUB_GIT_CACHE_DIR", "").strip()
        return cls(base) if base else None

    def close(self):
        # Best effort: abrupt termination may leave this directory behind.
        with self._lock:
            try:
                remove_tree(self.root)
            except OSError:
                pass

    @staticmethod
    def _run(git, args, cwd, timeout=180):
        code, out, err = git(args, cwd=str(cwd), timeout=timeout)
        if code != 0:
            # Do not expose a URL or credentials through an error message.
            raise CacheError(f"Git {args[0]} non riuscito (codice {code})")
        return out.strip()

    def checkout(self, git, remote, branch, destination, account=""):
        destination = Path(destination)
        if os.path.lexists(destination):
            raise CacheError("Checkout di destinazione già esistente")
        key = hashlib.sha256(json.dumps([remote, branch, account]).encode("utf-8")).hexdigest()
        cache = self.root / key
        try:
            with self._lock:
                self._run(git, ["check-ref-format", f"refs/heads/{branch}"], self.root)
                if not cache.is_dir():
                    cache.mkdir()
                    self._run(git, ["init", "--bare"], cache)
                    self._run(git, ["config", "gc.auto", "0"], cache)
                    self._run(git, ["config", "maintenance.auto", "false"], cache)
                # Ref update is local to the cache. Fetch must succeed; the old
                # ref is never used after an unsuccessful network operation.
                self._run(git, ["fetch", "--depth", "1", "--no-tags", "--no-auto-gc",
                                "--", remote, f"+refs/heads/{branch}:refs/heads/{branch}"], cache)
                head = self._run(git, ["rev-parse", f"refs/heads/{branch}"], cache)
                # Local clone uses hardlinks when supported, otherwise copies;
                # no alternates, so the resulting repository is self-contained.
                self._run(git, ["clone", "--no-checkout", "--no-tags", "--single-branch",
                                "--branch", branch, "--", str(cache), str(destination)],
                          destination.parent)
                self._run(git, ["remote", "set-url", "origin", remote], destination)
                self._run(git, ["config", "credential.useHttpPath", "true"], destination)
                self._run(git, ["config", "lfs.storage", str(cache / "lfs")], destination)
                # Set real origin before any LFS smudge or checkout.
                self._run(git, ["checkout", "-f", branch], destination)
                actual = self._run(git, ["rev-parse", "HEAD"], destination)
                current_branch = self._run(git, ["symbolic-ref", "--short", "HEAD"], destination)
                if actual != head or current_branch != branch:
                    raise CacheError("Verifica checkout non riuscita")
        except Exception as exc:
            # We only create this destination after checking it did not exist.
            # Do not follow symlinks or discard any other directories.
            if destination.is_dir() and not destination.is_symlink():
                try:
                    remove_tree(destination)
                except OSError:
                    pass
            raise CacheError("Checkout incrementale non riuscito") from exc
