# planA — Backend

## Project Overview
planA is a personal goal tracking application. It tracks objectives across the year, measures
what is being done to achieve them, and explicitly recognises what is being sacrificed in pursuit.
Goals compete for finite resources — time, recovery, attention, and willpower. The app surfaces
these tensions honestly without advising what to do.

Full design spec is in docs/planA-spec-v0.1.docx — read it for complete product context.

## Architecture
- **Pattern**: Thin routers → service layer → SQLAlchemy models
- **Routers**: app/routers/ (all routers live here)
- **Services**: app/services/ (all business logic lives here)
- **Models**: app/models/ (SQLAlchemy ORM — TimescaleDB hypertables for time series data)
- **Schemas**: app/schemas/ (Pydantic request/response)
- **Core**: app/core/ (database, Redis, Claude client)
- **Bot**: app/bot/ (Telegram handler, intent router, session manager)
- **Ingestion**: app/ingestion/ (Garmin and Strava sync jobs)
- **Intelligence**: app/intelligence/ (intent classification, milestone generation, memoir drafting)

## Tech Stack
- Python 3.11, FastAPI, SQLAlchemy, Alembic, Pydantic v2
- **TimescaleDB** (NOT plain PostgreSQL — metric readings are hypertables)
- Redis (conversation session memory + API response caching)
- python-telegram-bot (polling mode — no webhook, no public URL required)
- Poetry for dependency management
- APScheduler for Garmin and Strava ingestion jobs

## Deployment Model
**This is a local application.** It runs on a Mac mini and is accessed on the local network only.
- No Railway deployment
- No public URL
- No cloud hosting
- No authentication layer — single user, local network only
- Telegram is the only external communication channel
- Web app served by FastAPI static files, accessed at http://localhost:8000 or local IP

## Key Conventions
- All service methods take db as first argument
- Partial updates always use model_dump(exclude_unset=True)
- Missing resources raise 404 — there are no ownership checks (single user app)
- External services (Garmin, Strava, Claude API, Telegram) are behind abstractions
  with ENABLED flags for stub/real switching
- Never call external services directly from routers
- Timestamps always use datetime.now(timezone.utc) — never datetime.utcnow()
- TSS (Training Stress Score) is the unit for recovery load — used throughout
- Goal lifecycle states: Draft → Active → Primacy | Subordinate | Drifting → Released | Completed

## The planA Concept — Critical Context
Before writing any intelligence or interaction code, understand these principles:

**planA never tells the user what to do.** It surfaces reality and asks for acknowledgement.
When detecting drift, tension, or fade — surface it clearly, ask if the user wants to review,
and stop. Never recommend an action. Never suggest dropping a goal.

**Sacrifice is a first-class concept.** When a goal is missed or deprioritised, the app asks
which resource was depleted (time, recovery, attention, willpower) and why. This attribution
matters — it drives the longitudinal commitment profile.

**Release is the honest lifecycle end.** There is no "pause" state. A goal is either active
or released. Release is not failure — it is conscious closure with a generated memoir.

**Primacy tier goals are inviolable.** When a goal is planA, sacrifices against it are never
expected or accepted. Everything else yields to it.

## External Service Stubs
All external integrations have a stub mode controlled by env vars:

- **CLAUDE_ENABLED=false** → intelligence layer returns mock responses
  - Set to **true** for real Claude API calls
  - Requires ANTHROPIC_API_KEY
- **TELEGRAM_ENABLED=false** → bot handler logs messages but does not send
  - Set to **true** for real Telegram bot
  - Requires TELEGRAM_BOT_TOKEN
- **GARMIN_ENABLED=false** → ingestion returns mock health metrics
  - Set to **true** for real Garmin Connect sync
  - Requires GARMIN_EMAIL and GARMIN_PASSWORD
