# planA Bot — Design Reference

Current as of: 2026-05-29  
Source: `app/bot/handler.py`, `app/bot/handlers/` (registry + 11 handler files),  
`app/bot/intent.py`, `app/bot/session.py`, `app/bot/outreach.py`, `app/services/capture.py`

---

## 1. Redis keys

All keys are global (no user-id prefix — single-user app). All share a 30-minute TTL that resets on every write. A Redis failure silently degrades: `get_*` returns None, `set_*` / `clear_*` no-op.

| Key | Constant | Content | Set by | Cleared by |
|---|---|---|---|---|
| `bot:session` | `SESSION_KEY` | JSON list of `{"role": str, "content": str}` — the full conversation history passed to Claude | `append_message()` on every message (both user and assistant turns) | `clear_session()` — not called automatically; survives until TTL |
| `bot:pending_capture` | `PENDING_CAPTURE_KEY` | `{"text": str, "confidence": float}` — a progress capture that couldn't be matched to a goal | `progress_capture` handler when no goal matched | `FreeResponseHandler` on resolution (success or failure); any non-`free_response` handler, since the dispatcher clears it before calling any handler whose `uses_pending_capture()` returns False |
| `bot:pending_alert` | `PENDING_ALERT_KEY` | `{"goal_id": int, "alert_type": "drift"\|"fade"}` — a proactive alert awaiting acknowledgement | `send_drift_alert()` / `send_fade_alert()` when a Redis client is provided | `handle_message` when the reply is affirmative or negative |

### TTL behaviour

All three keys are written with `setex(key, 1800, value)`. The TTL is not reset on read — only on write. A 30-minute gap in conversation lets any of these keys expire silently. There is no per-key TTL differentiation.

### When Redis is unavailable

`REDIS_ENABLED=false` or a connection failure causes `get_redis()` to return `None`. All session functions accept `None` and no-op. The bot remains functional but:
- Every message is a cold start (no conversation history)
- `pending_capture` cannot be stored — unmatched progress captures are permanently lost
- `pending_alert` cannot be stored — yes/no replies to drift/fade alerts fall through to `free_response`

---

## 2. Message handling flow

The full sequence inside `handle_message`, in priority order:

```
Incoming Telegram text message
          │
          ▼
1.  Guard: ignore non-text or empty messages
          │
          ▼
2.  Classify intent + confidence
    ├─ CLAUDE_ENABLED=true  → single Claude call → JSON {"intent", "confidence"}
    └─ CLAUDE_ENABLED=false → _stub_classify() keyword rules → fixed confidence values
          │
          ▼
3.  Save original_intent (used by MorningCheckinHandler and other handlers)
          │
          ▼
4.  Morning override
    └─ if before 10am AND intent != "free_response":
           intent = "morning_checkin"
    (original_intent is preserved and passed in HandlerContext)
          │
          ▼
5.  Append user message to bot:session
          │
          ▼
6.  Open DB session; load all goals
          │
          ▼
7.  Read bot:pending_capture and bot:pending_alert
          │
          ▼
8.  response_text = None
          │
          ▼
9.  Check bot:pending_alert ◄─── HIGHEST PRIORITY CHECK (runs in handle_message, pre-dispatch)
    ├─ Alert exists AND message is affirmative ("yes", "review", "yeah", etc.)
    │     → clear bot:pending_alert
    │     → goal_query_module.build_response([alert_goal], db, claude_client)
    │     → response_text = goal summary
    │
    ├─ Alert exists AND message is negative ("no", "not now", "dismiss", etc.)
    │     → clear bot:pending_alert
    │     → response_text = "Noted."
    │
    └─ Alert exists but message is neither → fall through, alert survives
          │
          ▼ (only if response_text is still None)
10. Handler dispatch via REGISTRY
          │
          ├─ handler = REGISTRY.get(intent)
          │
          ├─ if NOT handler.uses_pending_capture():
          │     clear bot:pending_capture   ← dispatcher clears; handler doesn't need to
          │
          └─ response_text = await handler.handle(ctx)
                │
                ├─ morning_checkin   → write_capture(original_intent) [Fix 1]
                │                      get_resource_tension() → checkin_module
                │
                ├─ progress_capture → match_goal_by_keywords() THEN match_goal_title()
                │                     ├─ match → record_progress() → "Logged for X."
                │                     └─ no match → set_pending_capture() → "Which goal?"
                │
                ├─ physical_state   → write_capture("physical_state") → Claude generic
                ├─ illness_log      → write_capture("illness_log")    → Claude generic
                ├─ metric_log       → write_capture("metric_log")     → Claude generic
                │
                ├─ goal_query       → goal_query_module.build_response()
                │
                ├─ activity_query   → parse_date_reference() + query_activities()
                │                     → activity_query_module.build_response()
                │
                ├─ sacrifice_log    → extract_resource_from_text()
                │                     match_goal_by_keywords() THEN match_goal_title()
                │                     ├─ match → record_sacrifice() → count message
                │                     └─ no match → "Which goal did it affect?"
                │
                ├─ milestone_complete → list open milestones for all active goals
                │                       match_milestone_title()
                │                       ├─ match → update_milestone(achieved) → "Marked complete."
                │                       └─ no match → "Which one did you complete?"
                │
                ├─ goal_state_change → extract_target_state_from_text()
                │                      match_goal_by_keywords() THEN match_goal_title()
                │                      ├─ both → lifecycle service call → "Done — X is now Y."
                │                      ├─ no goal  → "Which goal?"
                │                      └─ no state → "What state?"
                │
                └─ free_response [uses_pending_capture() = True — dispatcher does NOT clear]
                      ├─ pending_capture exists:
                      │     match_goal_by_keywords() THEN match_goal_title()
                      │     ├─ match → record_progress(pending_text, goal_id) → "Logged for X."
                      │     │          clear bot:pending_capture
                      │     └─ no match → clear bot:pending_capture (silently drop)
                      │                   fall through to generic reply
                      └─ no pending: Claude generic reply (build_goals_system_prompt)
          │
          ▼
11. Append assistant response to bot:session
          │
          ▼
12. Send reply to Telegram
```

