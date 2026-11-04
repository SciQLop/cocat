# Self-service rooms: design

Status: draft for review. Date: 2026-11-04.

## Intent

Sharing a catalogue should feel like sharing a Google Doc. Anyone can sign up.
Anyone can create a room. The room owner invites people and decides what they can do.
No admin has to run a CLI command for any of it.

SciQLop stays the main client: that is where people edit catalogues.
A web UI handles everything around the data: accounts, rooms, members, invitations.

## Where we are today

- Accounts are created by an admin with `cocat create-user`. Self-registration is closed:
  the register route needs a superuser.
- A room is just a string. It has no name, no owner, and no metadata.
  Membership is a JSON list of room strings stored on each user row.
- Every new user gets a "personal" room named after the part of their email before the `@`.
  **This is a bug:** `john@lab-a.org` and `john@lab-b.org` share the same room.
- SciQLop's collaborative-catalogs plugin logs in with an email and password,
  lists `/rooms`, and joins `/room/{id}` over a websocket with the auth cookie.
  It also picks the email-prefix room by default.
- The JWT secret is regenerated at every restart. Password-reset tokens are printed to the log.
  Tables are only created when the DB file doesn't exist yet.

## Goals

1. Self-registration, with email verification and password reset.
2. Any user can create, rename and delete their own rooms.
3. The owner invites people, either by email or with a share link, and picks their role.
4. Owners can change roles, remove members, and revoke links. Members can leave.
5. SciQLop shows room names and roles, can create a room, and can accept an invitation.
6. The current SciQLop plugin keeps working while all this lands.
7. Users can log in with ORCID as well as with an email and password.

## Non-goals (for now)

- Editing catalogues in the browser. SciQLop does the editing.
- Shibboleth / eduGAIN (RENATER) login. It needs a SAML-to-OIDC broker and federation
  paperwork, which isn't worth it yet. Because providers are configuration, it can be
  added later through a broker such as EGI Check-in without a redesign.
- Browser-based login in SciQLop. It only becomes necessary once SSO-only users need
  the desktop client (see "Later").
- Per-catalogue permissions. Access is granted per room, like a shared folder.
- Organisations or teams as a separate concept.

## Anti-goals (would make it a failure even if it works)

- A removed member keeps reading or writing the room.
- Any secret (password, reset token, invite token) ends up in a log.
- A schema change that breaks existing users or rooms on the deployed server.
- The web UI becoming a second app with its own login and sessions.

## Design

### Roles

| Role   | Read | Write | Invite / manage members | Rename / delete room |
|--------|------|-------|-------------------------|----------------------|
| owner  | yes  | yes   | yes                     | yes                  |
| editor | yes  | yes   | no                      | no                   |
| viewer | yes  | no    | no                      | no                   |

A room has exactly one owner. The owner can hand ownership to another member.

### Data model (SQLite, via SQLAlchemy)

- `room`: `id` (string, primary key), `name`, `created_at`, `created_by`.
  New rooms get a random id (`uuid4().hex`). That also closes the path-traversal
  concern, because the id becomes the `.y` file name.
- `membership`: `room_id`, `user_id`, `role`. Primary key is the pair.
- `invitation`: `token` (random, stored as a hash), `room_id`, `role`,
  `email` (set for an email invite, empty for a share link), `created_by`,
  `expires_at`, `revoked`, `max_uses`, `uses`.
- The `user.rooms` JSON column goes away once data has been migrated.

**Migration:** each existing room string becomes a `room` row with the same id and name.
That keeps existing `.y` files in place. Every user who listed it becomes an editor.
The owner is the user whose email prefix matches; for other rooms it is the first member,
and an admin can fix it later. Schema changes go through Alembic from now on,
because `create_all` can't change an existing table.

### HTTP API (REST, under `/api`)

- `GET /api/me`, plus the fastapi-users auth routes. Registration becomes public.
- `GET /api/rooms` returns my rooms as `[{id, name, role}]`. `POST /api/rooms` creates one.
- `PATCH /api/rooms/{id}` renames. `DELETE /api/rooms/{id}` deletes (owner only).
- `GET /api/rooms/{id}/members`. Owners can `PATCH` a member's role or `DELETE` a member.
  `DELETE` on yourself means leave.
- `POST /api/rooms/{id}/invitations` creates an email invite or a share link.
  `GET` lists them, `DELETE` revokes.
- `GET /api/invitations/{token}` previews an invitation (room name, role, who invited).
  `POST /api/invitations/{token}/accept` accepts it.
- The old `GET /rooms` and websocket `/room/{id}` stay, so the current plugin keeps working.
  The websocket checks the `membership` table instead of the JSON list.

