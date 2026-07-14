# Backend Report — OpenWeightsBackend

> Stand: Code-Head (Migration `a43125413950`), erstellt für Flutter/Dart-Frontend-Team.

---

## 1. Overview

| Attribut | Wert |
|---|---|
| **Base-URL** | `http://127.0.0.1:8000` (dev) / produktion gemäß Deployment |
| **API-Prefix** | `/api/v1` (konfigurierbar via `API_V1_PREFIX` / `api_v1_prefix`) |
| **Versionierung** | Keine explizite Version im Pfad außer `v1` im Prefix |
| **Auth** | Custom JWT (HMAC-SHA256, Base64-encoded) + Refresh-Token-Rotation |
| **CORS** | `CORSMiddleware` aktiviert: `allow_origins=["*"]`, alle Methods/Headers |
| **Middleware** | `GZipMiddleware` (ab 1000 Bytes), `CacheControlMiddleware` (private, max-age=60 auf GET 200) |
| **DB** | SQLite (dev) / PostgreSQL (prod), SQLModel + Alembic |

### Auth-Flow

1. **`POST /api/v1/auth/register`** — User anlegen → `201` + `UserRead`
2. **`POST /api/v1/auth/login`** — Email/Password → `AuthToken { access_token, refresh_token, token_type, user }`
3. **Bearer-Schema:** `Authorization: Bearer <access_token>`
4. **`POST /api/v1/auth/refresh`** — `{ refresh_token }` → neuen `AuthToken` + Rotation (altes revoked, neues Token mit selber `family_id`)
5. **`POST /api/v1/auth/logout`** — `{ refresh_token }` → revoked setzen, `204`
6. **Token-Format Access:** `base64(payload).base64(signature)` — Payload = `{ sub: "<user_id>", exp: <unixtime> }`
7. **Ablauf:** Access = 10080 Minuten (7 Tage, konfigurierbar), Refresh = 30 Tage
8. **Brute-Force-Schutz:** 5 Fehlversuche pro IP in 15 Minuten → `429 Too Many Requests`

---

## 2. Feature-Gruppen

### 2.1 Health

| Methode | Pfad | Auth | Zweck |
|---|---|---|---|
| GET | `/api/v1/health` | ❌ | Gesundheitscheck |

**Response `200`:** `{ "status": "ok" }`

**Fehler:** Keine (immer 200).

---

### 2.2 Auth

Basis-Pfad: `/api/v1/auth`

| Methode | Pfad | Auth | Zweck |
|---|---|---|---|
| POST | `/register` | ❌ | User registrieren |
| POST | `/login` | ❌ | Login + Token |
| POST | `/refresh` | ❌ | Access+Refresh-Token rotieren |
| POST | `/logout` | ❌ | Refresh-Token revoken |

#### POST `/register`

**Request `UserCreate`:**
```json
{
  "name": "string",              // required, min 2 chars, getrimmt
  "email": "string",             // required, regex: [^@\s]+@[^@\s]+\.[^@\s]+, lowercase+trim
  "password": "string"           // required, min 8 chars
}
```

**Response `201` — `UserRead`:**
```json
{
  "id": 1,
  "name": "string",
  "email": "string",
  "created_at": "2026-01-01T00:00:00Z"
}
```

**Fehler:**
| Status | Grund |
|---|---|
| 409 | Email existiert bereits |
| 422 | Validierungsfehler (Name zu kurz, Password zu kurz, Email-Format) |

#### POST `/login`

**Request `LoginRequest`:**
```json
{
  "email": "string",
  "password": "string"
}
```

**Response `200` — `AuthToken`:**
```json
{
  "access_token": "string",
  "refresh_token": "string",
  "token_type": "bearer",
  "user": {
    "id": 1,
    "name": "string",
    "email": "string",
    "created_at": "2026-01-01T00:00:00Z"
  }
}
```

**Fehler:**
| Status | Grund |
|---|---|
| 401 | Ungültige Email/Passwort, Header `WWW-Authenticate: Bearer` |
| 429 | Zu viele Versuche (5/15min pro IP) |
| 500 | User-ID fehlt (sollte nie vorkommen) |

#### POST `/refresh`

**Request `RefreshRequest`:**
```json
{
  "refresh_token": "string"
}
```

**Response `200` — `AuthToken`** (gleiches Format wie Login)

**Fehler:**
| Status | Grund |
|---|---|
| 401 | Ungültiges Refresh-Token |
| 401 | Token abgelaufen |
| 401 | Token revoken → **alle Token des Users werden revoked** (Reuse-Detection) |
| 500 | User nicht gefunden (DB-Inkonsistenz) |

#### POST `/logout`

