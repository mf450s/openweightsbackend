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


def test_exercise_crud_and_visibility(client):
    assert register_user(client, email="owner@example.com", name="Owner").status_code == 201
    assert register_user(client, email="other@example.com", name="Other").status_code == 201

    owner_headers = auth_headers(client, email="owner@example.com")
    other_headers = auth_headers(client, email="other@example.com")

    group_response = client.post(
        "/api/v1/exercises/muscle-groups/",
        json={"name": "Chest"},
        headers=owner_headers,
    )
    assert group_response.status_code == 201
    group_id = group_response.json()["id"]

    region_response = client.post(
        "/api/v1/exercises/muscle-regions/",
        json={"name": "Upper Chest", "group_id": group_id},
        headers=owner_headers,
    )
    assert region_response.status_code == 201
    region_id = region_response.json()["id"]

    create_response = create_exercise(
        client,
        owner_headers,
        name="  Bench Press  ",
        muscle_region_id=region_id,
        execution_notes="  Keep shoulder blades retracted.  ",
    )
    assert create_response.status_code == 201
    exercise = create_response.json()
    exercise_id = exercise["id"]
    assert exercise["name"] == "Bench Press"
    assert exercise["execution_notes"] == "Keep shoulder blades retracted."
    assert exercise["created_by_user_id"] is not None

    public_list = client.get("/api/v1/exercises/")
    assert public_list.status_code == 200
    assert public_list.json() == []

    owner_list = client.get("/api/v1/exercises/", headers=owner_headers)
    assert owner_list.status_code == 200
    assert len(owner_list.json()) == 1

    other_list = client.get("/api/v1/exercises/", headers=other_headers)
    assert other_list.status_code == 200
    assert other_list.json() == []

    patch_response = client.patch(
        f"/api/v1/exercises/{exercise_id}",
        json={"is_public": True},
        headers=owner_headers,
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["is_public"] is True

    public_list_after = client.get("/api/v1/exercises/")
    assert public_list_after.status_code == 200
    assert len(public_list_after.json()) == 1

    read_by_other = client.get(f"/api/v1/exercises/{exercise_id}", headers=other_headers)
    assert read_by_other.status_code == 200

    forbidden_patch = client.patch(
        f"/api/v1/exercises/{exercise_id}",
        json={"name": "Hacked"},
        headers=other_headers,
    )
    assert forbidden_patch.status_code == 403

    delete_by_other = client.delete(f"/api/v1/exercises/{exercise_id}", headers=other_headers)
    assert delete_by_other.status_code == 403

    delete_by_owner = client.delete(f"/api/v1/exercises/{exercise_id}", headers=owner_headers)
    assert delete_by_owner.status_code == 204

    read_after_delete = client.get(f"/api/v1/exercises/{exercise_id}", headers=owner_headers)
    assert read_after_delete.status_code == 404


def test_exercise_alternatives_workflow(client):
    assert register_user(client, email="owner@example.com", name="Owner").status_code == 201
    headers = auth_headers(client, email="owner@example.com")

    first = create_exercise(client, headers, name="Incline Dumbbell Press", is_public=True)
    second = create_exercise(client, headers, name="Machine Chest Press", is_public=True)
    assert first.status_code == 201
    assert second.status_code == 201
    first_id = first.json()["id"]
    second_id = second.json()["id"]

    add_response = client.post(
        f"/api/v1/exercises/{first_id}/alternatives/{second_id}",
        headers=headers,
    )
    assert add_response.status_code == 204

    alternatives = client.get(f"/api/v1/exercises/{first_id}/alternatives", headers=headers)
    assert alternatives.status_code == 200
    assert len(alternatives.json()) == 1
    assert alternatives.json()[0]["id"] == second_id

    remove_response = client.delete(
        f"/api/v1/exercises/{first_id}/alternatives/{second_id}",
        headers=headers,
    )
    assert remove_response.status_code == 204

    alternatives_after = client.get(f"/api/v1/exercises/{first_id}/alternatives", headers=headers)
    assert alternatives_after.status_code == 200
    assert alternatives_after.json() == []


def test_exercise_endpoints_require_auth_where_needed(client):
    assert register_user(client, email="owner@example.com", name="Owner").status_code == 201
    headers = auth_headers(client, email="owner@example.com")

    create_without_auth = client.post(
        "/api/v1/exercises/",
        json={"name": "Squat", "laterality": "bilateral", "is_public": True},
    )
    assert create_without_auth.status_code == 401

    create_group_without_auth = client.post("/api/v1/exercises/muscle-groups/", json={"name": "Legs"})
    assert create_group_without_auth.status_code == 401

    exercise = create_exercise(client, headers, name="Back Squat", is_public=True)
    exercise_id = exercise.json()["id"]

    invalid_alternative = client.post(
        f"/api/v1/exercises/{exercise_id}/alternatives/{exercise_id}",
        headers=headers,
    )
    assert invalid_alternative.status_code == 400


def test_muscle_group_and_region_conflict_and_validation(client):
    assert register_user(client, email="owner@example.com", name="Owner").status_code == 201
    headers = auth_headers(client, email="owner@example.com")

    first_group = client.post(
        "/api/v1/exercises/muscle-groups/",
        json={"name": "Back"},
        headers=headers,
    )
    assert first_group.status_code == 201

    duplicate_group = client.post(
        "/api/v1/exercises/muscle-groups/",
        json={"name": "Back"},
        headers=headers,
    )
    assert duplicate_group.status_code == 409

    invalid_region = client.post(
        "/api/v1/exercises/muscle-regions/",
        json={"name": "Lats", "group_id": 99999},
        headers=headers,
    )
    assert invalid_region.status_code == 400

    created_group_id = first_group.json()["id"]
    first_region = client.post(
        "/api/v1/exercises/muscle-regions/",
        json={"name": "Lats", "group_id": created_group_id},
        headers=headers,
    )
    assert first_region.status_code == 201

    duplicate_region = client.post(
        "/api/v1/exercises/muscle-regions/",
        json={"name": "Lats", "group_id": created_group_id},
        headers=headers,
    )
    assert duplicate_region.status_code == 409


def test_exercise_create_update_conflicts_and_invalid_references(client):
    assert register_user(client, email="owner@example.com", name="Owner").status_code == 201
    headers = auth_headers(client, email="owner@example.com")

    invalid_region_create = create_exercise(
        client,
        headers,
        name="Invalid Region Exercise",
        muscle_region_id=99999,
    )
    assert invalid_region_create.status_code == 400

    first = create_exercise(client, headers, name="Overhead Press")
    second = create_exercise(client, headers, name="Arnold Press")
    assert first.status_code == 201
    assert second.status_code == 201
    second_id = second.json()["id"]

    duplicate_name_update = client.patch(
        f"/api/v1/exercises/{second_id}",
        json={"name": "Overhead Press"},
        headers=headers,
    )
    assert duplicate_name_update.status_code == 409

    invalid_region_update = client.patch(
        f"/api/v1/exercises/{second_id}",
        json={"muscle_region_id": 99999},
        headers=headers,
    )
    assert invalid_region_update.status_code == 400


def test_delete_exercise_blocked_when_used_in_templates_or_sessions(client):
    assert register_user(client, email="owner@example.com", name="Owner").status_code == 201
    headers = auth_headers(client, email="owner@example.com")

    exercise_response = create_exercise(client, headers, name="Romanian Deadlift", is_public=True)
    assert exercise_response.status_code == 201
    exercise_id = exercise_response.json()["id"]

    template_response = client.post("/api/v1/templates/", json={"name": "Pull Day"})
    assert template_response.status_code == 201
    template_id = template_response.json()["id"]

    template_exercise_response = client.post(
        f"/api/v1/templates/{template_id}/exercises",
        json={"exercise_id": exercise_id, "sets": 3, "reps": 10},
        headers=headers,
    )
    assert template_exercise_response.status_code == 201

    blocked_by_template = client.delete(f"/api/v1/exercises/{exercise_id}", headers=headers)
    assert blocked_by_template.status_code == 409

    remove_template_link = client.delete(
        f"/api/v1/templates/{template_id}/exercises/{template_exercise_response.json()['id']}"
    )
    assert remove_template_link.status_code == 204

    session_response = client.post(
        "/api/v1/sessions/",
        json={"performed_at": "2026-01-01T09:00:00Z"},
        headers=headers,
    )
    assert session_response.status_code == 201
    session_id = session_response.json()["id"]

    set_response = client.post(
        f"/api/v1/sessions/{session_id}/sets",
        json={"exercise_id": exercise_id, "set_number": 1, "reps": 8},
        headers=headers,
    )
    assert set_response.status_code == 201

    blocked_by_session = client.delete(f"/api/v1/exercises/{exercise_id}", headers=headers)
    assert blocked_by_session.status_code == 409


def test_alternative_permissions_for_non_owner(client):
    assert register_user(client, email="owner@example.com", name="Owner").status_code == 201
    assert register_user(client, email="other@example.com", name="Other").status_code == 201
    owner_headers = auth_headers(client, email="owner@example.com")
    other_headers = auth_headers(client, email="other@example.com")

    first = create_exercise(client, owner_headers, name="Dip", is_public=True)
    second = create_exercise(client, owner_headers, name="Close Grip Bench", is_public=True)
    assert first.status_code == 201
    assert second.status_code == 201
    first_id = first.json()["id"]
    second_id = second.json()["id"]

    add_by_other = client.post(
        f"/api/v1/exercises/{first_id}/alternatives/{second_id}",
        headers=other_headers,
    )
    assert add_by_other.status_code == 403

    add_by_owner = client.post(
        f"/api/v1/exercises/{first_id}/alternatives/{second_id}",
        headers=owner_headers,
    )
    assert add_by_owner.status_code == 204

    remove_by_other = client.delete(
        f"/api/v1/exercises/{first_id}/alternatives/{second_id}",
        headers=other_headers,
    )
    assert remove_by_other.status_code == 403
