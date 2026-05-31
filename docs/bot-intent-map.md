# planA Telegram Bot — Intent Map

Current as of: 2026-05-29  
Source files: `app/bot/handler.py`, `app/bot/handlers/` (11 handler files), `app/bot/intent.py`,  
`app/bot/session.py`, `app/intelligence/checkin.py`, `app/intelligence/goal_query.py`,  
`app/intelligence/activity_query.py`, `app/services/capture.py`,  
`app/bot/outreach.py`, `app/ingestion/scheduler.py`

---

## Classification pipeline

Every incoming text message passes through `classify_intent_with_confidence()` first.

**CLAUDE_ENABLED=true** — one Claude call returning `{"intent": "<label>", "confidence": 0.0–1.0}`.  
**CLAUDE_ENABLED=false** — keyword stub (see `_stub_classify`). Fixed confidence values per intent.

The result is one of eleven labels. Then the morning override fires:

```
if is_morning (before 10am) and intent != "free_response":
    original_intent = intent        ← saved before override
    intent = "morning_checkin"
```

This override is unconditional — physical_state, metric_log, illness_log, activity_query, and
progress_capture are all reassigned to morning_checkin before 10am. `original_intent` is preserved
and passed to `MorningCheckinHandler`, which uses it to write the original capture to the DB before
building the check-in response.

After classification and morning override, the message is dispatched to the appropriate handler
via `REGISTRY.get(intent)`. Each intent has its own handler class in `app/bot/handlers/`.

---

## Intents

### 1. `morning_checkin`

**What triggers it**  
Any message before 10am that isn't classified as `free_response`. Forced by the morning override
regardless of what the message actually says.

**Data injected into Claude prompt**  
`checkin.build_system_prompt()`:
- All non-terminal goals: state + title + description
- Primacy goal called out separately as "inviolable"
- Resource state: time committed vs envelope (hours + %), recovery committed vs TSS envelope (%), attention open-item count
- Today's Garmin readings (queried from DB): sleep_score, sleep_duration_hours, hrv, resting_hr, body_battery, stress — labelled as database-sourced
- Last 20 session messages for conversational continuity

**What gets written to the database**  
If `original_intent` is `physical_state`, `illness_log`, or `metric_log`, the corresponding
capture service is called before the check-in response is built. This preserves pre-10am health
reports even when intent is overridden.

**What the response looks like**  
Conversational check-in question from Claude — asks about physical and mental state, probes
capacity vs commitments. One question at a time, max 400 tokens.  
Stub: `"Good morning. How are you feeling today — physically and mentally? Good, neutral, or flat?"`

**Known gaps**  
- The check-in has no memory of yesterday's session unless Redis is live and the session
  hasn't expired (30-min TTL). A morning gap in conversation = cold start every day.
- No explicit end to the check-in conversation — it runs until something else is sent after 10am.
- The check-in system prompt doesn't explicitly acknowledge the physical/illness/metric
  data that was written from `original_intent` — it just runs the check-in format. The DB write
  happens correctly; the response doesn't reference it.

---

### 2. `progress_capture`

**What triggers it**  
Messages reporting activity just completed: "ran 10k", "cooked the recipe", "finished the chapter",
"trained this morning".  
Stub classifier triggers on: ran / cycled / trained / wrote / cooked / did / finished / completed.

**Data injected into Claude prompt**  
None. Goal matching is done in the service layer — no LLM call for this intent.

**What gets written to the database**  
`MetricReading(metric_type=habit_log, source=telegram)`:
- Matched: `text_value=str(goal_id)`, `notes=JSON{"goal_id": id, "text": original_text}`
- Unmatched: nothing written yet — sets `bot:pending_capture` in Redis and asks which goal

**Goal matching logic**  
1. `match_goal_by_keywords(text, goals)` — checks `goal.capture_keywords` JSON array, word-boundary match
2. `match_goal_title(text, goals)` — checks goal title, word-boundary match
3. If neither matches: stores pending capture in Redis and asks which goal

**What the response looks like**  
- Match found: `"Logged for {goal.title}."`  
- High confidence (>0.8), no match: `"Got it. Which goal was that for?"`  
- Low confidence, no match: `"Which goal was that for?"`

