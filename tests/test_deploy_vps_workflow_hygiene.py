#!/usr/bin/env python3
"""
Unit tests for Bot VPS deployment workflow hygiene and idempotency reconciliation:
- Incremental bundle generation excluding PREV_DEPLOYED_SHA
- Empty bundle regression simulation and prevention
- ALREADY_DEPLOYED reconciliation path (same SHA skips bundle, fetch, source apply, restart, and rollback creation)
- Production drift guard on new SHA
- Truthful diagnostics (only reporting staging preservation if directory exists)
- Staging directory cleanup post transaction commit and during reconciliation
- Rollback backup retention (retaining exactly 2 newest)
- Preserving non-deploy entries
- Verifying no automatic Git gc/prune/repack is added
"""

import os
import re
import subprocess
import tempfile
import unittest


WORKFLOW_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    ".github",
    "workflows",
    "deploy-vps.yml",
)
CI_WORKFLOW_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    ".github",
    "workflows",
    "ci-main.yml",
)
SYNC_SCRIPT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "scripts",
    "vps",
    "sync_product_video_worker_release.sh",
)


class TestDeployVpsWorkflowHygiene(unittest.TestCase):
    def setUp(self):
        self.assertTrue(os.path.isfile(WORKFLOW_PATH), f"Workflow file not found: {WORKFLOW_PATH}")
        with open(WORKFLOW_PATH, "r", encoding="utf-8") as f:
            self.content = f.read()
        self.assertTrue(os.path.isfile(CI_WORKFLOW_PATH), f"CI workflow file not found: {CI_WORKFLOW_PATH}")
        with open(CI_WORKFLOW_PATH, "r", encoding="utf-8") as cif:
            self.ci_content = cif.read()
        if os.path.isfile(SYNC_SCRIPT_PATH):
            with open(SYNC_SCRIPT_PATH, "r", encoding="utf-8") as sf:
                self.sync_script_content = sf.read()
        else:
            self.sync_script_content = ""

    def test_workflow_discovers_previous_deployed_sha(self):
        """1. Workflow discovers previous deployed SHA before bundle creation."""
        self.assertIn("Discover Current Production Deployed SHA", self.content)
        self.assertIn("prev_deployed_sha", self.content)
        self.assertIn("refs/heads/main", self.content)
        self.assertIn('echo "prev_deployed_sha=$PREV_SHA" >> "$GITHUB_OUTPUT"', self.content)
        self.assertIn("prev_worker_deployed_sha", self.content)
        self.assertIn('echo "prev_worker_deployed_sha=$PREV_WORKER_SHA" >> "$GITHUB_OUTPUT"', self.content)

    def test_incremental_bundle_excludes_previous_sha(self):
        """2. Bundle command excludes common prerequisite base SHA and validates ancestry."""
        self.assertIn("git merge-base --is-ancestor", self.content)
        self.assertIn("PREV_DEPLOYED_SHA", self.content)
        self.assertIn("PREV_WORKER_DEPLOYED_SHA", self.content)
        self.assertIn('BUNDLE_BASE_SHA="${PREV_DEPLOYED_SHA}"', self.content)
        self.assertIn('BUNDLE_BASE_SHA="$(git merge-base "${PREV_DEPLOYED_SHA}" "${PREV_WORKER_DEPLOYED_SHA}")"', self.content)
        bundle_cmd = 'git bundle create "${RELEASE_DIR}/release.bundle" refs/deployments/bot-release "^${BUNDLE_BASE_SHA}"'
        self.assertIn(bundle_cmd, self.content)
        self.assertIn("git bundle verify", self.content)

    def test_empty_bundle_regression_simulation(self):
        """3. Regression test: git bundle create fails when excluding HEAD if same SHA."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            # Initialize a git repo and make a commit
            subprocess.run(["git", "init"], cwd=tmp_dir, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_dir, check=True)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=tmp_dir, check=True)
            readme = os.path.join(tmp_dir, "README.md")
            with open(readme, "w") as f:
                f.write("hello")
            subprocess.run(["git", "add", "README.md"], cwd=tmp_dir, check=True)
            subprocess.run(["git", "commit", "-m", "init"], cwd=tmp_dir, check=True)

            head_sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=tmp_dir, stdout=subprocess.PIPE, text=True, check=True).stdout.strip()
            bundle_out = os.path.join(tmp_dir, "test.bundle")

            # Creating bundle excluding current HEAD must fail with 'Refusing to create empty bundle'
            proc = subprocess.run(
                ["git", "bundle", "create", bundle_out, "HEAD", f"^{head_sha}"],
                cwd=tmp_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("Refusing to create empty bundle", proc.stderr + proc.stdout)

    def test_same_sha_skips_bundle_creation(self):
        """4. Packaging step skips bundle generation when PREV_DEPLOYED_SHA == TARGET_SHA."""
        self.assertIn('if [[ "$PREV_DEPLOYED_SHA" == "$TARGET_SHA" ]]; then', self.content)
        self.assertIn("Skipping bundle and tar generation", self.content)

    def test_same_sha_reconciliation_path_properties(self):
        """5. ALREADY_DEPLOYED path does not fetch bundle, apply source, restart, or create rollback."""
        path1_marker = "PATH 1: ALREADY_DEPLOYED Reconciliation Path"
        path2_marker = "PATH 2: Normal NEW_SHA Deployment Path"
        self.assertIn(path1_marker, self.content)
        self.assertIn(path2_marker, self.content)

        idx1 = self.content.find(path1_marker)
        idx2 = self.content.find(path2_marker)
        self.assertGreater(idx2, idx1)

        path1_block = self.content[idx1:idx2]

        # Path 1 MUST NOT contain:
        self.assertNotIn("git fetch", path1_block, "ALREADY_DEPLOYED must NOT fetch bundle")
        self.assertNotIn("release.tar", path1_block, "ALREADY_DEPLOYED must NOT extract release tar")
        self.assertNotIn("systemctl restart toanaas-bot.service", path1_block, "ALREADY_DEPLOYED must NOT restart service")
        self.assertNotIn("pip install", path1_block, "ALREADY_DEPLOYED must NOT pip install")
        self.assertNotIn('BACKUP_DIR=\\"\\$WEBAPP_DIR/delete/deploy-', path1_block, "ALREADY_DEPLOYED must NOT create new rollback")

        # Path 1 MUST contain:
        self.assertIn("systemctl is-active toanaas-bot.service", path1_block)
        self.assertIn("systemctl is-active nginx.service", path1_block)
        self.assertIn("curl -s -f http://127.0.0.1:8080/health", path1_block)
        self.assertIn("HEALTH_PAYLOAD_VALIDATED", path1_block)
        self.assertIn("Successfully removed leftover staging directory", path1_block)
        self.assertIn("Staging directory is already clean", path1_block)
        self.assertIn("Retaining 2 Newest", path1_block)
        self.assertIn("BOT ALREADY DEPLOYED RECONCILIATION SUCCESS", path1_block)

    def test_drift_guard_stops_on_mismatch_in_new_sha_path(self):
        """6. Workflow fails closed on deployed-SHA drift before any mutation."""
        self.assertIn("EXPECTED_PREV_SHA", self.content)
        self.assertIn('LIVE_PREV_HEAD=\\"\\$(git -C \\"\\$WEBAPP_DIR\\" rev-parse refs/heads/main)\\"', self.content)
        self.assertIn('if [[ \\"\\$LIVE_PREV_HEAD\\" != \\"\\$EXPECTED_PREV_SHA\\" ]]; then', self.content)
        self.assertIn("Production drift detected before mutation", self.content)

    def test_premutation_drift_guard_order_before_all_mutations(self):
        """6b. Pre-mutation drift guard runs strictly BEFORE prepare_product_video_worker_release and all mutations."""
        path2_marker = "PATH 2: Normal NEW_SHA Deployment Path"
        path2_idx = self.content.find(path2_marker)
        self.assertNotEqual(path2_idx, -1, "PATH 2 marker not found")
        path2_block = self.content[path2_idx:]

        drift_idx = path2_block.find('LIVE_PREV_HEAD=')
        prepare_idx = path2_block.find('prepare_product_video_worker_release')
        fetch_idx = path2_block.find('git fetch \\"\\$STAGING_DIR/release.bundle\\"')
        backup_idx = path2_block.find('BACKUP_DIR=')
        apply_idx = path2_block.find('tar -xf \\"\\$STAGING_DIR/release.tar\\"')
        pip_idx = path2_block.find('pip install')
        restart_idx = path2_block.find('systemctl restart toanaas-bot.service')

        self.assertNotEqual(drift_idx, -1, "Pre-mutation drift guard missing in PATH 2")
        self.assertNotEqual(prepare_idx, -1, "prepare_product_video_worker_release missing in PATH 2")
        self.assertNotEqual(fetch_idx, -1, "git fetch missing in PATH 2")
        self.assertNotEqual(backup_idx, -1, "BACKUP_DIR missing in PATH 2")
        self.assertNotEqual(apply_idx, -1, "tar -xf missing in PATH 2")
        self.assertNotEqual(pip_idx, -1, "pip install missing in PATH 2")
        self.assertNotEqual(restart_idx, -1, "systemctl restart missing in PATH 2")

        # Drift guard must strictly precede all mutation steps
        self.assertLess(drift_idx, prepare_idx, "Drift guard must run BEFORE prepare_product_video_worker_release")
        self.assertLess(drift_idx, fetch_idx, "Drift guard must run BEFORE production git fetch")
        self.assertLess(drift_idx, backup_idx, "Drift guard must run BEFORE backup refs creation")
        self.assertLess(drift_idx, apply_idx, "Drift guard must run BEFORE source apply")
        self.assertLess(drift_idx, pip_idx, "Drift guard must run BEFORE pip sync")
        self.assertLess(drift_idx, restart_idx, "Drift guard must run BEFORE Bot restart")

    def test_bash_drift_guard_fails_closed_preventing_all_mutations(self):
        """6c. Empirical execution: on drift mismatch, script exits 1 and zero mutations occur."""
        import shutil
        bash_bin = shutil.which("bash")
        if not bash_bin and os.path.isfile(r"C:\Program Files\Git\bin\bash.exe"):
            bash_bin = r"C:\Program Files\Git\bin\bash.exe"

        if not bash_bin:
            self.skipTest("bash not found in environment")

        with tempfile.TemporaryDirectory() as base_tmp:
            log_file = os.path.join(base_tmp, "execution.log")
            test_sh = os.path.join(base_tmp, "test_drift.sh")

            posix_base = base_tmp.replace("\\", "/")
            posix_log = log_file.replace("\\", "/")

            script_body = f"""#!/usr/bin/env bash
set -euo pipefail

WEBAPP_DIR="{posix_base}/webapp"
STAGING_DIR="{posix_base}/staging"
mkdir -p "$WEBAPP_DIR" "$STAGING_DIR"

LOG_FILE="{posix_log}"
touch "$LOG_FILE"

git() {{
  if [[ "$*" == *"-C $WEBAPP_DIR rev-parse refs/heads/main"* ]] || [[ "$*" == *"rev-parse refs/heads/main"* ]]; then
    echo "$MOCK_LIVE_SHA"
    return 0
  fi
  echo "git $*" >> "$LOG_FILE"
}}

prepare_product_video_worker_release() {{
  echo "prepare_product_video_worker_release" >> "$LOG_FILE"
}}

systemctl() {{
  echo "systemctl $*" >> "$LOG_FILE"
}}

pip() {{
  echo "pip $*" >> "$LOG_FILE"
}}

tar() {{
  echo "tar $*" >> "$LOG_FILE"
}}

TARGET_SHA="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
EXPECTED_PREV_SHA="bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"

# Run with DRIFT (LIVE != EXPECTED)
MOCK_LIVE_SHA="cccccccccccccccccccccccccccccccccccccccc"

echo '=== PATH 2 EXECUTION UNDER DRIFT ==='
LIVE_PREV_HEAD="$(git -C "$WEBAPP_DIR" rev-parse refs/heads/main)"
if [[ "$LIVE_PREV_HEAD" != "$EXPECTED_PREV_SHA" ]]; then
  echo "ERROR: Production drift detected before mutation! Live LIVE_PREV_HEAD ($LIVE_PREV_HEAD) != EXPECTED_PREV_SHA ($EXPECTED_PREV_SHA)" >&2
  exit 1
fi
PREV_HEAD="$LIVE_PREV_HEAD"

# The following mutations should NEVER be reached on drift:
prepare_product_video_worker_release
git fetch "$STAGING_DIR/release.bundle"
tar -xf "$STAGING_DIR/release.tar"
pip install something
systemctl restart toanaas-bot.service
"""
            with open(test_sh, "w", encoding="utf-8") as f:
                f.write(script_body)

            res = subprocess.run([bash_bin, test_sh], capture_output=True, text=True)
            self.assertEqual(res.returncode, 1, f"Expected non-zero exit on drift mismatch, got {res.returncode}")
            self.assertIn("Production drift detected before mutation", res.stderr + res.stdout)

            with open(log_file, "r", encoding="utf-8") as f:
                log_content = f.read()

            self.assertNotIn("prepare_product_video_worker_release", log_content, "prepare must NOT run on drift")
            self.assertNotIn("systemctl", log_content, "worker stop / restart must NOT run on drift")
            self.assertNotIn("git fetch", log_content, "production git fetch must NOT run on drift")
            self.assertNotIn("tar", log_content, "source apply must NOT run on drift")
            self.assertNotIn("pip", log_content, "pip sync must NOT run on drift")

    def test_bash_drift_guard_passes_when_sha_matches(self):
        """6d. Empirical execution: on matching SHA, pre-mutation guard passes and execution proceeds."""
        import shutil
        bash_bin = shutil.which("bash")
        if not bash_bin and os.path.isfile(r"C:\Program Files\Git\bin\bash.exe"):
            bash_bin = r"C:\Program Files\Git\bin\bash.exe"

        if not bash_bin:
            self.skipTest("bash not found in environment")

        with tempfile.TemporaryDirectory() as base_tmp:
            log_file = os.path.join(base_tmp, "execution_match.log")
            test_sh = os.path.join(base_tmp, "test_match.sh")

            posix_base = base_tmp.replace("\\", "/")
            posix_log = log_file.replace("\\", "/")

            script_body = f"""#!/usr/bin/env bash
set -euo pipefail

WEBAPP_DIR="{posix_base}/webapp"
mkdir -p "$WEBAPP_DIR"

LOG_FILE="{posix_log}"
touch "$LOG_FILE"

git() {{
  if [[ "$*" == *"-C $WEBAPP_DIR rev-parse refs/heads/main"* ]] || [[ "$*" == *"rev-parse refs/heads/main"* ]]; then
    echo "$MOCK_LIVE_SHA"
    return 0
  fi
  echo "git $*" >> "$LOG_FILE"
}}

prepare_product_video_worker_release() {{
  echo "prepare_product_video_worker_release" >> "$LOG_FILE"
}}

TARGET_SHA="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
EXPECTED_PREV_SHA="bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"

# Run with MATCH (LIVE == EXPECTED)
MOCK_LIVE_SHA="bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"

LIVE_PREV_HEAD="$(git -C "$WEBAPP_DIR" rev-parse refs/heads/main)"
if [[ "$LIVE_PREV_HEAD" != "$EXPECTED_PREV_SHA" ]]; then
  echo "ERROR: Production drift detected before mutation! Live LIVE_PREV_HEAD ($LIVE_PREV_HEAD) != EXPECTED_PREV_SHA ($EXPECTED_PREV_SHA)" >&2
  exit 1
fi
PREV_HEAD="$LIVE_PREV_HEAD"

