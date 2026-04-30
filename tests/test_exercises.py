def register_user(client, *, email, name):
    payload = {
        "name": name,
        "email": email,
        "password": "supersecret",
        "default_pause_seconds": 90,
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
