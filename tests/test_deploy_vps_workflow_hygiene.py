#!/usr/bin/env python3
"""
Unit tests for Bot VPS deployment workflow hygiene:
- Incremental bundle generation excluding PREV_DEPLOYED_SHA
- Production drift guard
- Staging directory cleanup post transaction commit
- Rollback backup retention (retaining exactly 2 newest)
- Preserving non-deploy entries
- Preserving staging on failure
- Verifying no automatic Git gc/prune/repack is added
"""

import os
import re
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
        # Check step output assignment
        self.assertRegex(self.content, r'echo "prev_deployed_sha=\$PREV_SHA" >> "\$GITHUB_OUTPUT"')

    def test_incremental_bundle_excludes_previous_sha(self):
        """2. Bundle command excludes previous deployed SHA and validates ancestry."""
        self.assertIn("git merge-base --is-ancestor", self.content)
        self.assertIn("PREV_DEPLOYED_SHA", self.content)
        # Check bundle creation syntax: refs/deployments/bot-release "^${PREV_DEPLOYED_SHA}"
        bundle_pattern = r'git bundle create "[^"]*release\.bundle" refs/deployments/bot-release "\^(\$\{PREV_DEPLOYED_SHA\}|\$PREV_DEPLOYED_SHA)"'
        self.assertRegex(self.content, bundle_pattern)
        # Ensure it verifies bundle and fails closed if ancestry fails
        self.assertIn("git bundle verify", self.content)

    def test_drift_guard_stops_on_mismatch(self):
        """3. Workflow fails closed on deployed-SHA drift."""
        self.assertIn("EXPECTED_PREV_SHA", self.content)
        self.assertIn('if [[ \\"\\$PREV_HEAD\\" != \\"\\$EXPECTED_PREV_SHA\\" ]]; then', self.content)
        self.assertIn("Production drift detected", self.content)

    def test_staging_cleanup_post_transaction_commit_only(self):
        """4. Successful staging cleanup occurs only after transaction commit."""
        commit_idx = self.content.find("commit_product_video_release_transaction")
        cleanup_idx = self.content.find("Cleaning up Remote Staging Directory")
        self.assertNotEqual(commit_idx, -1, "commit_product_video_release_transaction step missing")
        self.assertNotEqual(cleanup_idx, -1, "Staging cleanup step missing")
        self.assertGreater(cleanup_idx, commit_idx, "Staging cleanup must occur AFTER commit_product_video_release_transaction")

    def test_cleanup_targets_exact_target_sha_staging_path(self):
        """5. Cleanup targets the exact target-SHA staging path without wildcards."""
        self.assertIn('CLEANUP_TARGET=\\"/tmp/deploy-bot-\\$TARGET_SHA\\"', self.content)
        self.assertIn('rm -rf \\"\\$CLEANUP_TARGET\\"', self.content)
        # Ensure no wildcard rm -rf /tmp/deploy-bot-* is present
        self.assertNotIn("rm -rf /tmp/deploy-bot-*", self.content)
        self.assertNotIn('rm -rf "$STAGING_DIR"/*', self.content)

    def test_rollback_pruning_logic_retains_two_newest(self):
        """6. Rollback pruning retains exactly two newest valid deploy backups."""
        self.assertIn("Retaining 2 Newest", self.content)
        self.assertIn("VALID_BACKUPS", self.content)
        self.assertIn('VALID_BACKUPS+=(\\"\\$bpath\\")', self.content)
        self.assertIn('for ((i=2; i<\\${#VALID_BACKUPS[@]}; i++)); do', self.content)

    def test_non_matching_delete_entries_untouched(self):
        """7. Non-matching files/directories in delete/ are not pruning targets."""
        # Check strict regex pattern for deploy backups: deploy-<40hex>-<14digits>
        pattern = r'\^deploy-\[0-9a-fA-F\]\{40\}-\[0-9\]\{14\}\\\$'
        self.assertRegex(self.content, pattern)

    def test_no_automatic_git_maintenance(self):
        """8. Workflow does not introduce automatic Git gc/prune/repack/reflog expire."""
        forbidden_commands = [
            "git gc",
            "git prune",
            "git repack",
            "reflog expire",
            "git reflog expire",
        ]
        for cmd in forbidden_commands:
            self.assertNotIn(cmd, self.content, f"Forbidden automatic git maintenance command found: {cmd}")

    def test_failure_preserves_staging_diagnostics(self):
        """9. Failure path preserves current staging for diagnostics."""
        # Ensure trap on ERR logs preservation message
        self.assertIn("trap ", self.content)
        self.assertIn("preserving staging directory for diagnostics", self.content)
        self.assertIn("ERR", self.content)

    def test_simulation_of_rollback_retention_regex(self):
        """Empirical regex simulation: verify only valid deploy directories match."""
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
