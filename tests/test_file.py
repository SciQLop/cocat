import pytest

from anyio import sleep
from pycrdt import Doc, Text
from wiredb import connect


pytestmark = pytest.mark.anyio

async def test_file_without_write_delay(tmp_path):
    update_path = tmp_path / "updates.y"
    doc = Doc()
    async with connect("file", doc=doc, path=update_path, write_delay=0):
        text = doc.get("text", type=Text)
        text += "Hello"
        await sleep(0.1)
        assert b"Hello" in update_path.read_bytes()


async def test_file_with_write_delay(tmp_path):
    update_path = tmp_path / "updates.y"
    doc = Doc()
    async with connect("file", doc=doc, path=update_path, write_delay=0.1):
        text = doc.get("text", type=Text)
        for i in range(20):
            text += "."
            await sleep(0.01)
        header = b"0.0.1\x00"
        assert update_path.read_bytes() == header
        await sleep(0.2)
        data = update_path.read_bytes()
        assert data.startswith(header)
        assert data != header