**Request `RefreshRequest`:**
```json
{
  "refresh_token": "string"
}
```

**Response `204`** — kein Body. Auch wenn Token nicht existiert: `204`.

---

### 2.3 Users / Profile

Basis-Pfad: `/api/v1/users` — **alle Endpoints auth-pflichtig**

| Methode | Pfad | Zweck |
|---|---|---|
| GET | `/` | Aktuellen User zurückgeben (als Liste mit 1 Element) |
| GET | `/me` | Eigenes Profil lesen |
| PATCH | `/me` | Profil updaten |
| POST | `/me/password` | Passwort ändern |
| GET | `/me/settings` | Settings lesen (Auto-Create falls nicht existiert) |
| PUT | `/me/settings` | Settings komplett ersetzen |
| PATCH | `/me/settings` | Settings mergen (nur geänderte Keys) |
| DELETE | `/me` | Account + alle Daten löschen (Passwort-Bestätigung) |

#### GET `/` und GET `/me`

**Response `200` — `UserRead`:**
```json
{
  "id": 1,
  "name": "string",
  "email": "string",
  "created_at": "2026-01-01T00:00:00Z"
}
```

#### PATCH `/me`

**Request `UserUpdate` — alle Felder optional:**
```json
{
  "name": "string",     // optional, min 2 chars
  "email": "string"     // optional, gleiche Validierung wie Register
}
```

**Response `200` — `UserRead`**

**Fehler:**
| Status | Grund |
|---|---|
| 409 | Email bereits vergeben |

#### POST `/me/password`

**Request `UserPasswordUpdate`:**
```json
{
  "current_password": "string",
  "new_password": "string"    // min 8 chars
}
```

**Response `204`**

**Fehler:**
| Status | Grund |
|---|---|
| 400 | Aktuelles Passwort falsch |

#### GET `/me/settings`

**Response `200` — `UserSettingsRead`:**
```json
{
  "user_id": 1,
  "preferences": {},
  "updated_at": "2026-01-01T00:00:00Z"
}
```

#### PUT `/me/settings`

**Request `UserSettingsUpdate`:**
```json
{
  "preferences": { "key": "value" }
}
```

Kompletter Replace von `preferences`.

#### PATCH `/me/settings`

**Request `UserSettingsPatch`:**
```json
{
  "preferences": { "key": "value" }
}
```

Merged nur die mitgelieferten Keys in bestehende `preferences`.

#### DELETE `/me`

**Request `UserDeleteRequest`:**
```json
{
  "password": "string"
}
```

**Response `204`**

Löscht: alle Sessions + Sets, Templates + TemplateExercises, Splits, RefreshTokens, Settings. Setzt `created_by_user_id` auf `null` bei selbst erstellten Übungen. Löscht den User.

**Fehler:**
| Status | Grund |
|---|---|
| 400 | Passwort falsch |

---

### 2.4 Exercises & Muscle Data

Basis-Pfad: `/api/v1/exercises`

#### Muscle Groups

| Methode | Pfad | Auth | Zweck |
|---|---|---|---|
| GET | `/muscle-groups/` | ❌ | Alle Muscle-Gruppen (cached 300s) |
| POST | `/muscle-groups/` | ✅ | Neue Gruppe anlegen |

##### GET `/muscle-groups/`

**Query:** `limit` (default 200, max 1000), `offset` (default 0)

**Response `200` — `PaginatedResponse[MuscleGroupRead]`:**
```json
[
  { "id": 1, "name": "Chest" }
]
```

- `offset=0` → cached für 300s
- Nur auth-pflichtig für POST

##### POST `/muscle-groups/`

**Request `MuscleGroupCreate`:**
```json
{ "name": "string" }   // min 2 chars
```

**Response `201` — `MuscleGroupRead`**

**Fehler:** 409 bei Duplikat

#### Muscle Regions

| Methode | Pfad | Auth | Zweck |
|---|---|---|---|
| GET | `/muscle-regions/` | ❌ | Muscle-Regionen (gefiltert cached) |
| POST | `/muscle-regions/` | ✅ | Neue Region anlegen |

##### GET `/muscle-regions/`

**Query:** `group_id` (int, optional), `limit` (default 500, max 2000), `offset` (default 0)

**Response `200` — `PaginatedResponse[MuscleRegionRead]`:**
```json
[
  { "id": 1, "name": "Upper Chest", "group_id": 1 }
]
```

- Cached 300s wenn `offset=0` und `group_id` gesetzt

##### POST `/muscle-regions/`

**Request `MuscleRegionCreate`:**
```json
{
  "name": "string",     // min 2 chars
  "group_id": 1         // optional, muss existieren
}
```

**Response `201` — `MuscleRegionRead`**

