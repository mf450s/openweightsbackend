def register_user(client, *, email, name):
    payload = {"name": name, "email": email, "password": "supersecret"}
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
    payload = {"name": "Bench Press", "laterality": "bilateral", "is_public": False}
    payload.update(overrides)
    return client.post("/api/v1/exercises/", json=payload, headers=headers)


def test_estimate_1rm():
    from app.services.progression_service import estimate_1rm

    est = estimate_1rm(100, 10)
    assert est is not None
    assert 130 <= est <= 140

    est_zero = estimate_1rm(0, 10)
    assert est_zero is None

    est_no_reps = estimate_1rm(100, 0)
    assert est_no_reps is None

    est_with_rir = estimate_1rm(100, 8, rir=2)
    assert est_with_rir is not None


def test_exercise_history(client):
    assert register_user(client, email="user@example.com", name="User").status_code == 201
    headers = auth_headers(client, email="user@example.com")

    exercise = create_exercise(client, headers, name="Squat", is_public=True)
    exercise_id = exercise.json()["id"]

    session_resp = client.post(
        "/api/v1/sessions/",
        json={"performed_at": "2026-01-01T09:00:00Z"},
        headers=headers,
    )
    session_id = session_resp.json()["id"]

    client.post(
        f"/api/v1/sessions/{session_id}/sets",
        json={"exercise_id": exercise_id, "set_number": 1, "weight_kg": 100, "reps": 5},
        headers=headers,
    )
    client.post(
        f"/api/v1/sessions/{session_id}/sets",
        json={"exercise_id": exercise_id, "set_number": 2, "weight_kg": 90, "reps": 8},
        headers=headers,
    )

    history_resp = client.get(f"/api/v1/exercises/{exercise_id}/history", headers=headers)
    assert history_resp.status_code == 200
    history = history_resp.json()
    assert len(history) == 1
    assert len(history[0]["sets"]) == 2
    assert history[0]["sets"][0]["set_number"] == 1
    assert history[0]["sets"][1]["set_number"] == 2


def test_exercise_history_requires_auth(client):
    assert register_user(client, email="user@example.com", name="User").status_code == 201
    headers = auth_headers(client, email="user@example.com")

    exercise = create_exercise(client, headers, name="Deadlift", is_public=True)
    exercise_id = exercise.json()["id"]

    history_resp = client.get(f"/api/v1/exercises/{exercise_id}/history")
    assert history_resp.status_code == 401


def test_exercise_history_other_user(client):
    assert register_user(client, email="owner@example.com", name="Owner").status_code == 201
    assert register_user(client, email="other@example.com", name="Other").status_code == 201
    owner_headers = auth_headers(client, email="owner@example.com")
    other_headers = auth_headers(client, email="other@example.com")

    exercise = create_exercise(client, owner_headers, name="OHP", is_public=False)
    exercise_id = exercise.json()["id"]

    history_other = client.get(f"/api/v1/exercises/{exercise_id}/history", headers=other_headers)
    assert history_other.status_code == 404


def test_exercise_1rm(client):
    assert register_user(client, email="user@example.com", name="User").status_code == 201
    headers = auth_headers(client, email="user@example.com")

    exercise = create_exercise(client, headers, name="Bench Press", is_public=True)
    exercise_id = exercise.json()["id"]

    session1 = client.post(
        "/api/v1/sessions/",
        json={"performed_at": "2026-01-01T09:00:00Z"},
        headers=headers,
    ).json()
    session2 = client.post(
        "/api/v1/sessions/",
        json={"performed_at": "2026-01-15T09:00:00Z"},
        headers=headers,
    ).json()

    client.post(
        f"/api/v1/sessions/{session1['id']}/sets",
        json={"exercise_id": exercise_id, "set_number": 1, "weight_kg": 80, "reps": 5},
        headers=headers,
    )
    client.post(
        f"/api/v1/sessions/{session2['id']}/sets",
        json={"exercise_id": exercise_id, "set_number": 1, "weight_kg": 90, "reps": 3},
        headers=headers,
    )

    rm_resp = client.get(f"/api/v1/exercises/{exercise_id}/1rm", headers=headers)
    assert rm_resp.status_code == 200
    data = rm_resp.json()
    assert len(data) == 2
    assert data[0]["estimated_1rm"] < data[1]["estimated_1rm"]


def test_personal_record_on_create(client):
    assert register_user(client, email="user@example.com", name="User").status_code == 201
    headers = auth_headers(client, email="user@example.com")

    exercise = create_exercise(client, headers, name="Deadlift", is_public=True)
    exercise_id = exercise.json()["id"]

    session = client.post(
        "/api/v1/sessions/",
        json={"performed_at": "2026-01-01T09:00:00Z"},
        headers=headers,
    ).json()

    resp = client.post(
        f"/api/v1/sessions/{session['id']}/sets",
        json={"exercise_id": exercise_id, "set_number": 1, "weight_kg": 100, "reps": 5},
        headers=headers,
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["personal_record"] is not None
    assert body["personal_record"]["pr_type"] == "max_weight"

    resp2 = client.post(
        f"/api/v1/sessions/{session['id']}/sets",
        json={"exercise_id": exercise_id, "set_number": 2, "weight_kg": 120, "reps": 5},
        headers=headers,
    )
    body2 = resp2.json()
    assert body2["personal_record"] is not None
    assert body2["personal_record"]["pr_type"] == "max_weight"

    resp3 = client.post(
        f"/api/v1/sessions/{session['id']}/sets",
        json={"exercise_id": exercise_id, "set_number": 3, "weight_kg": 80, "reps": 5},
        headers=headers,
    )
    body3 = resp3.json()
    assert body3["personal_record"] is None


def test_personal_record_on_update(client):
    assert register_user(client, email="user@example.com", name="User").status_code == 201
    headers = auth_headers(client, email="user@example.com")

    exercise = create_exercise(client, headers, name="Pull Up", is_public=True)
    exercise_id = exercise.json()["id"]

    session = client.post(
        "/api/v1/sessions/",
        json={"performed_at": "2026-01-01T09:00:00Z"},
        headers=headers,
    ).json()

    resp = client.post(
        f"/api/v1/sessions/{session['id']}/sets",
        json={"exercise_id": exercise_id, "set_number": 1, "weight_kg": 10, "reps": 10},
        headers=headers,
    )
    set_id = resp.json()["id"]

    resp2 = client.patch(
        f"/api/v1/sessions/{session['id']}/sets/{set_id}",
        json={"weight_kg": 25},
        headers=headers,
    )
    body2 = resp2.json()
    assert body2["personal_record"] is not None
    assert body2["personal_record"]["pr_type"] == "max_weight"
