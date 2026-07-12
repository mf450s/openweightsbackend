from datetime import date, timedelta

from app.models.session import SessionSet, WorkoutSession


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


def test_calendar_returns_sessions_grouped_by_day(client):
    assert register_user(client, email="user@example.com", name="User").status_code == 201
    headers = auth_headers(client, email="user@example.com")

    exercise = create_exercise(client, headers, name="Squat", is_public=True)
    assert exercise.status_code == 201
    exercise_id = exercise.json()["id"]

    # Create sessions on different days in July 2026
    session_day_1 = client.post(
        "/api/v1/sessions/",
        json={"performed_at": "2026-07-01T09:00:00Z"},
        headers=headers,
    )
    assert session_day_1.status_code == 201
    session_day_1_id = session_day_1.json()["id"]

    session_day_2 = client.post(
        "/api/v1/sessions/",
        json={"performed_at": "2026-07-02T10:00:00Z"},
        headers=headers,
    )
    assert session_day_2.status_code == 201
    session_day_2_id = session_day_2.json()["id"]

    # Two sessions on the same day (July 15)
    session_day_15_a = client.post(
        "/api/v1/sessions/",
        json={"performed_at": "2026-07-15T07:00:00Z"},
        headers=headers,
    )
    assert session_day_15_a.status_code == 201

    session_day_15_b = client.post(
        "/api/v1/sessions/",
        json={"performed_at": "2026-07-15T17:00:00Z"},
        headers=headers,
    )
    assert session_day_15_b.status_code == 201

    # Query calendar for July 2026
    response = client.get(
        "/api/v1/sessions/calendar?year=2026&month=7",
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()

    assert data["year"] == 2026
    assert data["month"] == 7

    # Should have 3 days with sessions
    assert len(data["days"]) == 3

    # Day 1 should have 1 session
    day_1 = [d for d in data["days"] if d["day"] == 1][0]
    assert len(day_1["sessions"]) == 1
    assert day_1["sessions"][0]["id"] == session_day_1_id

    # Day 2 should have 1 session
    day_2 = [d for d in data["days"] if d["day"] == 2][0]
    assert len(day_2["sessions"]) == 1
    assert day_2["sessions"][0]["id"] == session_day_2_id

    # Day 15 should have 2 sessions
    day_15 = [d for d in data["days"] if d["day"] == 15][0]
    assert len(day_15["sessions"]) == 2


def test_calendar_requires_auth(client):
    response = client.get("/api/v1/sessions/calendar?year=2026&month=7")
    assert response.status_code == 401


def test_calendar_empty_month(client):
    assert register_user(client, email="user@example.com", name="User").status_code == 201
    headers = auth_headers(client, email="user@example.com")

    response = client.get(
        "/api/v1/sessions/calendar?year=2026&month=7",
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["year"] == 2026
    assert data["month"] == 7
    assert data["days"] == []


def test_calendar_scoped_to_current_user(client):
    assert register_user(client, email="alice@example.com", name="Alice").status_code == 201
    assert register_user(client, email="bob@example.com", name="Bob").status_code == 201
    alice_headers = auth_headers(client, email="alice@example.com")
    bob_headers = auth_headers(client, email="bob@example.com")

    exercise = create_exercise(client, alice_headers, name="Deadlift", is_public=True)
    assert exercise.status_code == 201

    # Alice creates a session in July 2026
    alice_session = client.post(
        "/api/v1/sessions/",
        json={"performed_at": "2026-07-15T09:00:00Z"},
        headers=alice_headers,
    )
    assert alice_session.status_code == 201

    # Bob creates a session in July 2026
    bob_session = client.post(
        "/api/v1/sessions/",
        json={"performed_at": "2026-07-15T10:00:00Z"},
        headers=bob_headers,
    )
    assert bob_session.status_code == 201

    # Alice should only see her session
    alice_cal = client.get(
        "/api/v1/sessions/calendar?year=2026&month=7",
        headers=alice_headers,
    )
    assert alice_cal.status_code == 200
    assert len(alice_cal.json()["days"][0]["sessions"]) == 1
    assert alice_cal.json()["days"][0]["sessions"][0]["id"] == alice_session.json()["id"]

    # Bob should only see his session
    bob_cal = client.get(
        "/api/v1/sessions/calendar?year=2026&month=7",
        headers=bob_headers,
    )
    assert bob_cal.status_code == 200
    assert len(bob_cal.json()["days"][0]["sessions"]) == 1
    assert bob_cal.json()["days"][0]["sessions"][0]["id"] == bob_session.json()["id"]


def test_dashboard_stats_requires_auth(client):
    response = client.get("/api/v1/dashboard/stats")
    assert response.status_code == 401


def test_dashboard_stats_empty(client):
    assert register_user(client, email="user@example.com", name="User").status_code == 201
    headers = auth_headers(client, email="user@example.com")

    response = client.get("/api/v1/dashboard/stats", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["total_sessions"] == 0
    assert data["total_sets"] == 0
    assert data["total_volume"] == 0.0
    assert data["current_streak_days"] == 0
    assert data["this_week_sessions"] == 0
    assert data["this_week_volume"] == 0.0


def test_dashboard_stats_with_data(client):
    assert register_user(client, email="user@example.com", name="User").status_code == 201
    headers = auth_headers(client, email="user@example.com")

    exercise = create_exercise(client, headers, name="Squat", is_public=True)
    assert exercise.status_code == 201
    exercise_id = exercise.json()["id"]

    # Create a session with sets - use today so streak works
    today_str = date.today().isoformat()
    session_resp = client.post(
        "/api/v1/sessions/",
        json={"performed_at": f"{today_str}T09:00:00Z"},
        headers=headers,
    )
    assert session_resp.status_code == 201
    session_id = session_resp.json()["id"]

    # Add 2 sets with volume
    set1 = client.post(
        f"/api/v1/sessions/{session_id}/sets",
        json={
            "exercise_id": exercise_id,
            "set_number": 1,
            "weight_kg": 100.0,
            "reps": 10,
            "completed": True,
        },
        headers=headers,
    )
    assert set1.status_code == 201

    set2 = client.post(
        f"/api/v1/sessions/{session_id}/sets",
        json={
            "exercise_id": exercise_id,
            "set_number": 2,
            "weight_kg": 80.0,
            "reps": 8,
            "completed": True,
        },
        headers=headers,
    )
    assert set2.status_code == 201

    response = client.get("/api/v1/dashboard/stats", headers=headers)
    assert response.status_code == 200
    data = response.json()

    assert data["total_sessions"] == 1
    assert data["total_sets"] == 2
    # Volume: 100*10 + 80*8 = 1000 + 640 = 1640
    assert data["total_volume"] == 1640.0
    assert data["current_streak_days"] >= 1  # today's session counts
    assert data["this_week_sessions"] == 1
    assert data["this_week_volume"] == 1640.0
