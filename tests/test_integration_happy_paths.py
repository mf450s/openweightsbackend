def register_user(client, *, email="athlete@example.com", name="Athlete"):
    return client.post(
        "/api/v1/auth/register",
        json={"name": name, "email": email, "password": "supersecret"},
    )


def login_user(client, *, email="athlete@example.com", password="supersecret"):
    return client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )


def auth_headers(client, *, email="athlete@example.com"):
    response = login_user(client, email=email)
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_authenticated_user_can_build_and_log_workout_happy_path(client):
    assert register_user(client).status_code == 201
    headers = auth_headers(client)

    settings_response = client.patch(
        "/api/v1/users/me/settings",
        json={"preferences": {"units": "metric", "rest_seconds": 120}},
        headers=headers,
    )
    assert settings_response.status_code == 200
    assert settings_response.json()["preferences"]["units"] == "metric"

    group_response = client.post(
        "/api/v1/exercises/muscle-groups/",
        json={"name": "Chest"},
        headers=headers,
    )
    assert group_response.status_code == 201

    region_response = client.post(
        "/api/v1/exercises/muscle-regions/",
        json={"name": "Upper Chest", "group_id": group_response.json()["id"]},
        headers=headers,
    )
    assert region_response.status_code == 201
    region_id = region_response.json()["id"]

    bench_response = client.post(
        "/api/v1/exercises/",
        json={
            "name": "Barbell Bench Press",
            "muscle_region_id": region_id,
            "laterality": "bilateral",
            "is_public": True,
            "execution_notes": "  pause briefly on the chest  ",
        },
        headers=headers,
    )
    assert bench_response.status_code == 201
    bench = bench_response.json()
    bench_id = bench["id"]
    assert bench["execution_notes"] == "pause briefly on the chest"

    dumbbell_response = client.post(
        "/api/v1/exercises/",
        json={
            "name": "Incline Dumbbell Press",
            "muscle_region_id": region_id,
            "laterality": "bilateral",
            "is_public": True,
        },
        headers=headers,
    )
    assert dumbbell_response.status_code == 201
    dumbbell_id = dumbbell_response.json()["id"]

    alternative_response = client.post(
        f"/api/v1/exercises/{bench_id}/alternatives/{dumbbell_id}",
        headers=headers,
    )
    assert alternative_response.status_code == 204
    alternatives_response = client.get(f"/api/v1/exercises/{bench_id}/alternatives", headers=headers)
    assert alternatives_response.status_code == 200
    assert [item["id"] for item in alternatives_response.json()] == [dumbbell_id]

    split_response = client.post(
        "/api/v1/splits/",
        json={"name": "Push Pull Legs", "description": "Three day rotation"},
        headers=headers,
    )
    assert split_response.status_code == 201
    split_id = split_response.json()["id"]

    template_response = client.post(
        "/api/v1/templates/",
        json={"name": "Push Day", "split_id": split_id, "order_in_split": 1},
    )
    assert template_response.status_code == 201
    template = template_response.json()
    template_id = template["id"]
    assert template["split_id"] == split_id

    template_exercise_response = client.post(
        f"/api/v1/templates/{template_id}/exercises",
        json={
            "exercise_id": bench_id,
            "sets": 3,
            "reps": 8,
            "rir": 2,
            "order_in_template": 1,
            "pause_seconds": 180,
            "weight_kg": 80.0,
        },
        headers=headers,
    )
    assert template_exercise_response.status_code == 201
    template_exercise = template_exercise_response.json()
    template_exercise_id = template_exercise["id"]
    assert template_exercise["template_id"] == template_id

    session_response = client.post(
        "/api/v1/sessions/",
        json={
            "template_id": template_id,
            "performed_at": "2026-02-01T09:30:00Z",
            "started_at": "2026-02-01T09:30:00Z",
            "ended_at": "2026-02-01T10:15:00Z",
            "notes": "  strong morning workout  ",
        },
        headers=headers,
    )
    assert session_response.status_code == 201
    workout_session = session_response.json()
    session_id = workout_session["id"]
    assert workout_session["user_id"] is not None
    assert workout_session["template_id"] == template_id
    assert workout_session["notes"] == "strong morning workout"

    first_set_response = client.post(
        f"/api/v1/sessions/{session_id}/sets",
        json={
            "template_exercise_id": template_exercise_id,
            "set_number": 1,
            "weight_kg": 80.0,
            "reps": 8,
            "rir": 2,
            "completed": True,
        },
        headers=headers,
    )
    assert first_set_response.status_code == 201
    first_set = first_set_response.json()
    assert first_set["exercise_id"] == bench_id
    assert first_set["personal_record"]["pr_type"] == "max_weight"

    second_set_response = client.post(
        f"/api/v1/sessions/{session_id}/sets",
        json={
            "exercise_id": bench_id,
            "set_number": 2,
            "side": "bilateral",
            "weight_kg": 85.0,
            "reps": 6,
            "rir": 1,
            "session_notes": "  top set  ",
            "completed": True,
        },
        headers=headers,
    )
    assert second_set_response.status_code == 201
    second_set = second_set_response.json()
    assert second_set["session_notes"] == "top set"
    assert second_set["personal_record"]["pr_type"] == "max_weight"

    sets_response = client.get(f"/api/v1/sessions/{session_id}/sets", headers=headers)
    assert sets_response.status_code == 200
    assert [item["set_number"] for item in sets_response.json()] == [1, 2]

    sessions_response = client.get("/api/v1/sessions/", headers=headers)
    assert sessions_response.status_code == 200
    assert [item["id"] for item in sessions_response.json()] == [session_id]

    history_response = client.get(f"/api/v1/exercises/{bench_id}/history", headers=headers)
    assert history_response.status_code == 200
    history = history_response.json()
    assert len(history) == 1
    assert history[0]["session_id"] == session_id
    assert [item["set_number"] for item in history[0]["sets"]] == [1, 2]

    estimated_1rm_response = client.get(f"/api/v1/exercises/{bench_id}/1rm", headers=headers)
    assert estimated_1rm_response.status_code == 200
    estimated_1rm = estimated_1rm_response.json()
    assert len(estimated_1rm) == 1
    assert estimated_1rm[0]["estimated_1rm"] > 85.0