---

## 3. Pending state mechanics

### pending_capture

**What sets it:** the `ProgressCaptureHandler`, when neither `match_goal_by_keywords` nor `match_goal_title` finds a match. Both high-confidence (>0.8) and low-confidence cases store the capture text and confidence; they only differ in the response wording.

**What reads it:** `session_mgr.get_pending_capture()` in `handle_message` before dispatch — passed in `HandlerContext.pending_capture`. `FreeResponseHandler` checks it internally.

**What clears it:**
- Successful resolution (`FreeResponseHandler` + keyword/title match → `record_progress`)
- Failed resolution (`FreeResponseHandler` + no match → drop silently)
- The dispatcher, before calling any handler whose `uses_pending_capture()` returns False — i.e., all handlers except `FreeResponseHandler`

**Lifetime:** up to 30 minutes from last write; cleared on the next message that dispatches to any handler other than `FreeResponseHandler`.

### pending_alert

**What sets it:** `send_drift_alert()` / `send_fade_alert()` in outreach.py, when called with a `redis_client`. The scheduler's `_dispatch_drift_alerts` and `_dispatch_fade_alerts` always provide a Redis client.

**What reads it:** `session_mgr.get_pending_alert()` — checked before handler dispatch in `handle_message`.

**What clears it:** a reply that matches `_YES_WORDS` or `_NO_WORDS`. Messages that don't match either leave the alert in place.

**Lifetime:** up to 30 minutes; not cleared by normal conversation — only by an explicit yes/no.

### Priority when both pending states exist simultaneously

The check order in `handle_message` is:

```
pending_alert check  (step 9, pre-dispatch)
    ↓ only if no response set
handler dispatch     (step 10)
    ↓ within FreeResponseHandler only:
    pending_capture check
```

Consequence: **a yes/no reply always resolves the alert first**. If `pending_capture` and `pending_alert` coexist:
- A "yes" reply → clears pending_alert, returns goal summary. `pending_capture` is untouched.
- A "no" reply → clears pending_alert, returns "Noted." `pending_capture` is untouched.
- The `pending_capture` then activates on the *next* message if it's a `free_response`.

This means a user mid-capture who then receives a drift alert and replies "yes" will get a goal summary, then face "Which goal was that for?" on their next message — which may be confusing.

A neutral reply (neither yes nor no) leaves the alert in place and falls through to handler dispatch. If the message classifies as `free_response` with a `pending_capture`, the capture resolution runs instead.

### What happens to pending_capture on no-match resolution

When `FreeResponseHandler` finds a `pending_capture` but `match_goal_by_keywords` and `match_goal_title` both return None, the capture is **silently dropped**. The original progress text is lost. No error, no explanation to the user. The next message is treated as a fresh conversation turn.

---

## 4. Handler registry

The routing system uses a registry pattern (`app/bot/handlers/`):

