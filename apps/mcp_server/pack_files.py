"""Process-shared pack locks and atomic replacement of private draft files."""
from contextlib import contextmanager
import errno
import os
from pathlib import Path
import stat
from tempfile import NamedTemporaryFile
from threading import local
from time import monotonic, sleep

from .errors import MCPValidationError


PACK_LOCK_TIMEOUT = 5
_HELD = local()


@contextmanager
def pack_file_lock(root: Path, pack: str):
    """Keep the lock outside deletable packs; never unlink a live lock inode.

    Tool aliases reenter on the same thread. Independent threads/processes
    still use separate OS lock handles, including separate ASGI workers.
    """
    directory = root / ".mcp-locks"
    if directory.is_symlink():
        raise MCPValidationError("Pack lock directory must not be a symlink.")
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock_path = directory / f"{pack}.lock"
    if lock_path.is_symlink():
        raise MCPValidationError("Pack locks must be ordinary files.")
    identity = (os.getpid(), str(lock_path.resolve()))
    held = getattr(_HELD, "keys", set())
    if identity in held:
        yield
        return
    descriptor = os.open(lock_path, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode) or lock_path.is_symlink():
            raise MCPValidationError("Pack locks must be ordinary files.")
        if os.name == "nt":
            import msvcrt
            if os.fstat(descriptor).st_size == 0:
                os.write(descriptor, b"\0")

            def acquire():
                os.lseek(descriptor, 0, os.SEEK_SET)
                msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)

            def release():
                os.lseek(descriptor, 0, os.SEEK_SET)
                msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            def acquire():
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)

            def release():
                fcntl.flock(descriptor, fcntl.LOCK_UN)

        deadline = monotonic() + PACK_LOCK_TIMEOUT
        while True:
            try:
                acquire()
                break
            except OSError as error:
                if error.errno not in {errno.EAGAIN, errno.EACCES, errno.EDEADLK}:
                    raise
                if monotonic() >= deadline:
                    raise MCPValidationError(
                        "This content pack is busy. Retry after the current operation finishes.",
                        code="pack_busy", retryable=True,
                    ) from None
                sleep(0.02)
        _HELD.keys = held | {identity}
        try:
            yield
        finally:
            _HELD.keys = held
            release()
    finally:
        os.close(descriptor)


def atomic_write_text(path: Path, content: str):
    """A failed replacement leaves the old file intact and no temporary draft."""
    if path.is_symlink():
        raise MCPValidationError("Pack content files cannot be symlinks.")
    mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o600
    temporary = None
    try:
        with NamedTemporaryFile(mode="w", encoding="utf-8", newline="", dir=path.parent,
                                prefix=".pack-write-", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
            os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
