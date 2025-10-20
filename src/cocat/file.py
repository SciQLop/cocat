from contextlib import AsyncExitStack
from pathlib import Path
from types import TracebackType

import anyio
from anyio import CancelScope, TASK_STATUS_IGNORED, create_task_group, open_file, sleep
from anyio.abc import TaskStatus
from pycrdt import Decoder, Doc, write_message


class File:
    def __init__(
        self,
        path: Path | str,
        doc: Doc,
        *,
        write_delay: float = 0,
    ) -> None:
        self._path = anyio.Path(path)
        self._doc = doc
        self._write_delay = write_delay
        self._messages: list[bytes] = []
        self._write_cancel_scope: CancelScope | None = None

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
            await self._task_group.start(self._get_updates)
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

    async def _get_updates(self, *, task_status: TaskStatus[None] = TASK_STATUS_IGNORED):
        async with self._doc.events() as events:
            task_status.started()
            async for event in events:
                if self._write_cancel_scope is not None:
                    self._write_cancel_scope.cancel()
                message = write_message(event.update)
                self._messages.append(message)
                await self._task_group.start(self._write_updates)

    async def _write_updates(self, *, task_status: TaskStatus[None] = TASK_STATUS_IGNORED):
        with CancelScope() as self._write_cancel_scope:
            task_status.started()
            await sleep(self._write_delay)
            data = b"".join(self._messages)
            self._messages.clear()
            self._write_cancel_scope = None
            with CancelScope(shield=True):
                await self._file.write(data)
