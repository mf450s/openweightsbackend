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
        "is_public": True,
    }
    payload.update(overrides)
    return client.post("/api/v1/exercises/", json=payload, headers=headers)


def test_template_crud_and_template_exercise_workflow(client):
    assert register_user(client, email="owner@example.com", name="Owner").status_code == 201
    assert register_user(client, email="other@example.com", name="Other").status_code == 201
    owner_headers = auth_headers(client, email="owner@example.com")
    other_headers = auth_headers(client, email="other@example.com")

    public_exercise = create_exercise(client, owner_headers, name="Front Squat", is_public=True)
    private_exercise = create_exercise(
        client, owner_headers, name="Paused Front Squat", is_public=False
    )
    assert public_exercise.status_code == 201
    assert private_exercise.status_code == 201
    public_exercise_id = public_exercise.json()["id"]
    private_exercise_id = private_exercise.json()["id"]

    create_template_response = client.post(
        "/api/v1/templates/",
        json={"name": "  Push Day  ", "order_in_split": 1},
        headers=owner_headers,
    )
    assert create_template_response.status_code == 201
    template = create_template_response.json()
    template_id = template["id"]
    assert template["name"] == "Push Day"

    read_template_response = client.get(f"/api/v1/templates/{template_id}", headers=owner_headers)
    assert read_template_response.status_code == 200
    assert read_template_response.json()["id"] == template_id

    update_template_response = client.patch(
        f"/api/v1/templates/{template_id}",
        json={"name": "Upper Body Push", "order_in_split": 2},
        headers=owner_headers,
    )
    assert update_template_response.status_code == 200
    assert update_template_response.json()["name"] == "Upper Body Push"
    assert update_template_response.json()["order_in_split"] == 2

    add_public_exercise_response = client.post(
        f"/api/v1/templates/{template_id}/exercises",
        json={
            "exercise_id": public_exercise_id,
            "sets": 4,
            "reps": 8,
            "order_in_template": 2,
        },
        headers=owner_headers,
    )
    assert add_public_exercise_response.status_code == 201
    public_template_exercise_id = add_public_exercise_response.json()["id"]

    add_private_exercise_without_auth = client.post(
        f"/api/v1/templates/{template_id}/exercises",
        json={
            "exercise_id": private_exercise_id,
            "sets": 3,
            "reps": 5,
            "order_in_template": 1,
        },
    )
    assert add_private_exercise_without_auth.status_code == 401

    add_private_exercise_with_owner = client.post(
        f"/api/v1/templates/{template_id}/exercises",
        json={
            "exercise_id": private_exercise_id,
            "sets": 3,
            "reps": 5,
            "order_in_template": 1,
        },
        headers=owner_headers,
    )
    assert add_private_exercise_with_owner.status_code == 201
    private_template_exercise_id = add_private_exercise_with_owner.json()["id"]

    add_private_exercise_with_other_user = client.post(
        f"/api/v1/templates/{template_id}/exercises",
        json={
            "exercise_id": private_exercise_id,
            "sets": 2,
            "reps": 6,
            "order_in_template": 3,
        },
        headers=other_headers,
    )
    assert add_private_exercise_with_other_user.status_code == 404

    template_exercises = client.get(f"/api/v1/templates/{template_id}/exercises", headers=owner_headers)
    assert template_exercises.status_code == 200
    items = template_exercises.json()["items"]
    assert len(items) == 2
    assert items[0]["id"] == private_template_exercise_id
    assert items[1]["id"] == public_template_exercise_id

    patch_template_exercise_response = client.patch(
        f"/api/v1/templates/{template_id}/exercises/{public_template_exercise_id}",
        json={"reps": 10, "order_in_template": 5},
        headers=owner_headers,
    )
    assert patch_template_exercise_response.status_code == 200
    assert patch_template_exercise_response.json()["reps"] == 10
    assert patch_template_exercise_response.json()["order_in_template"] == 5

    move_to_private_without_auth = client.patch(
        f"/api/v1/templates/{template_id}/exercises/{public_template_exercise_id}",
        json={"exercise_id": private_exercise_id},
    )
    assert move_to_private_without_auth.status_code == 401

    delete_template_exercise_response = client.delete(
        f"/api/v1/templates/{template_id}/exercises/{private_template_exercise_id}",
        headers=owner_headers,
    )
    assert delete_template_exercise_response.status_code == 204

    delete_template_response = client.delete(f"/api/v1/templates/{template_id}", headers=owner_headers)
    assert delete_template_response.status_code == 204

    read_deleted_template = client.get(f"/api/v1/templates/{template_id}", headers=owner_headers)
    assert read_deleted_template.status_code == 404


