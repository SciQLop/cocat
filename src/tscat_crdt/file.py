from contextlib import AsyncExitStack
from pathlib import Path
from types import TracebackType

import anyio
from anyio import CancelScope, TASK_STATUS_IGNORED, create_task_group, open_file
from anyio.abc import TaskStatus
from pycrdt import Decoder, Doc, write_message


class File:
    def __init__(self, path: Path | str, doc: Doc) -> None:
        self._path = anyio.Path(path)
        self._doc = doc

    async def __aenter__(self) -> "File":
        async with AsyncExitStack() as stack:
            if await self._path.exists():
                updates = await self._path.read_bytes()
                decoder = Decoder(updates)
                while True:
                    update = decoder.read_message()
                    if not update:
                        break
                    self._doc.apply_update(update)
            self._file = await stack.enter_async_context(await open_file(self._path, mode="wb", buffering=0))
            self._task_group = await stack.enter_async_context(create_task_group())
            await self._task_group.start(self._write)
            self._stack = stack.pop_all()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> bool | None:
        self._task_group.cancel_scope.cancel()
        return await self._stack.__aexit__(exc_type, exc_val, exc_tb)

    async def _write(self, *, task_status: TaskStatus[None] = TASK_STATUS_IGNORED):
        async with self._doc.events() as events:
            task_status.started()
            async for event in events:
                message = write_message(event.update)
                with CancelScope(shield=True):
                    await self._file.write(message)
