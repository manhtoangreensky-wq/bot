import time
import pytest
from services import security_defense_shield as sds


def test_layer1_input_sanitization_and_injection_defense():
    # 1. Null byte removal
    malicious_null = "prompt_test\x00_drop_table"
    clean = sds.sanitize_text_input(malicious_null)
    assert "\x00" not in clean
    assert clean == "prompt_test_drop_table"

    # 2. Control characters removal
    malicious_ctrl = "Hello\x07\x08\x1bWorld\x7f!"
    clean_ctrl = sds.sanitize_text_input(malicious_ctrl)
    assert "\x07" not in clean_ctrl
    assert "\x1b" not in clean_ctrl
    assert "\x7f" not in clean_ctrl
    assert "HelloWorld" in clean_ctrl.replace(" ", "")

    # 3. Detection of SQL / Command injection patterns
    assert sds.is_malicious_prompt_payload("1; UNION SELECT * FROM users--") is True
    assert sds.is_malicious_prompt_payload("DROP DATABASE toandaas_db;") is True
    assert sds.is_malicious_prompt_payload("test {{7*7}} template") is True
    assert sds.is_malicious_prompt_payload("normal video editing prompt for tiktok") is False


def test_layer2_file_upload_integrity_and_magic_bytes():
    # 1. Path traversal elimination
    unsafe_filename = "../../../etc/passwd.mp4"
    safe = sds.sanitize_filename(unsafe_filename)
    assert ".." not in safe
    assert "/" not in safe
    assert "\\" not in safe
    assert safe == "passwd.mp4"

    # 2. Dangerous executable extension rejection
    assert sds.is_safe_upload_extension("malware.exe") is False
    assert sds.is_safe_upload_extension("script.sh") is False
    assert sds.is_safe_upload_extension("shell.php") is False
    assert sds.is_safe_upload_extension("virus.bat") is False
    assert sds.is_safe_upload_extension("payload.py") is False

    # 3. Safe media extension acceptance
    assert sds.is_safe_upload_extension("my_clip.mp4") is True
    assert sds.is_safe_upload_extension("photo.jpg") is True
    assert sds.is_safe_upload_extension("artwork.png") is True

    # 4. Disguised executable payload rejection (Magic bytes MZ / ELF / Shebang)
    fake_mp4_pe = b"MZ\x90\x00\x03\x00\x00\x00\x04\x00\x00\x00" + b"A" * 50
    assert sds.validate_media_magic_bytes(fake_mp4_pe, "video") is False

    fake_jpg_elf = b"\x7fELF\x02\x01\x01\x00\x00\x00\x00\x00" + b"B" * 50
    assert sds.validate_media_magic_bytes(fake_jpg_elf, "image") is False

    # 5. Real media header validation
    real_mp4 = b"\x00\x00\x00\x20ftypmp42\x00\x00\x00\x00isommp42" + b"C" * 50
    assert sds.validate_media_magic_bytes(real_mp4, "video") is True

    real_jpg = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01" + b"D" * 50
    assert sds.validate_media_magic_bytes(real_jpg, "image") is True

    real_png = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR" + b"E" * 50
    assert sds.validate_media_magic_bytes(real_png, "image") is True


def test_layer3_anti_ssrf_and_network_boundary_shield():
    # 1. Blocking loopback & local subnets
    assert sds.is_safe_public_url("http://127.0.0.1:8080/admin") is False
    assert sds.is_safe_public_url("http://localhost/secret") is False
    assert sds.is_safe_public_url("http://10.0.0.5/api") is False
    assert sds.is_safe_public_url("http://192.168.1.1/router") is False
    assert sds.is_safe_public_url("http://172.16.0.10/database") is False

    # 2. Blocking Cloud Instance Metadata API (AWS / GCP / Azure token theft)
    assert sds.is_safe_public_url("http://169.254.169.254/latest/meta-data/") is False
    assert sds.is_safe_public_url("http://metadata.google.internal/computeMetadata/v1/") is False

    # 3. Blocking non-HTTP schemes
    assert sds.is_safe_public_url("file:///etc/passwd") is False
    assert sds.is_safe_public_url("gopher://127.0.0.1:70") is False
    assert sds.is_safe_public_url("ftp://server/data") is False

    # 4. Allowing safe public endpoints and whitelisted VPS gateway
    assert sds.is_safe_public_url("https://api.shopaikey.com/v1/video") is True
    assert sds.is_safe_public_url("https://api.key4u.shop/v1/task") is True
    assert sds.is_safe_public_url("https://tg.toanaas.vn/healthz") is True


def test_layer4_anti_flood_rate_limiter():
    limiter = sds.SlidingWindowRateLimiter(max_requests=5, window_seconds=1.0)
    user_key = "user_9999"

    # First 5 requests must be allowed
    for _ in range(5):
        assert limiter.allow(user_key) is True

    # 6th request within 1.0s window must be blocked (Flood defense)
    assert limiter.allow(user_key) is False

    # Different user must not be blocked
    assert limiter.allow("user_8888") is True


def test_layer5_crash_resilience_and_system_status():
    @sds.safe_guard_boundary(fallback_return={"ok": False, "protected": True})
    def risky_operation():
        raise ZeroDivisionError("Unexpected runtime disaster")

    result = risky_operation()
    assert result == {"ok": False, "protected": True}

    status = sds.system_security_status()
    assert status["status"] == "active"
    assert status["layers"]["layer1_input_sanitization"] == "enabled"
    assert status["layers"]["layer2_magic_bytes_integrity"] == "enabled"
    assert status["layers"]["layer3_anti_ssrf_boundary"] == "enabled"
    assert status["layers"]["layer4_anti_flood_limiter"] == "enabled"
    assert status["layers"]["layer5_crash_resilience_shield"] == "enabled"
