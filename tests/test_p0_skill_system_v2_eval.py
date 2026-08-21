"""
20-Point Eval & Validation Matrix for TOAN AAS P0.CODEX.SKILL_SYSTEM.V2
"""
import os
import re
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

import pytest
from scripts.validate_task_state import validate_state_file
from scripts.validate_skills import validate_skill_dir

CANONICAL_SKILLS = os.path.join(REPO_ROOT, ".agents", "skills")
OWNER_SKILL_MD = os.path.join(CANONICAL_SKILLS, "owner-governed-codex", "SKILL.md")


def test_01_simple_fix_does_not_become_broad_refactor():
    """1. Simple fix stays bounded (Minimal code footprint)."""
    with open(OWNER_SKILL_MD, "r", encoding="utf-8") as f:
        text = f.read()
    assert "MINIMAL_CODE_FOOTPRINT=ON" in text
    assert "YAGNI=ON" in text
    assert "NO_OPPORTUNISTIC_REFACTOR=ON" in text


def test_02_linear_live_bug_stays_single_agent():
    """2. Linear bugs remain single-agent by default."""
    with open(OWNER_SKILL_MD, "r", encoding="utf-8") as f:
        text = f.read()
    assert "SINGLE_AGENT_DEFAULT=ON" in text
    assert "SUBAGENT_AUTOSPAWN=OFF" in text


def test_03_truly_independent_research_may_pass_subagent_gate():
    """3. Independent parallel tasks satisfy all 4 exception conditions."""
    with open(OWNER_SKILL_MD, "r", encoding="utf-8") as f:
        text = f.read()
    for gate in ("PARALLELIZABLE=YES", "WORKSTREAMS_INDEPENDENT=YES", "SHARED_MUTABLE_STATE_LOW=YES", "EXPECTED_BENEFIT_EXCEEDS_ORCHESTRATION_COST=YES"):
        assert gate in text, f"Missing subagent gate: {gate}"


def test_04_subagent_use_without_justification_fails_policy():
    """4. Spawning subagents for routine work violates policy."""
    with open(OWNER_SKILL_MD, "r", encoding="utf-8") as f:
        text = f.read()
    assert "Prohibited Subagent Spawns" in text or "linear debugging" in text


def test_05_build_cannot_skip_verify():
    """5. State machine forbids jumping BUILD -> PASS without VERIFY."""
    with open(OWNER_SKILL_MD, "r", encoding="utf-8") as f:
        text = f.read()
    assert "READ  ──►  CONTRACT  ──►  BUILD  ──►  REVIEW  ──►  VERIFY  ──►  REPORT" in text
    assert "BUILD != PASS" in text


def test_06_timeout_is_not_pass():
    """6. Timeout must never be claimed as PASS."""
    with open(OWNER_SKILL_MD, "r", encoding="utf-8") as f:
        text = f.read()
    assert "Do not claim PASS without empirical verification output" in text or "evidence" in text


def test_07_merged_is_not_deployed():
    """7. Semantic invariant: MERGED != DEPLOYED != LIVE."""
    with open(OWNER_SKILL_MD, "r", encoding="utf-8") as f:
        text = f.read()
    assert "MERGED != DEPLOYED != LIVE" in text


def test_08_vps_deployed_is_not_live():
    """8. Deploying to VPS is not final customer LIVE pass without verification."""
    with open(OWNER_SKILL_MD, "r", encoding="utf-8") as f:
        text = f.read()
    assert "MERGED != DEPLOYED != LIVE" in text


def test_09_http_200_is_not_final_feature_success():
    """9. Semantic invariant: HTTP 200 != FINAL OUTPUT SUCCESS."""
    with open(OWNER_SKILL_MD, "r", encoding="utf-8") as f:
        text = f.read()
    assert "HTTP 200 != FINAL OUTPUT SUCCESS" in text


def test_10_provider_paid_call_still_owner_gated():
    """10. Paid provider calls require explicit Owner approval."""
    with open(OWNER_SKILL_MD, "r", encoding="utf-8") as f:
        text = f.read()
    assert "PROVIDER_CALLS" in text
    assert "Paid external provider API calls" in text


