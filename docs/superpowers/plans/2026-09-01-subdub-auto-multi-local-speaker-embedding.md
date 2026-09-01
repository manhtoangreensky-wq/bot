# SubDub Auto Multi Local Speaker-Embedding Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace cross-provider speaker-label mapping in SubDub Auto Multi with hash-locked local acoustic speaker embeddings, then deliver a verified English multi-voice MP4 from the existing job `#B4CB6D5FE8` without creating another job or charging the Owner.

**Architecture:** Deepgram supplies one strict word-timed transcript without provider diarization. A new isolated service converts those exact word intervals to bounded 16 kHz acoustic units, computes a NumPy Kaldi-compatible 80-bin fbank, extracts WeSpeaker ResNet34 embeddings through CPU-only ONNX Runtime, selects a deterministic stable speaker count from 3-8, and rebuilds canonical source cues on that same word timeline. Existing translation, register classification, distinct voice assignment, per-cue TTS, cue-locked mux, validation, delivery, and receipt paths remain shared.

**Tech Stack:** Python 3.11+, NumPy 2.4.6, ONNX Runtime 1.29.0 CPU provider, FFmpeg PCM extraction, Pytest, SQLite compare-and-set, Telegram SubDub pipeline.

**Spec:** `docs/superpowers/specs/2026-09-01-subdub-auto-multi-local-speaker-embedding-design.md` at commit `c28866bc2a765da0a6dafb90d84c9ddfb1e845d5`, file SHA-256 `5a0b086488814d85c1bf5ec6cc11b996d4b99313a2832643c9a240fcf37da5e5`.

## Execution mode

The Owner explicitly authorized implementation and TDD in the same approval
that accepted the spec. `AGENTS.md` requires Single-Agent by Default, and all
tasks share the same model asset, Python modules, tests, and recovery state.
Use `superpowers:executing-plans` inline in this task. Do not dispatch
subagents.

## Repository context

- Project root: `C:\Users\toann\Documents\Codex\2026-08-01\sua\work\subdub-multi-exact-price`.
- Read before each execution batch:
  - `AGENTS.md`;
  - `docs/superpowers/specs/2026-09-01-subdub-auto-multi-local-speaker-embedding-design.md`;
  - `.agents/state/p0-subdub-multi-blackbox.yaml`.
- Preserve untracked Owner directories `.agents/tools/` and `artifacts/`.
- The source model comes only from
  `artifacts/speaker-embedding-diagnostic/voxceleb_resnet34.onnx`.
- The approved input fixture is
  `C:\Users\toann\Downloads\test sub\test nhiều giọng.mp4`, size 9,869,032
  bytes, SHA-256
  `83de97b744b931e544b569e6e750f8415545f226461bd2e36cfb49225898ad3e`.

## File structure

### Create

- `services/subdub_multi_speaker_embedding_onnx.py`: pure validation,
  feature extraction, ONNX inference, deterministic stable clustering, and
  word-to-cue reconstruction for Auto Multi only.
- `assets/models/subdub_auto_multi/voxceleb_resnet34.onnx`: exact approved
  model bytes.
- `assets/models/subdub_auto_multi/WESPEAKER.LICENSE.APACHE-2.0`: source-code
  license.
- `assets/models/subdub_auto_multi/VOXCELEB.MODEL.LICENSE.CC-BY-4.0`: weight
  license text.
- `assets/models/subdub_auto_multi/THIRD_PARTY_NOTICES.md`: attribution,
  source URL, file size, and SHA-256.
- `tests/test_p0_subdub_auto_multi_embedding_onnx.py`: focused model,
  frontend, inference, clustering, coverage, timeout, and cancellation tests.
- `tests/test_p0_subdub_auto_multi_acoustic_word_timeline.py`: strict Deepgram
  word authority and propagation tests.
- `tests/resource_gates/test_p0_subdub_auto_multi_embedding_fixture.py`:
  exact-fixture offline `k=5` resource gate.
- `tests/fixtures/subdub_auto_multi_fbank_golden.npz`: immutable feature
  values emitted by the Apache-licensed WeSpeaker C++ frontend reference.
- `tests/fixtures/subdub_auto_multi_fixture_words.json`: sanitized exact-
  fixture word timeline containing only sequential index, text, start, and end;
  no provider payload, speaker label, key, endpoint, file ID, or user data.

### Modify

- `bot.py`: strict word-timeline seam, Auto-Multi-only acoustic dispatch,
  aggregate evidence propagation, command literal, and fourth/final same-job
  recovery CAS.
- `services/subdub_blackboxes/auto_multi_speaker.py`: require and consume
  acoustic-prepared source cues; provider cross-timeline diarization is no
  longer a default or fallback authority.
- `tests/test_p0_subdub_multi_speaker_blackbox.py`: isolated acoustic adapter
  dispatch and no-provider-crosswalk assertions.
- `tests/test_p0_subdub_auto_multi_failed_job_recovery.py`: final acoustic CAS
  and attempt-five block.
- measured operational docs selected by `bao-cao-truoc-khi-push` after code is
  terminal.

### Byte-protected production files

Do not edit:

- `services/subdub_speaker_cast.py` — expected SHA-256
  `de93620f3f038b5759a53e696c5c85d3553fcee758686df56c70e6b11bac145b`;
- `services/subdub_two_speaker_asr_fallback.py` — expected SHA-256
  `94748def11c38d76952192a996fa42231d75b39d4d9ecd3407ff671d92e1177e`;
- `services/subdub_two_speaker_gender_onnx.py`;
- `services/subdub_blackboxes/auto_speaker.py`;
- `services/subdub_blackboxes/dub_only.py`;
- `services/subdub_blackboxes/subtitle_dub.py`;
- `services/subtitle_dub_product_pipeline.py`;
- all PayOS, wallet, `/naptien`, payment, top-up, Product Video, WebApp,
  onboarding, and PWA files.

## Global constraints

- Only exact state `voice_kind=auto_speaker_gender`,
  `voice_selection_mode=auto_speaker`, and `auto_speaker_lane=multi` may use
  the new backend.
- No ENV variable, key, endpoint, provider order, package version, database
  schema, wallet primitive, or public price changes.
- Local embedding performs zero network calls and creates zero
  `provider_usage_events`.
- Deepgram word-timed ASR is allowed only after the existing confirmed-product
  gate; provider diarization parameters are forbidden on the acoustic path.
- Speaker count is selected from 3 through 8; no expected-count input exists.
- Every source word is covered exactly once and retains provider start/end.
- Translation preserves cue count and timestamps exactly.
- Distinct validated voice count equals retained speaker count.
- The existing final mux receives original volume 40 and dubbed volume 150.
- Success requires a real validated/delivered MP4 followed by exactly one
  receipt.
- Final recovery targets only internal job `b4cb6d5fe8a7bdfce507`, public code
  `B4CB6D5FE8`, exact fixture SHA, English, 40/150, attempt 4, and
  `charged_xu=0`.
