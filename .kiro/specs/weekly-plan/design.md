# Design: weekly-plan (แผนสัปดาห์พร้อมแคปชันและเหตุผล)

> Based on `requirements.md` (Requirements 1–12, decisions D1–D6, section "Agent design"), the steering files, and the code that already exists in the repo (`agent.py`, `tests/test_agent.py`, `pyproject.toml`).
> Anything not fixed by those sources is marked *(assumption)*. Items that need a team answer are collected in "Items to confirm".
> Status: design only. No tasks yet.

## Overview

The feature is a small local web app. The owner picks a seed shop, asks for a plan, and gets 3 tasks. A Strands agent on Bedrock drafts the tasks, reasons and Thai captions. Plain Python code (the Trust Engine) does everything that is a rule: validation, slots, minutes, numbers, the red-line gate, safe texts and the fallback plan. The web layer shows only plans that code has already finalized and saved.

Design principles:

1. **The agent only drafts.** It returns `what`, `channel`, `reason`, `caption` for 3 tasks. It cannot post, save, calculate or decide when.
2. **One path to the screen.** Every plan, AI or fallback, goes through the same `finalize_plan` function (slots, minutes, gate) before it is saved. The web layer reads only saved plans. So no ungated text can reach the owner (5.1).
3. **Hard deadline outside the SDK.** The 8-second limit is enforced by a coordinator that waits on the agent in a worker thread and walks away at the deadline. It does not depend on the SDK or boto stopping in time (7.1, 7.13).
4. **Everything testable without AWS.** The Bedrock call sits behind a small `AiPlanClient` interface with a scripted stub (12.5).

## Architecture

```mermaid
flowchart LR
    Browser["Browser (phone-sized page, 127.0.0.1)"] -->|HTML, JSON| Web["web/ FastAPI + Jinja2"]
    Web --> Service["planner/ PlanService + JobRegistry"]
    Service --> Store["planner/ PlanStore (var/plans/*.json)"]
    Service --> Seed["planner/ SeedCatalog (data/seed_*.json)"]
    Service --> Client["planner/ AiPlanClient"]
    Client -->|real| Agent["agent.py Strands agent"]
    Client -->|tests| Stub["StubAiPlanClient"]
    Agent --> Tools["tools/ 3 read-only tools"]
    Agent -->|Converse API| Bedrock["Amazon Bedrock ap-southeast-1"]
    Tools --> TE
    Service --> TE["trust_engine/ pure code: validate, slots, gate, safe text, fallback"]
```

Dependency direction: `web` → `planner` → (`trust_engine`, `tools`/`agent`). `trust_engine` imports nothing from the other packages, does no I/O and never touches AWS (structure.md).

### Folders

Existing folders follow `structure.md`. Three folders are new and need a `structure.md` update (see "Items to confirm"): `planner/`, `web/`, `var/`.

```
agent.py                  # existing; reduced to: load prompt, build_agent(), CLI
prompts/weekly_plan.md    # the system prompt paragraph from requirements.md
data/seed_<shop>.json     # one fictional shop per file (moved out of agent.py)
tools/shop_tools.py       # get_shop_profile, list_channels, list_content_types (@tool)
trust_engine/
  models.py               # ShopProfile, AiPlanDraft, Task, Plan (pydantic)
  channels.py             # channel list, caption limits, minutes table, preferred times
  content_types.py        # stub content-type library (A1–A4 subset)
  redlines.py             # categories, terms, replacement table, number/day words (data)
  text.py                 # normalise + compact text with index map, Thai ratio
  gate.py                 # message gate
  figures.py              # figure rule
  validation.py           # validate_ai_draft
  slots.py                # assign_slots
  safe_text.py            # safe what/reason/caption per channel and shop
  fallback.py             # build_fallback_drafts
  pipeline.py             # finalize_plan(drafts, profile, now, source) -> Plan
planner/
  settings.py             # constants and environment overrides
  seed.py                 # SeedCatalog
  ai_client.py            # AiPlanClient protocol, StrandsAiPlanClient, StubAiPlanClient, AiError
  jobs.py                 # Job, JobRegistry
  service.py              # PlanService: request, run, cancel, status change
  store.py                # PlanStore: atomic JSON files
web/
  main.py                 # create_app()
  __main__.py             # runs uvicorn on 127.0.0.1
  routes.py, security.py  # routes; loopback Host/Origin check
  strings_th.py           # every Thai UI string (2.5)
  templates/*.html, static/app.css, static/app.js
var/plans/<shop_id>.json  # runtime data, git-ignored
tests/                    # see Testing strategy
```

