# Smart Offline Acceptance

`tests/test_p0_subdub_smart_delivery_end_to_end.py` composes real cached media
through the actual Smart runner, production exact post-prepare gate, both outer
audio/price guards and `send_public_subtitle_dub_final_outputs`. Only the quote
calculator/storage and final network transport are local test adapters. Receipt
value123 is a test value, never a production quote or wallet change.

Positive cached inputs have5 cues/1 voice and23 cues/5 voices. TTS file SHA256
is checked before replay. Production FFmpeg timeline, subtitle burn, MP4 mux,
FFprobe and decode run; the delivery adapter records exactly the final MP4 bytes
and matching SHA256 with one local acknowledgement. The production delivery
boundary revalidates the file. The generated two-voice cached fixture is also
checked by SHA256 and exercised through the send-failure path.

Negative controls: missing receipt, missing MP4, required audio track absent,
transport failure and a second delivery attempt. Invalid/failed output must not
become delivered or charge a user. No paid ASR, translation, TTS or Telegram call
runs in this suite. This is offline artifact/control-plane acceptance, not a
claim of semantic translation correctness, acoustic truth or live delivery.

Run with pytest and provide `SMART_POSTTTS_REPLAY_DIR` for cached media. The
optional media path is used only by tests and is not a production ENV setting.
All runtime code is unchanged by this test-only acceptance commit. Runtime
recovery remains anchored to the latest actually deployed fix, PR1314, until
another runtime fix is accepted and verified. Paid live tests stay deferred
under the Owner's current instruction.

Combined measured run:232 passed,1 skipped,7 subtests passed. The skip is an
older25-cue/5-voice archival replay whose separate artifact directory/manifest
were not supplied, not an excluded new failure. All7 new acceptance cases ran.
Fresh workflow hygiene:39 tests passed. Compilation and protected runtime diff
checks exited0. The acceptance commit changes tests/docs only; it does not need
a production restart or change the active deployed runtime recovery checkpoint.