- Root engine-job count must not increase. Attempt 5 is forbidden.
- No code step may stage `.agents/tools/` or `artifacts/`.
- Each production behavior is implemented only after its focused test has
  failed for the expected reason.

---

### Task 1: Hash-locked model assets and preflight contract

**Files:**
- Create: `services/subdub_multi_speaker_embedding_onnx.py`
- Create: `assets/models/subdub_auto_multi/voxceleb_resnet34.onnx`
- Create: `assets/models/subdub_auto_multi/WESPEAKER.LICENSE.APACHE-2.0`
- Create: `assets/models/subdub_auto_multi/VOXCELEB.MODEL.LICENSE.CC-BY-4.0`
- Create: `assets/models/subdub_auto_multi/THIRD_PARTY_NOTICES.md`
- Create/Test: `tests/test_p0_subdub_auto_multi_embedding_onnx.py`

**Interfaces:**
- Produces:
  - `MODEL_SHA256: str`;
  - `ALGORITHM_VERSION: str`;
  - `def model_preflight(*, session_factory: Callable | None = None) -> dict[str, object]`.
- `model_preflight()` returns only bounded metadata: `ok`, `status`,
  `model_sha256`, `model_bytes`, `input_name`, `output_name`,
  `embedding_dim`, `providers`. It raises
  `speaker_cast.AutoCastManualRequired` on every invalid asset/schema case.

- [ ] **Step 1: Record protected hashes before any edit**

Run:

```powershell
Get-FileHash -Algorithm SHA256 -LiteralPath `
  services\subdub_speaker_cast.py,services\subdub_two_speaker_asr_fallback.py
```

Expected: the two hashes in Global Constraints, in the same order.

- [ ] **Step 2: Write preflight RED tests**

Add these test names and literal behaviors to
`tests/test_p0_subdub_auto_multi_embedding_onnx.py`:

```python
from dataclasses import dataclass
from pathlib import Path

@dataclass
class FakeIO:
    name: str
    shape: list[object]
    type: str

class FakeSession:
    def __init__(self, *, inputs, outputs, providers):
        self._inputs = inputs
        self._outputs = outputs
        self._providers = providers

    def get_inputs(self):
        return list(self._inputs)

    def get_outputs(self):
        return list(self._outputs)

    def get_providers(self):
        return list(self._providers)

def write_exact_asset_fixture(tmp_path: Path):
    model = tmp_path / "voxceleb_resnet34.onnx"
    model.write_bytes(b"exact-test-model")
    notices = tuple(tmp_path / name for name in ("apache", "cc-by", "notices"))
    for notice in notices:
        notice.write_text("nonempty license fixture", encoding="utf-8")
    return model, notices

def test_acoustic_model_preflight_accepts_exact_assets(monkeypatch, tmp_path):
    model, notices = write_exact_asset_fixture(tmp_path)
    fake = FakeSession(
        inputs=[FakeIO("feats", ["B", "T", 80], "tensor(float)")],
        outputs=[FakeIO("embs", ["B", 256], "tensor(float)")],
        providers=["CPUExecutionProvider"],
    )
    monkeypatch.setattr(service, "MODEL_PATH", model)
    monkeypatch.setattr(service, "NOTICE_PATHS", notices)
    monkeypatch.setattr(service, "MODEL_SHA256", hashlib.sha256(model.read_bytes()).hexdigest())
    result = service.model_preflight(session_factory=lambda *_a, **_k: fake)
    assert result == {
        "ok": True,
        "status": "PASS",
        "model_sha256": hashlib.sha256(model.read_bytes()).hexdigest(),
        "model_bytes": len(model.read_bytes()),
        "input_name": "feats",
        "output_name": "embs",
        "embedding_dim": 256,
        "providers": ["CPUExecutionProvider"],
    }

@pytest.mark.parametrize("mutation", ["missing_model", "wrong_hash", "missing_notice"])
def test_acoustic_model_preflight_rejects_invalid_assets(monkeypatch, tmp_path, mutation):
    model, notices = write_exact_asset_fixture(tmp_path)
    expected_hash = hashlib.sha256(model.read_bytes()).hexdigest()
    if mutation == "missing_model":
        model.unlink()
    elif mutation == "wrong_hash":
        expected_hash = "0" * 64
    else:
        notices[0].unlink()
    monkeypatch.setattr(service, "MODEL_PATH", model)
    monkeypatch.setattr(service, "NOTICE_PATHS", notices)
    monkeypatch.setattr(service, "MODEL_SHA256", expected_hash)
    with pytest.raises(speaker_cast.AutoCastManualRequired):
        service.model_preflight(session_factory=lambda *_a, **_k: None)

@pytest.mark.parametrize("schema", ["wrong_input_name", "wrong_mel_bins", "wrong_output_name", "wrong_dim", "non_cpu_provider"])
def test_acoustic_model_preflight_rejects_schema_or_provider(monkeypatch, tmp_path, schema):
    model, notices = write_exact_asset_fixture(tmp_path)
    input_name = "wrong" if schema == "wrong_input_name" else "feats"
    mel_bins = 40 if schema == "wrong_mel_bins" else 80
    output_name = "wrong" if schema == "wrong_output_name" else "embs"
    output_dim = 128 if schema == "wrong_dim" else 256
    providers = ["CUDAExecutionProvider"] if schema == "non_cpu_provider" else ["CPUExecutionProvider"]
    fake = FakeSession(
        inputs=[FakeIO(input_name, ["B", "T", mel_bins], "tensor(float)")],
        outputs=[FakeIO(output_name, ["B", output_dim], "tensor(float)")],
        providers=providers,
    )
    monkeypatch.setattr(service, "MODEL_PATH", model)
    monkeypatch.setattr(service, "NOTICE_PATHS", notices)
    monkeypatch.setattr(service, "MODEL_SHA256", hashlib.sha256(model.read_bytes()).hexdigest())
    with pytest.raises(speaker_cast.AutoCastManualRequired):
        service.model_preflight(session_factory=lambda *_a, **_k: fake)
```

The helper writes deterministic local bytes only; no live ONNX import is used
in unit tests.

- [ ] **Step 3: Run RED and verify the missing module/interface is the cause**

Run:

```powershell
& 'C:\Users\toann\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest -q tests/test_p0_subdub_auto_multi_embedding_onnx.py -k model_preflight
```

Expected: collection/import FAIL naming
`services.subdub_multi_speaker_embedding_onnx` or
`model_preflight`; no unrelated error.

- [ ] **Step 4: Copy the exact binary and license sources**

Run from the project root:

```powershell
New-Item -ItemType Directory -Force assets\models\subdub_auto_multi
Copy-Item -LiteralPath artifacts\speaker-embedding-diagnostic\voxceleb_resnet34.onnx `
  -Destination assets\models\subdub_auto_multi\voxceleb_resnet34.onnx
Copy-Item -LiteralPath artifacts\speaker-embedding-diagnostic\wespeaker-master\LICENSE `
  -Destination assets\models\subdub_auto_multi\WESPEAKER.LICENSE.APACHE-2.0