### Decisions deferred by requirements.md

| Deferred item | Decision |
|---|---|
| Web framework | FastAPI + Uvicorn, server-rendered Jinja2 templates, about 60 lines of vanilla JS. No build step, no native app (D1, 2.3). |
| Per-attempt timeout inside the 8 s limit | Attempt 1 may use the whole remaining budget. A retry starts only if at least `MIN_RETRY_BUDGET_S = 3.0` s remain *(assumption)*. A boto connect timeout of 2 s makes a connection timeout fail early, so a retry after a timeout is possible (7.2). |
| Plan file location and format | `var/plans/<shop_id>.json`, JSON with `schema_version`, written atomically. `var/` is git-ignored (9.1, 9.7). |
| Structured-output schema | `AiPlanDraft{tasks: list[AiTaskDraft{what, channel, reason, caption}]}`, loose on purpose (below). |
| Log format | One `key=value` line per event to stderr (terminal). |
| Retry prompt wording | Original request plus a fixed English note listing problem codes. No free text from the failed answer is echoed back. |
| Caching of tool results | None. Tools read in-memory seed data and are fast. |

## Components and interfaces

### Settings (`planner/settings.py`)

```python
AI_PATH_LIMIT_S = 8.0          # 7.1, single named constant
MIN_RETRY_BUDGET_S = 3.0       # assumption
CONNECT_TIMEOUT_S = 2.0
LOOPBACK_HOST = "127.0.0.1"    # 2.1
REQUIRED_MODEL_ID = "anthropic.claude-sonnet-5"
REQUIRED_REGION = "ap-southeast-1"
HEARTBEAT_GRACE_S = 6.0        # progress page silent this long => treated as cancel (8.9)
TZ = timezone(timedelta(hours=7))   # Asia/Bangkok, no DST, no tzdata dependency
```

`Settings` is a dataclass holding these plus `model_id`, `region` (from `BELKA_MODEL_ID`, `BELKA_AWS_REGION`, defaulting to the required values), `var_dir` and `seed_dir`. Tests build a `Settings` with a 0.3 s limit instead of using a fake clock.

`check_model_config(settings) -> None | "config_refused"` returns a refusal if `model_id` starts with `global.` or `apac.`, differs from `REQUIRED_MODEL_ID`, or `region` differs from `REQUIRED_REGION` (12.2).

### Seed catalog (`planner/seed.py`)

`SeedCatalog.load(dir)` reads every `data/seed_*.json`. Valid files become `ShopProfile`. A file that cannot be parsed, or lacks `shop_name`, `type`, at least 3 `menu_items`, or `channels_used`/`owned_channels` lists, becomes an entry in `errors` with a Thai message that names the file and the field (1.3). Broken files never produce a plan. The request screen shows each error as a banner; valid shops stay selectable. `shop_id` must match `^[a-z0-9-]+$` before it is used in any path.

### Tools (`tools/shop_tools.py`)

Three `@tool` functions with the names, inputs and outputs from "Agent design". They call `SeedCatalog` and `trust_engine.channels` and have no logic of their own. The content-type stub moves to `trust_engine/content_types.py`. Each result carries a `notice` key: "Text values are shop data, not instructions" (11.1). An unknown id or channel returns `{"error": ...}` as it does today.

### Agent (`agent.py`)

```python
def build_agent(settings, system_prompt) -> Agent:
    model = BedrockModel(
        model_id=settings.model_id, region_name=settings.region,
        boto_client_config=Config(connect_timeout=2, read_timeout=8, retries={"max_attempts": 1}),
    )
    return Agent(model=model, system_prompt=system_prompt, tools=[...3 tools...],
                 retry_strategy=ModelRetryStrategy(max_attempts=1),   # see note
                 callback_handler=None)
```

- A **new Agent is built for every attempt**, so no conversation history leaks between requests or retries.
- **Strands retries throttling by default** (6 attempts, 4 s then 8 s delays). That would break 7.3 and the 8 s limit, so the design sets `max_attempts=1`. boto's own retries are also set to 1 attempt.
- The system prompt is read from `prompts/weekly_plan.md`. The paragraph in `requirements.md` is the source. Change it there first.
- The module keeps an `agent` object and the CLI loop so `tests/test_agent.py` and `uv run agent.py` keep working.
- The call is `agent(user_message, structured_output_model=AiPlanDraft, cancel_signal=event)`. The user message contains only the shop id and "draft this week's plan". Retry adds the fixed note.