def test_training_split_crud_happy_path_and_delete_detaches_templates(client):
    assert register_user(client).status_code == 201
    headers = auth_headers(client)

    create_response = client.post(
        "/api/v1/splits/",
        json={"name": "  Upper Lower  ", "description": "Four sessions per week"},
        headers=headers,
    )
    assert create_response.status_code == 201
    split = create_response.json()
    split_id = split["id"]
    assert split["name"] == "Upper Lower"
    assert split["description"] == "Four sessions per week"
    assert split["created_at"] is not None

    list_response = client.get("/api/v1/splits/", headers=headers)
    assert list_response.status_code == 200
    assert [item["id"] for item in list_response.json()] == [split_id]

    read_response = client.get(f"/api/v1/splits/{split_id}", headers=headers)
    assert read_response.status_code == 200
    assert read_response.json()["id"] == split_id

    update_response = client.patch(
        f"/api/v1/splits/{split_id}",
        json={"name": "Upper / Lower", "description": "Updated rotation"},
        headers=headers,
    )
    assert update_response.status_code == 200
    assert update_response.json()["name"] == "Upper / Lower"
    assert update_response.json()["description"] == "Updated rotation"

    template_response = client.post(
        "/api/v1/templates/",
        json={"name": "Upper A", "split_id": split_id, "order_in_split": 1},
    )
    assert template_response.status_code == 201
    template_id = template_response.json()["id"]

    delete_response = client.delete(f"/api/v1/splits/{split_id}", headers=headers)
    assert delete_response.status_code == 204

    read_deleted_response = client.get(f"/api/v1/splits/{split_id}", headers=headers)
    assert read_deleted_response.status_code == 404

    detached_template_response = client.get(f"/api/v1/templates/{template_id}")
    assert detached_template_response.status_code == 200
    detached_template = detached_template_response.json()
    assert detached_template["split_id"] is None
    assert detached_template["order_in_split"] is None