Copy-Item -LiteralPath assets\models\subdub_auto_gender\PANNs.MODEL.LICENSE.CC-BY-4.0 `
  -Destination assets\models\subdub_auto_multi\VOXCELEB.MODEL.LICENSE.CC-BY-4.0
```

Expected: model length 26,534,127 and SHA-256
`9FEA6516D7AD6BF0A76C7689F5A49B65D330FAD6DDE96C91BB4435FFBFE056A1`.

- [ ] **Step 5: Add exact attribution notice**

Create `THIRD_PARTY_NOTICES.md` with these facts, preserving the full license
files copied in Step 4:

```markdown
# Third-party notices — SubDub Auto Multi speaker embedding

## WeSpeaker source
- Project: WeSpeaker, https://github.com/wenet-e2e/wespeaker
- License: Apache License 2.0; see `WESPEAKER.LICENSE.APACHE-2.0`.

## VoxCeleb ResNet34 pretrained runtime model
- Upstream file: `voxceleb_resnet34.onnx`
- Upstream catalog: WeSpeaker `docs/pretrained.md`
- Dataset/model license: Creative Commons Attribution 4.0 International;
  see `VOXCELEB.MODEL.LICENSE.CC-BY-4.0`.
- Model bytes: 26,534,127
- SHA-256: `9fea6516d7ad6bf0a76c7689f5a49b65d330fad6dde96c91bb4435ffbfe056a1`
- This repository does not modify the pretrained weight tensor values.
```

- [ ] **Step 6: Implement minimal asset and schema preflight**

Start `services/subdub_multi_speaker_embedding_onnx.py` with:

```python
ROOT = Path(__file__).resolve().parents[1]
MODEL_DIR = ROOT / "assets" / "models" / "subdub_auto_multi"
MODEL_PATH = MODEL_DIR / "voxceleb_resnet34.onnx"
NOTICE_PATHS = (
    MODEL_DIR / "WESPEAKER.LICENSE.APACHE-2.0",
    MODEL_DIR / "VOXCELEB.MODEL.LICENSE.CC-BY-4.0",
    MODEL_DIR / "THIRD_PARTY_NOTICES.md",
)
MODEL_SHA256 = "9fea6516d7ad6bf0a76c7689f5a49b65d330fad6dde96c91bb4435ffbfe056a1"
ALGORITHM_VERSION = "wespeaker-resnet34-spectral-v1"
MODEL_INPUT_NAME = "feats"
MODEL_OUTPUT_NAME = "embs"
MEL_BINS = 80
EMBEDDING_DIM = 256

def model_preflight(*, session_factory=None) -> dict[str, object]:
    # Verify notices, size, SHA, CPU provider, names, tensor(float), and ranks.
    # Import onnxruntime lazily only when session_factory is None.
```

Configure `SessionOptions.inter_op_num_threads = 1` and
`intra_op_num_threads = 1`. Pass `providers=["CPUExecutionProvider"]`.

- [ ] **Step 7: Run GREEN and asset integrity checks**

Run:

```powershell
& 'C:\Users\toann\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest -q tests/test_p0_subdub_auto_multi_embedding_onnx.py -k model_preflight
Get-FileHash -Algorithm SHA256 assets\models\subdub_auto_multi\voxceleb_resnet34.onnx
git diff --check
```

Expected: all focused tests PASS, exact model SHA, diff-check exit 0.

- [ ] **Step 8: Commit Task 1 only**

```powershell
git add services/subdub_multi_speaker_embedding_onnx.py `
  tests/test_p0_subdub_auto_multi_embedding_onnx.py `
  assets/models/subdub_auto_multi
git commit -m "feat(subdub): add hash-locked multi speaker model"
```

Expected: `.agents/tools/` and `artifacts/` remain untracked and unstaged.

---

### Task 2: Strict Deepgram word-timeline authority

**Files:**
- Create/Test: `tests/test_p0_subdub_auto_multi_acoustic_word_timeline.py`
- Modify: `bot.py:40365-40411`
- Modify: `bot.py:64930-65106`
- Modify: `bot.py:244855-245425`

**Interfaces:**
- Produces:
  - `def deepgram_acoustic_word_items(data: dict, *, duration_seconds: float) -> list[dict]`;
  - keyword-only `require_auto_multi_word_timeline: bool = False` added to
    `asr_transcribe_audio`, `transcribe_media_to_segments`, and
    `video_dubbing_resolve_source_script` without changing their other
    parameters or defaults;
  - result field `word_timeline: list[dict]` only on the exact acoustic path.
- Consumes the existing `AgentDeepgram.diagnostic` with
  `require_diarization=False` and ignores every provider `speaker` field.

- [ ] **Step 1: Write strict extractor RED tests**

Use complete literal Deepgram payloads. The passing test asserts:

```python
assert bot.deepgram_acoustic_word_items(payload, duration_seconds=2.0) == [
    {"index": 0, "word": "Hello", "start": 0.1, "end": 0.4},
    {"index": 1, "word": "world", "start": 0.5, "end": 0.9},
]
```

Parameterized failures must return `[]` for missing text, bool/NaN/Inf times,
`end <= start`, decreasing start, duplicated identity, negative start, end past
source duration, or non-list word payload. Include arbitrary provider speaker
labels and assert they never appear in output.

- [ ] **Step 2: Run extractor RED**

Run:

```powershell
& 'C:\Users\toann\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest -q tests/test_p0_subdub_auto_multi_acoustic_word_timeline.py -k extractor
```

Expected: FAIL because `deepgram_acoustic_word_items` is absent.

- [ ] **Step 3: Implement the strict extractor without repairing input**

Implement a separate function; do not modify the permissive shared
`deepgram_word_items()`. Use `type(value) in {int, float}` rather than truthy
coercion; reject the entire list on the first malformed row. Normalize only
whitespace in text and round finite times to 3 decimals after validation.

- [ ] **Step 4: Run extractor GREEN**

Run the Step-2 command. Expected: all extractor tests PASS.

- [ ] **Step 5: Write routing RED tests**

Add tests that call `asr_transcribe_audio` with
`require_auto_multi_word_timeline=True` and a fake Deepgram diagnostic:

```python
assert captured_params["diarize_model"] is None
assert result["provider"] == "deepgram"
assert result["word_timeline"] == expected_words
```

Also assert:

- missing confirmed-product authority returns `AUTO_CAST_UNAVAILABLE` before
  the fake provider call;
- `ASR_PROVIDER="key4u"` still selects Deepgram for this exact flag;
- every call without the flag has the exact old result shape;
- `require_diarization=True` and `require_auto_multi_word_timeline=True`
  together fail closed as mutually exclusive.

- [ ] **Step 6: Run routing RED**

Run:

```powershell
& 'C:\Users\toann\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest -q tests/test_p0_subdub_auto_multi_acoustic_word_timeline.py -k "routing or propagation"
```

