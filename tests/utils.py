import subprocess
from dataclasses import dataclass


@dataclass
class Credentials:
    username: str
    password: str


WALLET: dict[str, Credentials] = {}


def create_user(email: str, password: str, db_path: str) -> None:
    command = [
        "cocat",
        "create-user",
        "--email",
        email,
        "--password",
        password,
        "--db_path",
        db_path,
    ]
    subprocess.check_call(command)


def add_user_to_room(email: str, room_id: str, db_path: str) -> None:
    command = [
        "cocat",
        "add-user-to-room",
        "--email",
        email,
        "--room_id",
        room_id,
        "--db_path",
        db_path,
    ]
    subprocess.check_call(command)


def get_credential(service_name: str, username: str | None) -> Credentials | None:
    return WALLET.get(service_name)


def set_password(service_name: str, username: str, password: str) -> None:
    WALLET[service_name] = Credentials(username, password)