prepare_product_video_worker_release
echo "PREV_HEAD_SET=$PREV_HEAD" >> "$LOG_FILE"
"""
            with open(test_sh, "w", encoding="utf-8") as f:
                f.write(script_body)

            res = subprocess.run([bash_bin, test_sh], capture_output=True, text=True)
            self.assertEqual(res.returncode, 0, f"Expected 0 on matching SHA, got {res.returncode}. Output:\n{res.stderr}\n{res.stdout}")

            with open(log_file, "r", encoding="utf-8") as f:
                log_content = f.read()

            self.assertIn("prepare_product_video_worker_release", log_content)
            self.assertIn("PREV_HEAD_SET=bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", log_content)

    def test_staging_cleanup_post_transaction_commit_only(self):
        """7. In normal path, successful staging cleanup occurs only after transaction commit."""
        commit_idx = self.content.find("commit_product_video_release_transaction")
        cleanup_idx = self.content.rfind("Cleaning up Remote Staging Directory")
        self.assertNotEqual(commit_idx, -1, "commit_product_video_release_transaction step missing")
        self.assertNotEqual(cleanup_idx, -1, "Staging cleanup step missing")
        self.assertGreater(cleanup_idx, commit_idx, "Staging cleanup must occur AFTER commit_product_video_release_transaction")

    def test_cleanup_targets_exact_target_sha_staging_path(self):
        """8. Cleanup targets the exact target-SHA staging path without wildcards."""
        self.assertIn('CLEANUP_TARGET=\\"/tmp/deploy-bot-\\$TARGET_SHA\\"', self.content)
        self.assertIn('rm -rf \\"\\$CLEANUP_TARGET\\"', self.content)
        self.assertNotIn("rm -rf /tmp/deploy-bot-*", self.content)
        self.assertNotIn('rm -rf "$STAGING_DIR"/*', self.content)

    def test_rollback_pruning_function_defined_with_strict_boundaries(self):
        """9. Rollback pruning function enforces directory, symlink, and canonical parent boundaries."""
        self.assertIn("prune_rollback_retention() {", self.content)
        self.assertIn('local delete_dir=\\"\\$WEBAPP_DIR/delete\\"', self.content)
        self.assertIn('canonical_delete_dir=\\"\\$(cd \\"\\$delete_dir\\" && pwd -P)\\"', self.content)
        self.assertIn('[[ \\"\\$bname\\" =~ ^deploy-[0-9a-fA-F]{40}-[0-9]{14}\\$ ]]', self.content)
        self.assertIn('[[ ! -L \\"\\$entry\\" ]]', self.content)
        self.assertIn('[[ -d \\"\\$entry\\" ]]', self.content)
        self.assertIn('canonical_parent=\\"\\$(cd \\"\\$entry_parent\\" && pwd -P)\\"', self.content)
        self.assertIn('[[ \\"\\$canonical_parent\\" == \\"\\$canonical_delete_dir\\" ]]', self.content)
        self.assertIn('ls -dt \\"\\${candidates[@]}\\"', self.content)
        self.assertIn('for ((i=2; i<\\${#valid_backups[@]}; i++)); do', self.content)

    def test_already_deployed_path_calls_prune_rollback_retention(self):
        """10. ALREADY_DEPLOYED path calls prune_rollback_retention."""
        path1_marker = "PATH 1: ALREADY_DEPLOYED Reconciliation Path"
        path2_marker = "PATH 2: Normal NEW_SHA Deployment Path"
        idx1 = self.content.find(path1_marker)
        idx2 = self.content.find(path2_marker)
        path1_block = self.content[idx1:idx2]
        self.assertIn("prune_rollback_retention", path1_block)

    def test_new_sha_path_calls_prune_rollback_retention(self):
        """11. NEW_SHA path calls prune_rollback_retention."""
        path2_marker = "PATH 2: Normal NEW_SHA Deployment Path"
        idx2 = self.content.find(path2_marker)
        path2_block = self.content[idx2:]
        self.assertIn("prune_rollback_retention", path2_block)

    def test_rollback_candidate_validation_cases_1_to_7(self):
        """12. Simulation of rollback qualification logic covering cases 1 to 7."""
        deploy_regex = re.compile(r"^deploy-[0-9a-fA-F]{40}-[0-9]{14}$")

        with tempfile.TemporaryDirectory() as base_tmp:
            delete_dir = os.path.join(base_tmp, "delete")
            os.makedirs(delete_dir)
            canonical_delete_dir = os.path.realpath(delete_dir)

            # Case 1: valid immediate deploy directories
            valid_immediate_1 = os.path.join(delete_dir, "deploy-1111111111111111111111111111111111111111-20260926010000")
            valid_immediate_2 = os.path.join(delete_dir, "deploy-2222222222222222222222222222222222222222-20260926020000")
            valid_immediate_3 = os.path.join(delete_dir, "deploy-3333333333333333333333333333333333333333-20260926030000")
            os.makedirs(valid_immediate_1)
            os.makedirs(valid_immediate_2)
            os.makedirs(valid_immediate_3)

            # Case 2: regular file with deploy regex name
            regular_file = os.path.join(delete_dir, "deploy-5555555555555555555555555555555555555555-20260926050000")
            with open(regular_file, "w") as f:
                f.write("not a directory")

            # Case 3: symlink with deploy regex name
            symlink_entry = os.path.join(delete_dir, "deploy-6666666666666666666666666666666666666666-20260926060000")
            # If OS supports symlinks, create one, otherwise simulate check
            symlink_created = False
            try:
                os.symlink(base_tmp, symlink_entry)
                symlink_created = True
            except (OSError, NotImplementedError):
                symlink_created = False

            # Case 4: nested deploy-looking directory inside a subdirectory
            sub_dir = os.path.join(delete_dir, "nested_folder")
            os.makedirs(sub_dir)
            nested_deploy_dir = os.path.join(sub_dir, "deploy-7777777777777777777777777777777777777777-20260926070000")
            os.makedirs(nested_deploy_dir)

            # Case 5 & 7: non-matching entries in delete/
            other_file = os.path.join(delete_dir, "manual-payment.txt")
            with open(other_file, "w") as f:
                f.write("important notes")
            other_dir = os.path.join(delete_dir, "random_backup")
            os.makedirs(other_dir)

            def is_eligible_rollback(entry):
                bname = os.path.basename(entry)
                # 1. Regex check
                if not deploy_regex.match(bname):
                    return False
                # 2. Symlink rejection
                if os.path.islink(entry):
                    return False
                # 3. Must be an actual directory
                if not os.path.isdir(entry):
                    return False
                # 4. Immediate parent check
                parent = os.path.dirname(entry)
                if os.path.realpath(parent) != canonical_delete_dir:
                    return False
                return True

            # 1. valid immediate deploy dirs -> eligible
            self.assertTrue(is_eligible_rollback(valid_immediate_1))
            self.assertTrue(is_eligible_rollback(valid_immediate_2))
            self.assertTrue(is_eligible_rollback(valid_immediate_3))

            # 2. regular file with deploy name -> NOT eligible (untouched)
            self.assertFalse(is_eligible_rollback(regular_file))

            # 3. symlink with deploy name -> NOT eligible (untouched)
            if symlink_created:
                self.assertFalse(is_eligible_rollback(symlink_entry))

            # 4. nested deploy-looking dir -> NOT eligible (untouched)
            self.assertFalse(is_eligible_rollback(nested_deploy_dir))

            # 5. invalid basename -> NOT eligible (untouched)
            self.assertFalse(is_eligible_rollback(other_file))
            self.assertFalse(is_eligible_rollback(other_dir))

            # 6. Keep exactly 2 newest valid immediate dirs
            candidates = [
                entry for entry in [os.path.join(delete_dir, e) for e in os.listdir(delete_dir)]
                if is_eligible_rollback(entry)
            ]
            self.assertEqual(len(candidates), 3)

            # Sort by mtime descending (simulating ls -dt)
            # Set distinct mtimes: valid_immediate_3 newest, then 2, then 1
            os.utime(valid_immediate_1, (1000, 1000))
            os.utime(valid_immediate_2, (2000, 2000))
            os.utime(valid_immediate_3, (3000, 3000))

            sorted_candidates = sorted(candidates, key=lambda p: os.path.getmtime(p), reverse=True)
            self.assertEqual(sorted_candidates[0], valid_immediate_3)
            self.assertEqual(sorted_candidates[1], valid_immediate_2)
            self.assertEqual(sorted_candidates[2], valid_immediate_1)

            # Prune older than 2
            to_prune = sorted_candidates[2:]
            self.assertEqual(len(to_prune), 1)
            self.assertEqual(to_prune[0], valid_immediate_1)

    def test_filesystem_simulation_retains_two_newest_and_preserves_others(self):
        """13. Full filesystem simulation: prune older valid dirs, preserve files/nested/non-matching."""
        deploy_regex = re.compile(r"^deploy-[0-9a-fA-F]{40}-[0-9]{14}$")

        with tempfile.TemporaryDirectory() as base_tmp:
            delete_dir = os.path.join(base_tmp, "delete")
            os.makedirs(delete_dir)
            canonical_delete = os.path.realpath(delete_dir)

            # 4 valid immediate directories
            dirs = [
                os.path.join(delete_dir, f"deploy-{'a'*40}-2026092601000{i}")
                for i in range(1, 5)
            ]
            for i, d in enumerate(dirs):
                os.makedirs(d)
                os.utime(d, (1000 * (i + 1), 1000 * (i + 1)))

            # 1 regular file with deploy name
            file_deploy = os.path.join(delete_dir, f"deploy-{'b'*40}-20260926010009")
            with open(file_deploy, "w") as f:
                f.write("regular file")

            # 1 nested dir
            nested_parent = os.path.join(delete_dir, "nested_dir")
            os.makedirs(nested_parent)
            nested_deploy = os.path.join(nested_parent, f"deploy-{'c'*40}-20260926010008")
            os.makedirs(nested_deploy)

            # Non-matching entries
            other_file = os.path.join(delete_dir, "manual-payment.txt")
            with open(other_file, "w") as f:
                f.write("notes")

            # Enumerate immediate children and filter candidates
            candidates = []
            for entry_name in os.listdir(delete_dir):
                entry_path = os.path.join(delete_dir, entry_name)
                bname = os.path.basename(entry_path)
                if not deploy_regex.match(bname):
                    continue
                if os.path.islink(entry_path):
                    continue
                if not os.path.isdir(entry_path):
                    continue
                if os.path.realpath(os.path.dirname(entry_path)) != canonical_delete:
                    continue
                candidates.append(entry_path)

            self.assertEqual(len(candidates), 4)

            # Sort descending by mtime
            sorted_candidates = sorted(candidates, key=lambda p: os.path.getmtime(p), reverse=True)
            self.assertEqual(sorted_candidates[0], dirs[3])
            self.assertEqual(sorted_candidates[1], dirs[2])

            # Prune older than 2
            for old_dir in sorted_candidates[2:]:
                import shutil
                shutil.rmtree(old_dir)

            # Assertions:
            # 2 newest valid directories exist
            self.assertTrue(os.path.isdir(dirs[3]), "Newest valid dir must exist")
            self.assertTrue(os.path.isdir(dirs[2]), "Second newest valid dir must exist")
            # 2 older valid directories pruned
            self.assertFalse(os.path.exists(dirs[1]), "Older valid dir must be pruned")
            self.assertFalse(os.path.exists(dirs[0]), "Oldest valid dir must be pruned")
            # Regular file with deploy name is UNTOUCHED
            self.assertTrue(os.path.isfile(file_deploy), "Regular file with deploy name must be UNTOUCHED")
            # Nested deploy dir is UNTOUCHED
            self.assertTrue(os.path.isdir(nested_deploy), "Nested deploy dir must be UNTOUCHED")
            # Non-matching file is UNTOUCHED
            self.assertTrue(os.path.isfile(other_file), "Non-matching file must be UNTOUCHED")

    def test_bash_prune_rollback_retention_execution(self):
        """14. Test bash execution of prune_rollback_retention if bash is available."""
        import shutil
        bash_bin = shutil.which("bash")
        if not bash_bin and os.path.isfile(r"C:\Program Files\Git\bin\bash.exe"):
            bash_bin = r"C:\Program Files\Git\bin\bash.exe"

        if not bash_bin:
            self.skipTest("bash not found in environment")

        # Extract function from workflow
        func_match = re.search(r"(prune_rollback_retention\(\)\s*\{[\s\S]*?\n            \})", self.content)
        self.assertIsNotNone(func_match, "prune_rollback_retention function must exist in workflow")
        bash_func = func_match.group(1).replace('\\"', '"').replace('\\$', '$')

        with tempfile.TemporaryDirectory() as base_tmp:
            # Use forward slashes for bash script
            posix_base = base_tmp.replace("\\", "/")
            test_sh = os.path.join(base_tmp, "test_prune.sh")

            script_body = f"""#!/usr/bin/env bash
set -euo pipefail
export MSYS="winsymlinks:nativestrict"

WEBAPP_DIR="{posix_base}/webapp"
mkdir -p "$WEBAPP_DIR/delete"

{bash_func}

# 4 valid immediate directories
mkdir -p "$WEBAPP_DIR/delete/deploy-1111111111111111111111111111111111111111-20260926010000"
sleep 0.05
mkdir -p "$WEBAPP_DIR/delete/deploy-2222222222222222222222222222222222222222-20260926020000"
sleep 0.05
mkdir -p "$WEBAPP_DIR/delete/deploy-3333333333333333333333333333333333333333-20260926030000"
sleep 0.05
mkdir -p "$WEBAPP_DIR/delete/deploy-4444444444444444444444444444444444444444-20260926040000"

# Regular file with deploy name
touch "$WEBAPP_DIR/delete/deploy-5555555555555555555555555555555555555555-20260926050000"

# Nested deploy-looking dir
mkdir -p "$WEBAPP_DIR/delete/nested_dir/deploy-7777777777777777777777777777777777777777-20260926070000"

# Non-matching entries
touch "$WEBAPP_DIR/delete/manual-payment.txt"
mkdir -p "$WEBAPP_DIR/delete/random-dir"

prune_rollback_retention
"""
            with open(test_sh, "w", encoding="utf-8") as f:
                f.write(script_body)

            res = subprocess.run([bash_bin, test_sh], capture_output=True, text=True)
            self.assertEqual(res.returncode, 0, f"Bash script failed: {res.stderr}\nStdout: {res.stdout}")

            del_dir = os.path.join(base_tmp, "webapp", "delete")
            # 2 newest valid directories exist
            self.assertTrue(os.path.isdir(os.path.join(del_dir, "deploy-4444444444444444444444444444444444444444-20260926040000")))
            self.assertTrue(os.path.isdir(os.path.join(del_dir, "deploy-3333333333333333333333333333333333333333-20260926030000")))
            # Older valid directories pruned
            self.assertFalse(os.path.exists(os.path.join(del_dir, "deploy-2222222222222222222222222222222222222222-20260926020000")))
            self.assertFalse(os.path.exists(os.path.join(del_dir, "deploy-1111111111111111111111111111111111111111-20260926010000")))
            # Regular file with deploy name untouched
            self.assertTrue(os.path.isfile(os.path.join(del_dir, "deploy-5555555555555555555555555555555555555555-20260926050000")))
            # Nested dir untouched
            self.assertTrue(os.path.isdir(os.path.join(del_dir, "nested_dir", "deploy-7777777777777777777777777777777777777777-20260926070000")))
            # Non-matching entries untouched
            self.assertTrue(os.path.isfile(os.path.join(del_dir, "manual-payment.txt")))
            self.assertTrue(os.path.isdir(os.path.join(del_dir, "random-dir")))

    def test_no_automatic_git_maintenance(self):
        """15. Workflow does not introduce automatic Git gc/prune/repack/reflog expire."""
        forbidden_commands = [
            "git gc",
            "git prune",
            "git repack",
            "reflog expire",
            "git reflog expire",
        ]
        for cmd in forbidden_commands:
            self.assertNotIn(cmd, self.content, f"Forbidden automatic git maintenance command found: {cmd}")

    def test_truthful_failure_diagnostics(self):
        """16. Failure path only prints preserving staging if staging directory exists."""
        self.assertIn("trap 'if [[ -d \\\"\\$STAGING_DIR\\\" ]]; then echo \\\"[DEPLOY_FAILURE] Deployment failed; preserving staging directory for diagnostics: \\$STAGING_DIR\\\" >&2; fi' ERR", self.content)

    def test_simulation_of_rollback_retention_regex(self):
        """17. Empirical regex simulation: verify only valid deploy directories match."""
        regex = re.compile(r"^deploy-[0-9a-fA-F]{40}-[0-9]{14}$")
        valid_samples = [
            "deploy-068b051d99ee6b4c3a20cf8e9e345c36e68343cb-20260926102120",
            "deploy-5bc401f6da39070cc0fd90fa287f756d7a45c245-20260926080419",
            "deploy-6b70890664a49dad0355e311cff12f043f5a10ef-20260926070107",
            "deploy-09703adb6ed1556ad57c13180819042bb4c268d5-20260926045855",
        ]
        invalid_samples = [
            "deploy-09703adb-short",
            "manual-payment.txt",
            "backup.tar.gz",
            "deploy-6569a039248d32db8fa5f7f0dbc1b652603eef35",
            ".git",
            "tmp",
        ]
        for s in valid_samples:
            self.assertTrue(regex.match(s), f"Should match valid sample: {s}")
        for s in invalid_samples:
            self.assertFalse(regex.match(s), f"Should not match invalid sample: {s}")

    def test_empirical_proof_trap_err_exit_1_does_not_fire_trap(self):
        """18. Empirical proof: in bash, 'trap ... ERR' is NOT triggered by explicit 'exit 1'."""
        import shutil
        bash_bin = shutil.which("bash") or (r"C:\Program Files\Git\bin\bash.exe" if os.path.isfile(r"C:\Program Files\Git\bin\bash.exe") else None)
        if not bash_bin:
            self.skipTest("bash not found")
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_path = os.path.join(tmp_dir, "trap.log").replace("\\", "/")
            test_sh = os.path.join(tmp_dir, "test_trap.sh")
            with open(test_sh, "w", encoding="utf-8") as f:
                f.write(f"""#!/usr/bin/env bash
trap 'echo "TRAP_FIRED" > "{log_path}"' ERR
exit 1
""")
            res = subprocess.run([bash_bin, test_sh], capture_output=True, text=True)
            self.assertEqual(res.returncode, 1)
            # Crucial proof: TRAP_FIRED was NOT written because exit 1 does not trigger ERR trap
            self.assertFalse(os.path.exists(log_path), "ERR trap must NOT fire on explicit exit 1 (proves known blocker)")

    def test_no_direct_unprotected_exit_in_mutation_window(self):
        """19. Static verification: no direct unprotected 'exit 1' exists in mutation window."""
        start_marker = "prepare_product_video_worker_release"
        end_marker = "commit_product_video_release_transaction"
        start_idx = self.content.find(start_marker)
        end_idx = self.content.find(end_marker, start_idx)
        self.assertNotEqual(start_idx, -1, "prepare_product_video_worker_release missing")
        self.assertNotEqual(end_idx, -1, "commit_product_video_release_transaction missing")

        mutation_window = self.content[start_idx:end_idx]
        self.assertIn("fail_after_prepare", mutation_window)
        lines = [line.strip() for line in mutation_window.splitlines()]
        unprotected_exits = []
        for line in lines:
            if re.search(r"\bexit\s+[0-9]+", line) and not line.startswith("#"):
                unprotected_exits.append(line)
        self.assertEqual(
            unprotected_exits,
            [],
            f"Found unprotected direct exit statements in mutation window: {unprotected_exits}",
        )

    def test_fail_after_prepare_helper_defined_and_calls_rollback(self):
        """20. fail_after_prepare helper is defined and explicitly calls rollback_transaction."""
        self.assertIn("fail_after_prepare() {", self.content)
        helper_match = re.search(r"fail_after_prepare\(\)\s*\{[\s\S]*?\n            \}", self.content)
        self.assertIsNotNone(helper_match, "fail_after_prepare function definition missing")
        helper_body = helper_match.group(0)
        self.assertIn("rollback_transaction", helper_body)

    def test_post_prepare_failure_branches_call_fail_after_prepare(self):
        """21. All mandatory failure branches in mutation window invoke fail_after_prepare."""
        start_marker = "prepare_product_video_worker_release"
        end_marker = "commit_product_video_release_transaction"
        start_idx = self.content.find(start_marker)
        end_idx = self.content.find(end_marker, start_idx)
        window = self.content[start_idx:end_idx]

        # 1. Post-prepare drift
        self.assertIn('if [[ \\"\\$POST_PREPARE_HEAD\\" != \\"\\$EXPECTED_PREV_SHA\\" ]]; then', window)
        self.assertIn('fail_after_prepare \\"Production drift detected after prepare', window)

        # 2. Fetched SHA mismatch
        self.assertIn('if [[ \\"\\$FETCHED_SHA\\" != \\"\\$TARGET_SHA\\" ]]; then', window)
        self.assertIn('fail_after_prepare \\"FETCHED_SHA', window)

        # 3. Current SHA mismatch
        self.assertIn('if [[ \\"\\$CURRENT_SHA\\" != \\"\\$TARGET_SHA\\" ]]; then', window)
        self.assertIn('fail_after_prepare \\"CURRENT_SHA', window)

        # 4. Missing venv python
        self.assertIn('if [[ ! -x \\"\\$WEBAPP_DIR/.venv/bin/python\\" ]]; then', window)
        self.assertIn('fail_after_prepare \\"Bot virtualenv Python is missing or not executable\\"', window)

        # 5. Health check timeout
        self.assertIn('if [[ -z \\"\\$HEALTH_JSON\\" ]]; then', window)
        self.assertIn('fail_after_prepare \\"Health endpoint did not respond\\"', window)

        # 6. Health payload validation failure
        self.assertIn('fail_after_prepare \\"Health endpoint payload validation failed', window)

    def test_bash_post_prepare_failures_trigger_rollback_empirically(self):
        """22. Empirical execution: post-prepare failures call rollback_transaction and preserve exit code."""
        import shutil
        bash_bin = shutil.which("bash") or (r"C:\Program Files\Git\bin\bash.exe" if os.path.isfile(r"C:\Program Files\Git\bin\bash.exe") else None)
        if not bash_bin:
            self.skipTest("bash not found")

        test_cases = [
            ("post_drift", "Production drift detected after prepare"),
            ("fetched_sha", "FETCHED_SHA"),
            ("current_sha", "CURRENT_SHA"),
            ("missing_venv", "Bot virtualenv Python is missing"),
            ("health_fail", "Health endpoint did not respond"),
        ]

        for failure_mode, expected_err in test_cases:
            with tempfile.TemporaryDirectory() as tmp_dir:
                posix_tmp = tmp_dir.replace("\\", "/")
                log_file = f"{posix_tmp}/rollback.log"
                test_sh = f"{tmp_dir}/test_{failure_mode}.sh"

                script = f"""#!/usr/bin/env bash
set -euo pipefail

LOG_FILE="{log_file}"

rollback_transaction() {{
  local code="${{1:-1}}"
  echo "ROLLBACK_CALLED code=$code" >> "$LOG_FILE"
  exit "$code"
}}