Expected: FAIL because the keyword/result field is absent.

- [ ] **Step 7: Implement additive flag propagation**

In `asr_transcribe_audio`:

```python
require_auto_multi_word_timeline = bool(require_auto_multi_word_timeline)
if require_diarization and require_auto_multi_word_timeline:
    return {
        "ok": False,
        "status": AUTO_CAST_UNAVAILABLE,
        "provider": "",
        "text": "",
        "segments": [],
        "word_timeline": [],
        "detail": "acoustic_word_timeline_conflict",
    }
provider_order = ["deepgram"] if (
    require_diarization or require_auto_multi_word_timeline
) else existing_provider_order
```

Call `deepgram_asr_adapter(audio_bytes, content_type,
require_diarization=False, timeout_seconds=timeout_seconds)` for the acoustic
flag, validate strict words, and return `ACOUSTIC_WORD_TIMELINE_REQUIRED` if
they are absent. Propagate the flag and `word_timeline` through direct media
transcription and `video_dubbing_resolve_source_script`. Set the direct
threshold to five minutes for the flag so the approved 133.375-second fixture
uses one globally timed response. Do not add chunk-word merging in this task.

- [ ] **Step 8: Run word-timeline GREEN and shared comparators**

```powershell
& 'C:\Users\toann\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest -q tests/test_p0_subdub_auto_multi_acoustic_word_timeline.py
& 'C:\Users\toann\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest -q tests/test_p0_subdub_multi_speaker_provider_fallback.py -k "deepgram or request"
```

Expected: both commands PASS; no provider network call.

- [ ] **Step 9: Commit Task 2**

```powershell
git add bot.py tests/test_p0_subdub_auto_multi_acoustic_word_timeline.py
git commit -m "feat(subdub): expose strict multi word timeline"
```

---

### Task 3: Acoustic units and independent NumPy fbank frontend

**Files:**
- Modify: `services/subdub_multi_speaker_embedding_onnx.py`
- Modify/Test: `tests/test_p0_subdub_auto_multi_embedding_onnx.py`
- Create: `tests/fixtures/subdub_auto_multi_fbank_golden.npz`
- Create temporary and delete after fixture generation:
  `tmp/subdub_auto_multi_fbank_reference.cc`

**Interfaces:**
- Produces:
  - `def validate_word_timeline(words: object, *, duration_seconds: float) -> list[dict]`;
  - `def build_acoustic_units(words: object, *, duration_seconds: float) -> list[dict]`;
  - `def compute_fbank(pcm_samples: numpy.ndarray) -> numpy.ndarray`.
- Unit shape:

```python
{
    "unit_index": int,
    "word_indexes": list[int],
    "start": float,
    "end": float,
    "original_speech_seconds": float,
}
```

- [ ] **Step 1: Write unit-builder RED tests**

Literal cases must prove: a 0.35-second-or-smaller gap remains in one unit;
larger gap splits; 2.5-second maximum splits only before a word; each word
index occurs once; six units minimum; more than
`speaker_cast.MAX_SIDECAR_CUES` fails; a short unit retains original times.

- [ ] **Step 2: Run unit-builder RED**

```powershell
& 'C:\Users\toann\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest -q tests/test_p0_subdub_auto_multi_embedding_onnx.py -k "word_timeline or acoustic_units"
```

Expected: FAIL naming the missing functions.

- [ ] **Step 3: Implement bounded validation and units**

Use constants:

```python
PCM_SAMPLE_RATE = 16_000
PCM_BYTES_PER_SAMPLE = 2
UNIT_MAX_SECONDS = 2.5
UNIT_SPLIT_GAP_SECONDS = 0.35
UNIT_MIN_FEATURE_SECONDS = 0.5
MIN_UNITS = 6
MIN_SPEAKERS = 3
MAX_SPEAKERS = 8
```

Reject rather than sort, repair, deduplicate, or truncate malformed words.

- [ ] **Step 4: Run unit-builder GREEN**

Run the Step-2 command. Expected: PASS.

- [ ] **Step 5: Generate an independent golden fbank fixture**

Create a temporary C++ harness using the exact Apache-licensed WeSpeaker
`runtime/core/frontend/fbank.h` with 80 bins, 16 kHz, frame length 400, frame
shift 160, dither 0, DC removal true, preemphasis 0.97, Hamming window, and
snip-edges. Feed a deterministic 0.75-second PCM waveform whose integer sample
formula is stored beside the expected array. Compile/run the reference outside
production code, then save only:

```text
sample_rate=16000
sample_formula_version=1
features float32 [T,80]
```

to `tests/fixtures/subdub_auto_multi_fbank_golden.npz`. Delete the temporary
harness and binary after comparing two identical reference runs.

Expected: fixture hash is stable across the two runs and contains no source
audio or personal data.

- [ ] **Step 6: Write fbank RED tests**

Tests reconstruct the deterministic PCM from the literal formula and assert:

```python
actual.shape == expected.shape
numpy.testing.assert_allclose(actual, expected, rtol=2e-4, atol=2e-4)
numpy.testing.assert_allclose(actual.mean(axis=0), 0.0, atol=2e-5)
```

Separate tests reject wrong rank/dtype, empty audio, NaN/Inf, and fewer than
400 samples. A 200 ms short unit test zero-pads only for features and asserts
its original start/end are unchanged.

- [ ] **Step 7: Run fbank RED**

```powershell
& 'C:\Users\toann\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest -q tests/test_p0_subdub_auto_multi_embedding_onnx.py -k fbank
```

Expected: FAIL because `compute_fbank` is absent.

- [ ] **Step 8: Implement NumPy frontend**

Implement the reference sequence exactly:

```text
float PCM scaled by 2^15
-> frames [400] at hop 160, snip edges
-> remove per-frame DC mean
-> preemphasis 0.97
-> periodic Hamming window 0.54 - 0.46*cos(2*pi*i/399)
-> zero-pad to 512
-> rfft power, bins [0:256]
-> 80 triangular mel filters, 20 Hz to Nyquist, Kaldi mel scale
-> max energy with float32 epsilon
-> natural log
-> per-unit feature-axis mean subtraction
```

Cache only the immutable mel matrix and Hamming window. No SciPy, Torch,
Torchaudio, Librosa, or global raw PCM cache.

- [ ] **Step 9: Run fbank GREEN and deterministic replay**

Run the Step-7 command twice. Expected: both PASS with identical test output.

- [ ] **Step 10: Commit Task 3**

```powershell
git add services/subdub_multi_speaker_embedding_onnx.py `
  tests/test_p0_subdub_auto_multi_embedding_onnx.py `
  tests/fixtures/subdub_auto_multi_fbank_golden.npz
git commit -m "feat(subdub): add deterministic speaker fbank"
```

---

### Task 4: CPU-only ONNX embeddings, lock, timeout, and cancellation