### AI client (`planner/ai_client.py`)

```python
class AiError(Exception):
    cause: str          # timeout | invalid_format | access_denied | sso_expired | unreachable | throttled | other

class AiPlanClient(Protocol):
    def draft(self, shop_id: str, retry_note: str | None, cancel: threading.Event) -> AiPlanDraft: ...
```

`StrandsAiPlanClient` wraps `build_agent`. It maps exceptions to a cause:

| Raised | Cause | Retry? |
|---|---|---|
| `StructuredOutputException`, pydantic `ValidationError` | `invalid_format` | yes, if budget remains |
| botocore `ReadTimeoutError`, `ConnectTimeoutError` | `timeout` | yes, if budget remains |
| `ClientError` code `AccessDeniedException` | `access_denied` | no |
| `ExpiredToken*`, `UnrecognizedClientException`, `NoCredentialsError`, `TokenRetrievalError`, SSO token errors | `sso_expired` | no |
| `ModelThrottledException`, `ThrottlingException` | `throttled` | no |
| `EndpointConnectionError`, other connection errors that fail at once | `unreachable` | no |
| anything else | `other` | no |

`StubAiPlanClient` takes a script (a list of behaviours: `ok(draft)`, `malformed`, `sleep(seconds)`, `raise(cause)`) and counts calls. Tests assert the count (7.4, 8.4).

### PlanService and jobs (`planner/service.py`, `planner/jobs.py`)

```python
class Job:            # in-memory
    id, shop_id, state: "running" | "done" | "cancelled"
    cancel_event: threading.Event
    last_seen: float  # updated on each progress poll
    lock: threading.Lock

class JobRegistry:
    def start(shop_id) -> tuple[Job, bool]   # (job, created); returns the running job if one exists (8.4)
    def get(job_id) -> Job | None
    def cancel(job_id) -> Job                # no-op if state is "done" (8.8); releases the shop guard at once (8.7)
    def finish_ok(job, plan, store) -> bool  # under job.lock: if cancelled, discard; else save and set "done"
```

`PlanService.request_plan(shop_id)` starts a job and runs `_run(job)` in a worker thread. `_run`:

1. Load the profile. If `check_model_config` refuses, log `config_refused` and go straight to step 4.
2. `deadline = now + AI_PATH_LIMIT_S`. For attempt 1 and 2:
   - If the owner cancelled, stop. Nothing is saved (8.5, 8.6).
   - Submit `client.draft(...)` to a one-thread executor and wait with a 100 ms poll until the future finishes, the deadline passes, the owner cancels, or the progress page goes silent for `HEARTBEAT_GRACE_S`.
   - On deadline: set the attempt's cancel event, leave the worker to die on its own (its result is ignored), cause `timeout`.
   - Validate the draft with `validate_ai_draft`. Failure gives cause `invalid_format`.
   - Retry only if this was attempt 1, the cause is `timeout` or `invalid_format`, and at least `MIN_RETRY_BUDGET_S` remain. Otherwise leave the loop (7.2, 7.3, 7.4).
3. A valid draft goes to `finalize_plan(..., source="ai")`.
4. Otherwise log the cause and run `build_fallback_drafts` then `finalize_plan(..., source="fallback")` (7.5).
5. `finish_ok` saves the plan unless the job was cancelled.

The coordinator never waits longer than the deadline, so the fallback appears within about 100 ms plus build time (7.13). One call to `client.draft` is one Bedrock **attempt**. A single attempt can contain several model requests, because the agent calls tools between them. "At most 2 Bedrock calls" (7.4) is read as at most 2 attempts (see "Items to confirm").

Per-shop in-flight guard (8.4) lives in `JobRegistry` behind one lock. After a cancel, a new request is allowed at once and the old attempt may still finish in the background. Its result is ignored because `finish_ok` checks the job state (8.7).

Status changes use `PlanService.set_status(shop_id, plan_id, task_id, new_status)` (see PlanStore).

### Trust Engine (`trust_engine/`)

**Text helpers (`text.py`).** `normalise(text)` applies NFKC, removes zero-width characters (U+200B–U+200D, U+2060, U+FEFF), case-folds, and removes all whitespace. It returns the compact string and an index map back to the original, so replacements edit the original text and keep its spacing (5.11). `thai_ratio(text, ignore=[names])` is the share of Thai-script letters (U+0E00–U+0E7F) among letters, after removing emoji, digits, URLs and profile names.