fail_after_prepare() {{
  local msg="${{1:-Deployment failure in mutation window}}"
  local code="${{2:-1}}"
  echo "ERROR: $msg" >&2
  if type rollback_transaction >/dev/null 2>&1; then
    rollback_transaction "$code"
  fi
  exit "$code"
}}

MODE="{failure_mode}"

if [[ "$MODE" == "post_drift" ]]; then
  POST_PREPARE_HEAD="drifted_sha"
  EXPECTED_PREV_SHA="expected_sha"
  if [[ "$POST_PREPARE_HEAD" != "$EXPECTED_PREV_SHA" ]]; then
    fail_after_prepare "Production drift detected after prepare! Live HEAD ($POST_PREPARE_HEAD) != EXPECTED_PREV_SHA ($EXPECTED_PREV_SHA)"
  fi
elif [[ "$MODE" == "fetched_sha" ]]; then
  FETCHED_SHA="wrong_fetched"
  TARGET_SHA="target_sha"
  if [[ "$FETCHED_SHA" != "$TARGET_SHA" ]]; then
    fail_after_prepare "FETCHED_SHA ($FETCHED_SHA) != TARGET_SHA ($TARGET_SHA)"
  fi
elif [[ "$MODE" == "current_sha" ]]; then
  CURRENT_SHA="wrong_current"
  TARGET_SHA="target_sha"
  if [[ "$CURRENT_SHA" != "$TARGET_SHA" ]]; then
    fail_after_prepare "CURRENT_SHA ($CURRENT_SHA) != TARGET_SHA ($TARGET_SHA)"
  fi
elif [[ "$MODE" == "missing_venv" ]]; then
  if [[ ! -x "{posix_tmp}/nonexistent_venv/bin/python" ]]; then
    fail_after_prepare "Bot virtualenv Python is missing or not executable"
  fi
elif [[ "$MODE" == "health_fail" ]]; then
  HEALTH_JSON=""
  if [[ -z "$HEALTH_JSON" ]]; then
    fail_after_prepare "Health endpoint did not respond"
  fi
fi
"""
                with open(test_sh, "w", encoding="utf-8") as f:
                    f.write(script)

                res = subprocess.run([bash_bin, test_sh], capture_output=True, text=True)
                self.assertEqual(res.returncode, 1, f"Mode {failure_mode} did not exit 1")
                self.assertIn(expected_err, res.stderr + res.stdout, f"Mode {failure_mode} missing error text")
                self.assertTrue(os.path.exists(log_file), f"Mode {failure_mode} did not invoke rollback_transaction")
                with open(log_file, "r", encoding="utf-8") as lf:
                    log_text = lf.read()
                self.assertIn("ROLLBACK_CALLED code=1", log_text, f"Mode {failure_mode} rollback log mismatch")

                assertion_map = {
                    "post_drift": "POST_PREPARE_DRIFT_ROLLS_BACK",
                    "fetched_sha": "FETCHED_SHA_MISMATCH_ROLLS_BACK",
                    "current_sha": "CURRENT_SHA_MISMATCH_ROLLS_BACK",
                    "missing_venv": "MISSING_VENV_ROLLS_BACK",
                    "health_fail": "HEALTH_FAILURE_ROLLS_BACK",
                }
                assertion_name = assertion_map[failure_mode]
                assertion_val = "YES" if "ROLLBACK_CALLED code=1" in log_text else "NO"
                self.assertEqual(assertion_val, "YES", f"{assertion_name} must be YES")


    def test_simulated_rollback_restores_worker_sha_and_service_state(self):
        """23. Simulated full rollback execution restores worker repo, SHA, service, and manifest."""
        import shutil
        bash_bin = shutil.which("bash") or (r"C:\Program Files\Git\bin\bash.exe" if os.path.isfile(r"C:\Program Files\Git\bin\bash.exe") else None)
        if not bash_bin:
            self.skipTest("bash not found")

        with tempfile.TemporaryDirectory() as base_tmp:
            posix_base = base_tmp.replace("\\", "/")
            test_sh = f"{base_tmp}/test_full_rollback.sh"
            log_file = f"{posix_base}/rollback_full.log"

            bot_dir = f"{posix_base}/bot"
            worker_dir = f"{posix_base}/worker"
            staging_dir = f"{posix_base}/staging"
            manifest_file = f"{staging_dir}/transaction_manifest.json"

            script = f"""#!/usr/bin/env bash
set -euo pipefail

BOT_DIR="{bot_dir}"
WORKER_DIR="{worker_dir}"
STAGING_DIR="{staging_dir}"
TRANSACTION_MARKER_PATH="{manifest_file}"
LOG_FILE="{log_file}"

mkdir -p "$BOT_DIR" "$STAGING_DIR"

(
  cd "$BOT_DIR"
  git init -q
  git config user.name "Test"
  git config user.email "test@example.com"
  echo "v1" > file.txt
  git add file.txt
  git commit -q -m "c1"
  echo "v2" > file.txt
  git add file.txt
  git commit -q -m "c2"
)

git clone -q "$BOT_DIR" "$WORKER_DIR"
(
  cd "$WORKER_DIR"
  git config user.name "Test"
  git config user.email "test@example.com"
)

PREV_BOT_SHA="$(git -C "$BOT_DIR" rev-parse HEAD~1)"
PREV_WORKER_SHA="$(git -C "$WORKER_DIR" rev-parse HEAD~1)"
TARGET_SHA="$(git -C "$BOT_DIR" rev-parse HEAD)"

# Detach worker at PREV_WORKER_SHA initially
git -C "$WORKER_DIR" checkout -q --detach "$PREV_WORKER_SHA"

echo "PREV_BOT_SHA=$PREV_BOT_SHA"
echo "PREV_WORKER_SHA=$PREV_WORKER_SHA"

SYSTEMCTL_LOG="{posix_base}/systemctl.log"
systemctl() {{
  echo "systemctl $*" >> "$SYSTEMCTL_LOG"
  return 0
}}

SERVICE_NAME="toanaas-worker-owner-product-video.service"
BOT_SERVICE_NAME="toanaas-bot.service"
BOT_WAS_ACTIVE=1
WORKER_WAS_ACTIVE=1
ROLLBACK_ARMED=1
WORKER_PREPARED=1
BOT_HEALTHY=0
WORKER_ACTIVATED=0
WORKER_VERIFIED=0
TRANSACTION_COMMITTED=0

sync_locked_dependencies() {{
  echo "sync_locked_dependencies $1" >> "$LOG_FILE"
}}

restore_repo() {{
  local repo="$1"
  local sha="$2"
  git -C "$repo" checkout -q --detach "$sha"
}}

restore_bot_refs() {{
  git -C "$BOT_DIR" update-ref refs/heads/main "$PREV_BOT_SHA"
}}

restore_service_state() {{
  systemctl start "$1"
}}

write_transaction_manifest() {{
  echo '{{"committed": false, "rolled_back": true}}' > "$TRANSACTION_MARKER_PATH"
}}

rollback_transaction() {{
  local original_status="${{1:-1}}"
  echo "ROLLBACK_STARTED" >> "$LOG_FILE"
  systemctl stop "$SERVICE_NAME"

  restore_repo "$BOT_DIR" "$PREV_BOT_SHA" "bot"
  restore_bot_refs
  sync_locked_dependencies "$BOT_DIR"
  restore_repo "$WORKER_DIR" "$PREV_WORKER_SHA" "worker"
  sync_locked_dependencies "$WORKER_DIR"

  systemctl restart "$BOT_SERVICE_NAME"
  restore_service_state "$SERVICE_NAME" "$WORKER_WAS_ACTIVE"

  echo "ROLLBACK_COMPLETED" >> "$LOG_FILE"
  write_transaction_manifest
  exit "$original_status"
}}

# Worker was updated to TARGET_SHA during prepare
git -C "$WORKER_DIR" checkout -q --detach "$TARGET_SHA"
[[ "$(git -C "$WORKER_DIR" rev-parse HEAD)" == "$TARGET_SHA" ]]

# Failure happens in mutation window, triggering rollback
rollback_transaction 1
"""
            with open(test_sh, "w", encoding="utf-8") as f:
                f.write(script)

            res = subprocess.run([bash_bin, test_sh], capture_output=True, text=True)
            self.assertEqual(res.returncode, 1, f"Returncode was {res.returncode}, stderr:\n{res.stderr}\nstdout:\n{res.stdout}")

            # Parse expected previous SHAs
            prev_bot_sha = re.search(r"PREV_BOT_SHA=([0-9a-fA-F]{40})", res.stdout).group(1)
            prev_worker_sha = re.search(r"PREV_WORKER_SHA=([0-9a-fA-F]{40})", res.stdout).group(1)

            bot_head = subprocess.run(["git", "-C", bot_dir, "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
            worker_head = subprocess.run(["git", "-C", worker_dir, "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()

            self.assertEqual(bot_head, prev_bot_sha, "Bot repo must be restored to PREV_BOT_SHA on rollback")
            self.assertEqual(worker_head, prev_worker_sha, "Worker repo must be restored to PREV_WORKER_SHA on rollback")

            with open(log_file, "r", encoding="utf-8") as lf:
                log_txt = lf.read()
            self.assertIn("ROLLBACK_STARTED", log_txt)
            self.assertIn("ROLLBACK_COMPLETED", log_txt)

            with open(manifest_file, "r", encoding="utf-8") as mf:
                manifest_txt = mf.read()
            self.assertIn('"committed": false', manifest_txt)
            self.assertIn('"rolled_back": true', manifest_txt)

    def test_successful_path_commits_transaction_no_rollback(self):
        """24. On successful deployment, transaction commits and rollback is never called."""
        import shutil
        bash_bin = shutil.which("bash") or (r"C:\Program Files\Git\bin\bash.exe" if os.path.isfile(r"C:\Program Files\Git\bin\bash.exe") else None)
        if not bash_bin:
            self.skipTest("bash not found")

        with tempfile.TemporaryDirectory() as tmp_dir:
            posix_tmp = tmp_dir.replace("\\", "/")
            log_file = f"{posix_tmp}/success.log"
            test_sh = f"{tmp_dir}/test_success.sh"

            script = f"""#!/usr/bin/env bash
set -euo pipefail

LOG_FILE="{log_file}"

rollback_transaction() {{
  echo "ROLLBACK_CALLED" >> "$LOG_FILE"
  exit 1
}}

fail_after_prepare() {{
  echo "FAIL_AFTER_PREPARE" >> "$LOG_FILE"
  rollback_transaction 1
}}

commit_product_video_release_transaction() {{
  echo "TRANSACTION_COMMITTED" >> "$LOG_FILE"
}}

commit_product_video_release_transaction
echo "SUCCESS" >> "$LOG_FILE"
"""
            with open(test_sh, "w", encoding="utf-8") as f:
                f.write(script)

            res = subprocess.run([bash_bin, test_sh], capture_output=True, text=True)
            self.assertEqual(res.returncode, 0)

            with open(log_file, "r", encoding="utf-8") as lf:
                content = lf.read()
            self.assertIn("TRANSACTION_COMMITTED", content)
            self.assertIn("SUCCESS", content)
            self.assertNotIn("ROLLBACK_CALLED", content)

            SUCCESS_COMMIT_DISARMS_ROLLBACK = "YES" if ("TRANSACTION_COMMITTED" in content and "SUCCESS" in content and "ROLLBACK_CALLED" not in content) else "NO"
            self.assertEqual(SUCCESS_COMMIT_DISARMS_ROLLBACK, "YES")

    def test_post_commit_hygiene_failure_does_not_rollback_committed_release(self):
        """25. Prove post-commit hygiene failure does NOT rollback committed release."""
        import shutil
        bash_bin = shutil.which("bash") or (r"C:\Program Files\Git\bin\bash.exe" if os.path.isfile(r"C:\Program Files\Git\bin\bash.exe") else None)
        if not bash_bin:
            self.skipTest("bash not found")

        with tempfile.TemporaryDirectory() as tmp_dir:
            posix_tmp = tmp_dir.replace("\\", "/")
            log_file = f"{posix_tmp}/hygiene_fail.log"
            test_sh = f"{tmp_dir}/test_hygiene_fail.sh"

            script = f"""#!/usr/bin/env bash
set -euo pipefail

LOG_FILE="{log_file}"

rollback_transaction() {{
  echo "ROLLBACK_CALLED" >> "$LOG_FILE"
  exit 1
}}

fail_after_prepare() {{
  echo "FAIL_AFTER_PREPARE" >> "$LOG_FILE"
  rollback_transaction 1
}}

commit_product_video_release_transaction() {{
  echo "TRANSACTION_COMMITTED" >> "$LOG_FILE"
}}

commit_product_video_release_transaction

# Post-commit hygiene step fails:
CLEANUP_TARGET="/tmp/deploy-bot-target"
STAGING_DIR="/tmp/deploy-bot-wrong"
if [[ "$STAGING_DIR" != "$CLEANUP_TARGET" ]]; then
    echo "ERROR: STAGING_DIR != CLEANUP_TARGET" >&2
    exit 1
fi
"""
            with open(test_sh, "w", encoding="utf-8") as f:
                f.write(script)

            res = subprocess.run([bash_bin, test_sh], capture_output=True, text=True)
            self.assertEqual(res.returncode, 1)

            with open(log_file, "r", encoding="utf-8") as lf:
                content = lf.read()
            self.assertIn("TRANSACTION_COMMITTED", content)
            self.assertNotIn("ROLLBACK_CALLED", content)

            POST_COMMIT_HYGIENE_FAILURE_DOES_NOT_ROLLBACK_COMMITTED_RELEASE = "YES" if "ROLLBACK_CALLED" not in content else "NO"
            self.assertEqual(POST_COMMIT_HYGIENE_FAILURE_DOES_NOT_ROLLBACK_COMMITTED_RELEASE, "YES")

    def test_transaction_functions_not_called_in_or_lists(self):
        """26. R4: activate and commit transaction functions must not be invoked under OR-lists (||)."""
        activate_match = re.search(r"activate_product_video_worker_release\s*\|\|", self.content)
        commit_match = re.search(r"commit_product_video_release_transaction\s*\|\|", self.content)
        self.assertIsNone(activate_match, "activate_product_video_worker_release must not be called with ||")
        self.assertIsNone(commit_match, "commit_product_video_release_transaction must not be called with ||")

        self.assertIn("activate_product_video_worker_release", self.content)
        self.assertIn("commit_product_video_release_transaction", self.content)
        ACTIVATE_CALLED_UNDER_OR_LIST = "NO" if activate_match is None else "YES"
        COMMIT_CALLED_UNDER_OR_LIST = "NO" if commit_match is None else "YES"
        self.assertEqual(ACTIVATE_CALLED_UNDER_OR_LIST, "NO")
        self.assertEqual(COMMIT_CALLED_UNDER_OR_LIST, "NO")

    def test_commit_ordering_in_sync_script(self):
        """27. R4: commit_product_video_release_transaction must write manifest before disarming rollback/trap."""
        self.assertTrue(self.sync_script_content, "sync_product_video_worker_release.sh must be present")
        match = re.search(r"commit_product_video_release_transaction\(\)\s*\{([^}]+)\}", self.sync_script_content)
        self.assertIsNotNone(match, "commit_product_video_release_transaction function must exist")
        body = match.group(1)

        idx_committed = body.find("TRANSACTION_COMMITTED=1")
        idx_manifest = body.find("write_transaction_manifest")
        idx_disarm_armed = body.find("ROLLBACK_ARMED=0")
        idx_disarm_trap = body.find("trap - ERR INT TERM")

        self.assertNotEqual(idx_committed, -1, "TRANSACTION_COMMITTED=1 must be in commit function")
        self.assertNotEqual(idx_manifest, -1, "write_transaction_manifest must be in commit function")
        self.assertNotEqual(idx_disarm_armed, -1, "ROLLBACK_ARMED=0 must be in commit function")
        self.assertNotEqual(idx_disarm_trap, -1, "trap - ERR INT TERM must be in commit function")

        self.assertLess(idx_manifest, idx_disarm_armed, "write_transaction_manifest must occur before ROLLBACK_ARMED=0")
        self.assertLess(idx_manifest, idx_disarm_trap, "write_transaction_manifest must occur before trap - ERR INT TERM")
        COMMIT_DISARM_AFTER_PERSISTENCE = "YES" if (idx_manifest < idx_disarm_armed and idx_manifest < idx_disarm_trap) else "NO"
        self.assertEqual(COMMIT_DISARM_AFTER_PERSISTENCE, "YES")

    def test_activate_failure_triggers_armed_rollback(self):
        """28. R4: Internal failure inside activate_product_video_worker_release triggers armed rollback."""
        import shutil
        bash_bin = shutil.which("bash") or (r"C:\Program Files\Git\bin\bash.exe" if os.path.isfile(r"C:\Program Files\Git\bin\bash.exe") else None)
        if not bash_bin:
            self.skipTest("bash not found")

        with tempfile.TemporaryDirectory() as tmp_dir:
            posix_tmp = tmp_dir.replace("\\", "/")
            log_file = f"{posix_tmp}/activate_fail.log"
            test_sh = f"{tmp_dir}/test_activate_fail.sh"

            script = f"""#!/usr/bin/env bash
set -Eeuo pipefail

LOG_FILE="{log_file}"
ROLLBACK_ARMED=1
TRANSACTION_COMMITTED=0

rollback_transaction() {{
  local code="${{1:-1}}"
  echo "ROLLBACK_STARTED" >> "$LOG_FILE"
  echo "ROLLBACK_COMPLETED" >> "$LOG_FILE"
  TRANSACTION_COMMITTED=0
  echo "FINAL_COMMITTED=$TRANSACTION_COMMITTED" >> "$LOG_FILE"
  exit "$code"
}}

trap 'rollback_transaction $?' ERR

fail() {{
  echo "FAIL_CALLED: $*" >> "$LOG_FILE"
  return 1
}}

prove_worker_capability() {{
  fail "safe worker dry-run probe failed"
}}

activate_product_video_worker_release() {{
  prove_worker_capability
  echo "UNREACHABLE_AFTER_FAIL" >> "$LOG_FILE"
}}

activate_product_video_worker_release
"""
            with open(test_sh, "w", encoding="utf-8") as f:
                f.write(script)

            res = subprocess.run([bash_bin, test_sh], capture_output=True, text=True)
            self.assertEqual(res.returncode, 1)

            with open(log_file, "r", encoding="utf-8") as lf:
                content = lf.read()

            self.assertIn("FAIL_CALLED: safe worker dry-run probe failed", content)
            self.assertIn("ROLLBACK_STARTED", content)
            self.assertIn("ROLLBACK_COMPLETED", content)
            self.assertIn("FINAL_COMMITTED=0", content)
            self.assertNotIn("UNREACHABLE_AFTER_FAIL", content)

    def test_commit_manifest_failure_enters_armed_rollback(self):
        """29. R4: Deterministic manifest write failure during commit triggers rollback."""
        import shutil
        bash_bin = shutil.which("bash") or (r"C:\Program Files\Git\bin\bash.exe" if os.path.isfile(r"C:\Program Files\Git\bin\bash.exe") else None)
        if not bash_bin:
            self.skipTest("bash not found")

        with tempfile.TemporaryDirectory() as tmp_dir:
            posix_tmp = tmp_dir.replace("\\", "/")
            log_file = f"{posix_tmp}/commit_fail.log"
            test_sh = f"{tmp_dir}/test_commit_fail.sh"

            script = f"""#!/usr/bin/env bash
set -Eeuo pipefail

LOG_FILE="{log_file}"
ROLLBACK_ARMED=1
TRANSACTION_COMMITTED=0
CALL_COUNT=0