**Files:**
- Modify: `services/subdub_multi_speaker_embedding_onnx.py`
- Modify/Test: `tests/test_p0_subdub_auto_multi_embedding_onnx.py`

**Interfaces:**
- Produces:

```python
def extract_unit_embeddings(
    pcm_path: str,
    units: object,
    *,
    deadline_monotonic: float,
    stop_requested: Callable[[], bool],
    session_factory: Callable | None = None,
) -> numpy.ndarray:  # float32 [N,256], row-L2-normalized
```

- One module-local `threading.Lock`; lazy session creation; one batch per unit
  because feature lengths differ.

- [ ] **Step 1: Write inference RED tests**

Use `FakeSession.run()` to assert exact feed/output names and float32 shape.
Tests must cover valid normalized embeddings, zero/NaN/Inf/wrong dimension,
inconsistent dimension, missing PCM, misaligned PCM size, source beyond
deadline, stopped callback, concurrent lock contention, and session exception.

- [ ] **Step 2: Run inference RED**

```powershell
& 'C:\Users\toann\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest -q tests/test_p0_subdub_auto_multi_embedding_onnx.py -k embedding
```

Expected: FAIL because `extract_unit_embeddings` is absent.

- [ ] **Step 3: Implement minimal inference runner**

Read exact mono s16le ranges from `pcm_path`; zero-pad only to 0.5 seconds;
call `compute_fbank`; enforce deadline/stop before every read, frontend, and
session call; L2-normalize each output. Raise existing
`AutoCastManualRequired` for bounded validation/provider exceptions; re-raise
`asyncio.CancelledError` only from the async wrapper in Task 7.

- [ ] **Step 4: Run inference GREEN and lock replay**

Run the Step-2 command twice. Expected: all tests PASS; lock is acquirable
after every failure.

- [ ] **Step 5: Commit Task 4**

```powershell
git add services/subdub_multi_speaker_embedding_onnx.py `
  tests/test_p0_subdub_auto_multi_embedding_onnx.py
git commit -m "feat(subdub): extract bounded speaker embeddings"
```

---

### Task 5: Deterministic stable 3-8 speaker clustering

**Files:**
- Modify: `services/subdub_multi_speaker_embedding_onnx.py`
- Modify/Test: `tests/test_p0_subdub_auto_multi_embedding_onnx.py`

**Interfaces:**
- Produces:

```python
def spectral_cluster_embeddings(
    base_embeddings: object,
    shifted_embeddings: object,
) -> dict[str, object]:
    # {ok,status,speaker_count,labels,cluster_sizes,eigenvalues,
    #  stability_pass,algorithm_version}
```

- [ ] **Step 1: Write clustering RED tests**

Use hand-authored embedding matrices with literal expected canonical labels for
three, five, and eight clusters. Tests also cover two/nine clusters, fewer than
six units, cluster with one unit, cluster under 0.8 original speech seconds,
NaN/Inf/zero norm, empty cluster, non-convergence, base/shifted `k`
disagreement, assignment disagreement, input permutation with restored source
order, and deterministic replay.

- [ ] **Step 2: Run clustering RED**

```powershell
& 'C:\Users\toann\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest -q tests/test_p0_subdub_auto_multi_embedding_onnx.py -k cluster
```

Expected: FAIL because `spectral_cluster_embeddings` is absent.

- [ ] **Step 3: Implement the bounded NumPy algorithm**

Implement:

```python
similarity = 0.5 * (1.0 + embeddings @ embeddings.T)
neighbor_count = max(2, unit_count - 10) if unit_count < 1000 else int(unit_count * 0.99)
pruned = symmetric_nearest_neighbor_matrix(similarity, neighbor_count)
laplacian = numpy.diag(numpy.abs(pruned).sum(axis=1)) - pruned
eigenvalues, eigenvectors = numpy.linalg.eigh(laplacian)
k = argmax(diff(eigenvalues[:9])) + 1
```

Accept only `3 <= k <= 8`. Use deterministic farthest-first centroid seeds:
first unit in source order, then the unit with greatest minimum distance;
stable lowest-index tie break; 30 iterations maximum. Canonicalize labels by
earliest unit source time. Compare base and shifted assignments after the same
canonicalization.

- [ ] **Step 4: Run clustering GREEN**

Run the Step-2 command. Expected: all clustering tests PASS twice.

- [ ] **Step 5: Commit Task 5**

```powershell
git add services/subdub_multi_speaker_embedding_onnx.py `
  tests/test_p0_subdub_auto_multi_embedding_onnx.py
git commit -m "feat(subdub): cluster stable acoustic speakers"
```

---

### Task 6: Full word coverage and canonical acoustic source cues

**Files:**
- Modify: `services/subdub_multi_speaker_embedding_onnx.py`
- Modify/Test: `tests/test_p0_subdub_auto_multi_embedding_onnx.py`

**Interfaces:**
- Produces:

```python
def build_clustered_segments(
    words: object,
    units: object,
    labels: object,
) -> list[dict]:
    # canonical cue_id/index/start/end/text/speaker/speaker_id/
    # speaker_confidence/chunk_index

def diarize_word_timeline(
    pcm_path: str,
    words: object,
    *,
    duration_seconds: float,
    deadline_monotonic: float,
    stop_requested: Callable[[], bool],
    session_factory: Callable | None = None,
) -> dict[str, object]:
```

- `diarize_word_timeline` composes Tasks 3-5 and returns bounded aggregate
  evidence plus source segments; it returns no embedding/raw PCM/provider
  payload.

- [ ] **Step 1: Write segment reconstruction RED tests**

Tests assert cluster changes create boundaries, adjacent same-cluster units
merge, word text/order/count are exact, every word appears once, cue times are
the first/last word times, speaker IDs follow earliest-time canonical order,
all selected labels appear, and malformed/missing/extra labels fail closed.

- [ ] **Step 2: Run reconstruction RED**

```powershell
& 'C:\Users\toann\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest -q tests/test_p0_subdub_auto_multi_embedding_onnx.py -k "clustered_segments or diarize_word_timeline"
```

Expected: FAIL naming missing functions.

- [ ] **Step 3: Implement source cue reconstruction**

Generate IDs with a stable hash of ordered word indexes/start/end and use
`speaker_cast.normalized_speaker_key(0, label)`. Confidence is the minimum
unit stability confidence contributing to a cue, bounded `[0,1]`; never copy a
provider speaker confidence.

- [ ] **Step 4: Implement the public composition result**

Return this bounded shape:

```python
{
    "ok": True,
    "status": "PASS",
    "provider": "local_wespeaker_resnet34_spectral",
    "segments": segments,
    "detected_speaker_count": k,
    "model_sha256": MODEL_SHA256,
    "algorithm_version": ALGORITHM_VERSION,
    "word_count": len(words),
    "unit_count": len(units),
    "embedding_window_count": len(units) * 2,
    "cluster_sizes": sorted(cluster_sizes),
    "stability_pass": True,
    "word_coverage_count": len(words),
}
```

