def register_user(client, **overrides):
    payload = {
        "name": "Max Mustermann",
        "email": "max@example.com",
        "password": "supersecret",
        "default_pause_seconds": 90,
    }
    payload.update(overrides)
    return client.post("/api/v1/auth/register", json=payload)


def login_user(client, email="max@example.com", password="supersecret"):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


def test_register_login_and_read_current_user(client):
    register_response = register_user(client)
    assert register_response.status_code == 201
    created = register_response.json()
    assert created["email"] == "max@example.com"
    assert "password" not in created
    assert "password_hash" not in created

    login_response = login_user(client)
    assert login_response.status_code == 200
    token_payload = login_response.json()
    assert token_payload["token_type"] == "bearer"
    assert token_payload["user"]["email"] == "max@example.com"

    headers = {"Authorization": f"Bearer {token_payload['access_token']}"}
    me_response = client.get("/api/v1/users/me", headers=headers)
    assert me_response.status_code == 200
    me = me_response.json()
    assert me["name"] == "Max Mustermann"


def test_register_rejects_duplicate_email_case_insensitively(client):
    assert register_user(client).status_code == 201

    duplicate_response = register_user(client, email="MAX@example.com")
    assert duplicate_response.status_code == 409


def test_login_rejects_invalid_credentials(client):
    assert register_user(client).status_code == 201

    login_response = login_user(client, password="wrongpassword")
    assert login_response.status_code == 401
    assert login_response.json()["detail"] == "Invalid email or password."


def test_profile_update_and_password_change_require_auth(client):
    assert register_user(client).status_code == 201
    login_response = login_user(client)
    token = login_response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    update_response = client.patch(
        "/api/v1/users/me",
        json={"name": "Maximilian", "default_pause_seconds": 120},
        headers=headers,
    )
    assert update_response.status_code == 200
    assert update_response.json()["name"] == "Maximilian"
    assert update_response.json()["default_pause_seconds"] == 120

    password_response = client.post(
        "/api/v1/users/me/password",
        json={"current_password": "supersecret", "new_password": "newsupersecret"},
        headers=headers,
    )
    assert password_response.status_code == 204

    old_login_response = login_user(client)
    assert old_login_response.status_code == 401

    new_login_response = login_user(client, password="newsupersecret")
    assert new_login_response.status_code == 200


def test_users_endpoints_require_authentication(client):
    list_response = client.get("/api/v1/users/")
    assert list_response.status_code == 401

    me_response = client.get("/api/v1/users/me")
    assert me_response.status_code == 401