```
app/bot/handlers/
├── base.py            HandlerContext dataclass, IntentHandler ABC,
│                      write_capture(), build_goals_system_prompt(), claude_response()
├── registry.py        HandlerRegistry class + REGISTRY singleton
├── __init__.py        imports all 11 handler files, re-exports REGISTRY
├── morning_checkin.py
├── progress_capture.py
├── physical_state.py
├── illness_log.py
├── metric_log.py
├── goal_query.py
├── activity_query.py
├── sacrifice_log.py
├── milestone_complete.py
├── goal_state_change.py
└── free_response.py
```

Each handler file calls `REGISTRY.register(XyzHandler())` at module load time. Importing
`app.bot.handlers` triggers all registrations. `app.bot.intent.INTENTS` is derived from
`REGISTRY.all_intents()` — there is no separate hardcoded frozenset to maintain.

`HandlerContext` fields passed to every handler:

| Field | Type | Description |
|---|---|---|
| `text` | str | Original message text |
| `intent` | str | Classified intent (post-override) |
| `original_intent` | str | Intent before morning override |
| `is_morning` | bool | True if before 10am |
| `goals` | list | All goals from DB (active + terminal) |
| `db` | Session | SQLAlchemy session |
| `claude_client` | Anthropic \| None | None when CLAUDE_ENABLED=false |
| `redis_client` | Redis \| None | None when REDIS_ENABLED=false |
| `pending_capture` | dict \| None | Contents of bot:pending_capture |
| `pending_alert` | dict \| None | Contents of bot:pending_alert |
| `messages` | list | Session history (last 20) |
| `confidence` | float | Classification confidence |

`ctx.active_goals` is a property that filters `goals` to non-terminal states.

`IntentHandler` interface:

| Method | Default | Description |
|---|---|---|
| `handle(ctx) → str` | abstract | Returns the response string |
| `writes_to_db() → bool` | False | Informational; not currently enforced |
| `uses_pending_capture() → bool` | False | If True, dispatcher skips clearing pending_capture |

Only `FreeResponseHandler` returns `True` for `uses_pending_capture()`.

---

## 5. Intent reference

| Intent | Triggers (stub classifier) | DB write | Response type | Data injected to Claude |
|---|---|---|---|---|
| `morning_checkin` | Before 10am (forced override for all non-free_response) | `write_capture(original_intent)` if original was physical/illness/metric | Conversational check-in | Goals, resource envelope (time/TSS/attention), today's Garmin readings |
| `progress_capture` | "ran", "cycled", "trained", "wrote", "cooked", "did", "finished", "completed" | `MetricReading(habit_log)` if matched; nothing if pending | "Logged for X." or "Which goal?" | None (goal matching is deterministic) |
| `physical_state` | "sore", "ache", "pain", "tired", "fatigue", "niggle" | `MetricReading(physical_state)` | Generic Claude reply | Goals list only |
| `illness_log` | "sick", "ill", "cold", "flu", "fever", "recover" | `MetricReading(illness_log)` | Generic Claude reply | Goals list only |
| `metric_log` | "kg", "lb", "weight", "unit", "alcohol", "drank" | `MetricReading(weight\|alcohol_units\|habit_log)` | Generic Claude reply | Goals list only |
| `goal_query` | "goal", "status", "progress", "tension", "resource" | None | Data-grounded Claude reply | Goals, milestones (state/date/achieved_at), sacrifice counts last 30d |
| `activity_query` | Activity keyword + temporal keyword + query-starter word | None | Factual Claude reply | Strava activity rows in parsed date range |
| `sacrifice_log` | "sacrificed", "skipped my", "missed my", "had to skip", "couldn't do", "gave up my" | `Sacrifice(goal_id, resource, notes)` if matched | Count message or "Which goal?" | None |
| `milestone_complete` | Completion verb + "milestone" | `Milestone(state=achieved)` if matched | "Marked complete. Next is Y." or "Which one?" | None |
| `goal_state_change` | "set as my plana", "make subordinate", "back to active", etc. | `Goal(state=…)` via lifecycle service | "Done — X is now Y." or clarification | None |
| `free_response` | Catch-all; or reply resolving pending_capture | `MetricReading(habit_log)` only if resolving pending | Generic Claude reply (or "Logged for X.") | Goals list only |

**Note on the morning override:** before 10am, `physical_state`, `illness_log`, and `metric_log` are reclassified to `morning_checkin` after `original_intent` is saved. `MorningCheckinHandler.handle()` calls `write_capture(ctx.original_intent, ctx.text)` before building the check-in response, so the DB write still happens. The Claude response comes from the check-in module and does not explicitly reference the captured data.

---

## 6. Design weaknesses

### 6.1  Adding a new intent still requires four touches

