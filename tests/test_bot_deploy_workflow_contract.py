from pathlib import Path


WORKFLOW = Path(".github/workflows/deploy-vps.yml").read_text(encoding="utf-8")
REMOTE_CONTRACT = WORKFLOW.replace(r'\"', '"').replace(r"\$", "$")


def test_deploy_does_not_pull_private_repo_or_mutate_worker_and_env() -> None:
    forbidden = (
        "git pull origin main",
        "git fetch origin",
        "/opt/toanaas-worker",
        "/etc/toanaas-worker.env",
        "sed -i",
        "toanaas-worker-owner-product-video.service",
        "toanaas-video-edit-worker.service",
        "rm ",
        "git reset --hard",
        "git clean",
    )

    for fragment in forbidden:
        assert fragment not in WORKFLOW


def test_runner_packages_verified_release_artifacts() -> None:
    required = (
        "fetch-depth: 0",
        "git archive",
        "release.tar",
        "refs/deployments/bot-release",
        "release.bundle",
        "git bundle list-heads",
        '!= "$GITHUB_SHA"',
        "checksums.sha256",
        "sha256sum release.tar release.bundle",
    )

    for fragment in required:
        assert fragment in REMOTE_CONTRACT


def test_runner_copies_all_artifacts_to_sha_scoped_staging() -> None:
    assert 'REMOTE_STAGING="/tmp/deploy-bot-${TARGET_SHA}"' in WORKFLOW
    assert "scp " in WORKFLOW
    assert '"${RELEASE_DIR}/release.tar"' in WORKFLOW
    assert '"${RELEASE_DIR}/release.bundle"' in WORKFLOW
    assert '"${RELEASE_DIR}/checksums.sha256"' in WORKFLOW
    assert '"$VPS_USER@$VPS_HOST:${REMOTE_STAGING}/"' in WORKFLOW


def test_vps_validates_target_and_backs_up_tracked_source() -> None:
    required = (
        "^[0-9a-fA-F]{40}",
        "sha256sum -c checksums.sha256",
        "WEBAPP_DIR='/opt/toanaas/bot'",
        'BACKUP_DIR="$WEBAPP_DIR/delete/deploy-$TARGET_SHA-$UTC_TIMESTAMP"',
        'git ls-files > "$BACKUP_DIR/tracked-files.txt"',
        '"$BACKUP_DIR/manifest.txt"',
    )

    for fragment in required:
        assert fragment in REMOTE_CONTRACT


def test_vps_quarantines_removed_tracked_files_without_deletion() -> None:
    required = (
        'git ls-tree -r --name-only "$TARGET_SHA"',
        "removed-files.txt",
        '"$BACKUP_DIR/removed/',
        'mv -- "$WEBAPP_DIR/$rel_path" "$BACKUP_DIR/removed/$rel_path"',
    )

    for fragment in required:
        assert fragment in REMOTE_CONTRACT


def test_vps_applies_exact_bundle_sha_with_compare_and_swap() -> None:
    required = (
        "refs/deployments/bot-release:refs/deployments/bot-release",
        'git cat-file -e "$TARGET_SHA^{commit}"',
        'tar -xf "$STAGING_DIR/release.tar" -C "$WEBAPP_DIR"',
        'git update-ref refs/heads/main "$TARGET_SHA" "$PREV_HEAD"',
        'git update-ref refs/remotes/origin/main "$TARGET_SHA"',
        'git read-tree "$TARGET_SHA"',
        'if [[ "$CURRENT_SHA" != "$TARGET_SHA" ]]',
        "git diff --exit-code -- . ':(exclude)delete/**'",
    )

    for fragment in required:
        assert fragment in REMOTE_CONTRACT


def test_deploy_restarts_only_bot_and_verifies_nginx_and_json_health() -> None:
    assert WORKFLOW.count("systemctl restart") == 1
    assert "systemctl restart toanaas-bot.service" in WORKFLOW
    assert "systemctl is-active toanaas-bot.service" in WORKFLOW
    assert "systemctl is-active nginx.service" in WORKFLOW
    assert "http://127.0.0.1:8080/health" in WORKFLOW
    assert "for attempt in {1..120}" in WORKFLOW
    assert "sleep 2" in WORKFLOW
    assert 'data.get("status") == "ok"' in REMOTE_CONTRACT