def test_template_endpoints_validation_and_not_found_cases(client):
    assert register_user(client, email="user@example.com", name="User").status_code == 201
    headers = auth_headers(client, email="user@example.com")

    missing = client.get("/api/v1/templates/999", headers=headers)
    assert missing.status_code == 404

    invalid_create = client.post("/api/v1/templates/", json={"name": "x"}, headers=headers)
    assert invalid_create.status_code == 422

    create_template = client.post("/api/v1/templates/", json={"name": "Leg Day"}, headers=headers)
    assert create_template.status_code == 201
    template_id = create_template.json()["id"]

    invalid_exercise_reference = client.post(
        f"/api/v1/templates/{template_id}/exercises",
        json={"exercise_id": 999, "sets": 3},
        headers=headers,
    )
    assert invalid_exercise_reference.status_code == 400

    wrong_template_for_exercise = client.patch(
        f"/api/v1/templates/{template_id}/exercises/999",
        json={"sets": 4},
        headers=headers,
    )
    assert wrong_template_for_exercise.status_code == 404


# ── Template reorder ─────────────────────────────────────────────────────────


def create_exercise(client, headers, **overrides):
    payload = {
        "name": "Bench Press",
        "laterality": "bilateral",
        "is_public": True,
    }
    payload.update(overrides)
    return client.post("/api/v1/exercises/", json=payload, headers=headers)


def test_reorder_template_exercises(client):
    assert register_user(client, email="user@example.com", name="User").status_code == 201
    headers = auth_headers(client, email="user@example.com")

    exercise = create_exercise(client, headers, name="Press", is_public=True)
    assert exercise.status_code == 201
    exercise_id = exercise.json()["id"]

    # Create template
    template_resp = client.post("/api/v1/templates/", json={"name": "Push Day"}, headers=headers)
    assert template_resp.status_code == 201
    template_id = template_resp.json()["id"]

    # Add 3 exercises
    te1 = client.post(
        f"/api/v1/templates/{template_id}/exercises",
        json={"exercise_id": exercise_id, "sets": 3, "order_in_template": 1},
        headers=headers,
    )
    te2 = client.post(
        f"/api/v1/templates/{template_id}/exercises",
        json={"exercise_id": exercise_id, "sets": 4, "order_in_template": 2},
        headers=headers,
    )
    te3 = client.post(
        f"/api/v1/templates/{template_id}/exercises",
        json={"exercise_id": exercise_id, "sets": 5, "order_in_template": 3},
        headers=headers,
    )
    assert te1.status_code == 201
    assert te2.status_code == 201
    assert te3.status_code == 201
    te1_id = te1.json()["id"]
    te2_id = te2.json()["id"]
    te3_id = te3.json()["id"]

    # Reorder: [te3, te1, te2]
    reorder_resp = client.put(
        f"/api/v1/templates/{template_id}/exercises/reorder",
        json={"exercise_ids": [te3_id, te1_id, te2_id]},
        headers=headers,
    )
    assert reorder_resp.status_code == 204

    # Verify order
    exercises_resp = client.get(f"/api/v1/templates/{template_id}/exercises", headers=headers)
    assert exercises_resp.status_code == 200
    exercises = exercises_resp.json()["items"]
    assert len(exercises) == 3
    # Should be ordered by order_in_template, then id
    order_map = {e["id"]: e["order_in_template"] for e in exercises}
    assert order_map[te3_id] == 1
    assert order_map[te1_id] == 2
    assert order_map[te2_id] == 3