The registry eliminates the if/elif routing block — a new handler is self-registering.
However, four other places still need updating manually for each new intent:
- `_USER_TEMPLATE` in `intent.py` — description for Claude's one-shot classification
- `_USER_TEMPLATE_CONFIDENCE` in `intent.py` — same description in the JSON-format prompt
- `_stub_classify()` in `intent.py` — keyword rules for CLAUDE_ENABLED=false mode
- `_STUB_CONFIDENCE` in `intent.py` — default confidence value for stub mode

There is no enforcement that all four are updated together. A new intent with a handler but missing
stub rules will fall through to `free_response` in stub mode, silently.

### 6.2  Single key per pending state — last write wins

`bot:pending_alert` is a single Redis key. If the scheduler fires a drift alert for goal A, then immediately fires a fade alert for goal B (two goals affected in the same scheduler run), the second `set_pending_alert` overwrites the first. The user's "yes" reply resolves the fade alert for goal B; the drift alert for goal A is permanently lost.

Similarly, `bot:pending_capture` holds only one capture at a time. A second unmatched progress capture overwrites the first.

### 6.3  No linkage between pending_alert and the originating message

`pending_alert` stores `goal_id` and `alert_type` but has no reference to the Telegram message that generated the alert. If the user sends several messages before responding to the alert, the conversation history grows but the alert-resolution code (`_is_affirmative` / `_is_negative`) will activate on any subsequent message that happens to contain "yes" or "no" — including "yes that was a hard week" or "no I didn't finish".

### 6.4  Affirmative/negative detection is substring-match, not position-aware

`_is_affirmative` and `_is_negative` scan the full message for any word from the respective sets. A message like "no, actually I did do my run — yes please show me" matches both sets. The affirmative check runs first, so the alert would be treated as acknowledged. There is no disambiguation.

### 6.5  Morning override is intent-transparent to Claude

When `physical_state` is overridden to `morning_checkin`, `MorningCheckinHandler` calls
`write_capture(ctx.original_intent, ...)` correctly, but the check-in module's system prompt
receives only the message text — it does not know the original intent was `physical_state`.
The check-in response is generated without explicitly noting "the user also reported a physical
symptom." The two pieces of information — the DB write (correct) and the Claude response
(check-in format) — are independent and don't reference each other.

### 6.6  No per-intent session context

The session is a flat chronological list. `goal_query` and `activity_query` both build rich structured context for their Claude calls, but that context is not stored in the session — only the plain text of the response is stored. A follow-up question ("which of those milestones is furthest behind?") will have the goal summary text in history but Claude will reconstruct it from conversational memory rather than from a fresh DB query. Stale or hallucinated details can creep in.

`morning_checkin` is the exception: it injects Garmin data and resource state fresh on every call via `checkin_module.build_response`, so its data stays current across turns.

### 6.7  Free-response resolution silently drops unmatched captures

If `pending_capture` exists and the user's reply doesn't match any goal by keyword or title, the capture text is discarded with no notification. The user receives a generic conversational reply and has no way to know their progress report was lost. This makes the user experience dependent on goal title or keyword coverage being high — a failing that is invisible until a capture is missed.

### 6.8  No pending state for sacrifice, milestone, and state-change clarifications

When `SacrificeLogHandler`, `MilestoneCompleteHandler`, or `GoalStateChangeHandler` can't find
a matching goal or milestone, they ask a clarifying question ("Which goal did it affect?"). But
there is no pending state for these — the next message is classified fresh. A direct answer
("my running goal") classifies as `free_response` and no action is taken. The entire capture is
lost if the user doesn't rephrase their original message with more identifying detail.

### 6.9  Fade detection suppression is global, not per-goal

`detect_fade` considers "any Telegram capture" (any MetricReading with source=telegram) as evidence of engagement. This resets the fade clock for *all* goals simultaneously. A user who logs one sacrifice for goal A resets the 14-day inactivity counter for goal B, even if goal B has had no actual activity.

### 6.10  Single-user key space blocks multi-user expansion

All Redis keys are global strings with no user-id component. Adding a second user would require a breaking change to every key name and every session function. This is intentional for the current single-user app model but is worth noting as a hard constraint.

### 6.11  `activate_goal` semantics mismatch

`goal_service.activate_goal` is documented as "Draft → Active" in its docstring, but the implementation uses `_assert_transition(goal, GoalState.active)` which accepts any valid source state. The `GoalStateChangeHandler` relies on this broader behaviour. If the service docstring were ever taken as specification and the function were tightened to reject non-draft sources, the bot's state-change routing would silently fail for primacy/subordinate/drifting → active transitions.
