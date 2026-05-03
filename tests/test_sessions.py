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


def test_sessions_crud_and_set_workflow(client):
    assert register_user(client, email="owner@example.com", name="Owner").status_code == 201
    assert register_user(client, email="other@example.com", name="Other").status_code == 201
    owner_headers = auth_headers(client, email="owner@example.com")
    other_headers = auth_headers(client, email="other@example.com")

    exercise = create_exercise(client, owner_headers, name="Paused Bench", is_public=False)
    assert exercise.status_code == 201
    exercise_id = exercise.json()["id"]

    template_response = client.post(
        "/api/v1/templates/",
        json={"name": "Push Day"},
    )
    assert template_response.status_code == 201
    template_id = template_response.json()["id"]

    template_exercise_response = client.post(
        f"/api/v1/templates/{template_id}/exercises",
        json={"exercise_id": exercise_id, "sets": 3, "reps": 8},
        headers=owner_headers,
    )
    assert template_exercise_response.status_code == 201
    template_exercise_id = template_exercise_response.json()["id"]

    create_session_response = client.post(
        "/api/v1/sessions/",
        json={
            "performed_at": "2026-01-01T09:00:00Z",
            "template_id": template_id,
            "notes": "  morning session  ",
        },
        headers=owner_headers,
    )
    assert create_session_response.status_code == 201
    created_session = create_session_response.json()
    session_id = created_session["id"]
    assert created_session["notes"] == "morning session"
    assert created_session["active_session"] is True

    list_owner_sessions = client.get("/api/v1/sessions/", headers=owner_headers)
    assert list_owner_sessions.status_code == 200
    assert len(list_owner_sessions.json()) == 1
    assert list_owner_sessions.json()[0]["active_session"] is True

    list_other_sessions = client.get("/api/v1/sessions/", headers=other_headers)
    assert list_other_sessions.status_code == 200
    assert list_other_sessions.json() == []

    read_by_other = client.get(f"/api/v1/sessions/{session_id}", headers=other_headers)
    assert read_by_other.status_code == 404

    update_session_response = client.patch(
        f"/api/v1/sessions/{session_id}",
        json={"notes": "  updated notes  "},
        headers=owner_headers,
    )
    assert update_session_response.status_code == 200
    assert update_session_response.json()["notes"] == "updated notes"

    finish_session_response = client.patch(
        f"/api/v1/sessions/{session_id}",
        json={"active_session": False},
        headers=owner_headers,
    )
    assert finish_session_response.status_code == 200
    assert finish_session_response.json()["active_session"] is False

    add_set_response = client.post(
        f"/api/v1/sessions/{session_id}/sets",
        json={
            "template_exercise_id": template_exercise_id,
            "set_number": 1,
            "reps": 8,
            "rir": 1,
            "completed": True,
        },
        headers=owner_headers,
    )
    assert add_set_response.status_code == 201
    session_set = add_set_response.json()
    set_id = session_set["id"]
    assert session_set["exercise_id"] == exercise_id

    list_sets_response = client.get(f"/api/v1/sessions/{session_id}/sets", headers=owner_headers)
    assert list_sets_response.status_code == 200
    assert len(list_sets_response.json()) == 1

    update_set_response = client.patch(
        f"/api/v1/sessions/{session_id}/sets/{set_id}",
        json={"session_notes": "  strong set  ", "weight_kg": 80.0},
        headers=owner_headers,
    )
    assert update_set_response.status_code == 200
    assert update_set_response.json()["session_notes"] == "strong set"
    assert update_set_response.json()["weight_kg"] == 80.0

    delete_set_response = client.delete(
        f"/api/v1/sessions/{session_id}/sets/{set_id}",
        headers=owner_headers,
    )
    assert delete_set_response.status_code == 204

    delete_session_response = client.delete(
        f"/api/v1/sessions/{session_id}",
        headers=owner_headers,
    )
    assert delete_session_response.status_code == 204

    read_deleted_session = client.get(f"/api/v1/sessions/{session_id}", headers=owner_headers)
    assert read_deleted_session.status_code == 404


def test_sessions_require_auth_and_validate_references(client):
    assert register_user(client, email="owner@example.com", name="Owner").status_code == 201
    headers = auth_headers(client, email="owner@example.com")

    without_auth = client.get("/api/v1/sessions/")
    assert without_auth.status_code == 401

    create_invalid_template = client.post(
        "/api/v1/sessions/",
        json={"performed_at": "2026-01-01T09:00:00Z", "template_id": 999},
        headers=headers,
    )
    assert create_invalid_template.status_code == 400

    create_session_response = client.post(
        "/api/v1/sessions/",
        json={"performed_at": "2026-01-01T09:00:00Z"},
        headers=headers,
    )
    assert create_session_response.status_code == 201
    session_id = create_session_response.json()["id"]

    missing_set_link = client.post(
        f"/api/v1/sessions/{session_id}/sets",
        json={"set_number": 1, "reps": 10},
        headers=headers,
    )
    assert missing_set_link.status_code == 400

    invalid_exercise = client.post(
        f"/api/v1/sessions/{session_id}/sets",
        json={"exercise_id": 999, "set_number": 1},
        headers=headers,
    )
    assert invalid_exercise.status_code == 400