**Fehler:**
| Status | Grund |
|---|---|
| 400 | `group_id` existiert nicht |
| 409 | Name + Group-Kombination bereits vorhanden |

#### Exercises (Haupt-CRUD)

| Methode | Pfad | Auth | Zweck |
|---|---|---|---|
| GET | `/` | optional | Übungen auflisten/filtern |
| GET | `/{exercise_id}` | optional | Einzel-Übung lesen |
| POST | `/` | ✅ | Übung anlegen |
| PATCH | `/{exercise_id}` | ✅ | Übung updaten (nur eigener Besitzer) |
| DELETE | `/{exercise_id}` | ✅ | Übung löschen (nur eigener Besitzer) |

##### GET `/`

**Query-Parameter:**
| Parameter | Typ | Default | Beschreibung |
|---|---|---|---|
| `search` | string | — | ILIKE-Suche auf Name |
| `muscle_region_id` | int | — | Filter auf Muskelregion |
| `muscle_group_id` | int | — | Filter auf Muskelgruppe (JOIN über Region) |
| `laterality` | string | — | `bilateral` / `unilateral` |
| `created_by` | string | — | `me` / `public` / `all` (nur mit Auth) |
| `limit` | int | 200 | max 1000 |
| `offset` | int | 0 | — |

**Zugriffslogik:**
- Ohne Auth: nur `is_public=true`
- Mit Auth + kein `created_by`: public + eigene
- `created_by=me`: nur eigene
- `created_by=public`: nur public
- `created_by=all`: public + eigene

**Response `200` — `PaginatedResponse[ExerciseRead]`:**
```json
[
  {
    "id": 1,
    "name": "Bench Press",
    "laterality": "bilateral",
    "created_by_user_id": null,
    "is_public": true,
    "execution_notes": null,
    "muscle_region_ids": [1, 2],
    "muscles": [
      { "id": 1, "name": "Upper Chest", "target_type": "primary" },
      { "id": 2, "name": "Triceps", "target_type": "secondary" }
    ]
  }
]
```

##### GET `/{exercise_id}`

**Zugriffslogik:** 
- Exercise existiert nicht → **404**
- Exercise existiert, aber privat + falscher Owner → **403 "Exercise is private."**
- Public oder eigener Besitzer → 200

**Response `200` — `ExerciseRead`**

**Fehler:**
| Status | Grund |
|---|---|
| 404 | Exercise existiert nicht |
| 403 | Exercise ist privat und gehört nicht dem User |

##### POST `/`

**Request `ExerciseCreate`:**
```json
{
  "name": "string",               // min 2 chars
  "laterality": "bilateral",      // default: bilateral
  "is_public": false,
  "execution_notes": null,
  "muscle_region_ids": [1, 2],    // optional, dedupliziert
  "muscle_region_id": 1           // deprecated, alternative zu muscle_region_ids
}
```

**Response `201` — `ExerciseRead`**

**Fehler:**
| Status | Grund |
|---|---|
| 400 | Muscle-Region-ID existiert nicht |
| 409 | User hat bereits Übung mit diesem Namen |

##### PATCH `/{exercise_id}`

**Request `ExerciseUpdate` — alle Felder optional:**
```json
{
  "name": "string",
  "muscle_region_ids": [1, 2],
  "muscle_region_id": 1,
  "laterality": "bilateral",
  "is_public": true,
  "execution_notes": "string"
}
```

**Response `200` — `ExerciseRead`**

**Fehler:**
| Status | Grund |
|---|---|
| 403 | Nicht der Besitzer (nur Ersteller kann editieren) |
| 404 | Nicht gefunden / kein Zugriff |
| 409 | Name bereits vorhanden |
| 400 | Muscle-Region existiert nicht |

##### DELETE `/{exercise_id}`

**Response `204`**

**Fehler:**
| Status | Grund |
|---|---|
| 403 | Nicht der Besitzer |
| 404 | Nicht gefunden / kein Zugriff |
| 409 | Übung wird in Templates oder Sessions verwendet → kann nicht gelöscht werden |

#### Exercise History

| Methode | Pfad | Auth | Zweck |
|---|---|---|---|
| GET | `/{exercise_id}/history` | ✅ | Set-Historie für eine Übung |
| GET | `/{exercise_id}/1rm-history` | ✅ | 1RM-Verlauf für eine Übung |

##### GET `/{exercise_id}/history`

**Query:** `limit` (default 50, max 500), `offset` (default 0)

**Response `200` — `list[ExerciseSessionHistory]`:**
```json
[
  {
    "session_id": 1,
    "performed_at": "2026-01-01T00:00:00Z",
    "sets": [
      { "set_number": 1, "weight_kg": 80.0, "reps": 10, "rir": 1 }
    ]
  }
]
```

