from pathlib import Path

import pytest
from conftest import (
    AppClient,
    assert_websocket_refused,
    login,
    make_user,
    ws_headers,
)
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from cocat.app.app import CocatApp
from cocat.app.storage import room_file


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
    listed = {
        listed["id"]: listed for listed in app_client.client.get("/api/rooms").json()
    }
    assert len(listed) == 2
    assert listed[room["id"]] == room

    renamed = app_client.client.patch(
        f"/api/rooms/{room['id']}", json={"name": "Renamed"}
    )
    assert renamed.status_code == 200
    assert renamed.json() == {**room, "name": "Renamed"}

    assert app_client.client.delete(f"/api/rooms/{room['id']}").status_code == 204
    assert [
        listed["name"] for listed in app_client.client.get("/api/rooms").json()
    ] == ["Personal"]


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

    rooms = {
        listed["id"]: listed for listed in app_client.client.get("/api/rooms").json()
    }
    assert len(rooms) == 2
    assert rooms[room["id"]] == {"id": room["id"], "name": "Lab", "role": "editor"}


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


def test_new_user_gets_personal_room_not_email_prefix(app_client):
    make_user(app_client.db_path, "john@a.org")
    make_user(app_client.db_path, "john@b.org")

    login(app_client.client, "john@a.org")
    rooms_a = app_client.client.get("/api/rooms").json()
    login(app_client.client, "john@b.org")
    rooms_b = app_client.client.get("/api/rooms").json()

    assert len(rooms_a) == 1
    assert len(rooms_b) == 1
    assert rooms_a[0]["name"] == "Personal"
    assert rooms_a[0]["id"] != "john"
    assert rooms_a[0]["id"] != rooms_b[0]["id"]
    members_url = "/api/rooms/{}/members"
    assert (
        app_client.client.get(members_url.format(rooms_a[0]["id"])).status_code == 404
    )

    login(app_client.client, "john@a.org")
    assert (
        app_client.client.get(members_url.format(rooms_b[0]["id"])).status_code == 404
    )


def test_legacy_rooms_endpoint_shape(app_client):
    make_user(app_client.db_path, "john@a.org")
    login(app_client.client, "john@a.org")
    personal = app_client.client.get("/api/rooms").json()[0]

    response = app_client.client.get("/rooms")

    assert response.status_code == 200
    assert response.json() == {"rooms": [personal["id"]]}


def test_websocket_member_accepted_nonmember_refused(app_client):
    make_user(app_client.db_path, "owner@x.org")
    make_user(app_client.db_path, "stranger@x.org")
    login(app_client.client, "owner@x.org")
    room = create_room(app_client)

    with app_client.client.websocket_connect(
        f"/room/{room['id']}", headers=ws_headers(app_client.client)
    ):
        pass

    login(app_client.client, "stranger@x.org")
    assert_websocket_refused(
        app_client.client,
        f"/room/{room['id']}",
        ws_headers(app_client.client),
    )


def test_websocket_does_not_hold_a_db_connection(tmp_path):
    update_dir = str(tmp_path / "update_dir")
    Path(update_dir).mkdir()
    db_path = str(tmp_path / "test.db")
    cocat_app = CocatApp(update_dir, db_path)
    with TestClient(cocat_app.app, base_url="https://testserver") as client:
        app_client = AppClient(client=client, db_path=db_path, update_dir=update_dir)
        make_user(db_path, "member@x.org")
        login(client, "member@x.org")
        room = create_room(app_client)

        with client.websocket_connect(
            f"/room/{room['id']}", headers=ws_headers(client)
        ):
            assert cocat_app.db.engine.pool.checkedout() == 0


def test_removed_member_is_disconnected_and_cannot_reconnect(app_client):
    make_user(app_client.db_path, "owner@x.org")
    make_user(app_client.db_path, "member@x.org")
    login(app_client.client, "owner@x.org")
    room = create_room(app_client)
    token = invite(app_client, room["id"])
    join_room(app_client, "member@x.org", token)
    member_id = next(
        member["user_id"]
        for member in list_members(app_client, room["id"])
        if member["email"] == "member@x.org"
    )

    login(app_client.client, "member@x.org")
    with app_client.client.websocket_connect(
        f"/room/{room['id']}", headers=ws_headers(app_client.client)
    ) as websocket:
        assert websocket.receive_bytes()

        login(app_client.client, "owner@x.org")
        response = app_client.client.delete(
            f"/api/rooms/{room['id']}/members/{member_id}"
        )
        assert response.status_code == 204

        with pytest.raises(WebSocketDisconnect) as excinfo:
            websocket.receive_bytes()
        assert excinfo.value.code == 1008

    login(app_client.client, "member@x.org")
    assert_websocket_refused(
        app_client.client,
        f"/room/{room['id']}",
        ws_headers(app_client.client),
    )


def test_delete_room_disconnects_and_removes_file(app_client):
    make_user(app_client.db_path, "owner@x.org")
    login(app_client.client, "owner@x.org")
    room = create_room(app_client)
    file_path = room_file(app_client.update_dir, room["id"])

    with app_client.client.websocket_connect(
        f"/room/{room['id']}", headers=ws_headers(app_client.client)
    ) as websocket:
        assert websocket.receive_bytes()
        assert file_path.exists()

        response = app_client.client.delete(f"/api/rooms/{room['id']}")
        assert response.status_code == 204

        with pytest.raises(WebSocketDisconnect) as excinfo:
            websocket.receive_bytes()
        assert excinfo.value.code == 1008

    assert not file_path.exists()


def test_delete_room_disconnects_every_member(app_client):
    make_user(app_client.db_path, "owner@x.org")
    make_user(app_client.db_path, "member@x.org")
    login(app_client.client, "owner@x.org")
    room = create_room(app_client)
    token = invite(app_client, room["id"])
    join_room(app_client, "member@x.org", token)
    member_headers = ws_headers(app_client.client)

    login(app_client.client, "owner@x.org")
    url = f"/room/{room['id']}"
    with (
        app_client.client.websocket_connect(
            url, headers=ws_headers(app_client.client)
        ) as owner_socket,
        app_client.client.websocket_connect(
            url, headers=member_headers
        ) as member_socket,
    ):
        assert owner_socket.receive_bytes()
        assert member_socket.receive_bytes()

        deleted = app_client.client.delete(f"/api/rooms/{room['id']}")
        assert deleted.status_code == 204

        for socket in (owner_socket, member_socket):
            with pytest.raises(WebSocketDisconnect) as excinfo:
                socket.receive_bytes()
            assert excinfo.value.code == 1008


@pytest.mark.parametrize("prefix", ["cocat", "/cocat/", "cocat/"])
def test_proxy_prefix_becomes_the_root_path(monkeypatch, update_dir, db_path, prefix):
    monkeypatch.setenv("COCAT_PROXY_PREFIX", prefix)
    assert CocatApp(update_dir, db_path).app.root_path == "/cocat"