**Known gaps**  
- No metric extraction from progress text — distance, duration, TSS in the message are not parsed.
  Everything goes into `text_value` as raw text.
- No confirmation beyond the one-line reply — no milestone progress triggered.
- Keyword matching requires goals to have `capture_keywords` set. Most template-created goals
  won't have these populated unless set manually.

---

### 3. `physical_state`

**What triggers it**  
Messages reporting physical symptoms: "sore legs", "tired", "fatigue", "niggle", "aching".  
After 10am only — before 10am it gets overridden to morning_checkin (but the DB write still fires).

**Data injected into Claude prompt**  
`build_goals_system_prompt()` — goals only: state + title, primacy goal flagged. No Garmin data,
no resource state.

**What gets written to the database**  
`MetricReading(metric_type=physical_state, source=telegram, text_value=text[:500])`

**What the response looks like**  
Generic Claude conversational reply in the goal-state context. Max 400 tokens.  
Stub: `"Noted. Is this affecting today's training?"`

**Known gaps**  
- No Garmin data in the response context — Claude can't cross-reference what the morning HRV or
  sleep score was when responding to a physical state report.
- Physical state is written to the DB but has no effect on the recovery composite or
  the next morning check-in system prompt. The check-in queries Garmin only, not physical_state logs.

---

### 4. `illness_log`

**What triggers it**  
Messages about being ill: "sick", "ill", "cold", "flu", "fever", "recover".  
After 10am only (but pre-10am DB write fires via original_intent path).

**Data injected into Claude prompt**  
Same as physical_state — `build_goals_system_prompt()` with goals only.

**What gets written to the database**  
`MetricReading(metric_type=illness_log, source=telegram, text_value=text[:500])`

**What the response looks like**  
Generic Claude reply in goal-state context.  
Stub: `"Got it. How long have you been feeling this way?"`

**Known gaps**  
- Same as physical_state — no cross-reference with Garmin data in the response.
- No effect on the resource envelope or recovery composite.
- No duration tracking — "Day 3 of this cold" is written as a new row with no linkage to earlier illness rows.

---

### 5. `metric_log`

**What triggers it**  
Messages containing a measurable value: "75.2kg", "3 units", "drank 2 glasses of wine".  
Stub classifier triggers on: kg / lb / weight / unit / units / drink / alcohol / drank.  
After 10am only (but pre-10am DB write fires via original_intent path).

**Data injected into Claude prompt**  
`build_goals_system_prompt()` — goals only.

**What gets written to the database**  
`_parse_metric()` dispatches:
- Weight keywords (kg, lb, weigh) → `metric_type=weight`, `value=extracted_float`
- Alcohol keywords (unit, drink, beer, wine, alcohol) → `metric_type=alcohol_units`, `value=extracted_float`
- Anything else → `metric_type=habit_log`, `value=extracted_float`

All rows: `source=telegram`, `text_value=original_text[:500]`

**What the response looks like**  
Generic Claude reply.  
Stub: `"Logged."`

**Known gaps**  
- Only weight and alcohol are dispatched to typed metric rows. "My resting HR is 52", "HRV 58
  this morning", "sleep 7.5 hours" — all land in habit_log with no metric_type.
- No validation of the extracted number or unit coherence.

---

### 6. `goal_query`

**What triggers it**  
Questions about goal status, progress, or resources: "how is my training goal going", "what's
my tension this week", "am I on track".  
Stub classifier triggers on: goal / status / progress / tension / resource.

**Data injected into Claude prompt**  
`goal_query.build_context()` — for each non-terminal goal:
- State, goal_type, target_date, weekly_time_hours, weekly_target
- All milestones: sequence, state, target_date, achieved_at
- Sacrifice count for the last 30 days with top-3 resource breakdown

**What gets written to the database**  
Nothing.

**What the response looks like**  
Data-grounded Claude answer, max 400 tokens. Factual, no recommendations.  
Stub: `"{goal}: N/M milestones achieved"` for each active goal.