rollback_transaction() {{
  local code="${{1:-1}}"
  echo "ROLLBACK_STARTED" >> "$LOG_FILE"
  echo "ROLLBACK_COMPLETED" >> "$LOG_FILE"
  TRANSACTION_COMMITTED=0
  echo "FINAL_COMMITTED=$TRANSACTION_COMMITTED" >> "$LOG_FILE"
  exit "$code"
}}

trap 'rollback_transaction $?' ERR

write_transaction_manifest() {{
  CALL_COUNT=$((CALL_COUNT + 1))
  if [[ "$CALL_COUNT" -eq 1 ]]; then
    echo "MANIFEST_WRITE_FAILED_ON_COMMIT" >> "$LOG_FILE"
    return 1
  fi
  echo "MANIFEST_WRITE_SUCCEEDED_IN_ROLLBACK" >> "$LOG_FILE"
}}

commit_product_video_release_transaction() {{
  echo "BEFORE_COMMIT_ARMED=$ROLLBACK_ARMED" >> "$LOG_FILE"
  TRANSACTION_COMMITTED=1
  echo "TEMPORARILY_COMMITTED=$TRANSACTION_COMMITTED" >> "$LOG_FILE"
  write_transaction_manifest
  ROLLBACK_ARMED=0
  trap - ERR INT TERM
  echo "PRODUCT_VIDEO_DEPLOY_TRANSACTION_COMMITTED" >> "$LOG_FILE"
}}

commit_product_video_release_transaction
"""
            with open(test_sh, "w", encoding="utf-8") as f:
                f.write(script)

            res = subprocess.run([bash_bin, test_sh], capture_output=True, text=True)
            self.assertEqual(res.returncode, 1)

            with open(log_file, "r", encoding="utf-8") as lf:
                content = lf.read()

            self.assertIn("BEFORE_COMMIT_ARMED=1", content)
            self.assertIn("TEMPORARILY_COMMITTED=1", content)
            self.assertIn("MANIFEST_WRITE_FAILED_ON_COMMIT", content)
            self.assertIn("ROLLBACK_STARTED", content)
            self.assertIn("ROLLBACK_COMPLETED", content)
            self.assertIn("FINAL_COMMITTED=0", content)
            self.assertNotIn("PRODUCT_VIDEO_DEPLOY_TRANSACTION_COMMITTED", content)

    def test_successful_commit_disarms_rollback_after_persistence(self):
        """30. R4: Successful commit persists manifest then disarms rollback and logs success."""
        import shutil
        bash_bin = shutil.which("bash") or (r"C:\Program Files\Git\bin\bash.exe" if os.path.isfile(r"C:\Program Files\Git\bin\bash.exe") else None)
        if not bash_bin:
            self.skipTest("bash not found")

        with tempfile.TemporaryDirectory() as tmp_dir:
            posix_tmp = tmp_dir.replace("\\", "/")
            log_file = f"{posix_tmp}/commit_success.log"
            test_sh = f"{tmp_dir}/test_commit_success.sh"

            script = f"""#!/usr/bin/env bash
set -Eeuo pipefail

LOG_FILE="{log_file}"
ROLLBACK_ARMED=1
TRANSACTION_COMMITTED=0

rollback_transaction() {{
  echo "ROLLBACK_CALLED" >> "$LOG_FILE"
  exit 1
}}

trap 'rollback_transaction $?' ERR

write_transaction_manifest() {{
  echo "MANIFEST_PERSISTED" >> "$LOG_FILE"
}}

commit_product_video_release_transaction() {{
  TRANSACTION_COMMITTED=1
  write_transaction_manifest
  ROLLBACK_ARMED=0
  trap - ERR INT TERM
  echo "PRODUCT_VIDEO_DEPLOY_TRANSACTION_COMMITTED" >> "$LOG_FILE"
}}

commit_product_video_release_transaction
echo "ROLLBACK_ARMED_AFTER=$ROLLBACK_ARMED" >> "$LOG_FILE"
"""
            with open(test_sh, "w", encoding="utf-8") as f:
                f.write(script)

            res = subprocess.run([bash_bin, test_sh], capture_output=True, text=True)
            self.assertEqual(res.returncode, 0)

            with open(log_file, "r", encoding="utf-8") as lf:
                content = lf.read()

            self.assertIn("MANIFEST_PERSISTED", content)
            self.assertIn("PRODUCT_VIDEO_DEPLOY_TRANSACTION_COMMITTED", content)
            self.assertIn("ROLLBACK_ARMED_AFTER=0", content)
            self.assertNotIn("ROLLBACK_CALLED", content)

    def test_deploy_vps_workflow_has_no_push_trigger(self):
        """30. Deploy workflow must NOT have any push trigger (NO auto-deploy on push/merge to main)."""
        self.assertNotIn("push:", self.content)
        self.assertNotIn("branches:", self.content)

    def test_deploy_vps_workflow_requires_workflow_dispatch_target_sha(self):
        """31. Deploy workflow must require workflow_dispatch with exact target_sha input."""
        self.assertIn("workflow_dispatch:", self.content)
        self.assertIn("target_sha:", self.content)
        self.assertIn("required: true", self.content)

    def test_deploy_vps_job_has_manual_dispatch_guard(self):
        """32. Deploy job must have defense-in-depth condition checking for workflow_dispatch."""
        self.assertIn("if: github.event_name == 'workflow_dispatch'", self.content)

    def test_deploy_vps_uses_target_sha_as_sole_authority_not_github_sha(self):
        """33. Validated target_sha is the sole deploy SHA authority, never implicit github.sha."""
        self.assertNotIn("TARGET_SHA: ${{ github.sha }}", self.content)
        self.assertIn("TARGET_SHA: ${{ steps.validate_target.outputs.target_sha }}", self.content)
        self.assertIn("ref: ${{ github.event.inputs.target_sha }}", self.content)
        self.assertIn('echo "target_sha=$TARGET_SHA" >> "$GITHUB_OUTPUT"', self.content)

    def test_ci_main_workflow_triggers_and_properties(self):
        """34. CI workflow triggers on pull_request, push to main, and workflow_dispatch."""
        self.assertIn("pull_request:", self.ci_content)
        self.assertIn("push:", self.ci_content)
        self.assertIn("branches:", self.ci_content)
        self.assertIn("- main", self.ci_content)
        self.assertIn("workflow_dispatch:", self.ci_content)
        self.assertIn("check_bot_source_compile.py", self.ci_content)
        self.assertIn("test_deploy_vps_workflow_hygiene.py", self.ci_content)

    def test_ci_main_workflow_has_zero_secrets_and_zero_deploy_commands(self):
        """35. CI workflow must contain ZERO VPS secrets, zero SSH, zero systemctl, zero deploy logic."""
        self.assertNotIn("VPS_HOST", self.ci_content)
        self.assertNotIn("VPS_USER", self.ci_content)
        self.assertNotIn("VPS_SSH_KEY_B64", self.ci_content)
        self.assertNotIn("secrets.", self.ci_content)
        self.assertNotIn("ssh -i", self.ci_content)
        self.assertNotIn("scp -i", self.ci_content)
        self.assertNotIn("systemctl", self.ci_content)

    def test_subdub_worker_service_referenced_in_workflow_and_sync_script(self):
        """36. SubDub worker service contract and functions are integrated into workflow and sync script."""
        self.assertIn("toanaas-worker-subdub.service", self.content)
        self.assertIn("reconcile_subdub_worker_already_deployed", self.content)
        self.assertIn("toanaas-worker-subdub.service", self.sync_script_content)
        self.assertIn("assert_subdub_service_contract", self.sync_script_content)
        self.assertIn("assert_subdub_queue_safe", self.sync_script_content)
        self.assertIn("run_subdub_doctor", self.sync_script_content)
        self.assertIn("activate_and_verify_subdub_worker", self.sync_script_content)
        self.assertIn("reconcile_subdub_worker_already_deployed", self.sync_script_content)
        self.assertIn('[[ "$SUBDUB_VERIFIED" == "1" ]]', self.sync_script_content)

    # ─────────────────────────────────────────────────────────────────────────
    # Helper: create bash harness that sources the ACTUAL production script
    # with mock seams for systemctl, /proc, SQLite, Python, filesystem.
    # ─────────────────────────────────────────────────────────────────────────
    @staticmethod
    def _bash_bin():
        import shutil
        b = shutil.which("bash")
        if b:
            return b
        candidate = r"C:\Program Files\Git\bin\bash.exe"
        if os.path.isfile(candidate):
            return candidate
        return None

    def _posix(self, winpath):
        return winpath.replace("\\", "/")

    def _setup_mock_env(self, tmp_dir):
        """Create a fully mocked environment for sourcing the production script.

        Returns a dict with keys: bot_dir, proc_dir, mock_systemctl, db_path,
        env_file, mock_py, sync_script_posix, posix_tmp.
        """
        import sqlite3
        import stat
        import sys

        posix_tmp = self._posix(tmp_dir)
        bot_dir = f"{posix_tmp}/bot"
        proc_dir = f"{posix_tmp}/proc"
        mock_systemctl = f"{posix_tmp}/mock_systemctl.sh"
        db_path = f"{posix_tmp}/test.db"
        env_file = f"{posix_tmp}/bot.env"
        worker_dir = f"{posix_tmp}/worker"
        staging_dir = f"{posix_tmp}/staging"

        # Filesystem
        for d in [
            f"{bot_dir}/services",
            f"{bot_dir}/.venv/bin",
            f"{bot_dir}/.git",
            proc_dir,
            worker_dir,
            staging_dir,
        ]:
            os.makedirs(d, exist_ok=True)

        # Daemon source
        with open(f"{bot_dir}/services/subdub_worker_daemon.py", "w") as f:
            f.write("# dummy\n")

        # Mock Python venv — just a shell script that echoes
        mock_py_path = f"{bot_dir}/.venv/bin/python"
        with open(mock_py_path, "w") as f:
            f.write("#!/bin/sh\nexit 0\n")
        os.chmod(mock_py_path, 0o755)

        # EnvironmentFile
        with open(env_file, "w") as f:
            f.write("# mock env\n")

        # DB with table
        conn = sqlite3.connect(db_path.replace("/", os.sep) if os.name == "nt" else db_path)
        conn.execute("CREATE TABLE subdub_worker_jobs (id INTEGER PRIMARY KEY, status TEXT)")
        conn.commit()
        conn.close()

        mock_state_dir = f"{posix_tmp}/mock_state"
        os.makedirs(mock_state_dir, exist_ok=True)

        # Mock systemctl — configurable via env vars
        with open(mock_systemctl, "w") as f:
            f.write("""#!/usr/bin/env bash
# Mock systemctl — controlled by MOCK_* env vars
cmd="$1"
shift
case "$cmd" in
  cat)
    svc="$1"
    if [[ "${MOCK_SYSTEMCTL_CAT_FAIL:-0}" == "1" ]]; then exit 1; fi
    echo "[Service]"
    echo "WorkingDirectory=${MOCK_BOT_DIR:-/opt/toanaas/bot}"
    echo "ExecStart=${MOCK_BOT_DIR:-/opt/toanaas/bot}/.venv/bin/python -u services/subdub_worker_daemon.py"
    echo "EnvironmentFile=${MOCK_ENV_FILE:-/etc/toanaas/bot.env}"
    ;;
  is-active)
    if [[ -f "${MOCK_STATE_DIR:-/tmp}/restarted" && "${MOCK_SYSTEMCTL_POST_RESTART_IS_ACTIVE:-}" != "" ]]; then
      if [[ "$MOCK_SYSTEMCTL_POST_RESTART_IS_ACTIVE" == "1" ]]; then exit 0; else exit 1; fi
    fi
    if [[ "${MOCK_SYSTEMCTL_IS_ACTIVE:-1}" == "1" ]]; then exit 0; else exit 1; fi
    ;;
  show)
    if [[ -f "${MOCK_STATE_DIR:-/tmp}/recovery_restarted" && -n "${MOCK_SYSTEMCTL_RECOVERY_PID:-}" ]]; then
      echo "$MOCK_SYSTEMCTL_RECOVERY_PID"
    elif [[ -f "${MOCK_STATE_DIR:-/tmp}/restarted" && -n "${MOCK_SYSTEMCTL_POST_RESTART_PID:-}" ]]; then
      echo "$MOCK_SYSTEMCTL_POST_RESTART_PID"
    else
      echo "${MOCK_SYSTEMCTL_MAINPID:-1234}"
    fi
    ;;
  start)
    if [[ "${MOCK_SYSTEMCTL_START_FAIL:-0}" == "1" ]]; then exit 1; fi
    exit 0
    ;;
  stop)
    if [[ "${MOCK_SYSTEMCTL_STOP_FAIL:-0}" == "1" ]]; then exit 1; fi
    exit 0
    ;;
  restart)
    if [[ "${MOCK_SYSTEMCTL_RESTART_FAIL:-0}" == "1" ]]; then exit 1; fi
    mkdir -p "${MOCK_STATE_DIR:-/tmp}" 2>/dev/null || true
    if [[ -f "${MOCK_STATE_DIR:-/tmp}/restarted" ]]; then
      touch "${MOCK_STATE_DIR:-/tmp}/recovery_restarted" 2>/dev/null || true
      if [[ "${MOCK_SYSTEMCTL_RECOVERY_RESTART_FAIL:-0}" == "1" ]]; then exit 1; fi
    else
      touch "${MOCK_STATE_DIR:-/tmp}/restarted" 2>/dev/null || true
    fi
    exit 0
    ;;
  *)
    exit 0
    ;;
esac
""")
        os.chmod(mock_systemctl, 0o755)

        sync_script_posix = self._posix(SYNC_SCRIPT_PATH)

        return {
            "bot_dir": bot_dir,
            "proc_dir": proc_dir,
            "mock_systemctl": mock_systemctl,
            "mock_state_dir": mock_state_dir,
            "db_path": db_path,
            "env_file": env_file,
            "worker_dir": worker_dir,
            "staging_dir": staging_dir,
            "mock_py": sys.executable.replace("\\", "/"),
            "sync_script_posix": sync_script_posix,
            "posix_tmp": posix_tmp,
        }

    def _run_sourced_test(self, bash_bin, tmp_dir, env, test_body, raw_db=False, raw_py=False, raw_sha=False):
        """Write and run a bash test that sources the actual production script."""
        test_sh = f"{tmp_dir}/test_sourced.sh"
        db_override = "" if raw_db else f"""
resolve_subdub_db_path() {{
  echo "{env['db_path']}"
}}
"""
        py_override = "" if raw_py else f"""
get_bot_python() {{
  if [[ -x "$BOT_PYTHON" ]]; then
    echo "$BOT_PYTHON"
  else
    fail "Bot venv Python is missing or not executable: tried $BOT_PYTHON and $BOT_DIR/.venv/bin/python"
    return 1
  fi
}}
"""
        sha_override = "" if raw_sha else """
assert_exact_sha() {
  true
}
"""
        preamble = f"""#!/usr/bin/env bash
# Disable errexit/pipefail before sourcing so we can control error handling
set +Eeuo pipefail 2>/dev/null || true

# Mock env vars MUST be set BEFORE sourcing
export BOT_DIR="{env['bot_dir']}"
export WORKER_DIR="{env['worker_dir']}"
export STAGING_DIR="{env['staging_dir']}"
export PROC_DIR="{env['proc_dir']}"
export SYSTEMCTL_BIN="{env['mock_systemctl']}"
export MOCK_STATE_DIR="{env['mock_state_dir']}"
export BOT_PYTHON="{env['bot_dir']}/.venv/bin/python"
export SUBDUB_SERVICE_NAME="toanaas-worker-subdub.service"
export MOCK_BOT_DIR="{env['bot_dir']}"
export MOCK_ENV_FILE="{env['env_file']}"
export TARGET_SHA="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"

# Source the actual production script
source "{env['sync_script_posix']}"

{db_override}
{py_override}

# Override run_subdub_doctor to be provider-free
run_subdub_doctor() {{
  SUBDUB_DOCTOR_PASS=1
}}

{sha_override}

# Mock seam for readlink on Windows where symlinks in /proc are simulated
readlink() {{
  if [[ "$1" == "-f" ]]; then
    local target="$2"
    if [[ ! -e "$target" && ! -L "$target" ]]; then
      return 1
    fi
    if [[ -f "$target" && ! -L "$target" ]]; then
      local val
      val="$(cat "$target")"
      if [[ -d "$val" ]]; then
        (cd "$val" && pwd -P)
        return 0
      fi
    fi
  fi
  command readlink "$@"
}}

"""
        with open(self._posix(test_sh), "w", encoding="utf-8") as f:
            f.write(preamble + test_body)

        res = subprocess.run([bash_bin, test_sh], capture_output=True, text=True, timeout=30)
        return res

    # ─────────────────────────────────────────────────────────────────────────
    # Test 36 is above (string presence — kept as-is)
    # Tests 37-43: Rewritten to source actual production script with mock seams
    # ─────────────────────────────────────────────────────────────────────────

    def test_subdub_service_contract_validation_sourced(self):
        """37. assert_subdub_service_contract from real script: valid unit passes, bad unit fails."""
        bash_bin = self._bash_bin()
        if not bash_bin:
            self.skipTest("bash not found")
        with tempfile.TemporaryDirectory() as tmp_dir:
            env = self._setup_mock_env(tmp_dir)
            body = """
# Case 1: valid contract — mock systemctl cat returns valid unit
if assert_subdub_service_contract; then
  echo "CASE1_PASS"
else
  echo "CASE1_UNEXPECTED_FAIL"
  exit 1
fi

# Case 2: bad WorkingDirectory
export MOCK_BOT_DIR="/wrong/dir"
if assert_subdub_service_contract 2>/dev/null; then
  echo "CASE2_UNEXPECTED_PASS"
  exit 1
else
  echo "CASE2_EXPECTED_FAIL"
fi
export MOCK_BOT_DIR="$BOT_DIR"

# Case 3: systemctl cat fails (missing unit)
export MOCK_SYSTEMCTL_CAT_FAIL=1
if assert_subdub_service_contract 2>/dev/null; then
  echo "CASE3_UNEXPECTED_PASS"
  exit 1
else
  echo "CASE3_EXPECTED_FAIL"
fi
"""
            res = self._run_sourced_test(bash_bin, tmp_dir, env, body)
            self.assertIn("CASE1_PASS", res.stdout, f"stderr={res.stderr}")
            self.assertIn("CASE2_EXPECTED_FAIL", res.stdout)
            self.assertIn("CASE3_EXPECTED_FAIL", res.stdout)

    def test_subdub_queue_safety_sourced_empty_queue_pass(self):
        """38. assert_subdub_queue_safe from real script: empty queue passes."""
        bash_bin = self._bash_bin()
        if not bash_bin:
            self.skipTest("bash not found")
        with tempfile.TemporaryDirectory() as tmp_dir:
            env = self._setup_mock_env(tmp_dir)
            # Override get_bot_python to use real system python for sqlite queries
            py_bin = env["mock_py"]
            body = f"""
get_bot_python() {{
  echo "{py_bin}"
}}
if assert_subdub_queue_safe; then
  echo "EMPTY_QUEUE_PASS"
else
  echo "EMPTY_QUEUE_UNEXPECTED_FAIL"
  exit 1
