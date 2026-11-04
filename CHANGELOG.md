# Version history

## 0.12.0

- Back up `users.db` before upgrading.
- Migrations run automatically, at server start and from the CLI.
- Email-prefix rooms keep working for existing users.
- Rooms that were shared by a prefix collision (`john@a.org` and `john@b.org` both in
  room `john`) are listed at upgrade time, and can be fixed with
  `cocat set-room-owner`.
- New users get a personal room. Older SciQLop plugins cannot find it until the
  SciQLop collaborative-catalogs plugin is updated.
- Rate-limit login and forgot-password to 10 requests per minute and per client. Behind
  a reverse proxy, set `COCAT_TRUSTED_PROXIES` to the number of proxies so that clients
  are told apart.
- Keep the JWT signing secret across restarts: it is stored in `<db-path>.secret`, or
  supplied with `COCAT_SECRET`.
- Breaking: `Session.connect()` no longer takes a `room_id`, call
  `set_config(room_id=...)` before `log_in`.

## 0.11.0

- Improve credential storing.

## 0.10.0

- Stop server gracefully.
- Use `keyring` for storing passwords.
- Automatically connect users to a room which ID is based on their email.
- Add `GET /room/{room_id}/users` for all users allowed in a room.
- Add `GET /rooms` for current user allowed rooms.

## 0.9.0

- Don't export from `cocat.cli`, because it has features that need the `server` extra.

## 0.8.0

- Add user room permissions (SQLite database is incompatible).
- Add reverse proxy prefix.

## 0.7.0

- Use `rich`'s pretty representations.
- Make `Catalogue` and `Event` iterable.
- Remove `synchronize` and `connect` from user API.
- Make some class methods private.

## 0.6.0

- Use `wiredb`'s v0.7 synchronous clients in user API.

## 0.5.0

- Refactor user API.
- Add support for VOTable import/export.

## 0.4.2

- Add `range` getter/setter and `on_change_range`.

## 0.4.1

- Add support for dynamic catalogues.
- Don't require a transaction for read-only operations.

## 0.4.0

- Add user authentication.
- Remove `client` extra-dependency.

## 0.3.1

- Add `wiredb` to dependencies.

## 0.3.0

- Add high-level user API and CLI.
- Remove models from public API.
- Disable event callback when same origin.

## 0.2.1

- Bump WireDB v0.2.0.

## 0.2.0

- Use file wire from [WireDB](https://github.com/davidbrochart/wiredb).

## 0.1.0

- Initial release.
