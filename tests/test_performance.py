def register_user(client, *, email, name):
    payload = {
        "name": name,
        "email": email,
        "password": "supersecret",
    }
    return client.post("/api/v1/auth/register", json=payload)


def login_user(client, *, email):
    return client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "supersecret"},
    )


def auth_headers(client, *, email):
    response = login_user(client, email=email)
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def create_exercise(client, headers, **overrides):
    payload = {
        "name": "Bench Press",
        "laterality": "bilateral",
        "is_public": False,
    }
    payload.update(overrides)
    return client.post("/api/v1/exercises/", json=payload, headers=headers)


def test_cache_control_headers_present(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert "Cache-Control" in response.headers
    assert "private" in response.headers["cache-control"]


def test_cache_control_not_on_mutations(client):
    assert register_user(client, email="test@example.com", name="Test").status_code == 201
    headers = auth_headers(client, email="test@example.com")
    response = client.post(
        "/api/v1/exercises/muscle-groups/",
        json={"name": "Shoulders"},
        headers=headers,
    )
    assert response.status_code == 201
    assert "cache-control" not in response.headers or "private" not in response.headers.get("cache-control", "")


def test_muscle_group_caching(client):
    assert register_user(client, email="test@example.com", name="Test").status_code == 201
    headers = auth_headers(client, email="test@example.com")

    list_before = client.get("/api/v1/exercises/muscle-groups/")
    assert list_before.status_code == 200
    assert list_before.json() == []

    client.post(
        "/api/v1/exercises/muscle-groups/",
        json={"name": "Chest"},
        headers=headers,
    )

    list_after = client.get("/api/v1/exercises/muscle-groups/")
    assert list_after.status_code == 200
    assert len(list_after.json()) == 1


def test_muscle_region_caching(client):
    assert register_user(client, email="test@example.com", name="Test").status_code == 201
    headers = auth_headers(client, email="test@example.com")

    group = client.post(
        "/api/v1/exercises/muscle-groups/",
        json={"name": "Legs"},
        headers=headers,
    ).json()
    group_id = group["id"]

    region = client.post(
        "/api/v1/exercises/muscle-regions/",
        json={"name": "Quads", "group_id": group_id},
        headers=headers,
    )
    assert region.status_code == 201

    list_filtered = client.get(f"/api/v1/exercises/muscle-regions/?group_id={group_id}")
    assert list_filtered.status_code == 200
    assert len(list_filtered.json()) == 1


def test_exercise_alternatives_union_query(client):
    assert register_user(client, email="test@example.com", name="Test").status_code == 201
    headers = auth_headers(client, email="test@example.com")

    first = create_exercise(client, headers, name="Flat Bench Press", is_public=True)
    second = create_exercise(client, headers, name="Incline Bench Press", is_public=True)
    third = create_exercise(client, headers, name="Decline Bench Press", is_public=True)
    assert first.status_code == 201
    assert second.status_code == 201
    assert third.status_code == 201
    first_id = first.json()["id"]
    second_id = second.json()["id"]
    third_id = third.json()["id"]

    client.post(f"/api/v1/exercises/{first_id}/alternatives/{second_id}", headers=headers)
    client.post(f"/api/v1/exercises/{first_id}/alternatives/{third_id}", headers=headers)

    resp_first = client.get(f"/api/v1/exercises/{first_id}/alternatives", headers=headers)
    assert resp_first.status_code == 200
    assert len(resp_first.json()) == 2
    ids = {e["id"] for e in resp_first.json()}
    assert ids == {second_id, third_id}

    resp_second = client.get(f"/api/v1/exercises/{second_id}/alternatives", headers=headers)
    assert resp_second.status_code == 200
    assert len(resp_second.json()) == 1
    assert resp_second.json()[0]["id"] == first_id


def test_delete_exercise_blocked_by_both_template_and_session(client):
    assert register_user(client, email="test@example.com", name="Test").status_code == 201
    headers = auth_headers(client, email="test@example.com")

    exercise = create_exercise(client, headers, name="Squat", is_public=True)
    assert exercise.status_code == 201
    exercise_id = exercise.json()["id"]

    template = client.post("/api/v1/templates/", json={"name": "Leg Day"}).json()
    template_id = template["id"]
    session_resp = client.post(
        "/api/v1/sessions/",
        json={"performed_at": "2026-01-01T09:00:00Z"},
        headers=headers,
    ).json()
    session_id = session_resp["id"]

    client.post(
        f"/api/v1/templates/{template_id}/exercises",
        json={"exercise_id": exercise_id, "sets": 3, "reps": 10},
        headers=headers,
    )
    client.post(
        f"/api/v1/sessions/{session_id}/sets",
        json={"exercise_id": exercise_id, "set_number": 1, "reps": 8},
        headers=headers,
    )

    delete_resp = client.delete(f"/api/v1/exercises/{exercise_id}", headers=headers)
    assert delete_resp.status_code == 409


def test_list_exercises_union_visibility(client):
    assert register_user(client, email="test@example.com", name="Test").status_code == 201
    assert register_user(client, email="other@example.com", name="Other").status_code == 201
    headers = auth_headers(client, email="test@example.com")
    other_headers = auth_headers(client, email="other@example.com")

    public_exercise = create_exercise(client, headers, name="Public One", is_public=True)
    private_exercise = create_exercise(client, headers, name="Private One", is_public=False)
    public_id = public_exercise.json()["id"]
    private_id = private_exercise.json()["id"]

    anon_list = client.get("/api/v1/exercises/")
    assert anon_list.status_code == 200
    anon_ids = {e["id"] for e in anon_list.json()}
    assert public_id in anon_ids
    assert private_id not in anon_ids

    owner_list = client.get("/api/v1/exercises/", headers=headers)
    owner_ids = {e["id"] for e in owner_list.json()}
    assert public_id in owner_ids
    assert private_id in owner_ids

    other_list = client.get("/api/v1/exercises/", headers=other_headers)
    other_ids = {e["id"] for e in other_list.json()}
    assert public_id in other_ids
    assert private_id not in other_ids
