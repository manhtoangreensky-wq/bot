# SubDub Multi-Speaker Blackbox Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a separately selectable Vietnamese multi-speaker Auto SubDub blackbox while preserving the proven two-speaker Auto lane as the unchanged default and preserving manual/default/subtitle, pricing, settlement, mux, and delivery behavior.

**Architecture:** The exact Auto state pair remains `voice_kind="auto_speaker_gender"` plus `voice_selection_mode="auto_speaker"`, so every existing quote, confirmation, Admin-free settlement, receipt, TTS, mux, and delivery gate remains shared. Only `auto_speaker_lane="multi"` selects a thin new adapter; no marker selects the current `auto_speaker` blackbox. The adapter injects one filtered PCM profile and one explicitly opt-in single-frame classifier profile, then delegates once to the existing Auto blackbox and protected lane runner.

**Tech Stack:** Python 3.14, asyncio, FFmpeg, python-telegram-bot, pytest, Git/GitHub Actions, Ubuntu VPS systemd.

---

## File map and protected boundary

- Create `services/subdub_blackboxes/auto_multi_speaker.py`: own the exact multi marker, require 2–16 provider-returned labels, inject the multi-only classifier and PCM filter, and delegate once to `auto_speaker.run_auto_speaker_blackbox`.
- Modify `services/subdub_blackboxes/auto_speaker.py`: add an optional classifier dependency whose default remains `subdub_speaker_cast.classify_speaker_registers`; do not change assignment, per-cue TTS, lane delegation, failure, mux, delivery, or settlement behavior.
- Modify `services/subdub_speaker_cast.py`: restore the two-speaker defaults from before PR #853 and expose one boolean opt-in used only by the multi adapter for one-frame pitch evidence.
- Modify `bot.py`: import/select the multi adapter, add and clear `auto_speaker_lane`, add one compact multi choice, keep the old callback/state path unchanged, make the multi job key distinct, and allow the multi extractor wrapper to request the PR #853 filter.
- Create `tests/test_p0_subdub_multi_speaker_blackbox.py`: focused marker, adapter, dispatch, extraction, 3+ label, pricing, and Admin-free regression coverage.
- Modify `tests/test_p0_subdub_per_speaker_auto_gender_cast.py`: restore the old default PCM/classifier expectations and retain the old route as a protected comparator.

Protected and byte-unchanged:

- `services/subdub_blackboxes/__init__.py`
- `services/subdub_blackboxes/base.py`
- `services/subdub_blackboxes/dub_only.py`
- `services/subdub_blackboxes/subtitle_dub.py`
- `services/subtitle_dub_product_pipeline.py`
- `services/subdub_auto_word_pricing.py`
- `services/subdub_auto_settlement.py`
- all subtitle-only/default/manual lane routing, wallet/payment/PayOS, DB migrations/data, ENV/secrets, provider adapters, Video Edit, and Product Video files.

Rollback anchors:

- two-speaker live anchor: PR #844 / `0c5e0dc9b0b11bb864124fa44403c7c049a06904` / job `5ECF6FB24B`;
- pre-separation runtime checkpoint: PR #853 / `7b4053acd9a2bd44c29a15ebc5e0e86152fab24f`;
- never reset, clean, delete, or overwrite the untracked deployment bundles and `evidence/` directory.

## Task 1: RED — lock the old lane and specify the new lane

**Files:**
- Create: `tests/test_p0_subdub_multi_speaker_blackbox.py`
- Modify: `tests/test_p0_subdub_per_speaker_auto_gender_cast.py`

- [ ] **Step 1: Add state and menu separation tests**

Add tests that construct the exact Auto pair and require these exact outcomes:

```python
old = bot.subdub_apply_voice_choice({}, "auto_speaker_gender", activation_enabled=True)
multi = bot.subdub_apply_voice_choice({}, "auto_multi_speaker", activation_enabled=True)
manual = bot.subdub_apply_voice_choice(multi, "default_female", activation_enabled=True)

assert old == {
    "voice_kind": "auto_speaker_gender",
    "voice_selection_mode": "auto_speaker",
}
assert multi["voice_kind"] == old["voice_kind"]
assert multi["voice_selection_mode"] == old["voice_selection_mode"]
assert multi["auto_speaker_lane"] == "multi"
assert "auto_speaker_lane" not in manual
```

Require exactly one old callback and one new callback in both dubbing menus:

```python
assert callbacks.count("videodub|voice|auto_speaker_gender") == 1
assert callbacks.count("videodub|voice|auto_multi_speaker") == 1
```

- [ ] **Step 2: Add dispatch and job-isolation tests**

Require no-marker Auto to select only the old callable, exact multi marker to select only the new callable, and manual/default states to remain outside Auto:

```python
assert bot.subdub_auto_blackbox_runner(old) is bot.auto_speaker.run_auto_speaker_blackbox
assert bot.subdub_auto_blackbox_runner(multi) is bot.auto_multi_speaker.run_auto_multi_speaker_blackbox
assert bot.subdub_auto_speaker_route_enabled(old) is True
assert bot.subdub_auto_speaker_route_enabled(multi) is True
assert bot.subdub_auto_multi_speaker_route_enabled(old) is False
assert bot.subdub_auto_multi_speaker_route_enabled(multi) is True
```

Keep the old job suffix byte-stable and isolate the multi retry/lease:

```python
assert bot.subtitle_dub_pipeline_job_key(7, 8, {**base, **old}).endswith("|auto_speaker")
assert bot.subtitle_dub_pipeline_job_key(7, 8, {**base, **multi}).endswith("|auto_multi_speaker")
```

- [ ] **Step 3: Add old-vs-multi acoustic profile tests**

Reset the deterministic frame-estimate fixture before each call. Require the default helper to reject the one-frame sample and the opt-in multi profile to accept it:

```python
assert speaker_cast._estimate_window_pitch(
    raw,
    deadline_monotonic=time.monotonic() + 10,
    stop_requested=lambda: False,
) is None
assert speaker_cast._estimate_window_pitch(
    raw,
    deadline_monotonic=time.monotonic() + 10,
    stop_requested=lambda: False,
    allow_single_pitch_frame=True,
) is not None
```

Require the old extractor command to contain no `-af`, and the multi adapter's injected extractor call to carry exactly:

```text
highpass=f=70,lowpass=f=320,afftdn=nr=6:nf=-50
```

- [ ] **Step 4: Add 3+ label and price/zero-Xu invariants**

Use three canonical Deepgram labels and existing validated pools. Assert all three keys survive and all assigned voice IDs are distinct while capacity allows. Also require one provider label to fail closed rather than invent speakers and 17 labels to keep the existing overflow failure.

For identical quote fields, require:

```python
assert bot.video_dubbing_invoice_breakdown({**priced, **old}) == \
       bot.video_dubbing_invoice_breakdown({**priced, **multi})
assert auto_speaker.is_auto_speaker_state(old)
assert auto_speaker.is_auto_speaker_state(multi)
```

The existing delivery settlement comparator must still prove the Admin branch sets `charge_status="admin_free"`, `charged_xu=0`, and does not call wallet settlement for either marker state.

- [ ] **Step 5: Run RED only after CPU release**

Run:

```powershell
python -m pytest -q tests/test_p0_subdub_multi_speaker_blackbox.py
```

Expected RED: missing `auto_multi_speaker`, missing marker helpers/callback/dispatch, old extractor still contains `-af`, and default classifier still accepts one pitch frame. A collection/import/dependency error is not a valid RED and must be corrected before production edits.

- [ ] **Step 6: Commit test-only RED**

```powershell
git add -- tests/test_p0_subdub_multi_speaker_blackbox.py tests/test_p0_subdub_per_speaker_auto_gender_cast.py
git commit -m "test(subdub): separate multi-speaker auto lane"
```

## Task 2: GREEN — isolate the acoustic profile in a thin adapter

**Files:**
- Create: `services/subdub_blackboxes/auto_multi_speaker.py`
- Modify: `services/subdub_blackboxes/auto_speaker.py`
- Modify: `services/subdub_speaker_cast.py`

- [ ] **Step 1: Restore the old classifier defaults and add one explicit opt-in**

Restore:

```python
_MIN_PITCH_FRAMES = 2
```

Add `allow_single_pitch_frame: bool = False` to `_estimate_window_pitch` and `classify_speaker_registers`. Use only:

```python
minimum_pitch_frames = 1 if allow_single_pitch_frame else _MIN_PITCH_FRAMES
minimum_inliers = max(minimum_pitch_frames, math.ceil(len(estimates) * 0.60))
support = (
    0.5
    if allow_single_pitch_frame and len(inliers) == 1
    else min(1.0, len(inliers) / 4.0)
)
```

Reject a non-boolean opt-in fail-closed. Pass the flag from `classify_speaker_registers` to `_estimate_window_pitch`; no other thresholds change.

- [ ] **Step 2: Add optional classifier injection without changing the default path**

Thread `classify_speakers: Callable[..., dict] | None = None` through `_classify_off_event_loop`, `run_auto_speaker_preflight`, and `run_auto_speaker_blackbox`. Resolve it at call time so monkeypatching remains valid:

```python
classifier = classify_speakers or speaker_cast.classify_speaker_registers
```

The default old path must call the same classifier with no opt-in keyword.

- [ ] **Step 3: Create the multi adapter**

Implement these narrow contracts in `auto_multi_speaker.py`:

```python
AUTO_MULTI_SPEAKER_LANE = "multi"
MULTI_PCM_AUDIO_FILTER = "highpass=f=70,lowpass=f=320,afftdn=nr=6:nf=-50"

def is_auto_multi_speaker_state(state):
    current = state or {}
    return (
        auto_speaker.is_auto_speaker_state(current)
        and current.get("auto_speaker_lane") == AUTO_MULTI_SPEAKER_LANE
    )

def classify_multi_speaker_registers(pcm_path, ranges_by_speaker, *, deadline_monotonic, stop_requested):
    if not isinstance(ranges_by_speaker, dict) or not 2 <= len(ranges_by_speaker) <= 16:
        raise speaker_cast.AutoCastManualRequired()
    return speaker_cast.classify_speaker_registers(
        pcm_path,
        ranges_by_speaker,
        deadline_monotonic=deadline_monotonic,
        stop_requested=stop_requested,
        allow_single_pitch_frame=True,
    )
```

`run_auto_multi_speaker_blackbox` must reject a missing/wrong marker before preparation, wrap the injected extractor with the exact `audio_filter`, pass `classify_speakers=classify_multi_speaker_registers`, and await exactly one call to `auto_speaker.run_auto_speaker_blackbox`. It must not copy assignment, TTS, mux, delivery, pricing, or settlement code.

- [ ] **Step 4: Run the service GREEN selectors**

Run:

```powershell
python -m pytest -q tests/test_p0_subdub_multi_speaker_blackbox.py -k "classifier or adapter or three_speaker"
python -m pytest -q tests/subdub_service_only/test_p0_subdub_auto_classifier_live_evidence.py tests/test_p0_subdub_auto_classifier_live_shape.py tests/test_p0_subdub_real_speech_register_classifier.py
```

Expected: new multi profile tests and existing ambiguity/resource/cancellation comparators pass; the old one-frame default remains rejected.

- [ ] **Step 5: Commit the isolated service layer**

```powershell
git add -- services/subdub_speaker_cast.py services/subdub_blackboxes/auto_speaker.py services/subdub_blackboxes/auto_multi_speaker.py tests/test_p0_subdub_multi_speaker_blackbox.py tests/test_p0_subdub_per_speaker_auto_gender_cast.py
git commit -m "feat(subdub): add isolated multi-speaker blackbox"
```

## Task 3: GREEN — wire one marker, one choice, and one dispatch

**Files:**
- Modify: `bot.py`
- Modify: `tests/test_p0_subdub_multi_speaker_blackbox.py`

- [ ] **Step 1: Add state marker ownership**

Import `auto_multi_speaker`, add `auto_speaker_lane` to `SUBDUB_AUTO_VOICE_FIELDS`, and treat both callbacks as Auto selection. Existing Auto explicitly removes the marker; multi sets it:

```python
selecting_auto = value in {"auto_speaker_gender", "auto_multi_speaker"}
...
selected.pop("auto_speaker_lane", None)
if value == "auto_multi_speaker":
    selected["auto_speaker_lane"] = auto_multi_speaker.AUTO_MULTI_SPEAKER_LANE
```

Manual/default choices continue through the existing payload and clear all Auto fields.

- [ ] **Step 2: Add exactly one compact menu choice**

Retain the existing Auto callback and row. Insert one adjacent row with callback `videodub|voice|auto_multi_speaker` and label `👥 Tự nhận nhiều giọng` for Vietnamese, `👥 Multi-speaker Auto` otherwise. Do not change any other text, layout, subtitle choice, confirmation button, or callback.

- [ ] **Step 3: Add exact multi dispatch and job isolation**

Add:

```python
def subdub_auto_multi_speaker_route_enabled(state=None) -> bool:
    return bool(
        subdub_auto_speaker_route_enabled(state)
        and auto_multi_speaker.is_auto_multi_speaker_state(state)
    )

def subdub_auto_blackbox_runner(state=None):
    if subdub_auto_multi_speaker_route_enabled(state):
        return auto_multi_speaker.run_auto_multi_speaker_blackbox
    return auto_speaker.run_auto_speaker_blackbox
```

Use this callable only inside the existing `if subdub_auto_speaker_route_enabled(state)` branch. Keep all payload dependencies identical. In `subtitle_dub_pipeline_job_key`, append `auto_multi_speaker` for the exact marker and retain `auto_speaker` byte-for-byte for no marker.

- [ ] **Step 4: Restore default extractor and expose only the filtered injection seam**

Add keyword-only `audio_filter: str = ""` to `_extract_subdub_auto_pcm`. Build the existing command unchanged, then insert `("-af", audio_filter)` only when nonempty. No-marker old dispatch passes no filter; only the multi adapter passes the exact filter.

- [ ] **Step 5: Run focused route/state/price GREEN**

