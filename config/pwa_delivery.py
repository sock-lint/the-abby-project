"""Nonsecret fingerprints of the stable worker scripts in this runtime image."""
import hashlib
import os
from pathlib import Path
import stat


PWA_REQUIRED_SCRIPTS = ("sw.js", "push-sw.js", "privacy-sw.js")
MAX_SCRIPT_BYTES = 2 * 1024 * 1024


def pwa_script_manifest(base_dir):
    """Attest all three actual runtime files, or return no partial proof.

    The public validation image intentionally differs from Coolify's private
    production build. Release checks therefore use these runtime bytes, never
    the validation build's hashes. Reads stay local and bounded; filenames,
    absolute paths and read errors are not disclosed by /health.
    """
    manifest = {}
    for name in PWA_REQUIRED_SCRIPTS:
        path = Path(base_dir) / "frontend_dist" / name
        try:
            flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
            with os.fdopen(os.open(path, flags), "rb") as stream:
                before = os.fstat(stream.fileno())
                if not stat.S_ISREG(before.st_mode) or not 0 < before.st_size <= MAX_SCRIPT_BYTES:
                    return None
                content = stream.read(MAX_SCRIPT_BYTES + 1)
                after = os.fstat(stream.fileno())
            if (len(content) != before.st_size or
                    (before.st_ino, before.st_size, before.st_mtime_ns) !=
                    (after.st_ino, after.st_size, after.st_mtime_ns)):
                return None
        except OSError:
            return None
        manifest["/" + name] = {"sha256": hashlib.sha256(content).hexdigest(), "bytes": len(content)}
    return manifest