**Known gaps**  
- Resource capacity (time envelope, TSS envelope) is NOT included in the context. Questions
  like "am I over-committed?" get milestone/sacrifice data but no capacity numbers.
- Willpower pattern (sacrifice attribution over 28 days) is not included.
- No awareness of drift events or fade status — a drifting goal's context doesn't say it's drifting.
- No Garmin readings — "how is my recovery affecting my goals?" can't be answered.

---

### 7. `activity_query`

**What triggers it**  
Questions about past workouts: "what was my ride on Sunday", "how far did I run last week",
"show me yesterday's session".

Stub classifier requires all three:
- An activity keyword (ride / riding / rode / cycle / run / ran / swim / walk / etc.)
- A temporal keyword (yesterday / last / a weekday name / week / today / this morning)
- A query-starter word at the start of the message (how / what / show / tell / did / was / were)

**Date parsing** (`parse_date_reference()`):
- "yesterday", "today", "this morning" → that calendar day
- Weekday names ("Sunday", "last Monday") → most recent past occurrence of that day
- "last week" → previous Mon–Sun range
- ISO date (YYYY-MM-DD) → that day
- No temporal marker found → defaults to yesterday

**Activity type filtering** (`_parse_activity_type()`):
- run / ride / swim / walk — word-matched from the text
- None → returns all activity types

**Data injected into Claude prompt**  
`activity_query.build_context()` — all `MetricReading(metric_type=activity)` rows in the
parsed date range, filtered by sport type. Fields: timestamp, source, name, sport_type,
distance_m, moving_time_s, TSS, normalized_power_w, average_hr, max_hr.  
Sourced from Strava ingestion notes JSON.

**What gets written to the database**  
Nothing.

**What the response looks like**  
Claude answer describing the activities — distance, time, TSS, HR. Max 300 tokens.  
Stub: formatted bullet list of matched activities.

**Known gaps**  
- "This month", "past two weeks", "in May" — not handled. Falls back to yesterday.
- Only Strava-ingested activities. Manual progress captures (habit_log) not included.
- Stub classifier requires the message to start with a query word — "tell me about my ride
  yesterday" works, but "my Sunday ride, what was the TSS?" doesn't match.
- "All my training this week" looks for a single day range unless "last week" is present.

---

### 8. `sacrifice_log`

**What triggers it**  
Messages reporting a skipped commitment: "sacrificed my run for work", "skipped training because
of meetings", "missed my long ride this weekend".  
Stub classifier triggers on: sacrificed / skipped my / missed my / had to skip / couldn't do /
gave up my / skipped training / skipped the.  
Checked before `progress_capture` in the stub classifier to avoid ambiguity.

**Data injected into Claude prompt**  
None. All routing is deterministic.

**What gets written to the database**  
`Sacrifice(goal_id, resource, notes)`:
- `resource` is inferred via keyword rules in `extract_resource_from_text()`:
  - work / meeting / deadline / busy / job → `time`
  - tired / exhausted / sore / sleep / recover → `recovery`
  - distracted / focus / mind / attention → `attention`
  - motivation / willpower / discipline / mental → `willpower`
  - default → `time`
- Written only if a goal is matched. No sacrifice row if no goal match.

**What the response looks like**  
- Goal matched: `"Logged — sacrifice attributed to {resource}. {goal} sacrifice count now {N}."`
- No goal matched: `"Sacrifice noted — which goal did it affect?"`

**Known gaps**  
- No follow-up loop when a goal isn't matched — if the user replies with the goal name, it's
  classified as free_response and the sacrifice is lost (no pending_sacrifice state exists).
- Resource inference is simple keyword rules with no nuance — "I was too tired from work" could
  plausibly be either recovery or time but will always resolve to physical state keywords first.
- No Strava cross-reference — if the user missed a planned ride, the absence isn't confirmed
  against the activity log; it's just taken at face value.

---

### 9. `milestone_complete`

**What triggers it**  
Messages reporting milestone completion: "just finished my foundation milestone", "hit my 18km
milestone today", "done with the long run block".  
Stub classifier requires: completion verb (completed / finished / hit my / done with / achieved)
AND the word "milestone".

