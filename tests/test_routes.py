from conftest import AppClient, login, make_user


def create_room(app: AppClient, name: str = "Lab") -> dict:
    response = app.client.post("/api/rooms", json={"name": name})
    assert response.status_code == 201
    return response.json()


def invite(app: AppClient, room_id: str) -> str:
    response = app.client.post(f"/api/rooms/{room_id}/invitations", json={})
    assert response.status_code == 201
    return response.json()["token"]


def list_members(app: AppClient, room_id: str) -> list[dict]:
    response = app.client.get(f"/api/rooms/{room_id}/members")
    assert response.status_code == 200
    return response.json()


def join_room(app: AppClient, email: str, token: str) -> None:
    login(app.client, email)
    response = app.client.post("/api/invitations/accept", json={"token": token})
    assert response.status_code == 200


def test_create_list_rename_delete_room(app_client):
    make_user(app_client.db_path, "owner@x.org")
    login(app_client.client, "owner@x.org")

    me = app_client.client.get("/api/me")
    assert me.status_code == 200
    assert me.json()["email"] == "owner@x.org"

    room = create_room(app_client)
    assert room["name"] == "Lab"
    assert room["role"] == "owner"
    assert app_client.client.get("/api/rooms").json() == [room]

    renamed = app_client.client.patch(
        f"/api/rooms/{room['id']}", json={"name": "Renamed"}
    )
    assert renamed.status_code == 200
    assert renamed.json() == {**room, "name": "Renamed"}

    assert app_client.client.delete(f"/api/rooms/{room['id']}").status_code == 204
    assert app_client.client.get("/api/rooms").json() == []


def test_invite_link_flow(app_client):
    make_user(app_client.db_path, "owner@x.org")
    make_user(app_client.db_path, "guest@x.org")
    login(app_client.client, "owner@x.org")
    room = create_room(app_client)
    token = invite(app_client, room["id"])

    app_client.client.cookies.clear()
    preview = app_client.client.post("/api/invitations/preview", json={"token": token})
    assert preview.status_code == 200
    assert preview.json()["room_id"] == room["id"]
    assert preview.json()["room_name"] == "Lab"
    assert preview.json()["role"] == "editor"
    assert preview.json()["inviter_email"] == "owner@x.org"
    assert preview.json()["expires_at"]

    join_room(app_client, "guest@x.org", token)

    assert app_client.client.get("/api/rooms").json() == [
        {"id": room["id"], "name": "Lab", "role": "editor"}
    ]


def test_member_management(app_client):
    make_user(app_client.db_path, "owner@x.org")
    make_user(app_client.db_path, "editor@x.org")
    login(app_client.client, "owner@x.org")
    room = create_room(app_client)
    token = invite(app_client, room["id"])
    join_room(app_client, "editor@x.org", token)

    login(app_client.client, "owner@x.org")
    emails = {
        member["email"]: member for member in list_members(app_client, room["id"])
    }
    assert set(emails) == {"owner@x.org", "editor@x.org"}
    owner_id = emails["owner@x.org"]["user_id"]
    editor_id = emails["editor@x.org"]["user_id"]
    assert emails["owner@x.org"]["role"] == "owner"

    member_url = f"/api/rooms/{room['id']}/members/{editor_id}"
    assert (
        app_client.client.patch(member_url, json={"role": "editor"}).status_code == 204
    )
    owner_url = f"/api/rooms/{room['id']}/owner"
    assert (
        app_client.client.post(owner_url, json={"user_id": editor_id}).status_code
        == 204
    )

    login(app_client.client, "editor@x.org")
    assert (
        app_client.client.delete(
            f"/api/rooms/{room['id']}/members/{owner_id}"
        ).status_code
        == 204
    )

    invitations = app_client.client.get(f"/api/rooms/{room['id']}/invitations")
    assert invitations.status_code == 200
    assert [invitation["role"] for invitation in invitations.json()] == ["editor"]
    invitation_id = invitations.json()[0]["id"]
    revoke_url = f"/api/rooms/{room['id']}/invitations/{invitation_id}"
    assert app_client.client.delete(revoke_url).status_code == 204
    assert app_client.client.get(f"/api/rooms/{room['id']}/invitations").json() == []


def test_errors_map_to_status(app_client):
    for email in ("owner@x.org", "editor@x.org", "stranger@x.org"):
        make_user(app_client.db_path, email)
    login(app_client.client, "owner@x.org")
    room = create_room(app_client)
    token = invite(app_client, room["id"])
    join_room(app_client, "editor@x.org", token)

    login(app_client.client, "editor@x.org")
    renamed = app_client.client.patch(f"/api/rooms/{room['id']}", json={"name": "X"})
    assert renamed.status_code == 403

    login(app_client.client, "stranger@x.org")
    members_url = f"/api/rooms/{room['id']}/members"
    assert app_client.client.get(members_url).status_code == 404
    assert app_client.client.get("/api/rooms/missing/members").status_code == 404

    login(app_client.client, "owner@x.org")
    owner_id = app_client.client.get("/api/me").json()["id"]
    leaving = app_client.client.delete(f"{members_url}/{owner_id}")
    assert leaving.status_code == 409


def test_viewer_role_not_assignable_yet(app_client):
    make_user(app_client.db_path, "owner@x.org")
    make_user(app_client.db_path, "editor@x.org")
    login(app_client.client, "owner@x.org")
    room = create_room(app_client)
    token = invite(app_client, room["id"])
    join_room(app_client, "editor@x.org", token)

    login(app_client.client, "owner@x.org")
    editor_id = next(
        member["user_id"]
        for member in list_members(app_client, room["id"])
        if member["email"] == "editor@x.org"
    )
    member_url = f"/api/rooms/{room['id']}/members/{editor_id}"

    assert (
        app_client.client.patch(member_url, json={"role": "viewer"}).status_code == 422
    )


def test_invitation_token_never_in_a_path(app_client):
    paths = app_client.client.get("/openapi.json").json()["paths"]

    assert paths
    assert all("{token}" not in path for path in paths)
    assert all("token" not in path for path in paths if path.startswith("/api"))
