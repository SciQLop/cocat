import os
import secrets
from pathlib import Path


def load_secret(path: Path) -> str:
    if env_secret := os.environ.get("COCAT_SECRET"):
        return env_secret

    _ensure_secret(path)
    return _read_secret(path)


def _ensure_secret(path: Path) -> None:
    try:
        _create_secret(path)
    except FileExistsError:
        pass
    except OSError as error:
        raise _secret_error(path, error) from error


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
    try:
        secret = path.read_text().strip()
    except OSError as error:
        raise _secret_error(path, error) from error
    if not secret:
        raise RuntimeError(f"Secret file {path} is empty")
    return secret


def _secret_error(path: Path, error: OSError) -> RuntimeError:
    return RuntimeError(
        f"Cannot access the secret file {path}: {error}. "
        "Fix the file or directory permissions, or set COCAT_SECRET to supply the "
        "secret another way."
    )
