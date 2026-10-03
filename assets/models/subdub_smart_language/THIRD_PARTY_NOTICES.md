# Local Language Model

This optional Smart language probe uses the multilingual Whisper small model
converted by SYSTRAN for CTranslate2. Weights are downloaded explicitly at release
time, not committed here and not downloaded in customer jobs.

- Model: https://huggingface.co/Systran/faster-whisper-small
- Pinned revision: `536b0662742c02347bc0e980a01041f333bce120`
- Upstream Whisper: https://github.com/openai/whisper (MIT license)
- faster-whisper: https://github.com/SYSTRAN/faster-whisper (MIT license)
- File sizes and SHA256 checks are in `services/subdub_smart_language.py`.

The helper only detects a supported dominant language. It does not provide
translation, speaker identity, voice cloning, lip synchronization or semantic QA.
