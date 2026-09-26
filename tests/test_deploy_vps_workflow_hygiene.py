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


class TestDeployVpsWorkflowHygiene(unittest.TestCase):
    def setUp(self):
        self.assertTrue(os.path.isfile(WORKFLOW_PATH), f"Workflow file not found: {WORKFLOW_PATH}")
        with open(WORKFLOW_PATH, "r", encoding="utf-8") as f:
            self.content = f.read()

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
        """6. Workflow fails closed on deployed-SHA drift in normal path."""
        self.assertIn("EXPECTED_PREV_SHA", self.content)
        self.assertIn('if [[ \\"\\$PREV_HEAD\\" != \\"\\$EXPECTED_PREV_SHA\\" ]]; then', self.content)
        self.assertIn("Production drift detected", self.content)

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


if __name__ == "__main__":
    unittest.main()