No word text, embedding, cluster centroid, or filesystem path appears in the
aggregate evidence fields.

- [ ] **Step 5: Run reconstruction GREEN**

Run the Step-2 command. Expected: PASS.

- [ ] **Step 6: Commit Task 6**

```powershell
git add services/subdub_multi_speaker_embedding_onnx.py `
  tests/test_p0_subdub_auto_multi_embedding_onnx.py
git commit -m "feat(subdub): build acoustic multi speaker cues"
```

---

### Task 7: Auto-Multi-only preparation and pipeline integration

**Files:**
- Modify: `bot.py:245305-245426`
- Modify: `bot.py:246858-247285`
- Modify: `bot.py:249158-249300`
- Modify: `services/subdub_blackboxes/auto_multi_speaker.py:1076-1275`
- Modify/Test: `tests/test_p0_subdub_multi_speaker_blackbox.py`
- Modify/Test: `tests/test_p0_subdub_auto_multi_acoustic_word_timeline.py`

**Interfaces:**
- Consumes `diarize_word_timeline` from Task 6.
- Produces in `auto_multi_speaker.py`:

```python
async def run_local_acoustic_diarization_off_event_loop(
    pcm_path: Path,
    word_timeline: list[dict],
    *,
    duration_seconds: float,
    acoustic_diarize: Callable = subdub_multi_speaker_embedding_onnx.diarize_word_timeline,
) -> dict[str, object]:
```

- Produces acoustic aggregate state fields prefixed `multi_acoustic_`.

- [ ] **Step 1: Write integration RED tests**

Complete fake preparation tests must prove:

- exact multi passes `require_auto_multi_word_timeline=True`;
- exact-two/manual/default pass false or omit the keyword;
- embedded/visual subtitle shortcuts are bypassed for exact acoustic multi;
- the fake local acoustic backend receives PCM plus the same strict words;
- acoustic source segments are installed before the fake translation call;
- translated segments preserve acoustic cue count/start/end;
- sidecar has the acoustic segments and five labels in the five-speaker test;
- provider `rediarize_underclustered_segments` is never called;
- an acoustic failure returns canonical manual-required before TTS/mux/charge;
- timeout/cancellation drains the thread, cleans PCM, and creates no sidecar.

- [ ] **Step 2: Run integration RED**

```powershell
& 'C:\Users\toann\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest -q tests/test_p0_subdub_multi_speaker_blackbox.py `
  tests/test_p0_subdub_auto_multi_acoustic_word_timeline.py `
  -k "local_acoustic or word_timeline_before_translation or no_provider_rediarization"
```

Expected: FAIL because acoustic dispatch is absent and provider rediarization
is still called.

- [ ] **Step 3: Add exact acoustic resolver flag**

In `video_dubbing_resolve_source_script`, when
`require_auto_multi_word_timeline=True`, skip embedded subtitle and visual OCR
returns, pass the flag to direct transcription, and require a nonempty strict
`word_timeline` before returning `source_kind="asr"`.

- [ ] **Step 4: Add bounded PCM plus off-loop acoustic helper**

Reuse `_extract_subdub_auto_pcm` with `(channels=1, sample_rate=16000,
sample_format="s16le")`. Create the helper in the Auto Multi module with a
300-second deadline, `threading.Event`, `asyncio.to_thread`, shielded wait,
bounded drain, and guaranteed transient PCM cleanup.

- [ ] **Step 5: Run acoustic preparation before translation**

In `video_dubbing_prepare_subtitles`, only when the exact Auto Multi state is
active and `require_auto_cast=True`:

1. require `source_info["word_timeline"]`;
2. build a minimal pre-translation prepared structure with source bytes/state;
3. extract PCM;
4. await the local acoustic helper;
5. replace `source_segments` with acoustic segments;
6. build/persist the sidecar from those segments;
7. continue into the existing translation block unchanged.

Do not build a two-label sidecar first. Do not call Gemini or the old
rediarization function as fallback.

- [ ] **Step 6: Simplify Auto Multi wrapper authority**

Remove the default provider-rediarization call from
`prepare_multi_subtitles`. Validate that prepared source/output segments and
sidecar already contain 3-8 acoustic labels. Keep existing register
classification, distinct voice assignment, per-cue synthesis, proof fields,
lane delegation, and failure normalization.

- [ ] **Step 7: Persist bounded acoustic evidence**

Copy only these fields into the current durable job/manifest state:

```text
multi_acoustic_backend
multi_acoustic_model_sha256
multi_acoustic_algorithm_version
multi_acoustic_speaker_count
multi_acoustic_word_count
multi_acoustic_unit_count
multi_acoustic_embedding_window_count
multi_acoustic_cluster_sizes
multi_acoustic_stability_pass
multi_acoustic_word_coverage_count
```

Do not persist word text, embeddings, PCM, model/session objects, provider raw
payload, labels before canonicalization, or paths outside the existing bounded
sidecar/workspace fields.

- [ ] **Step 8: Run integration GREEN and protected route comparators**

```powershell
& 'C:\Users\toann\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest -q tests/test_p0_subdub_multi_speaker_blackbox.py `
  tests/test_p0_subdub_auto_multi_acoustic_word_timeline.py
& 'C:\Users\toann\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest -q tests/test_p0_subdub_multi_speaker_provider_fallback.py
```

Expected: PASS; provider-fallback tests remain green but no active Auto Multi
dispatch depends on their speaker labels.

- [ ] **Step 9: Commit Task 7**

```powershell
git add bot.py services/subdub_blackboxes/auto_multi_speaker.py `
  tests/test_p0_subdub_multi_speaker_blackbox.py `
  tests/test_p0_subdub_auto_multi_acoustic_word_timeline.py
git commit -m "feat(subdub): route multi speaker through local acoustics"
```

---

### Task 8: Fourth and final same-job acoustic recovery CAS

**Files:**
- Modify: `bot.py:146032-146155`
- Modify: `bot.py:248180-248650`
- Modify/Test: `tests/test_p0_subdub_auto_multi_failed_job_recovery.py`

**Interfaces:**
- Adds command literal `--confirm-local-acoustic` to the existing admin
  recovery command.
- Adds keyword-only `allow_acoustic_recovery: bool = False` to the existing
  `claim_subdub_failed_auto_multi_recovery` signature without changing its
  other parameters or defaults.

- [ ] **Step 1: Write final-CAS RED test**

Seed the exact durable state after attempt 3:

```python
{
    "internal_job_id": "b4cb6d5fe8a7bdfce507",
    "public_code": "B4CB6D5FE8",
    "status": "failed_no_charge",
    "terminal_state": "failed_no_charge",
    "charge_status": "not_charged",
    "charged_xu": 0,
    "auto_multi_recovery_attempt_count": 3,
    "auto_multi_recovery_correction_attempt_count": 2,
    "auto_multi_recovery_crosswalk_correction_used": True,
    "output_sent": False,
    "delivery_attempted": False,
    "artifact_started": False,
    "final_mp4_exists": False,
    "output_validated": False,
}
```

Call claim with the exact owner/chat/source/language/40/150,
`allow_acoustic_recovery=True`, and an injected
`acoustic_preflight=lambda: {"ok": True, "status": "PASS",
"model_sha256": MODEL_SHA256, "algorithm_version": ALGORITHM_VERSION}`.
Assert attempt 4, correction 3, `auto_multi_acoustic_recovery_used=True`, same
job key/code/workspace, and unchanged root job count. Persist another terminal
failure and assert the fifth claim returns `recovery_already_used` with no
mutation.

- [ ] **Step 2: Run CAS RED**

```powershell
& 'C:\Users\toann\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest -q tests/test_p0_subdub_auto_multi_failed_job_recovery.py `
  -k acoustic_recovery