Nur completed-Sets. Sortiert: `performed_at DESC, session_id DESC, set_number ASC`.

**Fehler:** 404 bei nicht gefundener/access denied Übung

##### GET `/{exercise_id}/1rm-history`

**Query:** `limit` (default 50, max 500), `offset` (default 0)

**Response `200` — `list[OneRmHistoryPoint]`:**
```json
[
  {
    "session_id": 1,
    "performed_at": "2026-01-01T00:00:00Z",
    "estimated_1rm": 95.5
  }
]
```

1RM-Berechnung: Durchschnitt aus Epley-, Brzycki- und Lander-Formeln. Effektive Reps = reps + rir.

**Fehler:** 404 bei nicht gefundener Übung

#### Exercise Alternatives

| Methode | Pfad | Auth | Zweck |
|---|---|---|---|
| GET | `/{exercise_id}/alternatives` | optional | Alternativübungen auflisten |
| POST | `/{exercise_id}/alternatives/{alternative_id}` | ✅ | Alternative verknüpfen |
| DELETE | `/{exercise_id}/alternatives/{alternative_id}` | ✅ | Verknüpfung lösen |

##### GET `/{exercise_id}/alternatives`

**Response `200` — `list[ExerciseRead]`** (bidirektionale Abfrage, in beide Richtungen)

##### POST `/{exercise_id}/alternatives/{alternative_id}`

**Response `204`**

Symmetrische Relation (wird mit `sorted()` normalisiert gespeichert). Der Besitzer der *ersten* Übung muss der aufrufende User sein.

**Fehler:**
| Status | Grund |
|---|---|
| 400 | exercise_id == alternative_id |
| 403 | Nicht Besitzer der exercise |
| 404 | Eine der Übungen nicht gefunden/access denied |

---

### 2.5 Training Splits

Basis-Pfad: `/api/v1/splits` — **alle Endpoints auth-pflichtig**, alle Daten gehören dem aktuellen User.

| Methode | Pfad | Zweck |
|---|---|---|
| GET | `/` | Alle eigenen Splits |
| GET | `/{split_id}` | Einzelnen Split lesen |
| POST | `/` | Split anlegen |
| PATCH | `/{split_id}` | Split updaten |
| DELETE | `/{split_id}` | Split löschen (setzt `split_id=null` bei zugehörigen Templates) |

#### GET `/`

**Query:** `limit` (default 100, max 500), `offset` (default 0)

**Response `200` — `PaginatedResponse[TrainingSplitRead]`:**
```json
[
  {
    "id": 1,
    "user_id": 1,
    "name": "Push/Pull/Legs",
    "description": "PPL Split",
    "created_at": "2026-01-01T00:00:00Z"
  }
]
```

#### POST `/`

**Request `TrainingSplitCreate`:**
```json
{
  "name": "string",      // min 2 chars
  "description": null    // optional
}
```

#### DELETE `/{split_id}`

Setzt bei allen Templates mit diesem `split_id` die Felder `split_id` und `order_in_split` auf `null`. Löscht den Split.

---

### 2.6 Workout Templates

Basis-Pfad: `/api/v1/templates`

| Methode | Pfad | Auth | Zweck |
|---|---|---|---|
| GET | `/` | ✅ | Eigene Templates (user-scoped) |
| GET | `/{template_id}` | ✅ | Ein Template (nur eigenes) |
| POST | `/` | ✅ | Template anlegen (setzt user_id) |
| PATCH | `/{template_id}` | ✅ | Template updaten (nur eigenes) |
| DELETE | `/{template_id}` | ✅ | Template + zugehörige TemplateExercises löschen |
| POST | `/{template_id}/duplicate` | ✅ | Template deep-copy (nur eigenes) |
| GET | `/{template_id}/exercises` | ✅ | TemplateExercises auflisten (nur eigenes Template) |
| POST | `/{template_id}/exercises` | ✅ | TemplateExercise hinzufügen |
| PATCH | `/{template_id}/exercises/{te_id}` | ✅ | TemplateExercise updaten |
| DELETE | `/{template_id}/exercises/{te_id}` | ✅ | TemplateExercise löschen |
| PUT | `/{template_id}/exercises/reorder` | ✅ | Reihenfolge ändern |

> **Hinweis:** Templates sind jetzt user-scoped. Jedes Template hat ein `user_id`-Feld (FK → users.id). Alle Endpoints sind auth-pflichtig. LIST/GET/PATCH/DELETE prüfen, ob das Template dem aktuellen User gehört (sonst 404).

#### GET `/`

**Query:** `limit` (default 100, max 500), `offset` (default 0)

