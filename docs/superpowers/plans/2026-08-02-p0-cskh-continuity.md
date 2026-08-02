# P0.CSKH.CONTINUITY Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` for the sequential subtask checkpoints. Every behavior change follows RED → GREEN → refactor and no later subtask starts before the current focused gate is green.

**Goal:** Extend the existing TOAN AAS Telegram bot CSKH and AIChat code so bot/menu, Business CSKH, and AIChat share safe human-touch replies, live read-only pricing, and owner-isolated recent-session continuity.

**Architecture:** Keep `telegram_business_support.classify_cskh_message()` as the existing central resolver, make `aas_shared_knowledge` its deterministic shared reply facade, and add one small SQLite-backed conversation-turn service. `bot.py` bridges the service to existing runtime prices and Telegram transports without changing paid workflows.

**Tech Stack:** Python, SQLite, python-telegram-bot, existing TOAN AAS rule/playbook modules, pytest.

---

### Task 0: Close discovery checkpoint

**Files:**
- Create: `docs/superpowers/specs/2026-08-02-p0-cskh-continuity-design.md`
- Create: `docs/superpowers/plans/2026-08-02-p0-cskh-continuity.md`

- [ ] Verify `origin/main`, branch cleanliness, open PR conflicts, source documents, dispatch lines, canonical price sources, DB convention, and settings mechanism.
- [ ] Run existing focused CSKH/AIChat regression suite and `python -m py_compile bot.py`.
- [ ] Commit only the discovery/design record with `docs(cskh): record continuity discovery`.

### Task 1: Add the shared human-touch knowledge facade

**Files:**
- Modify: `services/aas_shared_knowledge.py`
- Modify: `services/telegram_business_support.py`
- Modify: `services/ai_chatbot_copilot.py`
- Modify: `knowledge/toan_aas_cskh_aichat_context.md`
- Create: `tests/test_p0_cskh_continuity_unified.py`
- Modify: `tests/test_p0_cskh4_aas_product_knowledge_pricing_mixed_intents.py`
- Modify: `tests/test_p0_cskh5c_business_self_echo_duplicate_guard.py`
- Modify: `tests/test_p0_cskh6_human_touch_playbook_safe_training_pack.py`

- [ ] Write failing tests that call:

```python
facts = {
    "available": True,
    "source": "runtime_canonical",
    "xu_to_vnd": 100,
    "image_tiers": [("Ảnh tiết kiệm", 51), ("Ảnh cao", 601)],
    "video_tiers": [("Cơ bản", 333)],
    "scene_seconds": 6,
    "subtitle_rate": 0.1,
    "dub_rate": 0.1,
}
reply = shared.classify_shared_answer("Tạo ảnh bao nhiêu", runtime_facts=facts)
assert "51 Xu" in reply["reply"]
assert reply["pricing_source"] == "runtime_canonical"
```

- [ ] Verify a missing explicit fact snapshot returns the honest invoice-safe copy without stale prices; verify a Vietnamese complaint starts with `Dạ em xin lỗi`; verify direct prompt, caption, and script requests contain a usable draft before the one optional follow-up.
- [ ] Extend these exact resolver signatures without importing `bot.py`:

```python
def classify_shared_answer(text, *, conversation_memory=None, media_type="", runtime_facts=None): ...
def classify_cskh_message(text="", *, media_type="", kb=None, training_data=None,
                          variation_seed=None, conversation_memory=None, runtime_facts=None): ...
def process_message(state, user_id, text, *, queue_unknown=True,
                    entry_source="live_chat", conversation_memory=None, runtime_facts=None): ...
```

- [ ] Preserve existing classifier/playbook/consent behavior, replace public banned phrases before send, and report `pricing_source="runtime_canonical"` only when an explicit snapshot supplied it.
- [ ] Run:

```powershell
python -m pytest -q tests/test_p0_cskh_continuity_unified.py -k human_touch
python -m pytest -q tests/test_p0_cskh4_aas_product_knowledge_pricing_mixed_intents.py tests/test_p0_cskh6_human_touch_playbook_safe_training_pack.py
python -m py_compile services/aas_shared_knowledge.py services/telegram_business_support.py services/ai_chatbot_copilot.py
git diff --check
```

- [ ] Commit with `feat(cskh): unify human-touch knowledge across reply surfaces`.

### Task 2: Add the one authorized conversation turn store

**Files:**
- Create: `services/cskh_session_memory.py`
- Modify: `bot.py`
- Modify: `tests/test_p0_cskh_continuity_unified.py`
- Modify: the three CSKH scope-guard test files listed in Task 1

- [ ] Write failing tests against the following storage seam using an in-memory SQLite connection:

```python
session = memory.record_turn(conn, owner_id="1", chat_id="10", surface="bot_menu",
                             role="user", content="token sk-live-secret", source_message_id="42", now=1000)
assert session.inserted is True
assert "sk-live-secret" not in memory.load_recent_session(conn, owner_id="1", chat_id="10", now=1001)["history_text"]
assert memory.load_recent_session(conn, owner_id="2", chat_id="10", now=1001)["turns"] == []
```

- [ ] Implement exactly these storage helpers in `services/cskh_session_memory.py`:

```python
def ensure_schema(conn) -> None: ...
def sanitize_content(value: str) -> tuple[str, bool]: ...
def record_turn(conn, *, owner_id, chat_id, surface, role, content, source_message_id, now) -> TurnWrite: ...
def load_recent_session(conn, *, owner_id, chat_id, now, session_window_hours, recent_turn_limit, character_budget) -> dict: ...
def purge_expired_turns(conn, *, now, retention_days, batch_size=500) -> int: ...
def closing_notice_needed(conn, *, owner_id, chat_id, session_id, source_message_id) -> bool: ...
```

- [ ] In `bot.py:init_db()`, call `cskh_session_memory.ensure_schema(c)` and add only the two authorized indexes. Add `cskh_runtime_setting_int`, `cskh_shared_context`, `cskh_record_exchange`, and a 5-minute task scheduler. It must use the latest owner user-turn key to cancel stale timers and persist the notice with a deterministic `closing-notice:<session_id>` source key only after mockable send success.
- [ ] The exact customer note is built from the configured window in hours and must contain no database/session/provider terminology.
- [ ] Run:

```powershell
python -m pytest -q tests/test_p0_cskh_continuity_unified.py -k memory
python -m py_compile services/cskh_session_memory.py bot.py
git diff --check
```

- [ ] Commit with `feat(cskh): add isolated shared recent-session memory`.

### Task 3: Wire all bot surfaces without paid side effects

**Files:**
- Modify: `bot.py`
- Modify: `services/ai_chatbot_copilot.py`
- Modify: `services/telegram_business_support.py`
- Modify: `tests/test_p0_cskh_continuity_unified.py`
- Modify: `tests/test_p0_aichat5_live_context_action_trace.py`
- Modify: `tests/test_p0_cskh5c_business_self_echo_duplicate_guard.py`

- [ ] Write failing tests for the five required directions, including this concrete prior-answer case:

```python
first = record_reply("bot_menu", "Hướng dẫn tạo video: 1. chọn Video, 2. chọn gói, 3. xem hóa đơn.")
follow = classify("cskh", "bước 2 tôi chưa hiểu", history=first)
assert "chọn gói" in follow["reply"].lower()
```

- [ ] Inject `cskh_live_pricing_snapshot()` and `cskh_shared_context()` through `handle_aichat_message`, `process_cskh_business_event`, and `telegram_business_support.process_business_event_runtime`.
- [ ] Add `handle_cskh_continuity_message()` after every valid pending-state handler and before `handle_support_persona_message()`. It handles only high-confidence covered human-touch intents; it must not call the legacy support classifier, queue learning, create a ticket, start a provider call, create a job, or mutate Xu.
- [ ] Record a safe `context_event` only from an allow-listed customer-facing summary such as `Khách đang xem dịch vụ tạo video`; never record callback data, route names, raw provider data, or debug text.
- [ ] Run:

```powershell
python -m pytest -q tests/test_p0_cskh_continuity_unified.py -k integration
python -m pytest -q tests/test_p0_aichat5_live_context_action_trace.py tests/test_p0_cskh5c_business_self_echo_duplicate_guard.py
python -m py_compile bot.py services/ai_chatbot_copilot.py services/telegram_business_support.py
git diff --check
```

- [ ] Commit with `test(cskh): prove cross-surface continuity and safety`.

### Task 4: Comparator and one PR

**Files:**
- Modify: only tests/docs required to record results; no product behavior changes.

- [ ] Run focused continuity, existing CSKH/AIChat, bot/menu, pricing-read, DB/settings, action-guard, callback, and no-side-effect tests.
- [ ] Run the identical accepted test command on branch head and a fresh clean `origin/main` worktree; capture node ids and failure-set comparison.
- [ ] Run `py_compile` on changed Python files, `git diff --check`, secret/private-path scans, and scope proof scans.
- [ ] Push the single branch and open one non-draft PR titled `P0.CSKH.CONTINUITY: unify human-touch replies and cross-surface session memory`.
- [ ] Stop without merge, deploy, provider call, real Telegram send, or manual smoke.