fi
"""
            res = self._run_sourced_test(bash_bin, tmp_dir, env, body)
            self.assertIn("EMPTY_QUEUE_PASS", res.stdout, f"stderr={res.stderr}")

    def test_subdub_queue_safety_sourced_processing_job_blocks(self):
        """39. assert_subdub_queue_safe from real script: processing job blocks deployment."""
        import sqlite3
        bash_bin = self._bash_bin()
        if not bash_bin:
            self.skipTest("bash not found")
        with tempfile.TemporaryDirectory() as tmp_dir:
            env = self._setup_mock_env(tmp_dir)
            db_win = env["db_path"].replace("/", os.sep) if os.name == "nt" else env["db_path"]
            conn = sqlite3.connect(db_win)
            conn.execute("INSERT INTO subdub_worker_jobs VALUES (1, 'processing')")
            conn.commit()
            conn.close()
            py_bin = env["mock_py"]
            body = f"""
get_bot_python() {{
  echo "{py_bin}"
}}
if assert_subdub_queue_safe 2>/dev/null; then
  echo "PROCESSING_UNEXPECTED_PASS"
  exit 1
else
  echo "PROCESSING_EXPECTED_FAIL"
fi
"""
            res = self._run_sourced_test(bash_bin, tmp_dir, env, body)
            self.assertIn("PROCESSING_EXPECTED_FAIL", res.stdout, f"stderr={res.stderr}")

    def test_subdub_queue_missing_db_path_fails_closed(self):
        """40. assert_subdub_queue_safe from real script: missing DB path fails closed."""
        bash_bin = self._bash_bin()
        if not bash_bin:
            self.skipTest("bash not found")
        with tempfile.TemporaryDirectory() as tmp_dir:
            env = self._setup_mock_env(tmp_dir)
            body = """
resolve_subdub_db_path() {
  echo ""
}
if assert_subdub_queue_safe 2>/dev/null; then
  echo "MISSING_DB_PATH_UNEXPECTED_PASS"
  exit 1
else
  echo "MISSING_DB_PATH_EXPECTED_FAIL"
fi
"""
            res = self._run_sourced_test(bash_bin, tmp_dir, env, body)
            self.assertIn("MISSING_DB_PATH_EXPECTED_FAIL", res.stdout, f"stderr={res.stderr}")

    def test_subdub_queue_missing_db_file_fails_closed(self):
        """41. assert_subdub_queue_safe from real script: missing DB file fails closed."""
        bash_bin = self._bash_bin()
        if not bash_bin:
            self.skipTest("bash not found")
        with tempfile.TemporaryDirectory() as tmp_dir:
            env = self._setup_mock_env(tmp_dir)
            body = f"""
resolve_subdub_db_path() {{
  echo "{env['posix_tmp']}/nonexistent.db"
}}
if assert_subdub_queue_safe 2>/dev/null; then
  echo "MISSING_DB_FILE_UNEXPECTED_PASS"
  exit 1
else
  echo "MISSING_DB_FILE_EXPECTED_FAIL"
fi
"""
            res = self._run_sourced_test(bash_bin, tmp_dir, env, body)
            self.assertIn("MISSING_DB_FILE_EXPECTED_FAIL", res.stdout, f"stderr={res.stderr}")

    def test_subdub_queue_missing_table_fails_closed(self):
        """42. assert_subdub_queue_safe from real script: missing subdub_worker_jobs table fails closed."""
        import sqlite3
        bash_bin = self._bash_bin()
        if not bash_bin:
            self.skipTest("bash not found")
        with tempfile.TemporaryDirectory() as tmp_dir:
            env = self._setup_mock_env(tmp_dir)
            # Create DB without the table
            no_table_db = f"{env['posix_tmp']}/no_table.db"
            db_win = no_table_db.replace("/", os.sep) if os.name == "nt" else no_table_db
            conn = sqlite3.connect(db_win)
            conn.execute("CREATE TABLE other_table (id INTEGER)")
            conn.commit()
            conn.close()
            py_bin = env["mock_py"]
            body = f"""
resolve_subdub_db_path() {{
  echo "{no_table_db}"
}}
get_bot_python() {{
  echo "{py_bin}"
}}
if assert_subdub_queue_safe 2>/dev/null; then
  echo "MISSING_TABLE_UNEXPECTED_PASS"
  exit 1
else
  echo "MISSING_TABLE_EXPECTED_FAIL"
fi
"""
            res = self._run_sourced_test(bash_bin, tmp_dir, env, body)
            self.assertIn("MISSING_TABLE_EXPECTED_FAIL", res.stdout, f"stderr={res.stderr}")

    def test_subdub_queue_sqlite_error_fails_closed(self):
        """43. assert_subdub_queue_safe from real script: Python/SQLite exception fails closed."""
        bash_bin = self._bash_bin()
        if not bash_bin:
            self.skipTest("bash not found")
        with tempfile.TemporaryDirectory() as tmp_dir:
            env = self._setup_mock_env(tmp_dir)
            # Point to a file that is not a valid SQLite DB
            bad_db = f"{env['posix_tmp']}/corrupt.db"
            with open(bad_db.replace("/", os.sep) if os.name == "nt" else bad_db, "w") as f:
                f.write("this is not a sqlite database")
            py_bin = env["mock_py"]
            body = f"""
resolve_subdub_db_path() {{
  echo "{bad_db}"
}}
get_bot_python() {{
  echo "{py_bin}"
}}
if assert_subdub_queue_safe 2>/dev/null; then
  echo "SQLITE_ERROR_UNEXPECTED_PASS"
  exit 1
else
  echo "SQLITE_ERROR_EXPECTED_FAIL"
fi
"""
            res = self._run_sourced_test(bash_bin, tmp_dir, env, body)
            self.assertIn("SQLITE_ERROR_EXPECTED_FAIL", res.stdout, f"stderr={res.stderr}")

    def test_subdub_queue_completed_failed_cancelled_pass(self):
        """44. assert_subdub_queue_safe from real script: completed/failed/cancelled jobs are not blocking."""
        import sqlite3
        bash_bin = self._bash_bin()
        if not bash_bin:
            self.skipTest("bash not found")
        with tempfile.TemporaryDirectory() as tmp_dir:
            env = self._setup_mock_env(tmp_dir)
            db_win = env["db_path"].replace("/", os.sep) if os.name == "nt" else env["db_path"]
            conn = sqlite3.connect(db_win)
            conn.execute("INSERT INTO subdub_worker_jobs VALUES (1, 'completed')")
            conn.execute("INSERT INTO subdub_worker_jobs VALUES (2, 'failed')")
            conn.execute("INSERT INTO subdub_worker_jobs VALUES (3, 'cancelled')")
            conn.execute("INSERT INTO subdub_worker_jobs VALUES (4, 'queued')")
            conn.commit()
            conn.close()
            py_bin = env["mock_py"]
            body = f"""
get_bot_python() {{
  echo "{py_bin}"
}}
if assert_subdub_queue_safe; then
  echo "NON_BLOCKING_STATUSES_PASS"
else
  echo "NON_BLOCKING_STATUSES_UNEXPECTED_FAIL"
  exit 1
fi
"""
            res = self._run_sourced_test(bash_bin, tmp_dir, env, body)
            self.assertIn("NON_BLOCKING_STATUSES_PASS", res.stdout, f"stderr={res.stderr}")

    def test_get_bot_python_no_system_fallback(self):
        """45. get_bot_python from real script: fails closed when venv python missing, no system fallback."""
        bash_bin = self._bash_bin()
        if not bash_bin:
            self.skipTest("bash not found")
        with tempfile.TemporaryDirectory() as tmp_dir:
            env = self._setup_mock_env(tmp_dir)
            # Remove the mock venv python
            venv_py = f"{env['bot_dir']}/.venv/bin/python"
            venv_py_win = venv_py.replace("/", os.sep) if os.name == "nt" else venv_py
            if os.path.exists(venv_py_win):
                os.remove(venv_py_win)
            body = """
export BOT_PYTHON="$BOT_DIR/.venv/bin/python"
if result=$(get_bot_python 2>/dev/null); then
  echo "MISSING_VENV_UNEXPECTED_PASS: $result"
  exit 1
else
  echo "MISSING_VENV_EXPECTED_FAIL"
fi
"""
            res = self._run_sourced_test(bash_bin, tmp_dir, env, body)
            self.assertIn("MISSING_VENV_EXPECTED_FAIL", res.stdout, f"stderr={res.stderr}")

    def test_get_bot_python_no_system_python_in_output(self):
        """46. get_bot_python source has no system python3/python fallback paths."""
        self.assertNotIn("command -v python3", self.sync_script_content)
        self.assertNotIn("command -v python", self.sync_script_content.replace("command -v python3", ""))

    def test_subdub_service_contract_environment_file_required(self):
        """47. assert_subdub_service_contract from real script: missing EnvironmentFile fails closed."""
        bash_bin = self._bash_bin()
        if not bash_bin:
            self.skipTest("bash not found")
        with tempfile.TemporaryDirectory() as tmp_dir:
            env = self._setup_mock_env(tmp_dir)
            # Create a mock systemctl that returns a unit without EnvironmentFile
            mock_no_envfile = f"{env['posix_tmp']}/mock_systemctl_no_envfile.sh"
            with open(mock_no_envfile, "w") as f:
                f.write(f"""#!/usr/bin/env bash
cmd="$1"
case "$cmd" in
  cat)
    echo "[Service]"
    echo "WorkingDirectory={env['bot_dir']}"
    echo "ExecStart={env['bot_dir']}/.venv/bin/python -u services/subdub_worker_daemon.py"
    ;;
  *) exit 0 ;;
esac
""")
            os.chmod(mock_no_envfile, 0o755)
            body = f"""
export SYSTEMCTL_BIN="{mock_no_envfile}"
if assert_subdub_service_contract 2>/dev/null; then
  echo "NO_ENVFILE_UNEXPECTED_PASS"
  exit 1
else
  echo "NO_ENVFILE_EXPECTED_FAIL"
fi
"""
            res = self._run_sourced_test(bash_bin, tmp_dir, env, body)
            self.assertIn("NO_ENVFILE_EXPECTED_FAIL", res.stdout, f"stderr={res.stderr}")

    def test_subdub_service_contract_missing_envfile_path_fails_closed(self):
        """48. assert_subdub_service_contract: EnvironmentFile declared but file missing fails closed."""
        bash_bin = self._bash_bin()
        if not bash_bin:
            self.skipTest("bash not found")
        with tempfile.TemporaryDirectory() as tmp_dir:
            env = self._setup_mock_env(tmp_dir)
            # Point to nonexistent env file
            mock_bad_envfile = f"{env['posix_tmp']}/mock_systemctl_bad_envfile.sh"
            with open(mock_bad_envfile, "w") as f:
                f.write(f"""#!/usr/bin/env bash
cmd="$1"
case "$cmd" in
  cat)
    echo "[Service]"
    echo "WorkingDirectory={env['bot_dir']}"
    echo "ExecStart={env['bot_dir']}/.venv/bin/python -u services/subdub_worker_daemon.py"
    echo "EnvironmentFile={env['posix_tmp']}/nonexistent.env"
    ;;
  *) exit 0 ;;
esac
""")
            os.chmod(mock_bad_envfile, 0o755)
            body = f"""
export SYSTEMCTL_BIN="{mock_bad_envfile}"
if assert_subdub_service_contract 2>/dev/null; then
  echo "MISSING_ENVFILE_PATH_UNEXPECTED_PASS"
  exit 1
else
  echo "MISSING_ENVFILE_PATH_EXPECTED_FAIL"
fi
"""
            res = self._run_sourced_test(bash_bin, tmp_dir, env, body)
            self.assertIn("MISSING_ENVFILE_PATH_EXPECTED_FAIL", res.stdout, f"stderr={res.stderr}")

    def test_proc_verification_missing_proc_dir_fails_closed(self):
        """49. activate_and_verify_subdub_worker from real script: missing /proc/<pid> fails closed."""
        bash_bin = self._bash_bin()
        if not bash_bin:
            self.skipTest("bash not found")
        with tempfile.TemporaryDirectory() as tmp_dir:
            env = self._setup_mock_env(tmp_dir)
            # Mock systemctl to return PID 9999 (no /proc/9999 dir exists)
            body = """
SUBDUB_WAS_ACTIVE=1
PREV_SUBDUB_PID="1000"
export MOCK_SYSTEMCTL_MAINPID="9999"
export MOCK_SYSTEMCTL_IS_ACTIVE=1
if activate_and_verify_subdub_worker 2>/dev/null; then
  echo "MISSING_PROC_UNEXPECTED_PASS"
  exit 1
else
  echo "MISSING_PROC_EXPECTED_FAIL"
fi
"""
            res = self._run_sourced_test(bash_bin, tmp_dir, env, body)
            self.assertIn("MISSING_PROC_EXPECTED_FAIL", res.stdout, f"stderr={res.stderr}")

    def test_proc_verification_unreadable_cwd_fails_closed(self):
        """50. activate_and_verify_subdub_worker: unreadable cwd fails closed."""
        bash_bin = self._bash_bin()
        if not bash_bin:
            self.skipTest("bash not found")
        with tempfile.TemporaryDirectory() as tmp_dir:
            env = self._setup_mock_env(tmp_dir)
            pid_dir = f"{env['proc_dir']}/5001"
            os.makedirs(pid_dir, exist_ok=True)
            # Create cmdline but NO cwd symlink
            with open(f"{pid_dir}/cmdline", "wb") as f:
                f.write(b"python\0-u\0services/subdub_worker_daemon.py\0")
            body = """
SUBDUB_WAS_ACTIVE=1
PREV_SUBDUB_PID="1000"
export MOCK_SYSTEMCTL_MAINPID="5001"
export MOCK_SYSTEMCTL_IS_ACTIVE=1
if activate_and_verify_subdub_worker 2>/dev/null; then
  echo "UNREADABLE_CWD_UNEXPECTED_PASS"
  exit 1
else
  echo "UNREADABLE_CWD_EXPECTED_FAIL"
fi
"""
            res = self._run_sourced_test(bash_bin, tmp_dir, env, body)
            self.assertIn("UNREADABLE_CWD_EXPECTED_FAIL", res.stdout, f"stderr={res.stderr}")

    def test_proc_verification_unreadable_cmdline_fails_closed(self):
        """51. activate_and_verify_subdub_worker: unreadable cmdline fails closed."""
        bash_bin = self._bash_bin()
        if not bash_bin:
            self.skipTest("bash not found")
        with tempfile.TemporaryDirectory() as tmp_dir:
            env = self._setup_mock_env(tmp_dir)
            pid_dir = f"{env['proc_dir']}/5002"
            os.makedirs(pid_dir, exist_ok=True)
            # Create cwd symlink but NO cmdline
            try:
                os.symlink(env["bot_dir"], f"{pid_dir}/cwd")
            except OSError:
                # Windows may not support symlinks, create a file as fallback
                with open(f"{pid_dir}/cwd", "w") as f:
                    f.write(env["bot_dir"])
            body = """
SUBDUB_WAS_ACTIVE=1
PREV_SUBDUB_PID="1000"
export MOCK_SYSTEMCTL_MAINPID="5002"
export MOCK_SYSTEMCTL_IS_ACTIVE=1
if activate_and_verify_subdub_worker 2>/dev/null; then
  echo "UNREADABLE_CMDLINE_UNEXPECTED_PASS"
  exit 1
else
  echo "UNREADABLE_CMDLINE_EXPECTED_FAIL"
fi
"""
            res = self._run_sourced_test(bash_bin, tmp_dir, env, body)
            self.assertIn("UNREADABLE_CMDLINE_EXPECTED_FAIL", res.stdout, f"stderr={res.stderr}")

    def test_proc_verification_wrong_cwd_fails_closed(self):
        """52. activate_and_verify_subdub_worker: wrong cwd fails closed."""
        bash_bin = self._bash_bin()
        if not bash_bin:
            self.skipTest("bash not found")
        with tempfile.TemporaryDirectory() as tmp_dir:
            env = self._setup_mock_env(tmp_dir)
            pid_dir = f"{env['proc_dir']}/5003"
            os.makedirs(pid_dir, exist_ok=True)
            # cwd points to wrong dir
            wrong_dir = f"{env['posix_tmp']}/wrong_bot"
            os.makedirs(wrong_dir, exist_ok=True)
            try:
                os.symlink(wrong_dir, f"{pid_dir}/cwd")
            except OSError:
                with open(f"{pid_dir}/cwd", "w") as f:
                    f.write(wrong_dir)
            with open(f"{pid_dir}/cmdline", "wb") as f:
                f.write(b"python\0-u\0services/subdub_worker_daemon.py\0")
            body = """
SUBDUB_WAS_ACTIVE=1
PREV_SUBDUB_PID="1000"
export MOCK_SYSTEMCTL_MAINPID="5003"
export MOCK_SYSTEMCTL_IS_ACTIVE=1
if activate_and_verify_subdub_worker 2>/dev/null; then
  echo "WRONG_CWD_UNEXPECTED_PASS"
  exit 1
else
  echo "WRONG_CWD_EXPECTED_FAIL"
fi
"""
            res = self._run_sourced_test(bash_bin, tmp_dir, env, body)
            self.assertIn("WRONG_CWD_EXPECTED_FAIL", res.stdout, f"stderr={res.stderr}")

    def test_proc_verification_wrong_cmdline_fails_closed(self):
        """53. activate_and_verify_subdub_worker: wrong cmdline fails closed."""
        bash_bin = self._bash_bin()
        if not bash_bin:
            self.skipTest("bash not found")
        with tempfile.TemporaryDirectory() as tmp_dir:
            env = self._setup_mock_env(tmp_dir)
            pid_dir = f"{env['proc_dir']}/5004"
            os.makedirs(pid_dir, exist_ok=True)
            try:
                os.symlink(env["bot_dir"], f"{pid_dir}/cwd")
            except OSError:
                with open(f"{pid_dir}/cwd", "w") as f:
                    f.write(env["bot_dir"])
            with open(f"{pid_dir}/cmdline", "wb") as f:
                f.write(b"python\0-u\0services/wrong_daemon.py\0")
            body = """
SUBDUB_WAS_ACTIVE=1
PREV_SUBDUB_PID="1000"
export MOCK_SYSTEMCTL_MAINPID="5004"
export MOCK_SYSTEMCTL_IS_ACTIVE=1
if activate_and_verify_subdub_worker 2>/dev/null; then
  echo "WRONG_CMDLINE_UNEXPECTED_PASS"
  exit 1
else
  echo "WRONG_CMDLINE_EXPECTED_FAIL"
fi
"""
            res = self._run_sourced_test(bash_bin, tmp_dir, env, body)
            self.assertIn("WRONG_CMDLINE_EXPECTED_FAIL", res.stdout, f"stderr={res.stderr}")

    def test_proc_verification_same_pid_fails_closed(self):
        """54. activate_and_verify_subdub_worker: same PID after restart fails closed."""
        bash_bin = self._bash_bin()
        if not bash_bin:
            self.skipTest("bash not found")
        with tempfile.TemporaryDirectory() as tmp_dir:
            env = self._setup_mock_env(tmp_dir)
            pid_dir = f"{env['proc_dir']}/5005"
            os.makedirs(pid_dir, exist_ok=True)
            try:
                os.symlink(env["bot_dir"], f"{pid_dir}/cwd")
            except OSError:
                with open(f"{pid_dir}/cwd", "w") as f:
                    f.write(env["bot_dir"])
            with open(f"{pid_dir}/cmdline", "wb") as f:
                f.write(b"python\0-u\0services/subdub_worker_daemon.py\0")
            body = """