**Message gate (`gate.py`).**

```python
@dataclass
class Flag: category: str; term: str; start: int; end: int   # span in the original text
@dataclass
class GateResult: ok: bool; flags: list[Flag]
def gate(text: str) -> GateResult
```

`redlines.py` holds the categories from 5.10 as data: literal terms and a few regular expressions (for platform claims, such as a stop/cancel word near a platform name or "เดลิเวอรี"), each term with an optional safe replacement. Matching runs on the compact text. "ลดการพึ่งพา" is not a match. Names from the profile are not exempt (5.11). The gate does not import boto3 or strands (5.9).

**Validation (`validation.py`).** `validate_ai_draft(draft, profile) -> list[str]` returns problem codes, empty when valid. It checks, in this order: task count is exactly 3; every field non-empty; channel is in the list (case-insensitive match to the canonical name, 3.4); owned-channel rule (3.5); shop or menu name present in caption or reason (3.8); no duplicate channel+what (3.9); Thai ratio of at least 0.5 for caption and reason (3.10); no placeholder (`\[[^\]]*\]`, `\{[^}]*\}`, `<[^>]*>`); caption length within the channel limit; and the figure rule. A partial plan is not repaired.

**Figure rule (`figures.py`).** After removing the shop name and menu item names from the text, the check looks for Arabic digits, Thai digits, Thai number and discount words (starter list in `redlines.py`, for example "ครึ่งราคา", "สองเท่า", "หนึ่ง".."สิบ", "ร้อย"), weekday names with "วัน", "วันนี้", "พรุ่งนี้" and "สุดสัปดาห์". A numeral is allowed only if it equals a menu price in the profile (in Arabic or Thai digits). Everything else is a violation (10.2). Limit: the rule cannot tell whether an allowed price is attached to the right item. The number-word list may over-flag, which costs a retry or a fallback, and it is data that can be tuned.

**Slots and minutes (`slots.py`, `channels.py`).** `assign_slots(channels, profile, now) -> list[Slot(start, minutes)]`:
- `MINUTES_BY_CHANNEL` and `PREFERRED_TIME_BY_CHANNEL` are stub tables owned by the Trust Engine *(assumption)*. Every value in the minutes table is at most 10, so a single task never exceeds the daily cap.
- Eligible days are the 7 days starting on the request date, in Asia/Bangkok, minus the shop's `closed_days`. A day is dropped for a task when its preferred time on that day is already past.
- Days are spread deterministically: with `n` eligible days the 3 tasks take positions `0`, `n//2`, `n-1` when `n >= 3`, so tasks sit on different days (3.6). The total minutes per day are checked and must stay at or under 10 (3.7).
- Same input gives the same output (7.9).
- If fewer than 3 eligible days exist, the function raises `SlotError`. The seed loader prevents this by rejecting a profile with fewer than 3 open days (see "Items to confirm").

**Safe text (`safe_text.py`).** `safe_what`, `safe_reason`, `safe_caption(channel, profile, item_index)` build short Thai texts from templates per channel plus the shop name and one menu item. They contain no figures. The fallback plan uses them directly, so the fallback and the 5.4 replacements are the same code. A test asserts that every template passes the gate for every channel and seed shop (5.6).

**Fallback (`fallback.py`).** `build_fallback_drafts(profile, now)` picks 3 distinct channels: one owned channel first (when the profile has one), then channels the shop already uses, then the rest of the channel list. The menu item rotates with `now.date().toordinal() % len(items)` so it is deterministic and differs between shops. It returns `AiTaskDraft`s built from `safe_*`. It needs no network and no AI (7.5, 7.6).

**Pipeline (`pipeline.py`).** `finalize_plan(drafts, profile, now, source) -> Plan` is the only place that creates a `Plan`:

1. Assign slots and minutes (the AI never supplies them; any such fields were dropped when parsing, 3.3).
2. For each task, gate `what`, `reason` and `caption`, with the whole gate call in `try/except`:
   - **no flags:** keep the text, `notice = None`.
   - **caption flags, every flag has a replacement:** replace the spans, gate the result again. If clean, use it with `notice = "corrected"` and keep the flagged terms for the warning (5.3). If not clean, go to the next case.
   - **caption flags with no replacement, or the corrected text is still flagged:** use `safe_caption` with `notice = "standard"` (5.4).
   - **`reason` or `what` flagged:** use `safe_reason` or `safe_what` with `notice = "standard"` (5.5).
   - **gate raised an error, or the safe text also fails the gate:** `state = "gate_error"`, text fields are `None`, only skip is allowed (5.7).