**Response `200` — `PaginatedResponse[WorkoutTemplateRead]`:**
```json
[
  {
    "id": 1,
    "split_id": 1,
    "name": "Push Day",
    "order_in_split": 1
  }
]
```

#### POST `/`

**Request `WorkoutTemplateCreate`:**
```json
{
  "split_id": 1,        // optional
  "name": "string",     // min 2 chars
  "order_in_split": 1   // optional
}
```

#### POST `/{template_id}/duplicate`

Deep-Copy: neues Template mit Name + "(Copy)", kopiert alle `template_exercises` inkl. Felder.

**Response `201` — `WorkoutTemplateRead`**

#### GET `/{template_id}/exercises`

**Query:** `limit` (default 200, max 1000), `offset` (default 0)

**Response `200` — `PaginatedResponse[TemplateExerciseRead]`:**
```json
[
  {
    "id": 1,
    "template_id": 1,
    "exercise_id": 1,
    "sets": 4,
    "reps": 10,
    "rir": 1,
    "order_in_template": 1,
    "pause_seconds": 90,
    "weight_kg": 80.0,
    "updated_at": "2026-01-01T00:00:00Z"
  }
]
```

Sortiert nach `order_in_template ASC, id ASC`.

#### POST `/{template_id}/exercises`

**Request `TemplateExerciseCreate`:**
```json
{
  "exercise_id": 1,      // required, muss existieren & zugänglich
  "sets": 4,
  "reps": 10,
  "rir": 1,
  "order_in_template": 1,
  "pause_seconds": 90,
  "weight_kg": 80.0
}
```

**Response `201` — `TemplateExerciseRead`**

#### PUT `/{template_id}/exercises/reorder`

**Request `ReorderExercisesRequest`:**
```json
{
  "exercise_ids": [3, 1, 2]
}
```

Setzt `order_in_template` 1-indexed gemäß Array-Reihenfolge.

**Response `204`**

**Fehler:**
| Status | Grund |
|---|---|
| 404 | Eine ID existiert nicht in diesem Template |

---

### 2.7 Workout Sessions

Basis-Pfad: `/api/v1/sessions` — **alle Endpoints auth-pflichtig**, alle Daten gehören dem aktuellen User.

#### Session-CRUD

| Methode | Pfad | Zweck |
|---|---|---|
| GET | `/` | Eigene Sessions (paginated) |
| GET | `/{session_id}` | Einzelne Session |
| POST | `/` | Session anlegen |
| PATCH | `/{session_id}` | Session updaten |
| DELETE | `/{session_id}` | Session + alle Sets löschen |

#### Calendar

| Methode | Pfad | Zweck |
|---|---|---|
| GET | `/calendar` | Sessions eines Monats, gruppiert nach Tag |

#### Workout Execution

| Methode | Pfad | Zweck |
|---|---|---|
| POST | `/{session_id}/start` | Session starten (setzt `started_at` + `active_session=true`) |
| POST | `/{session_id}/end` | Session beenden (setzt `ended_at` + `active_session=false`, gibt Volume+PRs zurück) |

#### Session Sets

| Methode | Pfad | Zweck |
|---|---|---|
| GET | `/{session_id}/sets` | Alle Sets einer Session |
| POST | `/{session_id}/sets` | Ein Set anlegen (mit PR-Detection) |
| PATCH | `/{session_id}/sets/{set_id}` | Set updaten (mit PR-Detection) |
| DELETE | `/{session_id}/sets/{set_id}` | Set löschen |
| POST | `/{session_id}/sets/bulk` | Mehrere Sets auf einmal anlegen |
| POST | `/{session_id}/sets/bulk/delete` | Mehrere Sets auf einmal löschen |

#### GET `/`

**Query:** `limit` (default 100, max 500), `offset` (default 0)

**Response `200` — `PaginatedResponse[WorkoutSessionRead]`:**
```json
[
  {
    "id": 1,
    "user_id": 1,
    "template_id": null,
    "performed_at": "2026-01-01T00:00:00Z",
    "notes": null,
    "started_at": null,
    "ended_at": null,
    "active_session": true
  }
]
```

Sortiert: `performed_at DESC, id DESC`.

#### POST `/`

**Request `WorkoutSessionCreate`:**
```json
{
  "template_id": null,              // optional
  "performed_at": "2026-01-01T00:00:00Z",  // required
  "notes": null,                    // optional
  "started_at": null,
  "ended_at": null,
  "active_session": true
}
```

**Response `201` — `WorkoutSessionRead`**

**Fehler:** 400 wenn `template_id` nicht existiert

#### POST `/{session_id}/start`

**Response `200` — `WorkoutSessionRead`** (aktualisiert mit started_at=now, active_session=true)

#### POST `/{session_id}/end`

