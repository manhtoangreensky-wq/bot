import argparse
import json
import pathlib
import sys


ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import bot  # noqa: E402


def safe_readiness_payload(readiness: dict, route_count: int, status: str, reason: str, *, no_charge: bool) -> dict:
    return {
        "ok": status in {"PASS", "CLEAN_GUARD"},
        "status": status,
        "reason": str(reason or readiness.get("reason") or ""),
        "ready": bool(readiness.get("ready")),
        "public_enabled": bool(readiness.get("public_enabled")),
        "route_count": int(route_count or 0),
        "tts_smoke": str(readiness.get("tts_smoke") or "NOT_TESTED"),
        "clone_smoke": str(readiness.get("clone_smoke") or "NOT_TESTED"),
        "provider_permission_blocked": bool(readiness.get("provider_permission_blocked")),
        "provider_called": False,
        "profile_created": False,
        "clean_guard": status == "CLEAN_GUARD",
        "no_charge": bool(no_charge),
    }


def run_smoke(no_charge: bool, confirm_paid: bool) -> dict:
    if confirm_paid:
        return {
            "ok": False,
            "status": "NOT_IMPLEMENTED",
            "reason": "This readiness smoke does not upload user samples or call clone provider.",
            "provider_called": False,
            "no_charge": bool(no_charge),
        }
    readiness = bot.get_minimax_voice_clone_readiness()
    route_attempts = bot.voice_clone_provider_route_attempts(readiness, admin_access=False)
    route_count = len(route_attempts)
    if bot.voice_clone_ready_for_processing(readiness, route_attempts):
        return safe_readiness_payload(readiness, route_count, "PASS", "voice_clone_ready_for_processing", no_charge=no_charge)
    return safe_readiness_payload(readiness, route_count, "CLEAN_GUARD", bot.voice_clone_admin_blocker(readiness), no_charge=no_charge)


def main() -> int:
    parser = argparse.ArgumentParser(description="Custom voice readiness smoke; does not call clone provider without a separate paid sample flow.")
    parser.add_argument("--no-charge", action="store_true")
    parser.add_argument("--confirm-paid", action="store_true")
    args = parser.parse_args()
    try:
        summary = run_smoke(bool(args.no_charge), bool(args.confirm_paid))
    except Exception as exc:
        print(json.dumps({"ok": False, "status": "FAIL_CUSTOM_VOICE_READINESS", "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