```

Expected: FAIL because the argument/literal/marker is absent.

- [ ] **Step 3: Add preflight before transaction and exact acoustic condition**

When the literal is present, call the injected/default
`model_preflight()` before opening `BEGIN IMMEDIATE`. Inside the existing
transaction, require every exact field from the spec. On success update:

```python
"auto_multi_recovery_attempt_count": 4,
"auto_multi_recovery_correction_attempt_count": 3,
"auto_multi_acoustic_recovery_used": True,
"auto_multi_acoustic_backend": "local_wespeaker_resnet34_spectral",
"auto_multi_acoustic_algorithm_version": ALGORITHM_VERSION,
"auto_multi_acoustic_model_sha256": MODEL_SHA256,
```

No flag may bypass attempt/source/owner/no-output/no-charge conditions.

- [ ] **Step 4: Add command parsing without changing earlier literals**

Accept only:

```text
/subdub_recover_failed_auto_multi <internal_id> <sha256> English 40 150 --confirm-paid --confirm-local-acoustic
```

The legacy observability-gap literal keeps its existing semantics. An acoustic
literal at attempt 0-2, wrong job/code, or already-used marker returns a safe
reason and performs no work.

- [ ] **Step 5: Run recovery GREEN and duplicate/concurrency suite**

```powershell
& 'C:\Users\toann\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest -q tests/test_p0_subdub_auto_multi_failed_job_recovery.py
```

Expected: PASS, including attempt-five and concurrent-CAS losers.

- [ ] **Step 6: Commit Task 8**

```powershell
git add bot.py tests/test_p0_subdub_auto_multi_failed_job_recovery.py
git commit -m "fix(subdub): authorize final acoustic same-job recovery"
```

---

### Task 9: Exact-fixture offline acoustic resource gate

**Files:**
- Create/Test: `tests/resource_gates/test_p0_subdub_auto_multi_embedding_fixture.py`
- Modify/Test as required by genuine failures:
  `services/subdub_multi_speaker_embedding_onnx.py`

**Interfaces:**
- Consumes the real model asset, exact source fixture, FFmpeg, NumPy, and ONNX
  Runtime.
- Produces sanitized measured JSON under an ignored temporary test directory;
  no raw PCM, transcript, embedding, or external request.

- [ ] **Step 1: Write the resource-gate test**

Read fixture path from mandatory environment variable
`SUBDUB_MULTI_FIXTURE_PATH`; verify exact source/model hashes; use FFmpeg to
produce transient mono 16 kHz PCM. Build the strict word fixture once from
`artifacts/speaker-embedding-diagnostic/vocal-run/tiny_en_transcript.json`:
flatten every nested word in source order, reject malformed or duplicate
times, assign new zero-based sequential indexes, normalize whitespace, and
write only
`[{"index": int, "word": str, "start": float, "end": float}]` to
`tests/fixtures/subdub_auto_multi_fixture_words.json`. Commit the sanitized
fixture; do not commit the source diagnostic JSON. The resource test loads the
sanitized fixture and calls real `diarize_word_timeline`; assert:

```python
assert result["ok"] is True
assert result["detected_speaker_count"] == 5
assert result["stability_pass"] is True
assert result["word_coverage_count"] == result["word_count"]
assert len(result["segments"]) >= 5
assert len({item["speaker_id"] for item in result["segments"]}) == 5
```

Store no provider key or raw provider response in the fixture. Use literal
provenance constants in the resource test:

```python
SOURCE_SHA256 = "83de97b744b931e544b569e6e750f8415545f226461bd2e36cfb49225898ad3e"
WORD_FIXTURE_SOURCE = "tiny_en_transcript.json sanitized word timeline"
```

- [ ] **Step 2: Run resource gate RED against the first full implementation**

Run with the local ONNX Runtime test target already present in artifacts:

```powershell
$env:PYTHONPATH="artifacts\speaker-embedding-diagnostic\asr-site"
$env:SUBDUB_MULTI_FIXTURE_PATH="C:\Users\toann\Downloads\test sub\test nhiều giọng.mp4"
& 'C:\Users\toann\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest -q tests/resource_gates/test_p0_subdub_auto_multi_embedding_fixture.py
```

Expected: initially FAIL at the first real model/frontend/clustering contract
that unit doubles could not expose; never change the expected speaker count to
make it pass.

- [ ] **Step 3: Correct only the measured implementation defect**

If the failure is model schema, frontend parity, unit construction,
eigengap/stability, or coverage, add a focused RED unit test for that exact
boundary before editing production. Do not add speaker hints, fixture-specific
hash branches, expected `k`, threshold exceptions, or label overrides.

- [ ] **Step 4: Run resource gate GREEN twice**

Run the Step-2 command twice from fresh temporary directories. Expected:
both PASS with `k=5`, identical canonical labels, cluster sizes, cue count, and
sidecar timeline signature.

- [ ] **Step 5: Run real-model negative gates**

On copies in a test temp directory, mutate one model byte and remove one
notice; expected: both fail before inference with bounded status codes. Verify
the repository model hash remains exact.

- [ ] **Step 6: Commit Task 9**

```powershell
git add services/subdub_multi_speaker_embedding_onnx.py `
  tests/test_p0_subdub_auto_multi_embedding_onnx.py `
  tests/resource_gates/test_p0_subdub_auto_multi_embedding_fixture.py `
  tests/fixtures
git commit -m "test(subdub): prove five acoustic speakers on fixture"
```

---

### Task 10: Full verification, review, documentation, and clean local head

**Files:**
- Modify only measured SubDub operational docs selected by
  `bao-cao-truoc-khi-push`.
- Do not modify code unless a new focused RED test proves a defect.

- [ ] **Step 1: Run focused suites**

```powershell
& 'C:\Users\toann\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m pytest -q tests/test_p0_subdub_auto_multi_embedding_onnx.py `
  tests/test_p0_subdub_auto_multi_acoustic_word_timeline.py `
  tests/test_p0_subdub_multi_speaker_blackbox.py `
  tests/test_p0_subdub_auto_multi_failed_job_recovery.py `
  tests/test_p0_subdub_multi_speaker_provider_fallback.py
```

