def test_create_and_list_users(client):
    payload = {
        "name": "Max Mustermann",
        "email": "max@example.com",
        "password_hash": "hashed-password",
        "default_pause_seconds": 90,
    }

    create_response = client.post("/api/v1/users/", json=payload)
    assert create_response.status_code == 201
    created = create_response.json()
    assert created["email"] == payload["email"]
    assert "password_hash" not in created

    list_response = client.get("/api/v1/users/")
    assert list_response.status_code == 200
    users = list_response.json()
    assert len(users) == 1
    assert users[0]["email"] == payload["email"]
