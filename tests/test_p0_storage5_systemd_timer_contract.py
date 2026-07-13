from pathlib import Path


REPO = Path(__file__).resolve().parents[1]


def test_vps_installer_has_exact_backend_local_timer_contract():
    installer = (REPO / "scripts" / "install_vps_storage_maintenance_timers.sh").read_text(encoding="utf-8")
    assert "TOANAAS_APP_DIR:-/opt/toanaas-worker" in installer
    assert "WorkingDirectory=$APP_DIR" in installer
    assert "storage_maintenance.py" in installer
    assert "OnCalendar=*-*-* 12:00:00 Asia/Ho_Chi_Minh" in installer
    assert "OnCalendar=Sun *-*-* 03:30:00 Asia/Ho_Chi_Minh" in installer
    assert "Persistent=true" in installer
    assert "--backend vps --execute" in installer
    assert "--keep-backups 5 --execute" in installer
    assert "toanaas-worker" in installer
    assert "/opt/toanaas-bot" not in installer
    assert "--now" not in installer
    assert "remote" not in installer.lower()
    assert "Product Video" not in installer


def test_storage_scripts_have_no_recursive_or_remote_delete_contract():
    scripts = [
        REPO / "scripts" / "install_vps_storage_maintenance_timers.sh",
        REPO / "scripts" / "install_vps_storage_cleanup_timer.sh",
        REPO / "scripts" / "vps_storage_cleanup.sh",
        REPO / "scripts" / "vps" / "cleanup_worker_temp.sh",
    ]
    combined = "\n".join(path.read_text(encoding="utf-8") for path in scripts)
    assert "rm -rf" not in combined
    assert "rsync --delete" not in combined
    assert "find " not in combined
    assert "ssh " not in combined
    assert "systemctl enable --now" not in combined