Expected: all PASS, no network calls.

- [ ] **Step 2: Run exact-two and direct-impact protection**

Run the current exact-two locked tests and every test that imports the changed
Auto Multi modules. Compare against a clean detached `origin/main` run for any
pre-existing failures. Expected: `NEW_FAILURES=0` and exact-two hashes remain
unchanged.

- [ ] **Step 3: Run full compile and syntax gates**

```powershell
& 'C:\Users\toann\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m py_compile bot.py local_worker.py `
  services/subdub_multi_speaker_embedding_onnx.py `
  services/subdub_blackboxes/auto_multi_speaker.py `
  tests/test_p0_subdub_auto_multi_embedding_onnx.py `
  tests/test_p0_subdub_auto_multi_acoustic_word_timeline.py `
  tests/test_p0_subdub_auto_multi_failed_job_recovery.py
git diff --check
```

Expected: exit 0, no output except optional line-ending warnings from Git.

- [ ] **Step 4: Run scope, secret, and forbidden-change scans**

Verify the staged production paths are only those allowed by the spec; scan
for key/token/endpoint values and PayOS/wallet strings in changed hunks;
confirm protected blob hashes and model/license hashes. Expected: zero secret
hits, zero forbidden paths, exact protected hashes.

- [ ] **Step 5: Apply `bao-cao-truoc-khi-push`**

Read that skill completely, review the code, update only measured current
SubDub operational truth, compare original/current feature documentation, and
prepare tester surfaces. Do not write inferred counts or mark a LIVE PASS.

- [ ] **Step 6: Independent diff review**

Review exact diff for speaker fabrication, fixture-specific branches,
unbounded CPU/memory, secret leakage, wrong lane dispatch, timing mutation,
duplicate provider/TTS calls, recovery replay, charge/wallet changes, model
license/hash, and delivery order. Required verdict: Critical 0, Important 0.

- [ ] **Step 7: Commit verification/docs only**

Stage explicit documentation/tester paths only and commit with a semantic
message. Expected: worktree clean except preserved `.agents/tools/` and
`artifacts/`; branch contains only scoped commits.

---

### Task 11: Rebase, PR, deploy, final same-job recovery, and MP4 audit

**Files:**
- No new production code expected.
- Read/write production only through the approved pipeline and exact same-job
  recovery command.

- [ ] **Step 1: Acquire shared resources explicitly**

Obtain exact LIVE/CHROME/VPS-DEPLOY release markers from Product Video/WebApp
before any fetch, push, PR, deploy, Telegram, provider, worker, or DB action.
Announce exact SubDub acquisition markers.

- [ ] **Step 2: Fetch/rebase latest main and rerun a post-rebase gate**

```powershell
git fetch origin main
git rebase origin/main
```

Run focused acoustic/recovery tests, full compile, model/hash/license, diff,
scope, and exact-two hashes. Expected: 0 behind/only scoped commits ahead,
all gates PASS.

- [ ] **Step 3: Push one branch and create one PR**

Push lease-safely, create one PR with exact RED/GREEN/resource/protected
evidence, wait for compile guard, and squash merge only if mergeable/CI
SUCCESS. Record PR URL and exact merge SHA.

- [ ] **Step 4: Wait exact-SHA deploy and runtime readback**

Watch only the deploy run whose `headSha` equals the merge SHA. After SUCCESS,
verify VPS checkout, tracked diff, services, health JSON, model bytes/SHA,
license files, `numpy==2.4.6`, `onnxruntime==1.29.0`, CPU provider, and a
sanitized acoustic preflight smoke.

- [ ] **Step 5: Snapshot the exact pre-recovery authority**

Read-only checks must prove:

```text
internal job=b4cb6d5fe8a7bdfce507
public code=B4CB6D5FE8
status/terminal=failed_no_charge/failed_no_charge
attempt/correction=3/2
crosswalk marker=true
acoustic marker=false
charged_xu=0
output/artifact/delivery=false/false/false
root-job count unchanged
transactions=0
wallet/credit/provider-usage deltas=0
```

Back up the exact row/CAS authority with mode 0600 before mutation.

- [ ] **Step 6: Send the final acoustic recovery exactly once**

In the signed-in Telegram Codex Web `AAS ONE` chat, send:

```text
/subdub_recover_failed_auto_multi b4cb6d5fe8a7bdfce507 83DE97B744B931E544B569E6E750F8415545F226461BD2E36CFB49225898AD3E English 40 150 --confirm-paid --confirm-local-acoustic
```

Immediately stop Browser interaction. Read-only durable state must show same
root-job count, attempt/correction `4/3`, acoustic marker true, and charge 0.
Never send the command again.

- [ ] **Step 7: Observe only the same job to terminal**

Use SQLite `-readonly`, workspace manifest, filesystem, and journal. Do not
press status/refresh, create another job, upload, Confirm, restart, resubmit,
or write DB. Report stage changes only when durable authority changes.

- [ ] **Step 8: Measure the final MP4 and delivery**

On delivery, record:

- final path, bytes, SHA-256;
- container/codecs/dimensions/duration/frame rate;
- audio codec/sample rate/channels/loudness;
- source and final duration difference;
- acoustic model/algorithm, speaker count, unit/window/cluster aggregates;
- distinct validated voice count and per-speaker cue counts;
- source/translated cue counts and all mismatch/drift counters;
- English translation evidence;
- original 40 / dubbed 150 evidence;
- public nonzero price and Owner charge 0;
- root-job/transaction/wallet/credit/provider-usage deltas;
- Telegram video message ID, receipt message ID, and exact MP4-then-receipt
  sequence with no automatic companion.

Any missing evidence means not LIVE PASS.

- [ ] **Step 9: Run completion audit and release resources**

Map every spec requirement to terminal, artifact, delivery, runtime, or test
evidence. Only after every item is proven may the goal be marked complete.
Send exact SubDub LIVE/CHROME/VPS-DEPLOY release markers regardless of PASS or
terminal no-charge failure when no shared action remains.

## Plan self-review checklist

- [ ] Every spec section maps to at least one task above.
- [ ] Function names and result fields are identical across producer/consumer
  tasks.
- [ ] Every code behavior has RED, expected failure, minimal GREEN, verify,
  and commit steps.
- [ ] No task references hidden conversation context.
- [ ] No red-flag wording from the writing-plans prohibited-pattern list
  appears in any action step.
- [ ] No task authorizes a new job, wallet mutation, ENV change, provider
  diarization, speaker-count hint, manual fallback, or retry after attempt 4.
- [ ] Exact-two byte locks, model/license hashes, resource bounds, and live MP4
  acceptance are explicit and measurable.

## Execution handoff

The Owner already selected Inline Execution and Single-Agent TDD in the spec
approval. After committing this plan, read `superpowers:executing-plans` and
execute Tasks 1-11 in order with review checkpoints. Do not offer or select
Subagent-Driven execution.