**Response `200`:**
```json
{
  "id": 1,
  "user_id": 1,
  "template_id": null,
  "performed_at": "...",
  "notes": null,
  "started_at": "...",
  "ended_at": "...",
  "active_session": false,
  "total_volume": 2500.50,
  "personal_records": [
    { "pr_type": "max_1rm", "value": 95.5 }
  ]
}
```

- `total_volume` = Summe aller completed `weight_kg * reps` (gerundet auf 2 Dezimalen)
- `personal_records` = alle PRs, die in dieser Session erzielt wurden

#### GET `/calendar`

**Query:** `year` (2020–2100, required), `month` (1–12, required)

**Response `200` — `CalendarResponse`:**
```json
{
  "year": 2026,
  "month": 1,
  "days": [
    {
      "day": 15,
      "sessions": [
        { "id": 1, "user_id": 1, ... }
      ]
    }
  ]
}
```

Nur Tage mit Sessions werden gelistet.

#### POST `/{session_id}/sets`

**Request `SessionSetCreate`:**
```json
{
  "exercise_id": 1,           // optional wenn template_exercise_id gesetzt
  "template_exercise_id": 1,  // optional
  "session_notes": null,
  "set_number": 1,            // required
  "side": null,               // "left" | "right" | "bilateral"
  "weight_kg": 80.0,
  "reps": 10,
  "rir": 1,
  "completed": true
}
```

**Response `201`:**
```json
{
  "id": 1,
  "session_id": 1,
  "exercise_id": 1,
  "template_exercise_id": 1,
  "session_notes": null,
  "set_number": 1,
  "side": null,
  "weight_kg": 80.0,
  "reps": 10,
  "rir": 1,
  "completed": true,
  "personal_record": { "pr_type": "max_1rm", "value": 95.5 }   // nur bei PR
}
```

**Fehler:**
| Status | Grund |
|---|---|
| 400 | exercise_id + template_exercise_id beide null |
| 400 | Exercise nicht zugänglich |

**PR-Detection** läuft automatisch bei Create/Update:
- `max_weight`: höchstes je gehobenes Gewicht
- `max_volume`: höchstes `weight * reps`
- `max_1rm`: höchster geschätzter 1RM (Durchschnitt Epley/Brzycki/Lander)

#### POST `/{session_id}/sets/bulk`

**Request `SessionSetBulkCreate`:**
```json
{
  "sets": [ { ... }, { ... } ]
}
```

Gleiches Set-Format wie Einzel-Anlage. Ein Transaction, PR-Detection für jedes Set.

**Response `200` — `list[SessionSetRead]`** (jeweils mit optionalem `personal_record`)

#### POST `/{session_id}/sets/bulk/delete`

**Request `SessionSetIdsDelete`:**
```json
{
  "set_ids": [1, 2, 3]
}
```

**Response `204`**

---

### 2.8 Dashboard

Basis-Pfad: `/api/v1/dashboard` — **auth-pflichtig**

| Methode | Pfad | Zweck |
|---|---|---|
| GET | `/stats` | Zusammenfassung: Sessions, Sets, Volume, Streak, Woche |

#### GET `/stats`

**Response `200` — `DashboardStats`:**
```json
{
  "total_sessions": 42,
  "total_sets": 315,
  "total_volume": 25000.75,
  "current_streak_days": 5,
  "this_week_sessions": 3,
  "this_week_volume": 4500.0
}
```

- `current_streak_days`: fortlaufende Tage ab heute (inklusiv) rückwärts mit mindestens einer Session
- `this_week`: Montag–Sonntag der aktuellen Woche

---

### 2.9 Database (Import/Export)

Basis-Pfad: `/api/v1/database` — **alle Endpoints auth-pflichtig**

| Methode | Pfad | Zweck |
|---|---|---|
| GET | `/export` | Komplette DB als ZIP aller CSV-Tabellen |
| GET | `/export/{table_name}` | Einzelne Tabelle als CSV |
| POST | `/import` | ZIP mit CSV-Tabellen importieren |
| POST | `/import/{table_name}` | Einzelne CSV-Tabelle importieren |

#### GET `/export`

**Response `200`:** ZIP-Datei (`application/zip`) mit je einer CSV pro Tabelle.

**Verfügbare Tabellen:**
| CSV-Name | DB-Table | Modell |
|---|---|---|
| `muscleGroups` | muscleGroups | MuscleGroup |
| `muscleRegions` | muscleRegions | MuscleRegion |
| `users` | users | User |
| `user_settings` | user_settings | UserSettings |
| `refresh_tokens` | refresh_tokens | RefreshToken |
| `exercises` | exercises | Exercise |
| `exercise_alternatives` | exercise_alternatives | ExerciseAlternative |
| `training_splits` | training_splits | TrainingSplit |
| `workout_templates` | workout_templates | WorkoutTemplate |
| `template_exercises` | template_exercises | TemplateExercise |
| `workout_sessions` | workout_sessions | WorkoutSession |
| `session_sets` | session_sets | SessionSet |
| `personal_records` | personal_records | PersonalRecord |