- **STRAVA_ENABLED=false** → ingestion returns mock activities
  - Set to **true** for real Strava API
  - Requires STRAVA_CLIENT_ID, STRAVA_CLIENT_SECRET, STRAVA_REFRESH_TOKEN
- **REDIS_ENABLED=false** → session memory and caching disabled
  - Set to **true** for Redis session memory (required for conversational check-ins)
  - Requires Redis at REDIS_URL

## Running the Project
```bash
# Start infrastructure (TimescaleDB + Redis)
docker compose up -d

# Run server (stub mode — no external credentials needed)
CLAUDE_ENABLED=false TELEGRAM_ENABLED=false GARMIN_ENABLED=false STRAVA_ENABLED=false REDIS_ENABLED=false poetry run uvicorn app.main:app --reload

# Run server (full mode — requires all credentials in .env)
poetry run uvicorn app.main:app --reload

# Database migrations
poetry run alembic upgrade head
poetry run alembic revision --autogenerate -m "description"

# Run tests
CLAUDE_ENABLED=false TELEGRAM_ENABLED=false GARMIN_ENABLED=false STRAVA_ENABLED=false REDIS_ENABLED=false poetry run pytest -v -m "not live"
```

## Telegram Bot
The Telegram bot runs in the same process as the FastAPI server, started in the lifespan handler.
It uses **polling** — no webhook, no public URL needed.

- Handler: app/bot/handler.py
- Intent router: app/bot/intent.py
- Session manager: app/bot/session.py (Redis-backed)

**Session memory:** Every incoming message retrieves the active session from Redis, appends the
message, injects current goal state context, and passes the full history to Claude. Sessions
expire after 30 minutes of inactivity. Goal state context is pulled fresh on every call.

**Morning check-in trigger:** Any message received before 10am local time triggers the morning
check-in flow. The bot does not push a morning notification — the user initiates by messaging.
After 10am, messages are treated as regular captures or interactions.

**Intent classification:** Incoming messages are classified by Claude into one of:
- morning_checkin — waking report: subjective feel, energy, sleep quality
- progress_capture — reporting an activity or work done toward a goal
- physical_state — physical symptom: sore, fatigued, injured, niggles
- illness_log — illness start, progression, or recovery note
- metric_log — a specific measurable value (weight, alcohol units, etc.)
- goal_query — question about goal status, progress, or resources
- activity_query — question about past workouts, rides, runs, or training sessions
- sacrifice_log — reporting a skipped or deprioritised commitment
- milestone_complete — reporting completion of a specific milestone
- goal_state_change — requesting a change to a goal's priority state
- free_response — continuation of conversation or anything else

Classification uses the last 3 session messages as context so short or ambiguous replies
(e.g. "2 before yesterday" after a cooking discussion) resolve correctly.

## Ingestion Jobs
Garmin and Strava data is pulled on a schedule via APScheduler:
- Garmin: polls hourly from 06:00–09:00, backstop at 07:30 and 10:00 if data hasn't appeared
- Strava: polls every 30 minutes
- On startup: Garmin catch-up runs immediately if today's readings are absent
- Ingestion jobs: app/ingestion/garmin.py, app/ingestion/strava.py
- Scheduler setup: app/ingestion/scheduler.py

**garminconnect library** is used for Garmin access (unofficial API, credential-based).
This is acceptable for personal use — formalise with official API later if needed.

## TimescaleDB Schema Notes
Metric readings (HRV, sleep score, TSS, weight, etc.) are stored as TimescaleDB hypertables
partitioned by timestamp. This is not plain PostgreSQL — hypertable creation must be done
via raw SQL in migrations, not Alembic autogenerate.

Pattern for hypertable creation in migrations:
```python
op.execute("SELECT create_hypertable('metric_readings', 'timestamp', if_not_exists => TRUE)")
```

Goal state, milestones, sacrifices, and sessions are standard PostgreSQL tables.

## Intelligence Layer
The intelligence layer (app/intelligence/) handles all LLM interactions:

- **intent.py**: Classify incoming messages — label and confidence, with session context
- **checkin.py**: Contextual morning check-in conversation
- **goal_query.py**: Answer questions about goal status, progress, and resources
- **activity_query.py**: Answer questions about past Strava activities
- **milestones.py**: Generate milestone progression from goal, deadline, capability baseline
- **memoir.py**: Draft goal reflection at completion or release from accumulated data
- **tension.py**: Plain language description of detected resource conflicts
- **patterns.py**: Periodic synthesis of commitment profile from sacrifice attribution history
- **week_context.py**: Date, week boundaries, and habit progress for system prompts

All LLM calls go through app/core/claude_client.py. The intelligence layer never calls
the Anthropic API directly.

**Model**: Always use claude-sonnet-4-6 for intelligence layer calls.

**Data provenance**: Always label injected structured data as coming from the database.
Never let Claude second-guess data provenance mid-session. Every system prompt that injects
real data (activities, goal state, resource calculations, metric readings) must explicitly
state that the data was retrieved from the database and is accurate.

## Resource Model
Four universal resources — every goal draws on all four:
- **Time**: Hours available per week. Envelope = 168 - sleep_hours - work_hours (~62hrs default)
- **Recovery**: TSS budget per week. Derived from 90-day Garmin/Strava baseline (~320 TSS default)
- **Attention**: Count of open decisions, active milestones, unresolved episodes this week
- **Willpower**: Pattern signal — sacrifice attribution over time, not a weekly capacity number

Time and recovery have real capacity numbers. Attention is a count. Willpower is longitudinal.
Do not attempt to express willpower as a percentage — it is a pattern observation only.

## Recovery Composite
The app builds its own recovery assessment — it does NOT trust Garmin body battery as primary.
Garmin's recovery algorithm is overly conservative and does not account for effort relative
to the user's fitness level.

Recovery composite weights:
- HRV morning reading: HIGH
- Subjective feel (Good/Neutral/Flat): HIGH — overrides algorithm when present
- Resting heart rate vs personal baseline: MEDIUM
- Sleep score and duration: MEDIUM
- Training intensity distribution relative to FTP: MEDIUM
- Body battery: LOW — present in data but not trusted as primary

Output states: Restored / Carrying Load / Depleted

## General Condition
Composite read of baseline health and capacity. Feeds resource envelope sizing.
Depleted general condition compresses the TSS tolerance for the week.
Sources: HRV, subjective feel, resting HR, sleep, training load, physical state log.

## Web Frontend
Simple HTML/JS frontend served by FastAPI static files at app/web/.
Five views: Now, Goals, Tension Map (greyed out), Reflection, Connectors.
No JavaScript framework — plain HTML, CSS, JS is sufficient.
No authentication — single user local app.

A natural language input bar is present on all views — same intent classification
pipeline as Telegram. Sends to POST /v1/capture.

## Testing Approach
Three levels:
1. **Unit tests** (tests/unit/): Service logic in isolation, SQLite, all external services mocked
2. **API tests** (tests/integration/api/): HTTP contracts via TestClient, stub mode
3. **Live tests** (tests/integration/live/): Real external services, marked @pytest.mark.live,
   run manually only

All non-live tests must pass before any session ends.
Never change test files to make tests pass — fix the implementation.

## Do Not
- Add authentication — this is a single user local app, no auth needed
- Use Railway or any cloud deployment — local only
- Use plain PostgreSQL image — always use timescale/timescaledb-ha
- Trust Garmin body battery as primary recovery signal
- Add a "pause" lifecycle state — release is the only honest closure
- Tell the user what to do in any intelligence layer output — surface only
- Use datetime.utcnow() — use datetime.now(timezone.utc) instead
- Hardcode any credentials or API keys
- Call external services directly from routers — always go through the service layer
- Skip tests — run the full non-live suite after every significant change
