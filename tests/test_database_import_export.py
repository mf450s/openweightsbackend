import csv
import io
import zipfile


def register_user(client, *, email="owner@example.com", name="Owner"):
    return client.post(
        "/api/v1/auth/register",
        json={"name": name, "email": email, "password": "supersecret"},
    )


def auth_headers(client, *, email="owner@example.com"):
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "supersecret"},
    )
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_database_export_requires_auth(client):
    response = client.get("/api/v1/database/export/exercises")
    assert response.status_code == 401


def test_export_table_as_csv(client):
    assert register_user(client).status_code == 201
    headers = auth_headers(client)

    exercise_response = client.post(
        "/api/v1/exercises/",
        json={"name": "Bench Press", "laterality": "bilateral", "is_public": False},
        headers=headers,
    )
    assert exercise_response.status_code == 201

    response = client.get("/api/v1/database/export/exercises", headers=headers)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    rows = list(csv.DictReader(io.StringIO(response.text)))
    assert len(rows) == 1
    assert rows[0]["name"] == "Bench Press"
    assert rows[0]["laterality"] == "bilateral"
    assert rows[0]["is_public"] == "False"


def test_import_table_from_csv(client):
    assert register_user(client).status_code == 201
    headers = auth_headers(client)
    csv_payload = (
        "id,name,laterality,created_by_user_id,is_public,execution_notes\n"
        "10,Imported Row,unilateral,,true,Keep elbows tucked\n"
    )

    response = client.post(
        "/api/v1/database/import/exercises",
        content=csv_payload,
        headers={**headers, "Content-Type": "text/csv"},
    )

    assert response.status_code == 200
    assert response.json() == {"imported": {"exercises": 1}, "replaced": False}

    read_response = client.get("/api/v1/exercises/10", headers=headers)
    assert read_response.status_code == 200
    assert read_response.json()["name"] == "Imported Row"
    assert read_response.json()["is_public"] is True


def test_export_and_import_database_zip(client):
    assert register_user(client).status_code == 201
    headers = auth_headers(client)
    exercise_response = client.post(
        "/api/v1/exercises/",
        json={"name": "Squat", "laterality": "bilateral", "is_public": True},
        headers=headers,
    )
    assert exercise_response.status_code == 201
    exercise_id = exercise_response.json()["id"]

    export_response = client.get("/api/v1/database/export", headers=headers)
    assert export_response.status_code == 200

    with zipfile.ZipFile(io.BytesIO(export_response.content)) as archive:
        assert "exercises.csv" in archive.namelist()
        exported_exercises = archive.read("exercises.csv").decode()
    assert "Squat" in exported_exercises

    delete_response = client.delete(f"/api/v1/exercises/{exercise_id}", headers=headers)
    assert delete_response.status_code == 204

    import_response = client.post(
        "/api/v1/database/import?replace=true",
        content=export_response.content,
        headers={**headers, "Content-Type": "application/zip"},
    )
    assert import_response.status_code == 200
    assert import_response.json()["imported"]["exercises"] == 1

    restored_response = client.get(f"/api/v1/exercises/{exercise_id}", headers=headers)
    assert restored_response.status_code == 200
    assert restored_response.json()["name"] == "Squat"


def test_import_rejects_unknown_csv_columns(client):
    assert register_user(client).status_code == 201
    headers = auth_headers(client)

    response = client.post(
        "/api/v1/database/import/exercises",
        content="id,name,unknown\n1,Row,value\n",
        headers={**headers, "Content-Type": "text/csv"},
    )

    assert response.status_code == 400
    assert "Unknown columns" in response.json()["detail"]
