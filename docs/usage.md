## Quickstart

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