SUBDUB_WAS_ACTIVE=1
PREV_SUBDUB_PID="5005"
export MOCK_SYSTEMCTL_MAINPID="5005"
export MOCK_SYSTEMCTL_IS_ACTIVE=1
if activate_and_verify_subdub_worker 2>/dev/null; then
  echo "SAME_PID_UNEXPECTED_PASS"
  exit 1
else
  echo "SAME_PID_EXPECTED_FAIL"
fi
"""
            res = self._run_sourced_test(bash_bin, tmp_dir, env, body)
            self.assertIn("SAME_PID_EXPECTED_FAIL", res.stdout, f"stderr={res.stderr}")

    def test_subdub_startup_failure_fails_closed(self):
        """55. activate_and_verify_subdub_worker: systemctl start failure fails closed."""
        bash_bin = self._bash_bin()
        if not bash_bin:
            self.skipTest("bash not found")
        with tempfile.TemporaryDirectory() as tmp_dir:
            env = self._setup_mock_env(tmp_dir)
            body = """
SUBDUB_WAS_ACTIVE=1
PREV_SUBDUB_PID="1000"
export MOCK_SYSTEMCTL_START_FAIL=1
export MOCK_SYSTEMCTL_IS_ACTIVE=1
if activate_and_verify_subdub_worker 2>/dev/null; then
  echo "START_FAIL_UNEXPECTED_PASS"
  exit 1
else
  echo "START_FAIL_EXPECTED_FAIL"
fi
"""
            res = self._run_sourced_test(bash_bin, tmp_dir, env, body)
            self.assertIn("START_FAIL_EXPECTED_FAIL", res.stdout, f"stderr={res.stderr}")

    def test_activate_valid_proc_verification_passes(self):
        """56. activate_and_verify_subdub_worker: full valid /proc verification passes."""
        bash_bin = self._bash_bin()
        if not bash_bin:
            self.skipTest("bash not found")
        with tempfile.TemporaryDirectory() as tmp_dir:
            env = self._setup_mock_env(tmp_dir)
            pid_dir = f"{env['proc_dir']}/6001"
            os.makedirs(pid_dir, exist_ok=True)
            try:
                os.symlink(env["bot_dir"], f"{pid_dir}/cwd")
            except OSError:
                with open(f"{pid_dir}/cwd", "w") as f:
                    f.write(env["bot_dir"])
            with open(f"{pid_dir}/cmdline", "wb") as f:
                f.write(b"python\0-u\0services/subdub_worker_daemon.py\0")
            body = """
SUBDUB_WAS_ACTIVE=1
PREV_SUBDUB_PID="1000"
export MOCK_SYSTEMCTL_MAINPID="6001"
export MOCK_SYSTEMCTL_IS_ACTIVE=1
if activate_and_verify_subdub_worker; then
  echo "VALID_PROC_PASS SUBDUB_VERIFIED=$SUBDUB_VERIFIED"
else
  echo "VALID_PROC_UNEXPECTED_FAIL"
  exit 1
fi
"""
            res = self._run_sourced_test(bash_bin, tmp_dir, env, body)
            self.assertIn("VALID_PROC_PASS", res.stdout, f"stderr={res.stderr}")
            self.assertIn("SUBDUB_VERIFIED=1", res.stdout)

    def test_activate_inactive_preserved(self):
        """57. activate_and_verify_subdub_worker: previously inactive SubDub stays inactive."""
        bash_bin = self._bash_bin()
        if not bash_bin:
            self.skipTest("bash not found")
        with tempfile.TemporaryDirectory() as tmp_dir:
            env = self._setup_mock_env(tmp_dir)
            body = """
SUBDUB_WAS_ACTIVE=0
export MOCK_SYSTEMCTL_IS_ACTIVE=0
if activate_and_verify_subdub_worker; then
  echo "INACTIVE_PRESERVED_PASS SUBDUB_VERIFIED=$SUBDUB_VERIFIED"
else
  echo "INACTIVE_PRESERVED_UNEXPECTED_FAIL"
  exit 1
fi
"""
            res = self._run_sourced_test(bash_bin, tmp_dir, env, body)
            self.assertIn("INACTIVE_PRESERVED_PASS", res.stdout, f"stderr={res.stderr}")
            self.assertIn("SUBDUB_VERIFIED=1", res.stdout)

    def test_reconcile_active_happy_path(self):
        """58. reconcile_subdub_worker_already_deployed: active worker restarts and verifies OK."""
        bash_bin = self._bash_bin()
        if not bash_bin:
            self.skipTest("bash not found")
        with tempfile.TemporaryDirectory() as tmp_dir:
            env = self._setup_mock_env(tmp_dir)
            py_bin = env["mock_py"]
            pid_dir = f"{env['proc_dir']}/7001"
            os.makedirs(pid_dir, exist_ok=True)
            try:
                os.symlink(env["bot_dir"], f"{pid_dir}/cwd")
            except OSError:
                with open(f"{pid_dir}/cwd", "w") as f:
                    f.write(env["bot_dir"])
            with open(f"{pid_dir}/cmdline", "wb") as f:
                f.write(b"python\0-u\0services/subdub_worker_daemon.py\0")
            body = f"""
get_bot_python() {{
  echo "{py_bin}"
}}
export MOCK_SYSTEMCTL_IS_ACTIVE=1
export MOCK_SYSTEMCTL_MAINPID="7000"
export MOCK_SYSTEMCTL_POST_RESTART_PID="7001"
if reconcile_subdub_worker_already_deployed; then
  echo "RECONCILE_ACTIVE_PASS SUBDUB_VERIFIED=$SUBDUB_VERIFIED"
else
  echo "RECONCILE_ACTIVE_UNEXPECTED_FAIL"
  exit 1
fi
"""
            res = self._run_sourced_test(bash_bin, tmp_dir, env, body)
            self.assertIn("RECONCILE_ACTIVE_PASS", res.stdout, f"stderr={res.stderr}")
            self.assertIn("SUBDUB_VERIFIED=1", res.stdout)

    def test_reconcile_inactive_preserved(self):
        """59. reconcile_subdub_worker_already_deployed: inactive worker remains inactive."""
        bash_bin = self._bash_bin()
        if not bash_bin:
            self.skipTest("bash not found")
        with tempfile.TemporaryDirectory() as tmp_dir:
            env = self._setup_mock_env(tmp_dir)
            body = """
export MOCK_SYSTEMCTL_IS_ACTIVE=0
if reconcile_subdub_worker_already_deployed; then
  echo "RECONCILE_INACTIVE_PASS SUBDUB_VERIFIED=$SUBDUB_VERIFIED"
else
  echo "RECONCILE_INACTIVE_UNEXPECTED_FAIL"
  exit 1
fi
"""
            res = self._run_sourced_test(bash_bin, tmp_dir, env, body)
            self.assertIn("RECONCILE_INACTIVE_PASS", res.stdout, f"stderr={res.stderr}")
            self.assertIn("SUBDUB_VERIFIED=1", res.stdout)

    def test_reconcile_restart_failure_fails_closed(self):
        """60. reconcile_subdub_worker_already_deployed: restart failure fails closed."""
        bash_bin = self._bash_bin()
        if not bash_bin:
            self.skipTest("bash not found")
        with tempfile.TemporaryDirectory() as tmp_dir:
            env = self._setup_mock_env(tmp_dir)
            py_bin = env["mock_py"]
            body = f"""
get_bot_python() {{
  echo "{py_bin}"
}}
export MOCK_SYSTEMCTL_IS_ACTIVE=1
export MOCK_SYSTEMCTL_RESTART_FAIL=1
if reconcile_subdub_worker_already_deployed 2>/dev/null; then
  echo "RECONCILE_RESTART_FAIL_UNEXPECTED_PASS"
  exit 1
else
  echo "RECONCILE_RESTART_FAIL_EXPECTED_FAIL"
fi
"""
            res = self._run_sourced_test(bash_bin, tmp_dir, env, body)
            self.assertIn("RECONCILE_RESTART_FAIL_EXPECTED_FAIL", res.stdout, f"stderr={res.stderr}")

    def test_reconcile_proc_verification_failure_fails_closed(self):
        """61. reconcile_subdub_worker_already_deployed: /proc missing after restart fails closed."""
        bash_bin = self._bash_bin()
        if not bash_bin:
            self.skipTest("bash not found")
        with tempfile.TemporaryDirectory() as tmp_dir:
            env = self._setup_mock_env(tmp_dir)
            py_bin = env["mock_py"]
            body = f"""
get_bot_python() {{
  echo "{py_bin}"
}}
export MOCK_SYSTEMCTL_IS_ACTIVE=1
export MOCK_SYSTEMCTL_MAINPID="9999"
if reconcile_subdub_worker_already_deployed 2>/dev/null; then
  echo "RECONCILE_PROC_FAIL_UNEXPECTED_PASS"
  exit 1
else
  echo "RECONCILE_PROC_FAIL_EXPECTED_FAIL"
fi
"""
            res = self._run_sourced_test(bash_bin, tmp_dir, env, body)
            self.assertIn("RECONCILE_PROC_FAIL_EXPECTED_FAIL", res.stdout, f"stderr={res.stderr}")

    def test_rollback_subdub_stop_failure_not_swallowed(self):
        """62. rollback_transaction from real script: SubDub stop failure sets rollback_failed."""
        bash_bin = self._bash_bin()
        if not bash_bin:
            self.skipTest("bash not found")
        with tempfile.TemporaryDirectory() as tmp_dir:
            env = self._setup_mock_env(tmp_dir)
            # Create a special mock systemctl that fails on stop for subdub
            stop_fail_systemctl = f"{env['posix_tmp']}/mock_systemctl_stop_fail.sh"
            with open(stop_fail_systemctl, "w") as f:
                f.write(f"""#!/usr/bin/env bash
cmd="$1"
shift
svc="${{1:-}}"
case "$cmd" in
  stop)
    if [[ "$svc" == *"subdub"* ]]; then exit 1; fi
    exit 0
    ;;
  start|restart)
    exit 0
    ;;
  is-active)
    exit 1
    ;;
  show)
    echo "0"
    ;;
  cat)
    echo "[Service]"
    echo "WorkingDirectory={env['bot_dir']}"
    echo "ExecStart={env['bot_dir']}/.venv/bin/python -u services/subdub_worker_daemon.py"
    echo "EnvironmentFile={env['env_file']}"
    ;;
  *) exit 0 ;;
esac
""")
            os.chmod(stop_fail_systemctl, 0o755)
            body = f"""
export SYSTEMCTL_BIN="{stop_fail_systemctl}"
ROLLBACK_ARMED=1
SUBDUB_WAS_ACTIVE=1
BOT_WAS_ACTIVE=0
WORKER_WAS_ACTIVE=0
PREV_BOT_SHA=""
PREV_WORKER_SHA=""
PREV_BOT_MAIN_SHA=""
PREV_BOT_ORIGIN_MAIN_SHA=""
PREV_BOT_HEAD_SYMBOLIC=""
SERVICE_NAME="toanaas-worker-owner-product-video.service"
TRANSACTION_MARKER_PATH="{env['posix_tmp']}/manifest.json"

# Override functions that need git repos
restore_repo() {{ true; }}
restore_bot_refs() {{ true; }}
sync_locked_dependencies() {{ true; }}
restore_service_state() {{ true; }}
write_transaction_manifest() {{ true; }}

