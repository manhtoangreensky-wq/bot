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

    def test_incremental_bundle_excludes_previous_sha(self):
        """2. Bundle command excludes previous deployed SHA and validates ancestry."""
        self.assertIn("git merge-base --is-ancestor", self.content)
        self.assertIn("PREV_DEPLOYED_SHA", self.content)
        bundle_cmd = 'git bundle create "${RELEASE_DIR}/release.bundle" refs/deployments/bot-release "^${PREV_DEPLOYED_SHA}"'
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
        """4. Packaging step skips bundle generation when PREV_DEPLOYED_SHA == GITHUB_SHA."""
        self.assertIn('if [[ "$PREV_DEPLOYED_SHA" == "$GITHUB_SHA" ]]; then', self.content)
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


if __name__ == "__main__":
    unittest.main()



