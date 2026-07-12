def register_user(client, **overrides):
    payload = {
        "name": "Max Mustermann",
        "email": "max@example.com",
        "password": "supersecret",
    }
    payload.update(overrides)
    return client.post("/api/v1/auth/register", json=payload)


def login_user(client, email="max@example.com", password="supersecret"):
    return client.post("/api/v1/auth/login", json={"email": email, "password": password})


from app.api.routes.auth import _login_attempts as _reset_login_attempts


def test_login_returns_refresh_token(client):
    assert register_user(client).status_code == 201
    response = login_user(client)
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"
    assert data["user"]["email"] == "max@example.com"


def test_refresh_with_valid_token_returns_new_tokens(client):
    assert register_user(client).status_code == 201
    login_resp = login_user(client).json()
    old_refresh = login_resp["refresh_token"]

    response = client.post("/api/v1/auth/refresh", json={"refresh_token": old_refresh})
    assert response.status_code == 200
    data = response.json()

    assert data["refresh_token"] != old_refresh
    assert data["token_type"] == "bearer"
    assert data["user"]["email"] == "max@example.com"

    me_resp = client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {data['access_token']}"},
    )
    assert me_resp.status_code == 200


def test_refresh_with_invalid_token_fails(client):
    response = client.post("/api/v1/auth/refresh", json={"refresh_token": "garbage-token"})
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid refresh token."


def test_refresh_with_revoked_token_reuses_detection(client):
    assert register_user(client).status_code == 201
    refresh_token = login_user(client).json()["refresh_token"]

    resp1 = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert resp1.status_code == 200

    resp2 = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert resp2.status_code == 401
    assert resp2.json()["detail"] == "Refresh token has been revoked."


def test_logout_revokes_refresh_token(client):
    assert register_user(client).status_code == 201
    refresh_token = login_user(client).json()["refresh_token"]

    logout_resp = client.post("/api/v1/auth/logout", json={"refresh_token": refresh_token})
    assert logout_resp.status_code == 204

    refresh_resp = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert refresh_resp.status_code == 401
    assert refresh_resp.json()["detail"] == "Refresh token has been revoked."


def test_logout_with_invalid_token_returns_204(client):
    response = client.post("/api/v1/auth/logout", json={"refresh_token": "nonexistent"})
    assert response.status_code == 204


def test_reuse_detection_revokes_all_user_sessions(client):
    assert register_user(client).status_code == 201

    r1 = login_user(client).json()["refresh_token"]
    r2 = login_user(client).json()["refresh_token"]

    client.post("/api/v1/auth/refresh", json={"refresh_token": r1})
    client.post("/api/v1/auth/refresh", json={"refresh_token": r1})

    resp = client.post("/api/v1/auth/refresh", json={"refresh_token": r2})
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Refresh token has been revoked."


def test_refresh_returns_same_user(client):
    assert register_user(client).status_code == 201
    refresh_token = login_user(client).json()["refresh_token"]

    resp = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert resp.status_code == 200
    assert resp.json()["user"]["email"] == "max@example.com"
    assert resp.json()["user"]["name"] == "Max Mustermann"


def test_multiple_refresh_cycles(client):
    assert register_user(client).status_code == 201
    refresh_token = login_user(client).json()["refresh_token"]

    for _ in range(3):
        resp = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
        assert resp.status_code == 200
        refresh_token = resp.json()["refresh_token"]

    resp = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert resp.status_code == 200


def test_access_token_from_refresh_is_valid(client):
    assert register_user(client).status_code == 201
    refresh_token = login_user(client).json()["refresh_token"]

    resp = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert resp.status_code == 200
    new_access = resp.json()["access_token"]

    me_resp = client.get(
        "/api/v1/users/me",
        headers={"Authorization": f"Bearer {new_access}"},
    )
    assert me_resp.status_code == 200
    assert me_resp.json()["email"] == "max@example.com"


def test_login_rate_limiting_block_and_reset(client):
    """Brute-force protection: 5 failed → 401, 6th → 429.
    Successful login resets the counter for that IP."""
    assert register_user(client).status_code == 201

    # --- Phase 1: Block after 5 failures ---
    for i in range(5):
        resp = login_user(client, password=f"wrong_{i}")
        assert resp.status_code == 401, f"Attempt {i+1} expected 401, got {resp.status_code}"

    # 6th attempt → 429
    resp = login_user(client)
    assert resp.status_code == 429
    assert "Too many login attempts" in resp.json()["detail"]

    # --- Phase 2: Successful login resets the counter ---
    # Clear the rate-limit state so we can test reset independently
    _reset_login_attempts.clear()
    register_user(client, email="reset_test@example.com", name="Reset Tester")

    # 3 failed attempts (under the limit)
    for i in range(3):
        resp = login_user(client, email="reset_test@example.com", password=f"bad_{i}")
        assert resp.status_code == 401

    # Successful login resets counter
    resp = login_user(client, email="reset_test@example.com")
    assert resp.status_code == 200

    # Now we can fail another 5 times
    for i in range(5):
        resp = login_user(client, email="reset_test@example.com", password=f"nope_{i}")
        assert resp.status_code == 401, f"Post-reset attempt {i+1} expected 401, got {resp.status_code}"

    # 6th → 429
    resp = login_user(client, email="reset_test@example.com", password="last_try")
    assert resp.status_code == 429
