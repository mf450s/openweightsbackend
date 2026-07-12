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
        muscle_region_ids=[region_id],
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

    create_group_without_auth = client.post(
        "/api/v1/exercises/muscle-groups/", json={"name": "Legs"}
    )
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
        muscle_region_ids=[99999],
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
        json={"muscle_region_ids": [99999]},
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


def test_exercise_multiple_muscle_regions(client):
    assert register_user(client, email="owner@example.com", name="Owner").status_code == 201
    headers = auth_headers(client, email="owner@example.com")

    group = client.post(
        "/api/v1/exercises/muscle-groups/",
        json={"name": "Chest"},
        headers=headers,
    )
    assert group.status_code == 201
    group_id = group.json()["id"]

    region1 = client.post(
        "/api/v1/exercises/muscle-regions/",
        json={"name": "Upper Chest", "group_id": group_id},
        headers=headers,
    )
    assert region1.status_code == 201
    region1_id = region1.json()["id"]

    region2 = client.post(
        "/api/v1/exercises/muscle-regions/",
        json={"name": "Lower Chest", "group_id": group_id},
        headers=headers,
    )
    assert region2.status_code == 201
    region2_id = region2.json()["id"]

    create_response = create_exercise(
        client,
        headers,
        name="Incline Press",
        muscle_region_ids=[region1_id, region2_id],
    )
    assert create_response.status_code == 201
    data = create_response.json()
    assert set(data["muscle_region_ids"]) == {region1_id, region2_id}

    exercise_id = data["id"]
    read_response = client.get(f"/api/v1/exercises/{exercise_id}", headers=headers)
    assert read_response.status_code == 200
    assert set(read_response.json()["muscle_region_ids"]) == {region1_id, region2_id}

    list_response = client.get("/api/v1/exercises/", headers=headers)
    assert list_response.status_code == 200
    listed = [e for e in list_response.json() if e["id"] == exercise_id]
    assert len(listed) == 1
    assert set(listed[0]["muscle_region_ids"]) == {region1_id, region2_id}

    patch_response = client.patch(
        f"/api/v1/exercises/{exercise_id}",
        json={"muscle_region_ids": [region1_id]},
        headers=headers,
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["muscle_region_ids"] == [region1_id]

    clear_response = client.patch(
        f"/api/v1/exercises/{exercise_id}",
        json={"muscle_region_ids": []},
        headers=headers,
    )
    assert clear_response.status_code == 200
    assert clear_response.json()["muscle_region_ids"] == []


def test_exercise_filter_by_muscle_region_id(client):
    assert register_user(client, email="owner@example.com", name="Owner").status_code == 201
    headers = auth_headers(client, email="owner@example.com")

    group = client.post(
        "/api/v1/exercises/muscle-groups/",
        json={"name": "Chest"},
        headers=headers,
    )
    assert group.status_code == 201
    group_id = group.json()["id"]

    r1 = client.post(
        "/api/v1/exercises/muscle-regions/",
        json={"name": "Upper", "group_id": group_id},
        headers=headers,
    )
    assert r1.status_code == 201
    r1_id = r1.json()["id"]

    r2 = client.post(
        "/api/v1/exercises/muscle-regions/",
        json={"name": "Lower", "group_id": group_id},
        headers=headers,
    )
    assert r2.status_code == 201
    r2_id = r2.json()["id"]

    e1 = create_exercise(client, headers, name="Incline", muscle_region_ids=[r1_id])
    assert e1.status_code == 201
    e1_id = e1.json()["id"]

    e2 = create_exercise(client, headers, name="Decline", muscle_region_ids=[r2_id])
    assert e2.status_code == 201
    e2_id = e2.json()["id"]

    filter_r1 = client.get(f"/api/v1/exercises/?muscle_region_id={r1_id}", headers=headers)
    assert filter_r1.status_code == 200
    ids = [e["id"] for e in filter_r1.json()]
    assert e1_id in ids
    assert e2_id not in ids

    filter_r2 = client.get(f"/api/v1/exercises/?muscle_region_id={r2_id}", headers=headers)
    assert filter_r2.status_code == 200
    ids = [e["id"] for e in filter_r2.json()]
    assert e2_id in ids
    assert e1_id not in ids


def test_exercise_response_includes_muscles_array(client):
    assert register_user(client, email="owner@example.com", name="Owner").status_code == 201
    headers = auth_headers(client, email="owner@example.com")

    group = client.post(
        "/api/v1/exercises/muscle-groups/",
        json={"name": "Chest"},
        headers=headers,
    )
    assert group.status_code == 201
    group_id = group.json()["id"]

    r1 = client.post(
        "/api/v1/exercises/muscle-regions/",
        json={"name": "Upper Chest", "group_id": group_id},
        headers=headers,
    )
    assert r1.status_code == 201
    r1_id = r1.json()["id"]
    r1_name = r1.json()["name"]

    r2 = client.post(
        "/api/v1/exercises/muscle-regions/",
        json={"name": "Lower Chest", "group_id": group_id},
        headers=headers,
    )
    assert r2.status_code == 201
    r2_id = r2.json()["id"]
    r2_name = r2.json()["name"]

    create_response = create_exercise(
        client,
        headers,
        name="Flat Press",
        muscle_region_ids=[r1_id, r2_id],
    )
    assert create_response.status_code == 201
    data = create_response.json()
    assert "muscles" in data
    muscles = data["muscles"]
    assert len(muscles) == 2
    muscle_ids = {m["id"] for m in muscles}
    muscle_names = {m["name"] for m in muscles}
    target_types = {m["target_type"] for m in muscles}
    assert muscle_ids == {r1_id, r2_id}
    assert muscle_names == {r1_name, r2_name}
    assert target_types == {"primary"}


def test_legacy_muscle_region_id_accepted(client):
    assert register_user(client, email="owner@example.com", name="Owner").status_code == 201
    headers = auth_headers(client, email="owner@example.com")

    group = client.post(
        "/api/v1/exercises/muscle-groups/",
        json={"name": "Legs"},
        headers=headers,
    )
    assert group.status_code == 201
    group_id = group.json()["id"]

    region = client.post(
        "/api/v1/exercises/muscle-regions/",
        json={"name": "Quads", "group_id": group_id},
        headers=headers,
    )
    assert region.status_code == 201
    region_id = region.json()["id"]

    create_response = client.post(
        "/api/v1/exercises/",
        json={
            "name": "Squat",
            "laterality": "bilateral",
            "is_public": False,
            "muscle_region_id": region_id,
        },
        headers=headers,
    )
    assert create_response.status_code == 201
    data = create_response.json()
    assert region_id in data["muscle_region_ids"]


def test_exercise_deduplicate_muscle_region_ids(client):
    assert register_user(client, email="owner@example.com", name="Owner").status_code == 201
    headers = auth_headers(client, email="owner@example.com")

    group = client.post(
        "/api/v1/exercises/muscle-groups/",
        json={"name": "Back"},
        headers=headers,
    )
    assert group.status_code == 201
    group_id = group.json()["id"]

    region = client.post(
        "/api/v1/exercises/muscle-regions/",
        json={"name": "Lats", "group_id": group_id},
        headers=headers,
    )
    assert region.status_code == 201
    region_id = region.json()["id"]

    create_response = create_exercise(
        client,
        headers,
        name="Pull Up",
        muscle_region_ids=[region_id, region_id, region_id],
    )
    assert create_response.status_code == 201
    data = create_response.json()
    assert len(data["muscle_region_ids"]) == 1
    assert data["muscle_region_ids"] == [region_id]
    assert len(data["muscles"]) == 1


# --- Enhanced search & filter tests ---

def test_exercise_search_by_name(client):
    assert register_user(client, email="owner@example.com", name="Owner").status_code == 201
    headers = auth_headers(client, email="owner@example.com")

    create_exercise(client, headers, name="Bench Press", is_public=True)
    create_exercise(client, headers, name="Incline Bench Press", is_public=True)
    create_exercise(client, headers, name="Squat", is_public=True)

    resp = client.get("/api/v1/exercises/?search=bench", headers=headers)
    assert resp.status_code == 200
    names = [e["name"] for e in resp.json()]
    assert "Bench Press" in names
    assert "Incline Bench Press" in names
    assert "Squat" not in names

    resp = client.get("/api/v1/exercises/?search=SQUAT", headers=headers)
    assert resp.status_code == 200
    names = [e["name"] for e in resp.json()]
    assert "Squat" in names


def test_exercise_filter_by_laterality(client):
    assert register_user(client, email="owner@example.com", name="Owner").status_code == 201
    headers = auth_headers(client, email="owner@example.com")

    create_exercise(client, headers, name="Bench Press", laterality="bilateral", is_public=True)
    create_exercise(client, headers, name="Dumbbell Curl", laterality="unilateral", is_public=True)

    resp = client.get("/api/v1/exercises/?laterality=unilateral", headers=headers)
    assert resp.status_code == 200
    names = [e["name"] for e in resp.json()]
    assert "Dumbbell Curl" in names
    assert "Bench Press" not in names

    resp = client.get("/api/v1/exercises/?laterality=bilateral", headers=headers)
    assert resp.status_code == 200
    names = [e["name"] for e in resp.json()]
    assert "Bench Press" in names
    assert "Dumbbell Curl" not in names


def test_exercise_filter_by_muscle_group(client):
    assert register_user(client, email="owner@example.com", name="Owner").status_code == 201
    headers = auth_headers(client, email="owner@example.com")

    group1 = client.post(
        "/api/v1/exercises/muscle-groups/", json={"name": "Chest"}, headers=headers
    )
    assert group1.status_code == 201
    g1_id = group1.json()["id"]

    group2 = client.post(
        "/api/v1/exercises/muscle-groups/", json={"name": "Legs"}, headers=headers
    )
    assert group2.status_code == 201
    g2_id = group2.json()["id"]

    r1 = client.post(
        "/api/v1/exercises/muscle-regions/",
        json={"name": "Upper Chest", "group_id": g1_id},
        headers=headers,
    )
    assert r1.status_code == 201
    r1_id = r1.json()["id"]

    r2 = client.post(
        "/api/v1/exercises/muscle-regions/",
        json={"name": "Quads", "group_id": g2_id},
        headers=headers,
    )
    assert r2.status_code == 201
    r2_id = r2.json()["id"]

    create_exercise(client, headers, name="Bench Press", muscle_region_ids=[r1_id], is_public=True)
    create_exercise(client, headers, name="Squat", muscle_region_ids=[r2_id], is_public=True)

    resp = client.get(f"/api/v1/exercises/?muscle_group_id={g1_id}", headers=headers)
    assert resp.status_code == 200
    names = [e["name"] for e in resp.json()]
    assert "Bench Press" in names
    assert "Squat" not in names

    resp = client.get(f"/api/v1/exercises/?muscle_group_id={g2_id}", headers=headers)
    assert resp.status_code == 200
    names = [e["name"] for e in resp.json()]
    assert "Squat" in names
    assert "Bench Press" not in names


def test_exercise_filter_by_created_by(client):
    assert register_user(client, email="owner@example.com", name="Owner").status_code == 201
    assert register_user(client, email="other@example.com", name="Other").status_code == 201
    owner_headers = auth_headers(client, email="owner@example.com")
    other_headers = auth_headers(client, email="other@example.com")

    create_exercise(client, owner_headers, name="Owner Exercise Private", is_public=False)
    create_exercise(client, owner_headers, name="Owner Exercise Public", is_public=True)
    create_exercise(client, other_headers, name="Other Exercise Public", is_public=True)

    resp = client.get("/api/v1/exercises/?created_by=me", headers=owner_headers)
    assert resp.status_code == 200
    names = [e["name"] for e in resp.json()]
    assert "Owner Exercise Private" in names
    assert "Owner Exercise Public" in names
    assert "Other Exercise Public" not in names

    resp = client.get("/api/v1/exercises/?created_by=public", headers=owner_headers)
    assert resp.status_code == 200
    names = [e["name"] for e in resp.json()]
    assert "Owner Exercise Public" in names
    assert "Other Exercise Public" in names
    assert "Owner Exercise Private" not in names

    resp = client.get("/api/v1/exercises/?created_by=all", headers=owner_headers)
    assert resp.status_code == 200
    names = [e["name"] for e in resp.json()]
    assert "Owner Exercise Private" in names
    assert "Owner Exercise Public" in names
    assert "Other Exercise Public" in names


def test_exercise_search_combined_filters(client):
    assert register_user(client, email="owner@example.com", name="Owner").status_code == 201
    headers = auth_headers(client, email="owner@example.com")

    group = client.post(
        "/api/v1/exercises/muscle-groups/", json={"name": "Chest"}, headers=headers
    )
    assert group.status_code == 201
    gid = group.json()["id"]

    region = client.post(
        "/api/v1/exercises/muscle-regions/",
        json={"name": "Upper", "group_id": gid},
        headers=headers,
    )
    assert region.status_code == 201
    rid = region.json()["id"]

    create_exercise(
        client, headers, name="Bench Press",
        laterality="bilateral", muscle_region_ids=[rid], is_public=True,
    )
    create_exercise(
        client, headers, name="Squat",
        laterality="bilateral", is_public=True,
    )

    resp = client.get(
        f"/api/v1/exercises/?search=bench&muscle_group_id={gid}",
        headers=headers,
    )
    assert resp.status_code == 200
    names = [e["name"] for e in resp.json()]
    assert "Bench Press" in names
    assert "Squat" not in names


# --- History & 1RM history endpoint tests ---

def test_exercise_history_endpoint(client):
    assert register_user(client, email="owner@example.com", name="Owner").status_code == 201
    headers = auth_headers(client, email="owner@example.com")

    # Create an exercise
    exercise = create_exercise(client, headers, name="Squat", is_public=True)
    assert exercise.status_code == 201
    exercise_id = exercise.json()["id"]

    # Create two sessions with sets for this exercise
    session1 = client.post(
        "/api/v1/sessions/",
        json={"performed_at": "2026-01-02T10:00:00Z"},
        headers=headers,
    )
    assert session1.status_code == 201
    session1_id = session1.json()["id"]

    client.post(
        f"/api/v1/sessions/{session1_id}/sets",
        json={"exercise_id": exercise_id, "set_number": 1, "weight_kg": 100, "reps": 5, "completed": True},
        headers=headers,
    )

    session2 = client.post(
        "/api/v1/sessions/",
        json={"performed_at": "2026-01-01T10:00:00Z"},
        headers=headers,
    )
    assert session2.status_code == 201
    session2_id = session2.json()["id"]

    client.post(
        f"/api/v1/sessions/{session2_id}/sets",
        json={"exercise_id": exercise_id, "set_number": 1, "weight_kg": 90, "reps": 8, "completed": True},
        headers=headers,
    )

    # Access without auth should 401
    resp = client.get(f"/api/v1/exercises/{exercise_id}/history")
    assert resp.status_code == 401

    # Access with auth should succeed
    resp = client.get(f"/api/v1/exercises/{exercise_id}/history", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2

    # Should be ordered by performed_at DESC (session1 first since it's later)
    assert data[0]["session_id"] == session1_id
    assert data[1]["session_id"] == session2_id

    # Each entry should have session_id, performed_at, sets
    for entry in data:
        assert "session_id" in entry
        assert "performed_at" in entry
        assert "sets" in entry
        assert len(entry["sets"]) == 1
        assert "set_number" in entry["sets"][0]
        assert "weight_kg" in entry["sets"][0]
        assert "reps" in entry["sets"][0]

    # Test pagination
    resp = client.get(
        f"/api/v1/exercises/{exercise_id}/history?limit=1&offset=0",
        headers=headers,
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["session_id"] == session1_id

    resp = client.get(
        f"/api/v1/exercises/{exercise_id}/history?limit=1&offset=1",
        headers=headers,
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["session_id"] == session2_id


def test_exercise_1rm_history_endpoint(client):
    assert register_user(client, email="owner@example.com", name="Owner").status_code == 201
    headers = auth_headers(client, email="owner@example.com")

    # Create an exercise
    exercise = create_exercise(client, headers, name="Bench Press", is_public=True)
    assert exercise.status_code == 201
    exercise_id = exercise.json()["id"]

    # Create two sessions with sets that have weight+reps for 1RM estimation
    session1 = client.post(
        "/api/v1/sessions/",
        json={"performed_at": "2026-01-02T10:00:00Z"},
        headers=headers,
    )
    assert session1.status_code == 201
    session1_id = session1.json()["id"]

    # 100kg x 5 reps -> 1RM estimate
    client.post(
        f"/api/v1/sessions/{session1_id}/sets",
        json={"exercise_id": exercise_id, "set_number": 1, "weight_kg": 100, "reps": 5, "completed": True},
        headers=headers,
    )

    session2 = client.post(
        "/api/v1/sessions/",
        json={"performed_at": "2026-01-01T10:00:00Z"},
        headers=headers,
    )
    assert session2.status_code == 201
    session2_id = session2.json()["id"]

    # 90kg x 8 reps -> different 1RM estimate
    client.post(
        f"/api/v1/sessions/{session2_id}/sets",
        json={"exercise_id": exercise_id, "set_number": 1, "weight_kg": 90, "reps": 8, "completed": True},
        headers=headers,
    )

    # Access without auth should 401
    resp = client.get(f"/api/v1/exercises/{exercise_id}/1rm-history")
    assert resp.status_code == 401

    # Access with auth should succeed
    resp = client.get(f"/api/v1/exercises/{exercise_id}/1rm-history", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2

    # Should be ordered by performed_at DESC
    assert data[0]["session_id"] == session1_id
    assert data[1]["session_id"] == session2_id

    # Each entry should have session_id, performed_at, estimated_1rm
    for entry in data:
        assert "session_id" in entry
        assert "performed_at" in entry
        assert "estimated_1rm" in entry
        assert isinstance(entry["estimated_1rm"], float)

    # The first entry (session1) should have a higher 1RM than the second
    assert data[0]["estimated_1rm"] > data[1]["estimated_1rm"]

    # Test pagination
    resp = client.get(
        f"/api/v1/exercises/{exercise_id}/1rm-history?limit=1&offset=0",
        headers=headers,
    )
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["session_id"] == session1_id


def test_exercise_history_requires_auth(client):
    assert register_user(client, email="owner@example.com", name="Owner").status_code == 201
    headers = auth_headers(client, email="owner@example.com")

    exercise = create_exercise(client, headers, name="Press", is_public=True)
    exercise_id = exercise.json()["id"]

    resp = client.get(f"/api/v1/exercises/{exercise_id}/history")
    assert resp.status_code == 401

    resp = client.get(f"/api/v1/exercises/{exercise_id}/1rm-history")
    assert resp.status_code == 401


def test_exercise_history_for_nonexistent_exercise(client):
    assert register_user(client, email="owner@example.com", name="Owner").status_code == 201
    headers = auth_headers(client, email="owner@example.com")

    resp = client.get("/api/v1/exercises/99999/history", headers=headers)
    assert resp.status_code == 404

    resp = client.get("/api/v1/exercises/99999/1rm-history", headers=headers)
    assert resp.status_code == 404