def test_reorder_invalid_exercise_id(client):
    assert register_user(client, email="user@example.com", name="User").status_code == 201
    headers = auth_headers(client, email="user@example.com")

    exercise = create_exercise(client, headers, name="Press", is_public=True)
    assert exercise.status_code == 201
    exercise_id = exercise.json()["id"]

    template_resp = client.post("/api/v1/templates/", json={"name": "Push Day"}, headers=headers)
    assert template_resp.status_code == 201
    template_id = template_resp.json()["id"]

    te = client.post(
        f"/api/v1/templates/{template_id}/exercises",
        json={"exercise_id": exercise_id, "sets": 3, "order_in_template": 1},
        headers=headers,
    )
    assert te.status_code == 201

    # Try reorder with invalid exercise ID
    reorder_resp = client.put(
        f"/api/v1/templates/{template_id}/exercises/reorder",
        json={"exercise_ids": [99999]},
        headers=headers,
    )
    assert reorder_resp.status_code == 404


def test_reorder_nonexistent_template(client):
    assert register_user(client, email="user@example.com", name="User").status_code == 201
    headers = auth_headers(client, email="user@example.com")

    reorder_resp = client.put(
        "/api/v1/templates/99999/exercises/reorder",
        json={"exercise_ids": [1]},
        headers=headers,
    )
    assert reorder_resp.status_code == 404


# ── Template duplicate ───────────────────────────────────────────────────────


def test_duplicate_template_deep_copy(client):
    assert register_user(client, email="user@example.com", name="User").status_code == 201
    headers = auth_headers(client, email="user@example.com")

    exercise1 = create_exercise(client, headers, name="Bench Press", is_public=True)
    exercise2 = create_exercise(client, headers, name="Incline Press", is_public=True)
    assert exercise1.status_code == 201
    assert exercise2.status_code == 201
    ex1_id = exercise1.json()["id"]
    ex2_id = exercise2.json()["id"]

    # Create template
    template_resp = client.post("/api/v1/templates/", json={"name": "Push Day"}, headers=headers)
    assert template_resp.status_code == 201
    template_id = template_resp.json()["id"]

    # Add 2 exercises
    te1 = client.post(
        f"/api/v1/templates/{template_id}/exercises",
        json={"exercise_id": ex1_id, "sets": 4, "reps": 8, "order_in_template": 1},
        headers=headers,
    )
    te2 = client.post(
        f"/api/v1/templates/{template_id}/exercises",
        json={"exercise_id": ex2_id, "sets": 3, "reps": 10, "order_in_template": 2},
        headers=headers,
    )
    assert te1.status_code == 201
    assert te2.status_code == 201

    # Duplicate the template
    dup_resp = client.post(f"/api/v1/templates/{template_id}/duplicate", headers=headers)
    assert dup_resp.status_code == 201
    dup = dup_resp.json()

    # Verify name
    assert dup["name"] == "Push Day (Copy)"
    assert dup["id"] != template_id

    # Verify exercises were copied
    original_exercises = client.get(f"/api/v1/templates/{template_id}/exercises", headers=headers)
    dup_exercises = client.get(f"/api/v1/templates/{dup['id']}/exercises", headers=headers)
    assert original_exercises.status_code == 200
    assert dup_exercises.status_code == 200

    orig_items = original_exercises.json()["items"]
    dup_items = dup_exercises.json()["items"]
    assert len(dup_items) == len(orig_items)

    # Verify exercise data matches (different IDs, same content)
    for orig, dup_te in zip(orig_items, dup_items):
        assert dup_te["id"] != orig["id"]
        assert dup_te["exercise_id"] == orig["exercise_id"]
        assert dup_te["sets"] == orig["sets"]
        assert dup_te["reps"] == orig["reps"]
        assert dup_te["order_in_template"] == orig["order_in_template"]


def test_duplicate_nonexistent_template(client):
    assert register_user(client, email="user@example.com", name="User").status_code == 201
    headers = auth_headers(client, email="user@example.com")

    response = client.post("/api/v1/templates/99999/duplicate", headers=headers)
    assert response.status_code == 404