Run:

```powershell
python -m pytest -q tests/test_p0_subdub_multi_speaker_blackbox.py
python -m pytest -q tests/test_p0_subdub_per_speaker_auto_gender_cast.py -k "exact_state or voice_state_reset or route_gate or dispatch_matrix or default_blackbox_pcm or auto_job_key or task7"
```

Expected: both lanes route once, old command/default behavior remains protected, manual/default/subtitle routes never enter multi, quote output is identical, and Admin remains 0 Xu.

- [ ] **Step 6: Commit bot wiring**

```powershell
git add -- bot.py tests/test_p0_subdub_multi_speaker_blackbox.py tests/test_p0_subdub_per_speaker_auto_gender_cast.py
git commit -m "feat(subdub): route multi-speaker auto separately"
```

## Task 4: REVIEW and VERIFY the protected surface

**Files:**
- Review only all changed files and protected paths.

- [ ] **Step 1: Inspect exact scope**

Run:

```powershell
git status --short
git diff --check origin/main...HEAD
git diff --stat origin/main...HEAD
git diff origin/main...HEAD -- bot.py services/subdub_speaker_cast.py services/subdub_blackboxes/auto_speaker.py services/subdub_blackboxes/auto_multi_speaker.py tests/test_p0_subdub_multi_speaker_blackbox.py tests/test_p0_subdub_per_speaker_auto_gender_cast.py
```

Confirm no ENV, secret, wallet, DB, provider adapter, subtitle lane, Product Video, protected engine, bundle, or evidence edit.

- [ ] **Step 2: Run compile and protected comparators**

Run:

```powershell
python -m py_compile bot.py services/subdub_speaker_cast.py services/subdub_blackboxes/auto_speaker.py services/subdub_blackboxes/auto_multi_speaker.py
python -m pytest -q tests/test_p0_subdub_multi_speaker_blackbox.py tests/subdub_service_only/test_p0_subdub_auto_classifier_live_evidence.py tests/test_p0_subdub_auto_classifier_live_shape.py tests/test_p0_subdub_real_speech_register_classifier.py
python -m pytest -q tests/test_p0_subdub_per_speaker_auto_gender_cast.py -k "exact_state or voice_state_reset or manual_modes_remain_scalar or route_gate or dispatch_matrix or default_blackbox_pcm or auto_job_key or navigation_callbacks or task7"
```

Do not claim PASS from collection, a partial selector, or a previous run. Record exact counts, duration, and exit codes.

- [ ] **Step 3: Verify artifact inputs read-only**

Run the existing `Download.mp4` sidecar/artifact verifier without provider calls. Require canonical media hash/path, 2 provider-returned IDs preserved without fallback, and no TTS/mux/delivery/wallet mutation. This is a regression fixture, not proof of 3+ real speakers.

## Task 5: SHIP and one authorized live fixture after reacquiring boundary

**Files:**
- No new source files unless verification identifies a reproducible failing requirement.

- [ ] **Step 1: Reacquire before external mutation**

Wait for exact `PRODUCT VIDEO LIVE RELEASED`, then announce `SUBDUB AUTO LIVE ACQUIRED`. Re-run fresh compile and focused tests after rebasing current `origin/main`. Stop if the old lane comparator changes.

- [ ] **Step 2: Push, PR, merge, and deploy exact SHA**

Push the feature branch, create the PR, merge only after CI/review, watch deployment, and verify both `/opt/toanaas/bot` and the required worker checkout are at the exact merge SHA before restart. Preserve all untracked runtime files and fail closed on SHA/hash mismatch.

- [ ] **Step 3: Run only the Owner-authorized fixture**

Use exact authorization `XÁC NHẬN LIVE SUBDUB NHIỀU GIỌNG DOWNLOAD.MP4`. Select the new multi callback, Vietnamese target, original audio 20%, dub 100%, and run exactly one provider path. Owner/Admin must charge 0 Xu. Do not fabricate extra speakers when Deepgram returns only two labels.

- [ ] **Step 4: Accept only a real terminal product**

Require one validated MP4 with audio, one SRT, one green Telegram receipt, one job/outbox, provider labels preserved, no duplicate callback/provider/TTS/mux/delivery, and durable `charged_xu=0`. `HTTP 200`, merged, deployed, or service active alone are not PASS.

- [ ] **Step 5: Release and report**

Send exact `SUBDUB AUTO LIVE RELEASED` only after all SubDub Telegram/provider/TTS/mux/wallet/merge/deploy/restart actions are terminal. Report the merge/runtime SHA, job ID, speaker-label count, per-label voice assignment evidence, artifact hashes/duration/audio, message ID, and zero-Xu receipt. If the fixture yields only two Deepgram labels, report that truth and keep 3+ acceptance proven only by automated synthetic tests.