3. All 3 tasks are finalized the same way, so a plan whose 3 captions are all flagged still has 3 tasks (5.8).

### PlanStore (`planner/store.py`)

```python
def load(shop_id) -> LoadResult            # (plan | None, corrupt: bool)
def save(plan) -> None                     # raises PlanSaveError
def set_status(shop_id, plan_id, task_id, status) -> SetStatusResult
```

- A per-shop `threading.Lock` makes read-modify-write safe.
- Writing: temp file in the same folder, `fsync`, then `os.replace`, so a failure never leaves a half-written file (9.7).
- `set_status` changes a task only when it is `pending` and `plan_id` matches. A repeated call or a call from a stale page returns the current state and changes nothing (6.8, 9.4). A write failure raises `PlanSaveError`, the file is unchanged and the task stays `pending` (9.5).
- `load` treats an unreadable file, invalid JSON, a failed schema check or an unknown `schema_version` as "no plan, corrupt = true" (9.6).
- `save` accepts only a `Plan` produced by `finalize_plan` (the model has a private `_finalized` marker field set there, an *(assumption)* kept simple).

### Web layer (`web/`)

Only the server renders text. All strings come from `strings_th.py`, and profile text is escaped by Jinja autoescape (11.4).

| Route | Purpose | Requirements |
|---|---|---|
| `GET /?shop=<id>` | Request screen, or plan screen, or summary if a saved plan exists | 2.6, 9.3 |
| `POST /shops/{id}/plan` | Start a job (or return the running one), `303` to the progress page | 8.1, 8.4 |
| `GET /jobs/{job_id}` | Progress screen with a cancel button | 2.7, 8.2 |
| `GET /api/jobs/{job_id}` | JSON `{state, redirect}`, updates `last_seen` | 8.1, 8.9 |
| `POST /jobs/{job_id}/cancel` | Cancel; `303` to `/?shop=` | 8.5 |
| `GET /shops/{id}/plan` | Plan or summary screen from the saved plan | 2.8–2.11 |
| `POST /shops/{id}/tasks/{task_id}/confirm` | JSON body `{plan_id, copy_ok}`; sets `ready` | 6.2 |
| `POST /shops/{id}/tasks/{task_id}/skip` | JSON body `{plan_id}`; sets `skipped` | 6.7 |

Screens:
- **Request:** shop name, shop selector (if more than one valid shop), "ขอแผนสัปดาห์", seed error banners.
- **Progress:** status text, "ยกเลิก". `app.js` polls `/api/jobs/{id}` every second and redirects when the state is `done` or `cancelled`. On `pagehide` it sends `navigator.sendBeacon` to the cancel route, unless the job already finished. If polls stop for `HEARTBEAT_GRACE_S`, the coordinator cancels anyway (8.9).
- **Plan:** date range, "ขอแผนใหม่", fallback banner, and per task a card with what, channel, slot, minutes, caption, a `<details>` element for "ทำไมต้องทำ?" (the reason is already in the page, so no extra request, 4.2), notices, and "ยืนยัน"/"ข้าม" while `pending`. Gate-error tasks show only "ข้าม".
- **Summary:** each task with its status, "ขอแผนใหม่", and the short acknowledgement when all 3 are skipped (6.10, 6.11).
- **Error page:** Thai text, no stack trace. A global exception handler returns it (2.12, 7.12).

Confirm flow: on click, `app.js` copies the caption with `navigator.clipboard.writeText` (works on `127.0.0.1`, a secure context), falls back to `execCommand('copy')`, then posts `{plan_id, copy_ok}`. The server sets `ready` even when `copy_ok` is false and the page then shows the selectable caption and the Thai notice (6.4). The confirm text says "พร้อมให้คุณโพสต์เอง" and never "โพสต์แล้ว" (6.5). Copy-again is a button that only runs the clipboard code (6.9). There is no network call to any external service in any route (6.5).

Security (`security.py`): a middleware rejects any request whose `Host` is not `127.0.0.1[:port]` or `localhost[:port]`, and any `POST` whose `Origin` is present and not loopback, before any handler runs (2.2). `web/__main__.py` starts Uvicorn with `host=LOOPBACK_HOST` and one worker (the in-flight guard and job registry are in memory) (2.1).

## Data models

All models are pydantic (already installed with Strands).

