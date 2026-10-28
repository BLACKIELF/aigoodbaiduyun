"""Private, atomic job records and process locks; no credentials in records."""

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import tempfile

try:
    import fcntl
except ImportError:
    fcntl = None


def state_root() -> Path:
    root = Path(os.environ.get("AIGOODBAIDUYUN_STATE_DIR", "~/.local/state/aigoodbaiduyun")).expanduser().resolve()
    root.mkdir(parents=True, mode=0o700, exist_ok=True)
    root.chmod(0o700)
    return root


def atomic_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix=".writing-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(data, stream, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def lock(path: Path, blocking: bool = False):
    if fcntl is None:
        raise ValueError("Persistent transfer locks currently require macOS or Linux.")
    path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
    except BlockingIOError:
        os.close(fd)
        return None
    return fd


def unlock(fd) -> None:
    if fd is not None:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


@contextmanager
def registry_lock(root: Path):
    fd = lock(root / "registry.lock", blocking=True)
    try:
        yield
    finally:
        unlock(fd)


def fingerprint(source: Path) -> str:
    """Detect source replacement/edits without reading GBs on every resume."""
    paths = [source] if source.is_file() else sorted(source.rglob("*"))
    value = hashlib.sha256()
    for item in paths:
        info = item.stat()
        value.update(json.dumps([str(item.relative_to(source.parent)), info.st_size, info.st_mtime_ns, info.st_mode]).encode())
    return value.hexdigest()