**Data injected into Claude prompt**  
None. All routing is deterministic.

**What gets written to the database**  
`Milestone(state=achieved)` via `update_milestone()`, if matched.

**What the response looks like**  
- Match found, more milestones remain: `"Milestone marked complete. {next} is next — due {date}."`
- Match found, last milestone: `"Milestone marked complete. No more pending milestones for that goal."`
- No match: `"I couldn't match that to a milestone — which one did you complete?"`

**Known gaps**  
- Matching is word-boundary on milestone titles only. If the user refers to a milestone by
  description rather than its exact title, it won't match.
- No pending state for the "which one?" case — if the user replies with the title, it's
  classified as free_response with no action.
- No Telegram notification at the time of Strava-triggered milestone completion (those go through
  a separate scheduler path) — so this intent only handles user-reported completions.

---

### 10. `goal_state_change`

**What triggers it**  
Messages requesting a goal priority change: "set cycling as my planA", "make training subordinate
now", "back to active please".  
Stub classifier triggers on phrases: "set as my plana" / "set as plana" / "make my plana" /
"as my plana" / "as my priority goal" / "set as priority" / "make subordinate" / "subordinate now" /
"back to active" / "set active" / "set as active".

**Data injected into Claude prompt**  
None. All routing is deterministic.

**What gets written to the database**  
`Goal(state=…)` via the lifecycle service:
- "primacy" → `goal_service.set_primacy()`
- "active" → `goal_service.activate_goal()`
- "subordinate" → `goal_service.set_subordinate()`
- "drifting" → `goal_service.mark_drifting()`

The lifecycle service enforces valid transitions. Invalid transitions raise an HTTPException
which is caught and returned as a message.

**What the response looks like**  
- Both goal and state matched: `"Done — {goal} is now {state}."`
- Goal not matched: `"Which goal did you want to change the state of?"`
- State not matched: `"What state? (planA, active, subordinate)"`
- Invalid transition: `"Couldn't change state: {error detail}"`

**Known gaps**  
- No pending state for the clarification cases — if the user answers "which goal?", their reply
  is free_response with no action.
- The stub classifier requires exact multi-word phrases; slight rewording ("put it as planA",
  "go back to active") won't match.
- `released` and `completed` are not accepted target states. There's no bot path to lifecycle-end
  a goal — that requires the web UI or direct API call.

---

### 11. `free_response`

**What triggers it**  
Anything not matched by the other classifiers — conversation continuations, replies to bot
questions, vague or ambiguous messages.

**Two sub-paths:**

**A. Pending capture resolution** (when `bot:pending_capture` exists)  
- Tries `match_goal_by_keywords(text, goals)` first, then `match_goal_title(text, goals)`
- Match found: writes `MetricReading(metric_type=habit_log)` with goal_id, clears pending, replies `"Logged for {title}."`
- No match: clears pending silently, falls through to sub-path B

**B. Ordinary free_response**  
- Data injected: `build_goals_system_prompt()` — goals state+title, primacy goal flagged. Nothing else.
- Response: Claude conversational reply, max 400 tokens.
- Stub: `"Tell me more."`

**What gets written to the database**  
Nothing unless resolving a pending capture, which writes habit_log.

**Known gaps**  
- Pending capture resolution silently drops the capture on no-match. The user receives a generic
  reply with no indication their progress report was lost.
- Generic system prompt has no resource data, Garmin readings, or milestone detail — resource
  or check-in follow-up questions in free conversation get an uninformed answer.

---

## Proactive outbound messages (scheduler-triggered)

These are not conversational — they originate from the APScheduler jobs in
`app/ingestion/scheduler.py` and send via `app/bot/outreach.py`. No session context.

### Drift alert

**Trigger** — Daily at 08:30. `detect_drift()` finds perpetual goals with metric readings
outside `target_min`/`target_max` for 3+ consecutive days (7-day lookback, gap breaks streak).  
Suppressed when: goal state is drifting/terminal/draft, `is_recovering=True`, no `target_metric_type`.

**Message format**  
```
{title} has been outside its target range for {N} consecutive days.

Metric: {metric_type}
Current: {value} — Target: {min}–{max}

Do you want to review this goal?
```

