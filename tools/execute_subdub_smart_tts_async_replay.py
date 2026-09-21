#!/usr/bin/env python3
"""Execute Subdub Smart Multivoice 21-cue TTS replay via ShopAIKey MiniMax Async Route.

Follows strict Owner-governed constraints:
- One bounded task
- Sequential cue execution with async polling
- Immediate task_id persistence to checkpoint (STATE_ASYNC_SUBMITTED)
- Zero double-debit exposure on timeout/restart
- Atomic receipt generation
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import pathlib
import sys
import time
from typing import Any

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.shopaikey_tts_async_adapter import (
    get_shopaikey_env,
    shopaikey_minimax_tts_async_bytes,
)
from services.subdub_tts_artifact_validator import validate_tts_audio_artifact
from services.subdub_tts_checkpoint import (
    STATE_ASYNC_SUBMITTED,
    STATE_SUBMITTING,
    STATE_SUCCEEDED,
    SubdubTTSCheckpointManager,
)


def load_env_file(env_file_path: str) -> None:
    path = os.path.abspath(env_file_path)
    if not os.path.isfile(path):
        return
    try:
        from dotenv import load_dotenv

        load_dotenv(path, override=False)
    except ImportError:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if s and not s.startswith("#") and "=" in s:
                    k, v = s.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip("'\"")
                    if k and k not in os.environ:
                        os.environ[k] = v


async def process_single_cue(
    cue_dict: dict[str, Any],
    checkpoint_mgr: SubdubTTSCheckpointManager,
    api_key: str,
    base_url: str,
    max_poll_seconds: float = 120.0,
) -> dict[str, Any]:
    cue_id = str(cue_dict.get("cue_id") or "").strip()
    voice_id = str(cue_dict.get("voice_id") or "").strip()
    text = str(cue_dict.get("text") or "").strip()
    speaker_id = str(cue_dict.get("speaker_id") or "").strip()
    chars = len(text)

    cue_obj = {
        "cue_id": cue_id,
        "id": cue_id,
        "text": text,
        "voice_id": voice_id,
        "speaker_id": speaker_id,
        "speaker": speaker_id,
        "character_count": chars,
    }

    unit_key = checkpoint_mgr.compute_key(cue_obj, voice_id)
    entry = checkpoint_mgr.entries.get(unit_key)

    # 1. Check if already SUCCEEDED and valid
    if entry and entry.get("state") == STATE_SUCCEEDED:
        art_path = str(entry.get("artifact_path") or "")
        if os.path.isfile(art_path) and os.path.getsize(art_path) > 0:
            val = validate_tts_audio_artifact(art_path)
            if val.ok:
                print(f"[{cue_id}] REUSED_CACHED: duration={val.duration:.2f}s, bytes={os.path.getsize(art_path)}, task_id={entry.get('task_id', '')}")
                return {
                    "cue_id": cue_id,
                    "status": "PASS_CACHED",
                    "task_id": entry.get("task_id", ""),
                    "duration": val.duration,
                    "bytes": os.path.getsize(art_path),
                    "artifact_path": art_path,
                    "artifact_sha256": entry.get("artifact_sha256", ""),
                    "voice_id": voice_id,
                    "character_count": chars,
                }

    # 2. Check if ASYNC_SUBMITTED exists with task_id -> resume poll without new submit
    existing_task_id = ""
    if entry and entry.get("state") == STATE_ASYNC_SUBMITTED:
        tid = str(entry.get("task_id") or "").strip()
        if tid:
            existing_task_id = tid
            print(f"[{cue_id}] RESUMING_ASYNC_POLL: task_id={existing_task_id} (zero duplicate submission)")

    # 3. If no existing_task_id, prepare intent (state=SUBMITTING)
    if not existing_task_id:
        can_reuse, path, cached_bytes, ent = checkpoint_mgr.prepare_cue_intent(cue_obj, voice_id)
        if can_reuse and cached_bytes:
            return {
                "cue_id": cue_id,
                "status": "PASS_CACHED",
                "task_id": (ent or {}).get("task_id", ""),
                "bytes": len(cached_bytes),
                "voice_id": voice_id,
                "character_count": chars,
            }

    # Callback to immediately record task_id upon successful submission
    def on_submit(task_id: str) -> None:
        checkpoint_mgr.record_cue_async_submitted(
            cue=cue_obj,
            voice_id=voice_id,
            task_id=task_id,
            provider_request_id="",
        )
        print(f"[{cue_id}] ASYNC_SUBMITTED: task_id={task_id}")

    t0 = time.monotonic()
    try:
        status, audio_bytes, detail, http_status, task_id = await shopaikey_minimax_tts_async_bytes(
            text=text,
            voice_id=voice_id,
            model="speech-02-hd",
            speed=1.0,
            tts_language_boost="auto",
            existing_task_id=existing_task_id,
            on_submit_hook=on_submit if not existing_task_id else None,
            api_key=api_key,
            base_url=base_url,
            max_poll_seconds=max_poll_seconds,
            poll_interval_seconds=2.0,
        )
    except Exception as exc:
        status = "FAIL_EXCEPTION"
        audio_bytes = b""
        detail = f"{type(exc).__name__}: {exc}"
        http_status = 0
        task_id = existing_task_id
    latency = time.monotonic() - t0

    if status != "PASS" or not audio_bytes:
        print(f"[{cue_id}] FAILED: status={status}, http={http_status}, detail={detail}, latency={latency:.2f}s")
        return {
            "cue_id": cue_id,
            "status": status,
            "http_status": http_status,
            "detail": detail,
            "task_id": task_id,
            "latency": latency,
            "voice_id": voice_id,
            "character_count": chars,
        }

    # Record success and validate artifact
    success_entry = checkpoint_mgr.record_cue_success(
        cue=cue_obj,
        voice_id=voice_id,
        audio_bytes=audio_bytes,
        duration=0.0,
        provider_label="shopaikey_minimax_async",
    )
    if task_id:
        success_entry["task_id"] = task_id
        checkpoint_mgr._save_manifest_atomic()

    duration = float(success_entry.get("duration", 0.0))
    artifact_path = str(success_entry.get("artifact_path", ""))
    artifact_sha256 = str(success_entry.get("artifact_sha256", ""))

    print(f"[{cue_id}] SUCCESS: {len(audio_bytes)} bytes, duration={duration:.2f}s, latency={latency:.2f}s, task_id={task_id}")

    return {
        "cue_id": cue_id,
        "status": "PASS",
        "task_id": task_id,
        "bytes": len(audio_bytes),
        "duration": duration,
        "artifact_path": artifact_path,
        "artifact_sha256": artifact_sha256,
        "latency": latency,
        "voice_id": voice_id,
        "character_count": chars,
    }


async def run_replay(args: argparse.Namespace) -> int:
    load_env_file(args.env_file)
    api_key = str(args.api_key or get_shopaikey_env("SHOPAIKEY_API_KEY")).strip()
    base_url = str(args.base_url or get_shopaikey_env("SHOPAIKEY_TTS_BASE_URL")).strip()

    if not api_key:
        print("ERROR: SHOPAIKEY_API_KEY is not configured or empty.", file=sys.stderr)
        return 1

    plan_path = os.path.abspath(args.plan_file)
    if not os.path.isfile(plan_path):
        print(f"ERROR: Plan file not found: {plan_path}", file=sys.stderr)
        return 1

    with open(plan_path, "r", encoding="utf-8") as f:
        plan_data = json.load(f)

    tts_plan = plan_data.get("tts_plan") or {}
    units = tts_plan.get("units") or []
    if not units:
        print(f"ERROR: No tts_plan.units found in {plan_path}", file=sys.stderr)
        return 1

    total_plan_chars = sum(int(u.get("character_count", 0)) for u in units)
    print("==================================================")
    print("SUBDUB AUTO SMART MULTIVOICE TTS ASYNC REPLAY")
    print("==================================================")
    print(f"Plan file:          {plan_path}")
    print(f"Total cues:         {len(units)}")
    print(f"Total characters:   {total_plan_chars}")
    print(f"Base URL:           {base_url or 'default'}")
    print(f"Manifest dir:       {args.manifest_dir}")
    print(f"Reset cue-0001:     {bool(args.reset_cue0001)}")
    print("==================================================")

    manifest_dir = os.path.abspath(args.manifest_dir)
    os.makedirs(manifest_dir, exist_ok=True)

    checkpoint_mgr = SubdubTTSCheckpointManager(
        workspace=manifest_dir,
        job_id="subdub_auto_smart_multivoice_live_acceptance",
        target_language="vi",
        quote_fingerprint="cbffd8ec364eac1277bd17d59226d282250bc64bac4bf25589fdb1e394d03f60",
    )

    # If --reset-cue0001 is authorized and cue-0001 is stuck in SUBMITTING without task_id
    if args.reset_cue0001:
        c1_key = checkpoint_mgr.cue_id_to_unit_key.get("cue-0001")
        if c1_key and c1_key in checkpoint_mgr.entries:
            c1_entry = checkpoint_mgr.entries[c1_key]
            if c1_entry.get("state") in (STATE_SUBMITTING, "AMBIGUOUS") and not c1_entry.get("task_id"):
                print("[cue-0001] Resetting stale SUBMITTING record per Owner authorization.")
                del checkpoint_mgr.entries[c1_key]
                del checkpoint_mgr.cue_id_to_unit_key["cue-0001"]
                checkpoint_mgr._save_manifest_atomic()

    max_cues = int(args.max_cues) if args.max_cues > 0 else len(units)
    target_units = units[:max_cues]

    receipt_results = []
    total_audio_bytes = 0
    total_duration = 0.0
    all_passed = True
    start_total_time = time.monotonic()

    for idx, unit in enumerate(target_units, 1):
        cid = unit.get("cue_id")
        spk = unit.get("speaker_id")
        voice = unit.get("voice_id")
        text = unit.get("text")
        chars = len(text)
        print(f"\n--- [{idx}/{len(target_units)}] {cid} ({spk} -> {voice}) chars={chars} ---")
        print(f"Text: \"{text}\"")

        res = await process_single_cue(
            cue_dict=unit,
            checkpoint_mgr=checkpoint_mgr,
            api_key=api_key,
            base_url=base_url,
            max_poll_seconds=float(args.max_poll_seconds),
        )
        receipt_results.append(res)

        if not res.get("status", "").startswith("PASS"):
            print(f"\n[FATAL] Stopped at {cid} due to failure. EARLY_STOP=ON.")
            all_passed = False
            break

        total_audio_bytes += int(res.get("bytes", 0))
        total_duration += float(res.get("duration", 0.0))

    total_elapsed = time.monotonic() - start_total_time

    # Generate receipt
    receipt = {
        "program": "P0.SUBDUB.AUTO.SMART.MULTIVOICE.V1",
        "route": f"{base_url}/tts/minimax/t2a_async_v2",
        "model": "speech-02-hd",
        "plan_sha256": "cbffd8ec364eac1277bd17d59226d282250bc64bac4bf25589fdb1e394d03f60",
        "timestamp": time.time(),
        "elapsed_seconds": total_elapsed,
        "total_cues_requested": len(target_units),
        "total_cues_succeeded": sum(1 for r in receipt_results if r.get("status", "").startswith("PASS")),
        "total_characters_synthesized": sum(r.get("character_count", 0) for r in receipt_results if r.get("status", "").startswith("PASS")),
        "total_audio_bytes": total_audio_bytes,
        "total_audio_duration_seconds": total_duration,
        "overall_status": "SUCCESS" if all_passed else "FAILED",
        "results": receipt_results,
    }

    receipt_path = os.path.abspath(args.receipt_file)
    os.makedirs(os.path.dirname(receipt_path), exist_ok=True)
    tmp_receipt = receipt_path + f".{time.time_ns()}.tmp"
    with open(tmp_receipt, "w", encoding="utf-8") as f:
        json.dump(receipt, f, indent=2, ensure_ascii=False)
    os.replace(tmp_receipt, receipt_path)

    print("\n==================================================")
    print(f"REPLAY RESULT: {receipt['overall_status']}")
    print(f"Cues succeeded:        {receipt['total_cues_succeeded']}/{receipt['total_cues_requested']}")
    print(f"Characters:            {receipt['total_characters_synthesized']}/{total_plan_chars}")
    print(f"Total audio bytes:     {total_audio_bytes} bytes")
    print(f"Total audio duration:  {total_duration:.2f}s")
    print(f"Total elapsed:         {total_elapsed:.2f}s")
    print(f"Receipt written to:    {receipt_path}")
    print("==================================================")

    return 0 if all_passed else 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Subdub Smart Multivoice TTS Async Replay")
    parser.add_argument(
        "--plan-file",
        default="/opt/toanaas/bot/reports/subdub_auto_smart_multivoice_live_asr_replay/subdub_smart_tts_replay_plan.json",
        help="Path to subdub_smart_tts_replay_plan.json",
    )
    parser.add_argument(
        "--manifest-dir",
        default="/opt/toanaas/bot/reports/subdub_auto_smart_multivoice_live_asr_replay/tts_artifacts",
        help="Directory storing subdub_tts_manifest.json and tts_artifacts",
    )
    parser.add_argument(
        "--receipt-file",
        default="/opt/toanaas/bot/reports/subdub_auto_smart_multivoice_live_asr_replay/subdub_smart_tts_async_execution_receipt.json",
        help="Path to output receipt json",
    )
    parser.add_argument(
        "--env-file",
        default="/etc/toanaas/bot.env",
        help="Path to environment file",
    )
    parser.add_argument("--api-key", default="", help="ShopAIKey API key override")
    parser.add_argument("--base-url", default="", help="Base URL override")
    parser.add_argument("--max-poll-seconds", type=float, default=120.0, help="Max poll seconds per cue")
    parser.add_argument("--max-cues", type=int, default=0, help="Max cues to run (0 for all)")
    parser.add_argument(
        "--reset-cue0001",
        action="store_true",
        help="Reset prior stale SUBMITTING record on cue-0001 as authorized by Owner",
    )

    args = parser.parse_args()
    code = asyncio.run(run_replay(args))
    sys.exit(code)


if __name__ == "__main__":
    main()
