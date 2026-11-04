import os
import secrets
from pathlib import Path


def load_secret(path: Path) -> str:
    if env_secret := os.environ.get("COCAT_SECRET"):
        return env_secret

    try:
        _create_secret(path)
    except FileExistsError:
        pass
    return _read_secret(path)


def _create_secret(path: Path) -> None:
    tmp_path = path.with_name(f"{path.name}.{secrets.token_hex(8)}.tmp")
    fd = os.open(tmp_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        with os.fdopen(fd, "w") as file:
            file.write(secrets.token_urlsafe(32))
        os.link(tmp_path, path)
    finally:
        os.unlink(tmp_path)


def _read_secret(path: Path) -> str:
    secret = path.read_text().strip()
    if not secret:
        raise RuntimeError(f"Secret file {path} is empty")
    return secret