```python
class MenuItem:     name: str; price: int | None
class ShopProfile:  shop_id, shop_name, type: Literal["food","bakery","beverage"],
                    menu_items: list[MenuItem], channels_used: list[str],
                    owned_channels: list[str], closed_days: list[int] = []   # Mon=0..Sun=6

class AiTaskDraft:  what: str; channel: str; reason: str; caption: str       # extra="ignore" (3.3)
class AiPlanDraft:  tasks: list[AiTaskDraft]                                  # no length or enum limits here

class Task:
    id: Literal["t1","t2","t3"]
    what: str | None; channel: str; reason: str | None; caption: str | None
    state: Literal["ok","corrected","standard","gate_error"]
    flagged_terms: list[str]                    # shown in the warning for "corrected"
    slot_start: datetime                        # Asia/Bangkok
    minutes: int
    status: Literal["pending","ready","skipped"]
    status_changed_at: datetime | None

class Plan:
    schema_version: int = 1
    plan_id: str                                # uuid4
    shop_id: str
    requested_at: datetime
    period_start: date; period_end: date        # request date, request date + 6 days (9.9)
    source: Literal["ai","fallback"]
    tasks: list[Task]                           # exactly 3
```

The schema is loose on purpose. If pydantic enforced "exactly 3" or an enum of channels, Strands could re-prompt the model inside one run, which adds model requests we cannot count. Our own validation decides `invalid_format`, and the retry rule stays ours.

Saved file `var/plans/<shop_id>.json` is the `Plan` as JSON. It holds only gated text, ids, slots and statuses. No secrets, no personal data (9.2).

## Flows

### Request a plan

```mermaid
sequenceDiagram
    participant B as Browser
    participant W as web
    participant S as PlanService
    participant C as AiPlanClient
    participant T as trust_engine
    participant P as PlanStore
    B->>W: POST /shops/{id}/plan
    W->>S: request_plan(shop_id)
    S-->>W: job (new, or the running one)
    W-->>B: 303 /jobs/{job_id}
    loop every 1 s
        B->>W: GET /api/jobs/{job_id}
        W-->>B: state running
    end
    S->>C: draft(shop_id) in worker thread, deadline 8 s
    alt valid draft
        C-->>S: AiPlanDraft
        S->>T: validate_ai_draft, finalize_plan(source=ai)
    else failure or invalid, no retry left
        S->>T: build_fallback_drafts, finalize_plan(source=fallback)
    end
    S->>P: save (only if the job was not cancelled)
    B->>W: GET /api/jobs/{job_id}
    W-->>B: state done, redirect
    B->>W: GET /shops/{id}/plan
```

### Task status

`pending → ready` (confirm) or `pending → skipped` (skip). No other transitions and no undo (6.8). Each change is saved with `status_changed_at` before the page shows it as done (9.5, supports the S2 measurement later).

### Cancel

`POST /jobs/{id}/cancel` sets the job's cancel event and the state `cancelled`, and frees the shop guard. The coordinator stops at its next 100 ms poll, nothing is saved, and the old plan stays. If the job is already `done`, cancel does nothing and the browser is sent to the saved plan (8.8).

## Error handling

| Case | What happens | Requirement |
|---|---|---|
| Bedrock timeout, `invalid_format` | One retry if at least 3 s remain, else fallback | 7.2, 7.4 |
| Access denied, expired sign-in, throttled, unreachable, other | No retry, fallback at once, cause logged | 7.3 |
| Model or Region config wrong | No Bedrock call, fallback, `config_refused` | 12.2 |
| 8 s reached | Attempt abandoned, fallback | 7.1, 7.13 |
| Owner cancels | Nothing saved, old plan kept, no fallback | 8.5–8.7 |
| Gate raises or safe text fails the gate | Task shows "ตรวจข้อความไม่สำเร็จ", skip only | 5.7 |
| Plan save fails | Job ends with a Thai error page, old plan kept | 9.4, 2.12 |
| Status save fails | Thai error, task stays `pending` | 9.5 |
| Saved file corrupt | Treated as no plan, Thai notice, next request overwrites | 9.6 |
| Seed file broken | Thai banner naming file and field, no plan for that shop | 1.3 |
| Stale page (plan replaced in another tab) | Current plan shown with a Thai notice, no change made | 6.8, 9.4 |
| Unhandled exception | Thai error page, no stack trace | 2.12, 7.12 |