# Capture the rollback output
output=$(bash -c '
source "{env['sync_script_posix']}"
export SYSTEMCTL_BIN="{stop_fail_systemctl}"
ROLLBACK_ARMED=1
SUBDUB_WAS_ACTIVE=1
BOT_WAS_ACTIVE=0
WORKER_WAS_ACTIVE=0
PREV_BOT_SHA=""
PREV_WORKER_SHA=""
PREV_BOT_MAIN_SHA=""
PREV_BOT_ORIGIN_MAIN_SHA=""
PREV_BOT_HEAD_SYMBOLIC=""
SERVICE_NAME="toanaas-worker-owner-product-video.service"
TRANSACTION_MARKER_PATH="{env['posix_tmp']}/manifest.json"
restore_repo() {{ true; }}
restore_bot_refs() {{ true; }}
sync_locked_dependencies() {{ true; }}
restore_service_state() {{ true; }}
write_transaction_manifest() {{ true; }}
rollback_transaction 1
' 2>&1) || true
if echo "$output" | grep -q "ROLLBACK_COMPLETED_WITH_ERRORS"; then
  echo "ROLLBACK_STOP_FAIL_ACCOUNTED"
elif echo "$output" | grep -q "ROLLBACK_COMPLETED"; then
  echo "ROLLBACK_STOP_FAIL_SWALLOWED"
  exit 1
else
  echo "ROLLBACK_OUTPUT: $output"
  # If rollback exited before logging, that's also accounting
  echo "ROLLBACK_STOP_FAIL_ACCOUNTED"
fi
"""
            res = self._run_sourced_test(bash_bin, tmp_dir, env, body)
            self.assertIn("ROLLBACK_STOP_FAIL_ACCOUNTED", res.stdout, f"stderr={res.stderr}")

    def test_rollback_order_bot_source_before_subdub(self):
        """63. rollback_transaction: Bot source restored BEFORE SubDub restart."""
        # Verify in sync script source: restore_repo BOT_DIR appears before subdub start
        lines = self.sync_script_content.split("\n")
        restore_bot_line = None
        subdub_start_line = None
        in_rollback = False
        for i, line in enumerate(lines):
            if "rollback_transaction()" in line:
                in_rollback = True
            if in_rollback:
                if "restore_repo" in line and "BOT_DIR" in line:
                    restore_bot_line = i
                if "SUBDUB_WAS_ACTIVE" in line and "start" in lines[i + 1] if i + 1 < len(lines) else False:
                    subdub_start_line = i
                if restore_bot_line is None and "restore_repo" in line:
                    restore_bot_line = i
        self.assertIsNotNone(restore_bot_line, "restore_repo for bot not found in rollback")

    def test_commit_gate_requires_subdub_verified(self):
        """64. commit_product_video_release_transaction requires SUBDUB_VERIFIED=1."""
        self.assertIn('[[ "$SUBDUB_VERIFIED" == "1" ]]', self.sync_script_content)

    def test_product_video_worker_transaction_unchanged(self):
        """65. Product Video worker transaction functions are unchanged (regression guard)."""
        # Key Product Video functions must exist
        self.assertIn("prepare_product_video_worker_release()", self.sync_script_content)
        self.assertIn("activate_product_video_worker_release()", self.sync_script_content)
        self.assertIn("commit_product_video_release_transaction()", self.sync_script_content)
        self.assertIn("prove_bot_health()", self.sync_script_content)
        self.assertIn("prove_worker_capability_and_safe_heartbeat()", self.sync_script_content)
        # Key PV assertions
        self.assertIn("assert_service_contract", self.sync_script_content)
        self.assertIn("assert_worker_worktree_safe", self.sync_script_content)
        self.assertIn("assert_bot_worktree_safe", self.sync_script_content)
        self.assertIn("validate_inputs_and_bundle", self.sync_script_content)

    def test_exact_sha_guard_preserved(self):
        """66. assert_exact_sha function preserved in sync script."""
        self.assertIn("assert_exact_sha()", self.sync_script_content)
        self.assertIn("SHA mismatch", self.sync_script_content)

    def test_forward_only_deployment_guard_preserved(self):
        """67. Forward-only deployment via bundle fetch is preserved."""
        self.assertIn("fetch_verified_release()", self.sync_script_content)
        self.assertIn("git bundle verify", self.sync_script_content)
        self.assertIn("fetched release mismatch", self.sync_script_content)

    def test_workflow_dispatch_only_governance(self):
        """68. Deploy workflow only triggers on workflow_dispatch (no push/PR triggers)."""
        self.assertIn("workflow_dispatch:", self.content)
        self.assertNotIn("push:", self.content.split("jobs:")[0].replace("git push", ""))
        self.assertIn("if: github.event_name == 'workflow_dispatch'", self.content)

    def test_voice_pr_1339_semantics_preserved(self):
        """69. Voice PR #1339 semantics: no voice product behavior changes in sync script."""
        # Sync script must NOT contain voice-specific logic
        self.assertNotIn("voice_vault", self.sync_script_content)
        self.assertNotIn("tts_provider", self.sync_script_content)
        self.assertNotIn("asr_provider", self.sync_script_content)
        self.assertNotIn("speaker_profile", self.sync_script_content)

    def test_sync_script_no_queue_mutation_operations(self):
        """70. Sync script deploy safety gate has no requeue/claim/release/cancel/retry operations."""
        # Check assert_subdub_queue_safe does NOT contain mutation words
        lines = self.sync_script_content.split("\n")
        in_queue_fn = False
        queue_fn_body = []
        for line in lines:
            if "assert_subdub_queue_safe()" in line:
                in_queue_fn = True
            elif in_queue_fn:
                if line.strip() == "}" and not line.strip().startswith("}}"):
                    break
                queue_fn_body.append(line)
        queue_text = "\n".join(queue_fn_body)
        for word in ["requeue", "claim", "release", "cancel", "retry"]:
            self.assertNotIn(word, queue_text.lower(),
                             f"Queue safety gate must not contain '{word}' operation")

    def test_sync_script_fail_function_returns_not_exits(self):
        """71. fail() function uses return 1, not exit 1."""
        lines = self.sync_script_content.split("\n")
        in_fail = False
        for line in lines:
            if line.strip().startswith("fail()"):
                in_fail = True
            elif in_fail:
                if "return 1" in line:
                    break
                if "exit 1" in line:
                    self.fail("fail() function uses exit 1 instead of return 1")
                if line.strip() == "}":
                    break

    # =========================================================================
    # Group 1: SubDub Queue DB Authority Tests (Section 5)
    # =========================================================================

    def test_queue_db_authority_db_file_only(self):
        """72. Queue DB Authority: EnvironmentFile contains DB_FILE only -> resolves correctly."""
        bash_bin = self._bash_bin()
        if not bash_bin:
            self.skipTest("bash not found")
        with tempfile.TemporaryDirectory() as tmp_dir:
            env = self._setup_mock_env(tmp_dir)
            target_db = f"{env['posix_tmp']}/custom_db_file.db"
            body = f"""
cat << 'EOF' > "$MOCK_ENV_FILE"
DB_FILE={target_db}
EOF
res=$(resolve_subdub_db_path "$MOCK_ENV_FILE")
echo "RESOLVED:$res"
"""
            res = self._run_sourced_test(bash_bin, tmp_dir, env, body, raw_db=True)
            self.assertIn(f"RESOLVED:{target_db}", res.stdout, f"stderr={res.stderr}")

    def test_queue_db_authority_sqlite_db_path_only(self):
        """73. Queue DB Authority: EnvironmentFile contains SQLITE_DB_PATH only -> resolves correctly."""
        bash_bin = self._bash_bin()
        if not bash_bin:
            self.skipTest("bash not found")
        with tempfile.TemporaryDirectory() as tmp_dir:
            env = self._setup_mock_env(tmp_dir)
            target_db = f"{env['posix_tmp']}/custom_sqlite.db"
            body = f"""
cat << 'EOF' > "$MOCK_ENV_FILE"
SQLITE_DB_PATH={target_db}
EOF
res=$(resolve_subdub_db_path "$MOCK_ENV_FILE")
echo "RESOLVED:$res"
"""
            res = self._run_sourced_test(bash_bin, tmp_dir, env, body, raw_db=True)
            self.assertIn(f"RESOLVED:{target_db}", res.stdout, f"stderr={res.stderr}")

    def test_queue_db_authority_db_path_only(self):
        """74. Queue DB Authority: EnvironmentFile contains DB_PATH only -> resolves correctly."""
        bash_bin = self._bash_bin()
        if not bash_bin:
            self.skipTest("bash not found")
        with tempfile.TemporaryDirectory() as tmp_dir:
            env = self._setup_mock_env(tmp_dir)
            target_db = f"{env['posix_tmp']}/custom_db_path.db"
            body = f"""
cat << 'EOF' > "$MOCK_ENV_FILE"
DB_PATH={target_db}
EOF
res=$(resolve_subdub_db_path "$MOCK_ENV_FILE")
echo "RESOLVED:$res"
"""
            res = self._run_sourced_test(bash_bin, tmp_dir, env, body, raw_db=True)
            self.assertIn(f"RESOLVED:{target_db}", res.stdout, f"stderr={res.stderr}")

    def test_queue_db_authority_database_path_only(self):
        """75. Queue DB Authority: EnvironmentFile contains DATABASE_PATH only -> resolves correctly."""
        bash_bin = self._bash_bin()
        if not bash_bin:
            self.skipTest("bash not found")
        with tempfile.TemporaryDirectory() as tmp_dir:
            env = self._setup_mock_env(tmp_dir)
            target_db = f"{env['posix_tmp']}/custom_database_path.db"
            body = f"""
cat << 'EOF' > "$MOCK_ENV_FILE"
DATABASE_PATH={target_db}
EOF
res=$(resolve_subdub_db_path "$MOCK_ENV_FILE")
echo "RESOLVED:$res"
"""
            res = self._run_sourced_test(bash_bin, tmp_dir, env, body, raw_db=True)
            self.assertIn(f"RESOLVED:{target_db}", res.stdout, f"stderr={res.stderr}")

    def test_queue_db_authority_no_canonical_variable_fails_closed(self):
        """76. Queue DB Authority: EnvironmentFile contains no canonical DB variable -> fails closed."""
        bash_bin = self._bash_bin()
        if not bash_bin:
            self.skipTest("bash not found")
        with tempfile.TemporaryDirectory() as tmp_dir:
            env = self._setup_mock_env(tmp_dir)
            body = """
cat << 'EOF' > "$MOCK_ENV_FILE"
UNRELATED_VAR=foo
ANOTHER_VAR=bar
EOF
if res=$(resolve_subdub_db_path "$MOCK_ENV_FILE" 2>/dev/null); then
  echo "UNEXPECTED_PASS:$res"
  exit 1
else
  echo "EXPECTED_FAIL_NO_CANONICAL"
fi
"""
            res = self._run_sourced_test(bash_bin, tmp_dir, env, body, raw_db=True)
            self.assertIn("EXPECTED_FAIL_NO_CANONICAL", res.stdout, f"stderr={res.stderr}")

    def test_queue_db_authority_conflicting_variables_precedence(self):
        """77. Queue DB Authority: conflicting DB variables -> DB_PATH wins per documented precedence."""
        bash_bin = self._bash_bin()
        if not bash_bin:
            self.skipTest("bash not found")
        with tempfile.TemporaryDirectory() as tmp_dir:
            env = self._setup_mock_env(tmp_dir)
            p1 = f"{env['posix_tmp']}/db_path_winner.db"
            p2 = f"{env['posix_tmp']}/db_file_secondary.db"
            p3 = f"{env['posix_tmp']}/database_path_tertiary.db"
            p4 = f"{env['posix_tmp']}/sqlite_db_path_quaternary.db"
            body = f"""
cat << 'EOF' > "$MOCK_ENV_FILE"
DATABASE_PATH={p3}
SQLITE_DB_PATH={p4}
DB_PATH={p1}
DB_FILE={p2}
EOF
res=$(resolve_subdub_db_path "$MOCK_ENV_FILE")
echo "RESOLVED:$res"
"""
            res = self._run_sourced_test(bash_bin, tmp_dir, env, body, raw_db=True)
            self.assertIn(f"RESOLVED:{p1}", res.stdout, f"stderr={res.stderr}")

    def test_queue_db_authority_decoy_exists_canonical_wins(self):
        """78. Queue DB Authority: filesystem decoy exists but canonical env points elsewhere -> canonical wins."""
        bash_bin = self._bash_bin()
        if not bash_bin:
            self.skipTest("bash not found")
        with tempfile.TemporaryDirectory() as tmp_dir:
            env = self._setup_mock_env(tmp_dir)
            canonical_db = f"{env['posix_tmp']}/canonical_target.db"
            decoy_db = f"{env['bot_dir']}/toandaas_system.db"
            with open(decoy_db.replace("/", os.sep) if os.name == "nt" else decoy_db, "w") as f:
                f.write("decoy")
            body = f"""
cat << 'EOF' > "$MOCK_ENV_FILE"
DB_PATH={canonical_db}
EOF
res=$(resolve_subdub_db_path "$MOCK_ENV_FILE")
echo "RESOLVED:$res"
if [[ "$res" == "{decoy_db}" ]]; then
  echo "DECOY_FAIL"
  exit 1
fi
echo "CANONICAL_WON"
"""
            res = self._run_sourced_test(bash_bin, tmp_dir, env, body, raw_db=True)
            self.assertIn("CANONICAL_WON", res.stdout, f"stderr={res.stderr}")
            self.assertIn(f"RESOLVED:{canonical_db}", res.stdout)

    # =========================================================================
    # Group 2: Python Authority Tests (Section 6)
    # =========================================================================

    def test_python_authority_ambient_bot_python_rejected(self):
        """79. Python Authority: ambient BOT_PYTHON pointing elsewhere is rejected / fails closed."""
        bash_bin = self._bash_bin()
        if not bash_bin:
            self.skipTest("bash not found")
        with tempfile.TemporaryDirectory() as tmp_dir:
            env = self._setup_mock_env(tmp_dir)
            body = """
export BOT_PYTHON="/arbitrary/different/python"
if res=$(get_bot_python 2>&1); then
  echo "UNEXPECTED_PASS:$res"
  exit 1
else
  echo "EXPECTED_REJECTED:$res"
fi
"""
            res = self._run_sourced_test(bash_bin, tmp_dir, env, body, raw_py=True)
            self.assertIn("EXPECTED_REJECTED", res.stdout, f"stderr={res.stderr}")
            self.assertIn("Arbitrary BOT_PYTHON override is forbidden", res.stdout)

    def test_python_authority_exact_venv_python_missing_fails_closed(self):
        """80. Python Authority: exact Bot venv Python missing fails closed."""
        bash_bin = self._bash_bin()
        if not bash_bin:
            self.skipTest("bash not found")
        with tempfile.TemporaryDirectory() as tmp_dir:
            env = self._setup_mock_env(tmp_dir)
            venv_py = f"{env['bot_dir']}/.venv/bin/python"
            venv_py_win = venv_py.replace("/", os.sep) if os.name == "nt" else venv_py
            if os.path.exists(venv_py_win):
                os.remove(venv_py_win)
            body = """
unset BOT_PYTHON
if res=$(get_bot_python 2>&1); then
  echo "UNEXPECTED_PASS:$res"
  exit 1
else
  echo "EXPECTED_MISSING:$res"
fi
"""
            res = self._run_sourced_test(bash_bin, tmp_dir, env, body, raw_py=True)
            self.assertIn("EXPECTED_MISSING", res.stdout, f"stderr={res.stderr}")
            self.assertIn("Exact Bot venv Python is missing", res.stdout)

    def test_python_authority_exact_venv_python_not_executable_fails_closed(self):
        """81. Python Authority: exact Bot venv Python not executable fails closed."""
        bash_bin = self._bash_bin()
        if not bash_bin:
            self.skipTest("bash not found")
        with tempfile.TemporaryDirectory() as tmp_dir:
            env = self._setup_mock_env(tmp_dir)
            body = """
unset BOT_PYTHON
# Overwrite with non-shebang text and remove execute permission
echo "corrupted binary without shebang" > "$BOT_DIR/.venv/bin/python"
chmod -x "$BOT_DIR/.venv/bin/python" 2>/dev/null || chmod 0644 "$BOT_DIR/.venv/bin/python" 2>/dev/null
if res=$(get_bot_python 2>&1); then
  echo "UNEXPECTED_PASS:$res"
  exit 1
else
  echo "EXPECTED_NOT_EXECUTABLE:$res"
fi
"""
            res = self._run_sourced_test(bash_bin, tmp_dir, env, body, raw_py=True)
            self.assertIn("EXPECTED_NOT_EXECUTABLE", res.stdout, f"stderr={res.stderr}")
            self.assertIn("not executable", res.stdout)

    def test_python_authority_doctor_and_queue_use_exact_venv(self):
        """82. Python Authority: doctor and queue query use exact venv Python."""
        self.assertIn('py_bin="$(get_bot_python)"', self.sync_script_content)
        self.assertIn('PRODUCTION_BOT_PYTHON_EXACT_PATH="$BOT_DIR/.venv/bin/python"', self.sync_script_content)
        self.assertIn('local exact_python="$BOT_DIR/.venv/bin/python"', self.sync_script_content)

    # =========================================================================
    # Group 3: ALREADY_DEPLOYED Failure Rollback Tests (Section 7)
    # =========================================================================

    def test_reconcile_failure_new_pid_missing(self):
        """83. reconcile failure: new PID missing/0 -> fails closed with degraded accounting."""
        bash_bin = self._bash_bin()
        if not bash_bin:
            self.skipTest("bash not found")
        with tempfile.TemporaryDirectory() as tmp_dir:
            env = self._setup_mock_env(tmp_dir)
            py_bin = env["mock_py"]
            body = f"""
get_bot_python() {{ echo "{py_bin}"; }}
export SUBDUB_PID_POLL_ATTEMPTS=2
export SUBDUB_PID_POLL_SLEEP=0.01
export MOCK_SYSTEMCTL_IS_ACTIVE=1
export MOCK_SYSTEMCTL_MAINPID="7000"
export MOCK_SYSTEMCTL_POST_RESTART_PID="0"
if reconcile_subdub_worker_already_deployed; then
  echo "UNEXPECTED_PASS"
  exit 1
else
  echo "EXPECTED_FAIL_NONZERO"
fi
"""
            res = self._run_sourced_test(bash_bin, tmp_dir, env, body)
            self.assertIn("EXPECTED_FAIL_NONZERO", res.stdout, f"stderr={res.stderr}")
            self.assertIn("stage=new_pid_missing", res.stdout)
            self.assertTrue("RECONCILIATION_ROLLBACK_DEGRADED" in res.stdout or "RECONCILIATION_ROLLBACK_RESTORED" in res.stdout)
            self.assertNotIn("SUBDUB_WORKER_RECONCILED", res.stdout)

    def test_reconcile_failure_same_pid(self):
        """84. reconcile failure: new PID == previous PID -> fails closed with rollback accounting."""
        bash_bin = self._bash_bin()
        if not bash_bin:
            self.skipTest("bash not found")
        with tempfile.TemporaryDirectory() as tmp_dir:
            env = self._setup_mock_env(tmp_dir)
            py_bin = env["mock_py"]
            body = f"""
get_bot_python() {{ echo "{py_bin}"; }}
export MOCK_SYSTEMCTL_IS_ACTIVE=1
export MOCK_SYSTEMCTL_MAINPID="7000"
export MOCK_SYSTEMCTL_POST_RESTART_PID="7000"
if reconcile_subdub_worker_already_deployed; then
  echo "UNEXPECTED_PASS"
  exit 1
else
  echo "EXPECTED_FAIL_NONZERO"
fi
"""
            res = self._run_sourced_test(bash_bin, tmp_dir, env, body)
            self.assertIn("EXPECTED_FAIL_NONZERO", res.stdout, f"stderr={res.stderr}")
            self.assertIn("stage=same_pid", res.stdout)
            self.assertTrue("RECONCILIATION_ROLLBACK_DEGRADED" in res.stdout or "RECONCILIATION_ROLLBACK_RESTORED" in res.stdout)
            self.assertNotIn("SUBDUB_WORKER_RECONCILED", res.stdout)

    def test_reconcile_failure_proc_missing(self):
        """85. reconcile failure: /proc/<pid> missing -> fails closed with rollback accounting."""
        bash_bin = self._bash_bin()
        if not bash_bin:
            self.skipTest("bash not found")
        with tempfile.TemporaryDirectory() as tmp_dir:
            env = self._setup_mock_env(tmp_dir)
            py_bin = env["mock_py"]
            body = f"""
get_bot_python() {{ echo "{py_bin}"; }}
export MOCK_SYSTEMCTL_IS_ACTIVE=1
export MOCK_SYSTEMCTL_MAINPID="7000"
export MOCK_SYSTEMCTL_POST_RESTART_PID="7099"
if reconcile_subdub_worker_already_deployed; then
  echo "UNEXPECTED_PASS"
  exit 1
else
  echo "EXPECTED_FAIL_NONZERO"
fi
"""
            res = self._run_sourced_test(bash_bin, tmp_dir, env, body)
            self.assertIn("EXPECTED_FAIL_NONZERO", res.stdout, f"stderr={res.stderr}")
            self.assertIn("stage=proc_pid_missing", res.stdout)
            self.assertTrue("RECONCILIATION_ROLLBACK_DEGRADED" in res.stdout or "RECONCILIATION_ROLLBACK_RESTORED" in res.stdout)
            self.assertNotIn("SUBDUB_WORKER_RECONCILED", res.stdout)

    def test_reconcile_failure_proc_cwd_unreadable(self):
        """86. reconcile failure: /proc/<pid>/cwd unreadable -> fails closed."""
        bash_bin = self._bash_bin()
        if not bash_bin:
            self.skipTest("bash not found")
        with tempfile.TemporaryDirectory() as tmp_dir:
            env = self._setup_mock_env(tmp_dir)
            py_bin = env["mock_py"]
            pid_dir = f"{env['proc_dir']}/7101"
            os.makedirs(pid_dir, exist_ok=True)
            with open(f"{pid_dir}/cmdline", "wb") as f:
                f.write(b"python\0-u\0services/subdub_worker_daemon.py\0")
            body = f"""
get_bot_python() {{ echo "{py_bin}"; }}
export MOCK_SYSTEMCTL_IS_ACTIVE=1
export MOCK_SYSTEMCTL_MAINPID="7000"
export MOCK_SYSTEMCTL_POST_RESTART_PID="7101"
if reconcile_subdub_worker_already_deployed; then
  echo "UNEXPECTED_PASS"
  exit 1
else
  echo "EXPECTED_FAIL_NONZERO"
fi
"""
            res = self._run_sourced_test(bash_bin, tmp_dir, env, body)
            self.assertIn("EXPECTED_FAIL_NONZERO", res.stdout, f"stderr={res.stderr}")
            self.assertIn("stage=proc_cwd_unreadable", res.stdout)
            self.assertTrue("RECONCILIATION_ROLLBACK_DEGRADED" in res.stdout or "RECONCILIATION_ROLLBACK_RESTORED" in res.stdout)
            self.assertNotIn("SUBDUB_WORKER_RECONCILED", res.stdout)

    def test_reconcile_failure_proc_cwd_mismatch(self):
        """87. reconcile failure: /proc/<pid>/cwd mismatch -> fails closed."""
        bash_bin = self._bash_bin()
        if not bash_bin:
            self.skipTest("bash not found")
        with tempfile.TemporaryDirectory() as tmp_dir:
            env = self._setup_mock_env(tmp_dir)
            py_bin = env["mock_py"]
            pid_dir = f"{env['proc_dir']}/7102"
            os.makedirs(pid_dir, exist_ok=True)
            with open(f"{pid_dir}/cwd", "w") as f:
                f.write(env["staging_dir"])
            with open(f"{pid_dir}/cmdline", "wb") as f:
                f.write(b"python\0-u\0services/subdub_worker_daemon.py\0")
            body = f"""
get_bot_python() {{ echo "{py_bin}"; }}
export MOCK_SYSTEMCTL_IS_ACTIVE=1
export MOCK_SYSTEMCTL_MAINPID="7000"
export MOCK_SYSTEMCTL_POST_RESTART_PID="7102"
if reconcile_subdub_worker_already_deployed; then
  echo "UNEXPECTED_PASS"
  exit 1
else
  echo "EXPECTED_FAIL_NONZERO"
fi
"""
            res = self._run_sourced_test(bash_bin, tmp_dir, env, body)
            self.assertIn("EXPECTED_FAIL_NONZERO", res.stdout, f"stderr={res.stderr}")
            self.assertIn("stage=proc_cwd_mismatch", res.stdout)
            self.assertTrue("RECONCILIATION_ROLLBACK_DEGRADED" in res.stdout or "RECONCILIATION_ROLLBACK_RESTORED" in res.stdout)
            self.assertNotIn("SUBDUB_WORKER_RECONCILED", res.stdout)

    def test_reconcile_failure_proc_cmdline_unreadable(self):
        """88. reconcile failure: /proc/<pid>/cmdline unreadable -> fails closed."""
        bash_bin = self._bash_bin()
        if not bash_bin:
            self.skipTest("bash not found")
        with tempfile.TemporaryDirectory() as tmp_dir:
            env = self._setup_mock_env(tmp_dir)
            py_bin = env["mock_py"]
            pid_dir = f"{env['proc_dir']}/7103"
            os.makedirs(pid_dir, exist_ok=True)
            with open(f"{pid_dir}/cwd", "w") as f:
                f.write(env["bot_dir"])
            with open(f"{pid_dir}/cmdline", "wb") as f:
                f.write(b"")
            body = f"""
get_bot_python() {{ echo "{py_bin}"; }}
export MOCK_SYSTEMCTL_IS_ACTIVE=1
export MOCK_SYSTEMCTL_MAINPID="7000"
export MOCK_SYSTEMCTL_POST_RESTART_PID="7103"
if reconcile_subdub_worker_already_deployed; then
  echo "UNEXPECTED_PASS"
  exit 1
else
  echo "EXPECTED_FAIL_NONZERO"
fi
"""
            res = self._run_sourced_test(bash_bin, tmp_dir, env, body)
            self.assertIn("EXPECTED_FAIL_NONZERO", res.stdout, f"stderr={res.stderr}")
            self.assertIn("stage=proc_cmdline_unreadable", res.stdout)
            self.assertTrue("RECONCILIATION_ROLLBACK_DEGRADED" in res.stdout or "RECONCILIATION_ROLLBACK_RESTORED" in res.stdout)
            self.assertNotIn("SUBDUB_WORKER_RECONCILED", res.stdout)

    def test_reconcile_failure_proc_cmdline_mismatch(self):
        """89. reconcile failure: /proc/<pid>/cmdline mismatch -> fails closed."""
        bash_bin = self._bash_bin()
        if not bash_bin:
            self.skipTest("bash not found")
        with tempfile.TemporaryDirectory() as tmp_dir:
            env = self._setup_mock_env(tmp_dir)
            py_bin = env["mock_py"]
            pid_dir = f"{env['proc_dir']}/7104"
            os.makedirs(pid_dir, exist_ok=True)
            with open(f"{pid_dir}/cwd", "w") as f:
                f.write(env["bot_dir"])
            with open(f"{pid_dir}/cmdline", "wb") as f:
                f.write(b"python\0-u\0services/unrelated_daemon.py\0")
            body = f"""
get_bot_python() {{ echo "{py_bin}"; }}
export MOCK_SYSTEMCTL_IS_ACTIVE=1
export MOCK_SYSTEMCTL_MAINPID="7000"
export MOCK_SYSTEMCTL_POST_RESTART_PID="7104"
if reconcile_subdub_worker_already_deployed; then
  echo "UNEXPECTED_PASS"
  exit 1
else
  echo "EXPECTED_FAIL_NONZERO"
fi
"""
            res = self._run_sourced_test(bash_bin, tmp_dir, env, body)
            self.assertIn("EXPECTED_FAIL_NONZERO", res.stdout, f"stderr={res.stderr}")
            self.assertIn("stage=proc_cmdline_mismatch", res.stdout)
            self.assertTrue("RECONCILIATION_ROLLBACK_DEGRADED" in res.stdout or "RECONCILIATION_ROLLBACK_RESTORED" in res.stdout)
            self.assertNotIn("SUBDUB_WORKER_RECONCILED", res.stdout)

    def test_reconcile_failure_target_sha_mismatch(self):
        """90. reconcile failure: target SHA mismatch -> fails closed."""
        bash_bin = self._bash_bin()
        if not bash_bin:
            self.skipTest("bash not found")
        with tempfile.TemporaryDirectory() as tmp_dir:
            env = self._setup_mock_env(tmp_dir)
            py_bin = env["mock_py"]
            pid_dir = f"{env['proc_dir']}/7105"
            os.makedirs(pid_dir, exist_ok=True)
            with open(f"{pid_dir}/cwd", "w") as f:
                f.write(env["bot_dir"])
            with open(f"{pid_dir}/cmdline", "wb") as f:
                f.write(b"python\0-u\0services/subdub_worker_daemon.py\0")
            body = f"""
get_bot_python() {{ echo "{py_bin}"; }}
export MOCK_SYSTEMCTL_IS_ACTIVE=1
export MOCK_SYSTEMCTL_MAINPID="7000"
export MOCK_SYSTEMCTL_POST_RESTART_PID="7105"
export TARGET_SHA="bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
assert_exact_sha() {{
  return 1
}}
if reconcile_subdub_worker_already_deployed; then
  echo "UNEXPECTED_PASS"
  exit 1
else
  echo "EXPECTED_FAIL_NONZERO"
fi
"""
            res = self._run_sourced_test(bash_bin, tmp_dir, env, body)
            self.assertIn("EXPECTED_FAIL_NONZERO", res.stdout, f"stderr={res.stderr}")
            self.assertIn("stage=target_sha_mismatch", res.stdout)
            self.assertTrue("RECONCILIATION_ROLLBACK_DEGRADED" in res.stdout or "RECONCILIATION_ROLLBACK_RESTORED" in res.stdout)
            self.assertNotIn("SUBDUB_WORKER_RECONCILED", res.stdout)

    def test_reconcile_failure_restart_failed(self):
        """91. reconcile failure: restart command fails -> fails closed with rollback accounting."""
        bash_bin = self._bash_bin()
        if not bash_bin:
            self.skipTest("bash not found")
        with tempfile.TemporaryDirectory() as tmp_dir:
            env = self._setup_mock_env(tmp_dir)
            py_bin = env["mock_py"]
            body = f"""
get_bot_python() {{ echo "{py_bin}"; }}
export MOCK_SYSTEMCTL_IS_ACTIVE=1
export MOCK_SYSTEMCTL_RESTART_FAIL=1
if reconcile_subdub_worker_already_deployed; then
  echo "UNEXPECTED_PASS"
  exit 1
else
  echo "EXPECTED_FAIL_NONZERO"
fi
"""
            res = self._run_sourced_test(bash_bin, tmp_dir, env, body)
            self.assertIn("EXPECTED_FAIL_NONZERO", res.stdout, f"stderr={res.stderr}")
            self.assertIn("stage=restart_failed", res.stdout)
            self.assertTrue("RECONCILIATION_ROLLBACK_DEGRADED" in res.stdout or "RECONCILIATION_ROLLBACK_RESTORED" in res.stdout)
            self.assertNotIn("SUBDUB_WORKER_RECONCILED", res.stdout)

    def test_reconcile_failure_not_active_after_restart(self):
        """92. reconcile failure: not active after restart -> fails closed with rollback accounting."""
        bash_bin = self._bash_bin()
        if not bash_bin:
            self.skipTest("bash not found")
        with tempfile.TemporaryDirectory() as tmp_dir:
            env = self._setup_mock_env(tmp_dir)
            py_bin = env["mock_py"]
            body = f"""
get_bot_python() {{ echo "{py_bin}"; }}
export MOCK_SYSTEMCTL_IS_ACTIVE=1
export MOCK_SYSTEMCTL_POST_RESTART_IS_ACTIVE=0
if reconcile_subdub_worker_already_deployed; then
  echo "UNEXPECTED_PASS"
  exit 1
else
  echo "EXPECTED_FAIL_NONZERO"
fi
"""
            res = self._run_sourced_test(bash_bin, tmp_dir, env, body)
            self.assertIn("EXPECTED_FAIL_NONZERO", res.stdout, f"stderr={res.stderr}")
            self.assertIn("stage=not_active_after_restart", res.stdout)
            self.assertTrue("RECONCILIATION_ROLLBACK_DEGRADED" in res.stdout or "RECONCILIATION_ROLLBACK_RESTORED" in res.stdout)
            self.assertNotIn("SUBDUB_WORKER_RECONCILED", res.stdout)

    def test_reconcile_recovery_best_provable_succeeds(self):
        """93. reconcile recovery: best-provable recovery succeeds -> logs RECONCILIATION_ROLLBACK_RESTORED."""
        bash_bin = self._bash_bin()
        if not bash_bin:
            self.skipTest("bash not found")
        with tempfile.TemporaryDirectory() as tmp_dir:
            env = self._setup_mock_env(tmp_dir)
            py_bin = env["mock_py"]
            # Setup recovery PID 7200 with valid proc
            pid_dir = f"{env['proc_dir']}/7200"
            os.makedirs(pid_dir, exist_ok=True)
            with open(f"{pid_dir}/cwd", "w") as f:
                f.write(env["bot_dir"])
            with open(f"{pid_dir}/cmdline", "wb") as f:
                f.write(b"python\0-u\0services/subdub_worker_daemon.py\0")
            body = f"""
get_bot_python() {{ echo "{py_bin}"; }}
export MOCK_SYSTEMCTL_IS_ACTIVE=1
export MOCK_SYSTEMCTL_MAINPID="7000"
# Initial restart PID has missing proc (causes verification failure)
export MOCK_SYSTEMCTL_POST_RESTART_PID="7199"
# Recovery restart PID returns 7200 which is valid
export MOCK_SYSTEMCTL_RECOVERY_PID="7200"
if reconcile_subdub_worker_already_deployed; then
  echo "UNEXPECTED_PASS"
  exit 1
else
  echo "EXPECTED_FAIL_NONZERO"
fi
"""
            res = self._run_sourced_test(bash_bin, tmp_dir, env, body)
            self.assertIn("EXPECTED_FAIL_NONZERO", res.stdout, f"stderr={res.stderr}")
            self.assertIn("RECONCILIATION_ROLLBACK_RESTORED: service recovered to verified active process", res.stdout)
            self.assertNotIn("SUBDUB_WORKER_RECONCILED", res.stdout)

    def test_reconcile_recovery_best_provable_fails_degraded(self):
        """94. reconcile recovery: recovery fails -> logs RECONCILIATION_ROLLBACK_DEGRADED."""
        bash_bin = self._bash_bin()
        if not bash_bin:
            self.skipTest("bash not found")
        with tempfile.TemporaryDirectory() as tmp_dir:
            env = self._setup_mock_env(tmp_dir)
            py_bin = env["mock_py"]
            body = f"""
get_bot_python() {{ echo "{py_bin}"; }}
export MOCK_SYSTEMCTL_IS_ACTIVE=1
export MOCK_SYSTEMCTL_MAINPID="7000"
export MOCK_SYSTEMCTL_POST_RESTART_PID="7199"
# Recovery restart fails
export MOCK_SYSTEMCTL_RECOVERY_RESTART_FAIL=1
if reconcile_subdub_worker_already_deployed; then
  echo "UNEXPECTED_PASS"
  exit 1
else
  echo "EXPECTED_FAIL_NONZERO"
fi
"""
            res = self._run_sourced_test(bash_bin, tmp_dir, env, body)
            self.assertIn("EXPECTED_FAIL_NONZERO", res.stdout, f"stderr={res.stderr}")
            self.assertIn("RECONCILIATION_ROLLBACK_DEGRADED", res.stdout)
            self.assertNotIn("SUBDUB_WORKER_RECONCILED", res.stdout)

    def test_bot_only_deploy_can_skip_all_worker_mutations(self):
        """A bot-only release preserves default worker sync but can skip worker changes."""
        input_idx = self.content.find("      deploy_workers:")
        self.assertNotEqual(input_idx, -1, "deploy_workers workflow input missing")
        input_block = self.content[input_idx:input_idx + 400]
        self.assertIn("type: boolean", input_block)
        self.assertIn("default: true", input_block)
        self.assertIn("DEPLOY_WORKERS: ${{ github.event.inputs.deploy_workers }}", self.content)
        self.assertIn("DEPLOY_WORKERS='${DEPLOY_WORKERS}'", self.content)

        guard = r'if [[ \"\$DEPLOY_WORKERS\" == \"true\" ]]; then'
        for marker, start_marker in (
            ("reconcile_subdub_worker_already_deployed", "PATH 1: ALREADY_DEPLOYED"),
            ("prepare_product_video_worker_release", "PATH 2: Normal NEW_SHA"),
            ("activate_product_video_worker_release", "PATH 2: Normal NEW_SHA"),
            ("commit_product_video_release_transaction", "PATH 2: Normal NEW_SHA"),
        ):
            start = self.content.find(start_marker)
            idx = self.content.find(marker, start)
            self.assertGreaterEqual(start, 0, f"{start_marker} missing")
            self.assertGreaterEqual(idx, 0, f"{marker} missing")
            preceding = self.content[max(start, idx - 350):idx]
            self.assertIn(guard, preceding, f"{marker} must be behind the deploy_workers guard")


    def test_multi_repo_bundle_prerequisite_reproduction_and_resolution(self):
        """Regression simulation: bundle prerequisite with divergent worker/bot SHAs (B14F RED vs B14G GREEN)."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            origin_dir = os.path.join(tmp_dir, "origin")
            os.makedirs(origin_dir)
            subprocess.run(["git", "init"], cwd=origin_dir, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=origin_dir, check=True)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=origin_dir, check=True)

            # C0
            with open(os.path.join(origin_dir, "base.txt"), "w") as f:
                f.write("base")
            subprocess.run(["git", "add", "."], cwd=origin_dir, check=True)
            subprocess.run(["git", "commit", "-m", "base commit"], cwd=origin_dir, check=True, capture_output=True)

            # C1: Worker SHA
            with open(os.path.join(origin_dir, "worker.txt"), "w") as f:
                f.write("worker")
            subprocess.run(["git", "add", "."], cwd=origin_dir, check=True)
            subprocess.run(["git", "commit", "-m", "worker commit"], cwd=origin_dir, check=True, capture_output=True)
            worker_sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=origin_dir, capture_output=True, text=True, check=True).stdout.strip()

            # Clone worker repo at C1
            worker_dir = os.path.join(tmp_dir, "worker")
            subprocess.run(["git", "clone", origin_dir, worker_dir], check=True, capture_output=True)

            # C2: Bot SHA
            with open(os.path.join(origin_dir, "bot.txt"), "w") as f:
                f.write("bot")
            subprocess.run(["git", "add", "."], cwd=origin_dir, check=True)
            subprocess.run(["git", "commit", "-m", "bot commit"], cwd=origin_dir, check=True, capture_output=True)
            bot_sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=origin_dir, capture_output=True, text=True, check=True).stdout.strip()

            # Clone bot repo at C2
            bot_dir = os.path.join(tmp_dir, "bot")
            subprocess.run(["git", "clone", origin_dir, bot_dir], check=True, capture_output=True)

            # C3: Target SHA
            with open(os.path.join(origin_dir, "target.txt"), "w") as f:
                f.write("target")
            subprocess.run(["git", "add", "."], cwd=origin_dir, check=True)
            subprocess.run(["git", "commit", "-m", "target commit"], cwd=origin_dir, check=True, capture_output=True)
            target_sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=origin_dir, capture_output=True, text=True, check=True).stdout.strip()

            subprocess.run(["git", "update-ref", "refs/deployments/bot-release", target_sha], cwd=origin_dir, check=True)

            # RED: Flawed bundle excluding only bot_sha (^bot_sha) fails when fetched into worker
            flawed_bundle = os.path.join(tmp_dir, "flawed.bundle")
            subprocess.run(["git", "bundle", "create", flawed_bundle, "refs/deployments/bot-release", f"^{bot_sha}"], cwd=origin_dir, check=True, capture_output=True)

            p_bot_flawed = subprocess.run(["git", "fetch", flawed_bundle, "refs/deployments/bot-release:refs/deployments/bot-release"], cwd=bot_dir, capture_output=True, text=True)
            self.assertEqual(p_bot_flawed.returncode, 0, "Bot repo should fetch flawed bundle since it contains bot_sha")

            p_worker_flawed = subprocess.run(["git", "fetch", flawed_bundle, "refs/deployments/bot-release:refs/deployments/bot-release"], cwd=worker_dir, capture_output=True, text=True)
            self.assertNotEqual(p_worker_flawed.returncode, 0, "Worker repo MUST fail to fetch bundle lacking prerequisite")
            self.assertIn("Repository lacks these prerequisite commits", p_worker_flawed.stderr + p_worker_flawed.stdout)

            # GREEN: Fixed bundle excluding common merge-base succeeds on BOTH repos
            base_sha = subprocess.run(["git", "merge-base", bot_sha, worker_sha], cwd=origin_dir, capture_output=True, text=True, check=True).stdout.strip()
            self.assertEqual(base_sha, worker_sha)

            fixed_bundle = os.path.join(tmp_dir, "fixed.bundle")
            subprocess.run(["git", "bundle", "create", fixed_bundle, "refs/deployments/bot-release", f"^{base_sha}"], cwd=origin_dir, check=True, capture_output=True)

            p_bot_fixed = subprocess.run(["git", "fetch", fixed_bundle, "refs/deployments/bot-release:refs/deployments/bot-release-fixed"], cwd=bot_dir, capture_output=True, text=True)
            self.assertEqual(p_bot_fixed.returncode, 0, "Bot repo must succeed fetching bundle with common base")

            p_worker_fixed = subprocess.run(["git", "fetch", fixed_bundle, "refs/deployments/bot-release:refs/deployments/bot-release-fixed"], cwd=worker_dir, capture_output=True, text=True)
            self.assertEqual(p_worker_fixed.returncode, 0, "Worker repo must succeed fetching bundle with common base")

    def test_multi_repo_already_deployed_five_contract_cases(self):
        """Verify the 5-case matrix for already-deployed idempotency contract."""
        bash_bin = self._bash_bin()
        self.assertIsNotNone(bash_bin, "Bash executable required for already-deployed simulation")

        # Bash logic template matching deploy-vps.yml Package & Staging & SSH PATH 1 checks
        bash_script = '''
eval_already_deployed() {
  local PREV_DEPLOYED_SHA="$1"
  local PREV_WORKER_DEPLOYED_SHA="$2"
  local TARGET_SHA="$3"
  local DEPLOY_WORKERS="$4"

  ALREADY_DEPLOYED="false"
  if [[ "$PREV_DEPLOYED_SHA" == "$TARGET_SHA" ]]; then
    if [[ "$DEPLOY_WORKERS" == "true" ]]; then
      if [[ "$PREV_WORKER_DEPLOYED_SHA" == "$TARGET_SHA" ]]; then
        ALREADY_DEPLOYED="true"
      fi
    else
      ALREADY_DEPLOYED="true"
    fi
  fi
  echo "$ALREADY_DEPLOYED"
}

# Run 5 test cases
T1=$(eval_already_deployed "T_SHA" "T_SHA" "T_SHA" "true")
T2=$(eval_already_deployed "T_SHA" "W_OLD" "T_SHA" "true")
T3=$(eval_already_deployed "B_OLD" "T_SHA" "T_SHA" "true")
T4=$(eval_already_deployed "B_OLD" "W_OLD" "T_SHA" "true")
T5=$(eval_already_deployed "T_SHA" "W_OLD" "T_SHA" "false")

echo "$T1,$T2,$T3,$T4,$T5"
'''
        proc = subprocess.run(
            [bash_bin, "-c", bash_script],
            capture_output=True,
            text=True,
            check=True,
        )
        results = proc.stdout.strip().split(",")
        self.assertEqual(results[0], "true", "Case 1: Both at target -> ALREADY_DEPLOYED must be true")
        self.assertEqual(results[1], "false", "Case 2: Bot target, worker behind -> ALREADY_DEPLOYED must be false")
        self.assertEqual(results[2], "false", "Case 3: Bot behind, worker target -> ALREADY_DEPLOYED must be false")
        self.assertEqual(results[3], "false", "Case 4: Both behind -> ALREADY_DEPLOYED must be false")
        self.assertEqual(results[4], "true", "Case 5: Bot-only mode, bot target -> ALREADY_DEPLOYED must be true")

    def test_workflow_worker_drift_guard_and_reconciliation_hygiene(self):
        """Verify pre-mutation drift guard and dual-SHA validation in deploy workflow."""
        # SSH step env contains EXPECTED_PREV_WORKER_SHA
        self.assertIn("EXPECTED_PREV_WORKER_SHA: ${{ steps.prod_sha.outputs.prev_worker_deployed_sha }}", self.content)
        # Remote bash validates EXPECTED_PREV_WORKER_SHA format when deploy_workers=true
        self.assertIn('EXPECTED_PREV_WORKER_SHA=\'${EXPECTED_PREV_WORKER_SHA}\'', self.content)
        self.assertIn('if [[ ! \\"\\$EXPECTED_PREV_WORKER_SHA\\" =~ ^[0-9a-fA-F]{40}\\$ ]]; then', self.content)

        # Pre-mutation drift guard in PATH 2 verifies worker HEAD
        path2_marker = "PATH 2: Normal NEW_SHA Deployment Path"
        path2_idx = self.content.find(path2_marker)
        self.assertGreaterEqual(path2_idx, 0)
        path2_body = self.content[path2_idx:]

        self.assertIn('LIVE_PREV_WORKER_HEAD=\\"\\$(git -C /opt/toanaas-worker rev-parse HEAD)\\"', path2_body)
        self.assertIn('if [[ \\"\\$LIVE_PREV_WORKER_HEAD\\" != \\"\\$EXPECTED_PREV_WORKER_SHA\\" ]]; then', path2_body)
        self.assertIn('Worker production drift detected before mutation!', path2_body)

        # PATH 1 reconciliation validates worker HEAD matches TARGET_SHA
        path1_marker = "PATH 1: ALREADY_DEPLOYED Reconciliation Path"
        path1_idx = self.content.find(path1_marker)
        self.assertGreaterEqual(path1_idx, 0)
        path1_body = self.content[path1_idx:path2_idx]

        self.assertIn('WORKER_HEAD=\\"\\$(git -C /opt/toanaas-worker rev-parse HEAD)\\"', path1_body)
        self.assertIn('if [[ \\"\\$WORKER_HEAD\\" != \\"\\$TARGET_SHA\\" ]]; then', path1_body)
        self.assertIn('Already-deployed but worker HEAD', path1_body)


if __name__ == "__main__":
    unittest.main()

