## Quickstart

### User API

Cocat consists of the following objects:

- [DB][cocat.DB]: the object representing the database, which allows creating events and catalogues, modifying them and being notified of the changes.
- [Event][cocat.Event]: an object representing an event, which allows modifying its properties and being notified of the changes.
- [Catalogue][cocat.Catalogue]: an object representing a catalogue, which allows modifying its properties and being notified of the changes. A catalogue contains a set of events, but events are in general independent of catalogues.

User A on one machine could start creating catalogues and events:

```py
from cocat import DB

db0 = DB()
event0 = db0.create_event(
    start="2025-01-31",
    stop="2026-01-31",
    author="John",
    attributes={"foo": "bar"},
)
catalogue0 = db0.create_catalogue(
    name="cat0",
    author="Paul",
    attributes={"baz": 3}
)
catalogue0.add_events(event0)
event0.stop = "2026-01-30"
```

Up to now their data is local, but they could share the database using a web server. Here is how such a web server can be set up:

```py
from anyio import run, sleep_forever
from wiredb import bind

async def main():
    async with bind("websocket", host="localhost", port=8000):
        await sleep_forever()

run(main)
```

And here is how user A can connect to this server:

```py
from anyio import run, sleep_forever
from wiredb import connect

async def main():
    async with connect("websocket", doc=db0.doc, host="http://localhost", port=8000):
        await sleep_forever()

run(main)
```

User B on another machine could connect their database to user A's and synchronize their catalogues and events:

```py
from anyio import run, sleep_forever
from cocat import DB
from wiredb import connect

async def main():
    db1 = DB()
    async with connect("websocket", doc=db1.doc, host="http://localhost", port=8000):
        print(db1.catalogues)
        print(db1.events)

run(main)
```

### High-level API

A higher-level API is also provided, which is more suitable for an interactive workflow that
can be done in Jupyter or a Python REPL. Notice the top-level `await`s, that work out-of-the-box
in Jupyter, but not in a classic Python REPL. Instead, an async Python REPL would have to be used (`python -m asyncio`).

```py
from cocat import (
    create_catalogue,
    create_event,
    load_catalogue,
    load_event,
    save_catalogue,
    save_event,
    set_config,
)

set_config(host="http://localhost", port=8000, file_path="updates.y")
log_in("paul@example.com", "my_password")

catalogue0 = create_catalogue(name="cat0", author="Paul")
await save_catalogue(catalogue0)

catalogue1 = await load_catalogue("56c935a2-0109-49c0-b91d-dd5b2de8feef")

event0 = create_event(
    start="2025-01-31",
    stop="2026-01-31",
    author="John",
)
await save_event(event0)

event1 = await load_event("497393db-7dd6-4d7b-9ff1-8a8155bfed54")
```

### CLI

A command-line interface allows to launch a server and manage users.
Because the server can only be accessed by authenticated users, one has to create users first:

```py
cocat create-user --email "paul@example.com" --password "my_password" --db-path "users.db"
```

Then the server can be launched:

```bash
cocat serve --host "127.0.0.1" --port 8000 --directory "update_dir" --db-path "users.db"
```

The server will listen to `http://127.0.0.1:8000` and the updates will be stored
in the `update_dir` directory, with one file per room. Rooms are identified with
the path a client connects to. For instance, if a client connects to
`http://127.0.0.1:8000/my_room`, then the room ID is `my_room` and the corresponding
file path is `update_dir/my_room.y`.
