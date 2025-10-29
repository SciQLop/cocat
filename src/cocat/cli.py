from functools import partial
from pathlib import Path
from typing import Any

from anyio import get_cancelled_exc_class, run, sleep_forever
from anyio.abc import TaskStatus
from cyclopts import App
from wiredb import Room, bind, connect


app = App()

@app.command
def serve(
    *,
    host: str = "localhost",
    port: int = 8000,
    directory: str = "",
):
    run(_serve, host, port, directory)


class StoredRoom(Room):
    def __init__(self, directory: str, *args, **kwargs):
        self._directory = directory
        super().__init__(*args, **kwargs)

    async def run(self, *args: Any, **kwargs: Any):
        if self._directory is not None:
            await self.task_group.start(self.connect_to_file)
        await super().run(*args, **kwargs)

    async def connect_to_file(self, *, task_status: TaskStatus[None]) -> None:
        async with connect("file", doc=self.doc, path=f"{Path(self._directory) / self.id.lstrip('/')}.y"):
            task_status.started()
            await sleep_forever()


async def _serve(host: str, port: int, directory: str):
    try:
        async with bind("websocket", room_factory=partial(StoredRoom, directory), host=host, port=port):
            await sleep_forever()
    except get_cancelled_exc_class():
        pass


def main():
    app()