#### POST `/import`

**Request:** ZIP-Datei (`application/zip`) im Body. Enthält CSV-Dateien mit den Namen aus Tabelle oben.

**Query:** `?replace=false` — wenn `true`, werden existierende Daten vor Import gelöscht.

Import-Reihenfolge (FK-Abhängigkeiten): muscleGroups → muscleRegions → users → user_settings → refresh_tokens → exercises → exercise_alternatives → training_splits → workout_templates → template_exercises → workout_sessions → session_sets → personal_records.

**Response `200` — `ImportSummary`:**
```json
{
  "imported": { "exercises": 10, "muscleGroups": 5 },
  "replaced": false
}
```

**Fehler:**
| Status | Grund |
|---|---|
| 400 | Kein ZIP, unbekannte Tabellen, CSV-Validity, Constraint-Verletzungen |
| 400 | Unbekannte CSV-Columns |

---

## 3. Datenmodelle (DB-Schema)

### 3.1 Enum-Werte

| Enum | Werte | Verwendung |
|---|---|---|
| `Laterality` | `"bilateral"`, `"unilateral"` | Exercise.laterality |
| `Side` | `"left"`, `"right"`, `"bilateral"` | SessionSet.side |

### 3.2 Tabellen

#### `users`
| Spalte | Typ | Constraints |
|---|---|---|
| id | Integer | PK |
| name | String | NOT NULL |
| email | String | UNIQUE, INDEX |
| password_hash | String | NOT NULL |
| created_at | DateTime | NOT NULL |

#### `user_settings`
| Spalte | Typ | Constraints |
|---|---|---|
| user_id | Integer | PK, FK → users.id |
| preferences | JSON | NOT NULL, Default `{}` |
| updated_at | DateTime | NOT NULL |

#### `refresh_tokens`
| Spalte | Typ | Constraints |
|---|---|---|
| id | Integer | PK |
| user_id | Integer | FK → users.id, INDEX |
| token_hash | String | UNIQUE, INDEX |
| family_id | String | INDEX |
| expires_at | DateTime | NOT NULL |
| revoked | Boolean | Default false |
| created_at | DateTime | NOT NULL |

#### `muscleGroups`
| Spalte | Typ | Constraints |
|---|---|---|
| id | Integer | PK |
| name | String | INDEX |

#### `muscleRegions`
| Spalte | Typ | Constraints |
|---|---|---|
| id | Integer | PK |
| name | String | INDEX |
| group_id | Integer | FK → muscleGroups.id (nullable), INDEX |
| UNIQUE | (name, group_id) | `uq_muscle_region_name_per_group` |

#### `exercises`
| Spalte | Typ | Constraints |
|---|---|---|
| id | Integer | PK |
| name | String | INDEX |
| laterality | Enum (bilateral/unilateral) | Default bilateral |
| created_by_user_id | Integer | FK → users.id (nullable), INDEX |
| is_public | Boolean | INDEX, Default false |
| execution_notes | Text | nullable |
| UNIQUE | (name, created_by_user_id) | `uq_exercise_name_per_user` |

#### `exercise_muscle_regions`
| Spalte | Typ | Constraints |
|---|---|---|
| exercise_id | Integer | PK, FK → exercises.id |
| muscle_region_id | Integer | PK, FK → muscleRegions.id |
| target_type | String | Not null, Default "primary" |

Many-to-Many-Junction. Composite PK.

#### `exercise_alternatives`
| Spalte | Typ | Constraints |
|---|---|---|
| exercise_id | Integer | PK, FK → exercises.id |
| alternative_id | Integer | PK, FK → exercises.id, INDEX |

#### `training_splits`
| Spalte | Typ | Constraints |
|---|---|---|
| id | Integer | PK |
| user_id | Integer | FK → users.id, INDEX |
| name | String | NOT NULL |
| description | Text | nullable |
| created_at | DateTime | NOT NULL |

#### `workout_templates`
| Spalte | Typ | Constraints |
|---|---|---|
| id | Integer | PK |
| split_id | Integer | FK → training_splits.id (nullable), INDEX |
| user_id | Integer | FK → users.id (nullable), INDEX |
| name | String | NOT NULL |
| order_in_split | Integer | nullable |