def test_session_set_template_exercise_validation_paths(client):
    assert register_user(client, email="owner@example.com", name="Owner").status_code == 201
    headers = auth_headers(client, email="owner@example.com")

    exercise = create_exercise(client, headers, name="Row", is_public=True)
    assert exercise.status_code == 201
    exercise_id = exercise.json()["id"]

    template_a = client.post("/api/v1/templates/", json={"name": "Template A"})
    template_b = client.post("/api/v1/templates/", json={"name": "Template B"})
    assert template_a.status_code == 201
    assert template_b.status_code == 201
    template_a_id = template_a.json()["id"]
    template_b_id = template_b.json()["id"]

    template_exercise_a = client.post(
        f"/api/v1/templates/{template_a_id}/exercises",
        json={"exercise_id": exercise_id, "sets": 3, "reps": 10},
        headers=headers,
    )
    template_exercise_b = client.post(
        f"/api/v1/templates/{template_b_id}/exercises",
        json={"exercise_id": exercise_id, "sets": 4, "reps": 8},
        headers=headers,
    )
    assert template_exercise_a.status_code == 201
    assert template_exercise_b.status_code == 201

    session_a = client.post(
        "/api/v1/sessions/",
        json={"performed_at": "2026-01-01T09:00:00Z", "template_id": template_a_id},
        headers=headers,
    )
    assert session_a.status_code == 201
    session_id = session_a.json()["id"]

    invalid_template_exercise = client.post(
        f"/api/v1/sessions/{session_id}/sets",
        json={"template_exercise_id": 99999, "set_number": 1},
        headers=headers,
    )
    assert invalid_template_exercise.status_code == 400

    wrong_template_link = client.post(
        f"/api/v1/sessions/{session_id}/sets",
        json={"template_exercise_id": template_exercise_b.json()["id"], "set_number": 1},
        headers=headers,
    )
    assert wrong_template_link.status_code == 400

    valid_set = client.post(
        f"/api/v1/sessions/{session_id}/sets",
        json={
            "template_exercise_id": template_exercise_a.json()["id"],
            "set_number": 1,
            "reps": 10,
        },
        headers=headers,
    )
    assert valid_set.status_code == 201
    set_id = valid_set.json()["id"]

    wrong_template_link_update = client.patch(
        f"/api/v1/sessions/{session_id}/sets/{set_id}",
        json={"template_exercise_id": template_exercise_b.json()["id"]},
        headers=headers,
    )
    assert wrong_template_link_update.status_code == 400


def test_update_session_and_set_not_found_paths(client):
    assert register_user(client, email="owner@example.com", name="Owner").status_code == 201
    headers = auth_headers(client, email="owner@example.com")

    create_session_response = client.post(
        "/api/v1/sessions/",
        json={"performed_at": "2026-01-01T09:00:00Z"},
        headers=headers,
    )
    assert create_session_response.status_code == 201
    session_id = create_session_response.json()["id"]

    invalid_template_update = client.patch(
        f"/api/v1/sessions/{session_id}",
        json={"template_id": 99999},
        headers=headers,
    )
    assert invalid_template_update.status_code == 400

    set_response = client.post(
        f"/api/v1/sessions/{session_id}/sets",
        json={"set_number": 1, "reps": 8, "exercise_id": 999},
        headers=headers,
    )
    assert set_response.status_code == 400

    exercise = create_exercise(client, headers, name="Leg Press", is_public=True)
    assert exercise.status_code == 201
    exercise_id = exercise.json()["id"]
    valid_set = client.post(
        f"/api/v1/sessions/{session_id}/sets",
        json={"set_number": 1, "reps": 8, "exercise_id": exercise_id},
        headers=headers,
    )
    assert valid_set.status_code == 201
    set_id = valid_set.json()["id"]

    wrong_session_patch = client.patch(
        f"/api/v1/sessions/99999/sets/{set_id}",
        json={"reps": 9},
        headers=headers,
    )
    assert wrong_session_patch.status_code == 404

    wrong_set_patch = client.patch(
        f"/api/v1/sessions/{session_id}/sets/99999",
        json={"reps": 9},
        headers=headers,
    )
    assert wrong_set_patch.status_code == 404

    wrong_set_delete = client.delete(
        f"/api/v1/sessions/{session_id}/sets/99999",
        headers=headers,
    )
    assert wrong_set_delete.status_code == 404
