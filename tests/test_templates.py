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
    private_exercise = create_exercise(client, owner_headers, name="Paused Front Squat", is_public=False)
    assert public_exercise.status_code == 201
    assert private_exercise.status_code == 201
    public_exercise_id = public_exercise.json()["id"]
    private_exercise_id = private_exercise.json()["id"]

    create_template_response = client.post(
        "/api/v1/templates/",
        json={"name": "  Push Day  ", "order_in_split": 1},
    )
    assert create_template_response.status_code == 201
    template = create_template_response.json()
    template_id = template["id"]
    assert template["name"] == "Push Day"

    read_template_response = client.get(f"/api/v1/templates/{template_id}")
    assert read_template_response.status_code == 200
    assert read_template_response.json()["id"] == template_id

    update_template_response = client.patch(
        f"/api/v1/templates/{template_id}",
        json={"name": "Upper Body Push", "order_in_split": 2},
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
    assert add_private_exercise_without_auth.status_code == 400

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
    assert add_private_exercise_with_other_user.status_code == 400

    template_exercises = client.get(f"/api/v1/templates/{template_id}/exercises")
    assert template_exercises.status_code == 200
    items = template_exercises.json()
    assert len(items) == 2
    assert items[0]["id"] == private_template_exercise_id
    assert items[1]["id"] == public_template_exercise_id

    patch_template_exercise_response = client.patch(
        f"/api/v1/templates/{template_id}/exercises/{public_template_exercise_id}",
        json={"reps": 10, "order_in_template": 5},
    )
    assert patch_template_exercise_response.status_code == 200
    assert patch_template_exercise_response.json()["reps"] == 10
    assert patch_template_exercise_response.json()["order_in_template"] == 5

    move_to_private_without_auth = client.patch(
        f"/api/v1/templates/{template_id}/exercises/{public_template_exercise_id}",
        json={"exercise_id": private_exercise_id},
    )
    assert move_to_private_without_auth.status_code == 400

    delete_template_exercise_response = client.delete(
        f"/api/v1/templates/{template_id}/exercises/{private_template_exercise_id}"
    )
    assert delete_template_exercise_response.status_code == 204

    delete_template_response = client.delete(f"/api/v1/templates/{template_id}")
    assert delete_template_response.status_code == 204

    read_deleted_template = client.get(f"/api/v1/templates/{template_id}")
    assert read_deleted_template.status_code == 404


def test_template_endpoints_validation_and_not_found_cases(client):
    missing = client.get("/api/v1/templates/999")
    assert missing.status_code == 404

    invalid_create = client.post("/api/v1/templates/", json={"name": "x"})
    assert invalid_create.status_code == 422

    create_template = client.post("/api/v1/templates/", json={"name": "Leg Day"})
    assert create_template.status_code == 201
    template_id = create_template.json()["id"]

    invalid_exercise_reference = client.post(
        f"/api/v1/templates/{template_id}/exercises",
        json={"exercise_id": 999, "sets": 3},
    )
    assert invalid_exercise_reference.status_code == 400

    wrong_template_for_exercise = client.patch(
        f"/api/v1/templates/{template_id}/exercises/999",
        json={"sets": 4},
    )
    assert wrong_template_for_exercise.status_code == 404