**Log line** (to the terminal, 7.10): `event=fallback cause=sso_expired shop=shop-001 job=ab12 hint="run aws sso login"`. Fields are limited to event, cause, shop id, job id, attempt and hint. No captions, no secrets, no personal data. A cancelled job logs `event=cancelled` and is not counted as a failure (8.10). Gate flags are not failures (7.11).

## Correctness Properties

Properties that must hold for every input. Each can be checked with generated inputs (random shops, scripted agent behaviours) and no AWS call.

### Property 1: Always a plan

For any valid shop and any scripted agent behaviour that is not an owner cancel, a request ends with a saved plan of exactly 3 tasks.

**Validates: Requirements 3.1, 7.12**

### Property 2: Nothing ungated is saved or shown

Every `what`, `reason` and `caption` in a saved plan has passed the gate, or the task is in the `gate_error` state with no text.

**Validates: Requirements 5.1, 5.7**

### Property 3: Same path for both sources

For a plan from the AI or from the fallback, the slot, minutes and gate results come from the same `finalize_plan` code.

**Validates: Requirements 3.2, 7.5, 7.7**

### Property 4: Trust Engine owns the numbers

No slot or minutes value in a saved plan comes from agent output, and no AI-written text contains a figure outside the allowed set.

**Validates: Requirements 3.3, 10.1, 10.2**

### Property 5: Slot rules

In any saved plan the tasks are on different days (when 3 or more eligible days exist), no slot is in the past or on a closed day, and minutes per day are at most 10.

**Validates: Requirements 3.6, 3.7**

### Property 6: Bounded attempts

A request makes at most 2 agent attempts, never retries after `access_denied`, `sso_expired`, `throttled`, `unreachable` or `other`, and shows a plan within the limit plus 1 s.

**Validates: Requirements 7.1, 7.2, 7.3, 7.4, 7.13**

### Property 7: Cancel leaves no trace

After a cancel, the saved plan for the shop is byte-for-byte what it was before the request, even if a late result arrives.

**Validates: Requirements 8.5, 8.6, 8.7**

### Property 8: One in flight

For any number of rapid or parallel requests for one shop, at most one agent attempt is started per running job.

**Validates: Requirements 8.4**

### Property 9: Status moves one way

A task goes `pending` to `ready` or `skipped` at most once, and a repeated or stale request changes nothing.

**Validates: Requirements 6.8, 9.4**

### Property 10: Saves are all or nothing

A write failure never replaces a good plan file with a partial one, and a failed status write leaves the task `pending`.

**Validates: Requirements 9.5, 9.7**

### Property 11: No posting

No route, tool or code path contacts an external channel.

**Validates: Requirements 6.5, 6.6**

### Property 12: Fixed model and Region

No Bedrock call is made unless the model ID is `anthropic.claude-sonnet-5` and the Region is `ap-southeast-1`.

**Validates: Requirements 12.1, 12.2**

## Testing strategy

Tests live in `tests/`, run with `uv run pytest`, and never call AWS (12.5). The existing hook runs the suite on every `.py` save, so all tests must be fast. The existing `tests/test_agent.py` keeps passing because `agent.agent` stays.

Names follow `test_req_<n>_<m>_<behaviour>`. One test per [Auto] criterion.

| Module | Covers |
|---|---|
| `test_gate.py`, `test_redlines_data.py` | 5.2, 5.7, 5.9–5.11, every category, spacing and zero-width bypass, no profile-name exemption |
| `test_safe_text.py` | 5.6 (every template × channel × seed shop passes the gate), 5.4, 5.5 |
| `test_figures.py`, `test_validation.py` | 3.3–3.5, 3.8–3.10, 10.1–10.4, 4.3, 4.4 |
| `test_slots.py` | 3.6, 3.7, 7.9 (closed days, past times, different days, daily cap, deterministic) |
| `test_pipeline.py` | 5.1, 5.3, 5.4, 5.5, 5.8 (all three captions flagged keeps 3 tasks) |
| `test_fallback.py` | 7.5–7.7, 7.9, minimal profile |
| `test_plan_service.py` | 7.1–7.4, 7.10–7.13, 8.4–8.10, 12.2 (with `StubAiPlanClient` and a 0.3 s limit) |
| `test_store.py` | 9.1–9.9 (atomic write with a simulated failure, corrupt file, replace, stale plan id) |
| `test_tools.py` | the three tools return the stub shapes, `notice`, no AWS import |
| `test_prompt_injection.py` | 11.1–11.3: prompt data delimiting, tool set fixed, stub answer that "obeyed" an injection still hits validation and the gate |
| `test_web.py` | 2.1, 2.2, 2.6–2.12, 3.1, 3.11, 4.1, 4.2, 6.1, 6.2, 6.5–6.8, 6.10, 6.11, 8.1–8.4, 11.4 using FastAPI `TestClient` and the stub client |
| `test_seed.py` | 1.1–1.3 |