#### `template_exercises`
| Spalte | Typ | Constraints |
|---|---|---|
| id | Integer | PK |
| template_id | Integer | FK → workout_templates.id (nullable), INDEX |
| exercise_id | Integer | FK → exercises.id (nullable), INDEX |
| sets | Integer | nullable |
| reps | Integer | nullable |
| rir | Integer | nullable |
| order_in_template | Integer | nullable |
| pause_seconds | Integer | nullable |
| weight_kg | Numeric(6,2) | nullable |
| updated_at | DateTime | nullable |

#### `workout_sessions`
| Spalte | Typ | Constraints |
|---|---|---|
| id | Integer | PK |
| user_id | Integer | FK → users.id (nullable), INDEX |
| template_id | Integer | FK → workout_templates.id (nullable), INDEX |
| performed_at | DateTime | NOT NULL, INDEX |
| notes | Text | nullable |
| started_at | DateTime | nullable |
| ended_at | DateTime | nullable |
| active_session | Boolean | Default true, NOT NULL |
| COMPOSITE INDEX | (user_id, performed_at, id) | Performance |

#### `session_sets`
| Spalte | Typ | Constraints |
|---|---|---|
| id | Integer | PK |
| session_id | Integer | FK → workout_sessions.id (nullable), INDEX |
| exercise_id | Integer | FK → exercises.id (nullable), INDEX |
| template_exercise_id | Integer | FK → template_exercises.id (nullable), INDEX |
| session_notes | Text | nullable |
| set_number | Integer | NOT NULL |
| side | Enum (left/right/bilateral) | nullable |
| weight_kg | Numeric(6,2) | nullable |
| reps | Integer | nullable |
| rir | Integer | nullable |
| completed | Boolean | Default true, NOT NULL |
| COMPOSITE INDEX | (session_id, set_number, id) | Performance |

#### `personal_records`
| Spalte | Typ | Constraints |
|---|---|---|
| id | Integer | PK |
| user_id | Integer | FK → users.id, INDEX |
| exercise_id | Integer | FK → exercises.id, INDEX |
| pr_type | String | INDEX (values: "max_weight", "max_volume", "max_1rm") |
| value | Numeric(6,2) | NOT NULL |
| achieved_at | DateTime | NOT NULL |
| session_set_id | Integer | FK → session_sets.id (nullable) |
| created_at | DateTime | NOT NULL |

### 3.3 Relationen

```
User 1──* WorkoutSession
User 1──* TrainingSplit
User 1──1 UserSettings
User 1──* RefreshToken

TrainingSplit 1──* WorkoutTemplate
WorkoutTemplate 1──* TemplateExercise
WorkoutTemplate 1──* WorkoutSession

Exercise 1──* TemplateExercise
Exercise 1──* SessionSet
Exercise 1──* PersonalRecord
Exercise *──* MuscleRegion (via exercise_muscle_regions)
Exercise *──* Exercise (via exercise_alternatives)

MuscleGroup 1──* MuscleRegion

WorkoutSession 1──* SessionSet

TemplateExercise 1──* SessionSet
```

---

## 4. Cross-Cutting Concerns

### Auth-Header
`Authorization: Bearer <access_token>` — immer via `HTTPBearer`.

### Pagination
Einheitlich: `limit` + `offset` Query-Parameter. Alle List-Endpoints returnen `PaginatedResponse`:
```json
{
  "items": [...],
  "total": 42,
  "limit": 100,
  "offset": 0
}
```
Damit kann das Frontend die Gesamtzahl ermitteln und Pagination-UI bauen.

### Error-Response-Format
Standard FastAPI-Fehlerformat:
```json
{
  "detail": "Error message text"
}
```
Kein einheitliches Error-Schema — nur das `detail`-Feld.

### Cache
In-Memory-Cache für `muscleGroups` und `muscleRegions` (300s TTL). Wird invalidated bei Create.

### Brute-Force-Schutz
In-Memory-Dict (`_login_attempts`) via IP → Timestamp-Liste. Reset bei erfolgreichem Login. Geht bei Server-Neustart verloren.

### Personal Records
Automatische PR-Detection beim Anlegen/Updaten von SessionSets. Drei PR-Typen: `max_weight`, `max_volume`, `max_1rm`. PR wird nur gespeichert, wenn neuer Wert > bisheriger Bestwert.

### 1RM-Berechnung
Durchschnitt aus Epley-, Brzycki- und Lander-Formel. Effektive Reps = `reps + rir`.

### Datei-Uploads
Keine Datei-Uploads vorhanden.

### WebSockets / Realtime
Nicht vorhanden.

### Caching-Header
Alle `GET 200`-Responses erhalten automatisch `Cache-Control: private, max-age=60`.

### GZip
Automatisch ab 1000 Byte Response-Größe.