**What gets written to the database**  
The outreach function writes `{"goal_id": id, "alert_type": "drift"}` to `bot:pending_alert` in Redis.

**Reply handling**  
A yes reply (contains: yes / review / yeah / yep / please / sure / ok / okay) calls
`goal_query_module.build_response()` for the alerted goal and clears the pending alert.  
A no reply returns `"Noted."` and clears the pending alert.  
Any other reply leaves the alert in place and falls through to normal routing.

**Gap** — No automatic state change to `drifting` even on a yes reply — the user just gets a
goal summary. They have to issue a separate `goal_state_change` message to move the goal to
drifting state.

---

### Fade alert

**Trigger** — Every Monday at 09:00. `detect_fade()` finds achievement goals with no
milestone updates AND no Telegram captures for 14+ days. Goals created less than 14 days
ago are excluded.

Note: the "any Telegram capture" check is global (not per-goal) — any message at all
resets the fade clock, regardless of which goal it was for.

**Message format**  
```
No activity recorded for {title} in {N} days.

Is this goal still a priority?
```

**What gets written to the database**  
The outreach function writes `{"goal_id": id, "alert_type": "fade"}` to `bot:pending_alert` in Redis.

**Reply handling**  
Same as drift alert — yes returns a goal summary, no returns "Noted.".

**Gap** — Same bot:pending_alert key as drift: if both fire before the user replies, the second
overwrites the first. Also: fade suppression is too broad — a capture for goal A resets the fade
clock for goal B.

---

### Milestone progress notification

**Trigger** — Strava sync job (`_strava_job`), after `process_activity()` finds that an
ingested activity advances a milestone metric.

**Message format**  
- Milestone achieved: `"{activity_type} logged — {metric_str}. Milestone achieved: {title}."`
- Progress update: `"{activity_type} logged — {metric_str}. {period} {metric}: {current} / {target}."`

**What gets written to the database**  
Milestone state is updated by `process_activity()` before the notification fires.

**Gap** — Outbound only. No user acknowledgement flow, no reply expected.

---

## Message patterns that fall through to free_response incorrectly

These are message types that have a meaningful action the app could take, but currently
receive only a generic conversational reply:

| Message type | Example | Should be | Gap |
|---|---|---|---|
| Sacrifice with no goal match | "Skipped my long run" (no goal name found) | Pending sacrifice, ask which goal | No pending_sacrifice state; reply lands in free_response |
| Milestone complete with no title match | "Done with phase one" (title is "Foundation") | Pending milestone, ask which | No pending_milestone state; free_response |
| Goal state change — clarification reply | User answered "which goal?" with a name | Retry goal_state_change | free_response, no action |
| Typed metric: resting HR / HRV | "My resting HR is 52" | Write `resting_hr` MetricReading | Falls to `habit_log` in `_parse_metric()` |
| Activity query without query-starter | "My ride on Sunday, what was the TSS?" | activity_query | Stub classifier requires query-start word |
| Activity query beyond yesterday default | "What did I do in April?" | activity_query with month range | Date parser has no month/N-day-range support |
| Sacrifice acknowledgement in check-in | "I've been skipping runs for work" | Prompt for sacrifice attribution | No sacrifice capture in morning flow |
| Typed metric: sleep / HRV | "HRV 58 this morning" | Write `hrv` MetricReading | Falls to `habit_log` |

---

## Session and state

| Key | Store | TTL | Content |
|---|---|---|---|
| `bot:session` | Redis | 30 min (reset on every message) | JSON list of `{role, content}` dicts — last 20 used |
| `bot:pending_capture` | Redis | 30 min | `{text: str, confidence: float}` — a progress capture awaiting goal confirmation |
| `bot:pending_alert` | Redis | 30 min | `{goal_id: int, alert_type: "drift"\|"fade"}` — a proactive alert awaiting yes/no reply |

When Redis is unavailable (`REDIS_ENABLED=false`): session is always empty (cold start every message),
pending captures can't be stored (progress captures with no title match are silently lost),
and pending alerts can't be stored (drift/fade replies fall through to free_response).
