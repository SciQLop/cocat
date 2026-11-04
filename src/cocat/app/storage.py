from contextlib import suppress
from pathlib import Path


def room_file(update_dir: str, room_id: str) -> Path:
    if room_id in ("", ".", "..") or any(char in room_id for char in ("/", "\\", "\0")):
        raise ValueError(f"Invalid room id: {room_id!r}")
    path = (Path(update_dir) / f"{room_id}.y").resolve()
    if not path.is_relative_to(Path(update_dir).resolve()):
        raise ValueError(f"Invalid room id: {room_id!r}")
    return path


def remove_room_file(update_dir: str, room_id: str) -> None:
    with suppress(FileNotFoundError, PermissionError):
        room_file(update_dir, room_id).unlink()