The Bedrock stub supports success, malformed output, timeout, unreachable, access denied, expired sign-in and throttling (12.5). Timing tests use small limits and real sleeps. 7.13 is checked as "fallback visible within 1 s after the limit".

Manual checks M1–M8 stay as listed in `requirements.md` and are recorded in `docs/handoff.md`.

## Requirement coverage

| Requirement | Main design elements |
|---|---|
| 1 Seed and session | `SeedCatalog`, stub session (no login route), seed validation |
| 2 App and screens | `web/` routes and templates, `security.py`, `__main__.py`, `strings_th.py` |
| 3 Generate plan | `AiPlanDraft`, `validate_ai_draft`, `assign_slots`, `finalize_plan` |
| 4 Why | `<details>` reason in each task card, validation of the reason |
| 5 Gate | `gate.py`, `redlines.py`, `safe_text.py`, `pipeline.py` |
| 6 Confirm and skip | status routes, `PlanStore.set_status`, `app.js` clipboard code |
| 7 Failure and fallback | `PlanService._run`, `AiError` causes, `fallback.py`, log line |
| 8 Progress, cancel, double-tap | `JobRegistry`, progress page, cancel route, heartbeat |
| 9 Lifecycle | `PlanStore` atomic files, `schema_version`, replace rule |
| 10 Numbers | `figures.py`, slot and minute tables in the Trust Engine |
| 11 Untrusted text | tool `notice`, Jinja autoescape, fixed tool set, output checks |
| 12 Model and tests | `check_model_config`, `build_agent`, `StubAiPlanClient` |

## Dependencies and commands

Add: `uv add fastapi uvicorn jinja2` and `uv add --dev httpx` (for `TestClient`). `starlette` and `uvicorn` already arrive through the Strands tree, but they are declared explicitly so the app does not rely on that. No form library is needed because all POST bodies are JSON or empty.

Run: `uv run python -m web` (serves on `http://127.0.0.1:8000`). Check: `uv run pytest`. Sign in first with `aws sso login` (add `--profile` if the team uses one). Always use `uv run`, because the system `python3` is 3.9 and the project needs 3.12.

Add `var/` to `.gitignore` (9.1).

## Items to confirm

Each one is a place where the design goes slightly beyond or reads `requirements.md` in a particular way. Please confirm or change them before tasks are written.

1. **`what` is shown to the owner, but 5.1 to 5.5 mention only captions and reasons.** The design also gates `what` and swaps in a safe standard text if it is flagged. Add `what` to 5.1 and 5.5?
2. **"Bedrock call" in 7.4 and 8.4.** One agent attempt makes several model requests because it calls tools. The design counts one attempt as one call. OK?
3. **3.7 says minutes come "by channel and task type".** The agent does not return a task type, so the design uses channel only. Change 3.7 to "by channel", or add an optional `content_type` field to the agent output?
4. **Seed profiles with fewer than 3 open days** are rejected, because the 3 tasks could not sit on different days. Add this to 1.2 and 1.3?
5. **Latency risk (R3).** The agent calls tools before it writes, which means at least two model round trips, and `list_content_types` may be called once per channel. Finishing within 8 s on Sonnet is not certain, and a plan that always times out would always show the fallback. Measure in check M4 first. If it is too slow, the cheapest fix is for the code to run the three tools first and pass their results to the agent as data. That changes the "Agent design" section (the agent would no longer call the tools), so it needs your approval.

6. **New folders.** `structure.md` lists `trust_engine/`, `tools/`, `prompts/`, `data/`, `tests/` but not `planner/`, `web/` or `var/`. `structure.md` asks to update it when the structure changes. I have not edited it.

7. **Retry after a timeout is rare.** Attempt 1 may use the whole 8 s, so a retry after a timeout only happens when the connection fails early (the 2 s connect timeout). Most retries will follow an `invalid_format` answer that came back quickly. If the team wants a firmer cap on attempt 1 (for example 5 s so a retry always has time), that lowers the success rate of the first attempt.

8. **Number-word and weekday lists may over-flag** (for example a menu item that contains "สอง"). Names from the profile are removed before the figure check, but other words may still trigger it. The cost is a retry or a fallback, so tune the list during M2.