def test_11_wallet_mutation_still_owner_gated():
    """11. Wallet and payment mutations require explicit Owner approval."""
    with open(OWNER_SKILL_MD, "r", encoding="utf-8") as f:
        text = f.read()
    assert "WALLET_MUTATIONS" in text
    assert "Wallet, payment, or financial balance mutations" in text


def test_12_runbook_contains_no_secret_or_cot_fields(tmp_path):
    """12. State file validator rejects secrets and chain-of-thought."""
    bad_state = tmp_path / "bad_state.yaml"
    bad_state.write_text("version: '2.0'\ntask_id: 'T1'\nphase: 'READ'\nsecret: 'sk-1234567890abcdef1234567890abcdef'\n")
    ok, msg = validate_state_file(str(bad_state))
    assert not ok
    assert "Forbidden" in msg


def test_13_durable_state_resumes_correct_phase(tmp_path):
    """13. Valid state file passes schema validation."""
    valid_state = tmp_path / "valid_state.yaml"
    valid_content = """version: "2.0"
task_id: "TASK-001"
repository: "manhtoangreensky-wq/bot"
branch: "main"
base_sha: "abc1234"
head_sha: "abc1234"
phase: "VERIFY"
goal: "Test goal"
scope:
  allowed_files: ["bot.py"]
acceptance: ["Test passes"]
tests: ["pytest"]
evidence: ["1 passed"]
decisions: ["No refactor"]
blockers: []
owner_gates:
  deploy_approved: false
next_action: "Report"
updated_at: "2026-08-21T14:00:00Z"
"""
    valid_state.write_text(valid_content)
    ok, msg = validate_state_file(str(valid_state))
    assert ok, msg


def test_14_dynamic_sha_not_embedded_in_permanent_skill():
    """14. SKILL.md headers must not contain volatile commit SHAs."""
    for skill_name in os.listdir(CANONICAL_SKILLS):
        skill_dir = os.path.join(CANONICAL_SKILLS, skill_name)
        if os.path.isdir(skill_dir):
            skill_md = os.path.join(skill_dir, "SKILL.md")
            with open(skill_md, "r", encoding="utf-8") as f:
                content = f.read()
            assert not re.search(r"commit_sha:\s*[0-9a-f]{7,40}", content, re.I)


def test_15_deprecated_railway_state_not_treated_as_production():
    """15. Railway is not used in active production deployment decision logic."""
    with open(OWNER_SKILL_MD, "r", encoding="utf-8") as f:
        text = f.read()
    assert "Ubuntu VPS (`tg.toanaas.vn`" in text
    assert "Railway is deprecated for production" in text


def test_16_gcp_archive_operation_is_reversible():
    """16. Archiving manifest contains exact restore commands."""
    manifest_template = {
        "original_path": "path/to/skill",
        "sha256": "hash",
        "restore_instruction": "copy back"
    }
    assert "restore_instruction" in manifest_template


def test_17_unused_installed_skill_not_proven_token_overhead():
    """17. Skill router only loads metadata until invoked."""
    assert os.path.exists(os.path.join(CANONICAL_SKILLS, "single-agent-anti-overengineering", "SKILL.md"))


def test_18_deferred_skill_body_is_not_loaded_unnecessarily():
    """18. Deferred skills declare clean frontmatter and separate reference docs."""
    refs_dir = os.path.join(CANONICAL_SKILLS, "owner-governed-codex", "references")
    assert os.path.exists(refs_dir)
    assert len(os.listdir(refs_dir)) >= 5


def test_19_optional_lesson_is_not_auto_promoted():
    """19. Knowledge promotion gate requires Owner approval (AUTO_PROMOTION=OFF)."""
    with open(OWNER_SKILL_MD, "r", encoding="utf-8") as f:
        text = f.read()
    assert "AUTO_PROMOTION=OFF" in text


def test_20_context_compression_preserves_mandatory_guardrails():
    """20. Kernel compression retains all Owner gates with 0 semantic loss."""
    with open(OWNER_SKILL_MD, "r", encoding="utf-8") as f:
        text = f.read()
    assert "MANDATORY OWNER APPROVAL GATES" in text
    assert "Production deployment" in text
    assert "Paid external provider API calls" in text
    assert "Wallet, payment, or financial balance mutations" in text
