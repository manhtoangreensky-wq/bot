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

    def test_rollback_pruning_logic_retains_two_newest(self):
        """9. Rollback pruning retains exactly two newest valid deploy backups."""
        self.assertIn("Retaining 2 Newest", self.content)
        self.assertIn("VALID_BACKUPS", self.content)
        self.assertIn('VALID_BACKUPS+=(\\"\\$bpath\\")', self.content)
        self.assertIn('for ((i=2; i<\\${#VALID_BACKUPS[@]}; i++)); do', self.content)

    def test_non_matching_delete_entries_untouched(self):
        """10. Non-matching files/directories in delete/ are not pruning targets."""
        pattern = r'\^deploy-\[0-9a-fA-F\]\{40\}-\[0-9\]\{14\}\\\$'
        self.assertRegex(self.content, pattern)

    def test_no_automatic_git_maintenance(self):
        """11. Workflow does not introduce automatic Git gc/prune/repack/reflog expire."""
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
        """12. Failure path only prints preserving staging if staging directory exists."""
        self.assertIn("trap 'if [[ -d \\\"\\$STAGING_DIR\\\" ]]; then echo \\\"[DEPLOY_FAILURE] Deployment failed; preserving staging directory for diagnostics: \\$STAGING_DIR\\\" >&2; fi' ERR", self.content)

    def test_simulation_of_rollback_retention_regex(self):
        """13. Empirical regex simulation: verify only valid deploy directories match."""
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