All permission checks live in one place: a single dependency that takes the user,
the room and the minimum role. Every route calls it.

### Websocket enforcement

- **Viewer:** the server drops document-update messages coming from a viewer's socket.
  It still answers their sync requests, so they receive changes but can't send any.
  The plugin must also disable editing for viewers. Otherwise their local copy
  drifts from the server.
- **Removal, role change, room deletion:** the server closes that user's open sockets
  for the room. That needs a registry of open sockets by `(room, user)`.

### Web UI (NiceGUI)

- Mounted inside the existing FastAPI app with `ui.run_with(app, mount_path="/ui")`.
  Same process, same port, same reverse-proxy prefix.
- It reuses the existing auth cookie, so there is no second login system.
  A NiceGUI page is a FastAPI route, so it can read the cookie and resolve the user.
- Pages:
  - sign up, log in, verify email, reset password
  - my rooms: list, create, rename, delete, leave
  - room page: members and roles, pending invitations, "copy share link", invite by email
  - accept invitation: shows who is inviting you to what, with a sign-up step if needed
  - account: change password, delete account
- The UI calls the same Python service functions as the REST API, not HTTP.
  One implementation, two front ends.

### Login

- Email and password, with email verification, as fastapi-users provides.
- **ORCID** through fastapi-users' OAuth router and `httpx_oauth.clients.openid.OpenID`,
  which needs only a discovery URL, a client id and a secret. The client is registered
  on orcid.org; there is no federation agreement.
- Providers come from configuration, a list of `{name, discovery_url, client_id,
  client_secret}`, so more can be added later without code.
- Accounts are linked by verified email, so password and ORCID logins reach the same account.

### Email

An SMTP sender, configured by environment variables. It sends verification, password-reset
and invitation emails. With no SMTP configured, the server still runs. Verification is
skipped, and invite links are shown in the UI to copy by hand. Small or offline
deployments keep working that way.

### SciQLop plugin changes (in the SciQLop repo)

- The room list shows names and roles from `GET /api/rooms`.
- New actions: "New room", "Share…" (opens the room page in the browser),
  and "Join with link" (paste a link and accept it).
- "Create account" and "Forgot password" open the web UI in the browser.
  The account itself is never handled inside the plugin.
- Read-only mode for viewer rooms.
- Stop deriving a default room from the email prefix. Use the last room opened instead.

## Phases

Each phase can ship on its own, and the current plugin keeps working after each one.

0. **Hardening (prerequisite).**
   - Persistent JWT secret.
   - No tokens in logs.
   - Always create missing tables; adopt Alembic.
   - Room id validation.
   - Rate limiting on login, register and forgot-password. This matters once
     registration is open.
1. **Rooms, memberships and invitations: model and REST API.** Includes the migration
   and the fix for the shared email-prefix room. No UI yet: tests go through HTTP,
   like the current server tests.
2. **NiceGUI spike, then the UI.**
   - The spike checks two things. First, that NiceGUI runs under anycorn,
     the server cocat uses (NiceGUI normally runs under uvicorn). Second, that it
     works behind the `/cocat/` proxy prefix.
   - If anycorn fails, switch `cocat serve` to uvicorn: anycorn isn't load-bearing.
   - Then build the pages above.
3. **Email and ORCID.** SMTP sender, verification, reset, invitation emails.
   ORCID login in the web UI.
4. **SciQLop plugin.** Room names and roles, create, share, join with link, viewer mode.
5. **Enforcement.** Viewer write-blocking on the websocket. Kick on removal or deletion.
6. **Later.** Presence ("who's here", using the CRDT awareness protocol). A read-only
   catalogue view in the browser. Per-user quotas on room count and room size.
   Shibboleth/eduGAIN through a broker, plus browser login for SciQLop
   (RFC 8252 loopback flow, personal access tokens), if users ask for it.

Phases 1 and 2 give the "Google Doc" feel. Phase 5 makes the viewer role trustworthy.
Until phase 5, the UI only offers owner and editor.

## Risks

- **NiceGUI under anycorn:** unproven. The phase 2 spike settles it. Fallback: uvicorn.
- **Viewer enforcement depends on wiredb internals:** whether we can filter messages per
  socket without forking it. If not, wrap the channel class (`YWebSocket`) that cocat
  already owns.
- **Open registration on a lab server invites abuse.** Mitigations: email verification,
  rate limits, quotas, and an optional allow-list of email domains.
- **pycrdt is stuck below 0.13** until wiredb moves.
- **ORCID often hides the email address.** Users can keep their ORCID email private,
  and then there's nothing to link on. Such users confirm an email in the web UI
  after their first ORCID login.
