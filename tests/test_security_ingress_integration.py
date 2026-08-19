import unittest
import os, sys

sys.path.insert(0, r"C:\Users\toann\Documents\Codex\2026-08-16\codex-native2-app-asdk-app-6a81c45077b08191a008f1138b563004-3\work\video-route1-ai-real")

from services import security_defense_shield as sds

class TestSecurityIngressIntegration(unittest.TestCase):
    def test_legitimate_coding_prompts_preserved(self):
        prompts = [
            "Tạo video hướng dẫn lập trình Python với hàm def hello(): print('Hi')",
            "Viết cho tôi đoạn code SQL: SELECT id, name FROM users WHERE active = 1 ORDER BY created_at DESC;",
            "Làm thế nào để chạy command bash: git add . && git commit -m 'feat: add video' && git push",
            "Mô tả template Jinja2: <div>{{ user.name }}</div>",
            "Viết prompt cho AI: A cinematic shot of a cyberpunk city at night, 8k resolution, photorealistic"
        ]
        for p in prompts:
            cleaned = sds.sanitize_text_input(p)
            self.assertEqual(cleaned, p.strip(), f"Legitimate prompt must not be altered: {p}")
            self.assertFalse(sds.is_malicious_prompt_payload(p), f"Legitimate prompt must not be flagged: {p}")

    def test_malicious_payload_detection(self):
        bad_payloads = [
            "DROP DATABASE toandaas_db;",
            "1; UNION SELECT username, password FROM admin_users--",
            "{{7*7}} SSTI probe payload",
            "text with null byte \x00 in the middle"
        ]
        for p in bad_payloads:
            self.assertTrue(sds.is_malicious_prompt_payload(p), f"Must detect payload: {p}")

    def test_file_upload_security(self):
        # Traversal
        self.assertEqual(sds.sanitize_filename("../../etc/passwd"), "passwd")
        self.assertEqual(sds.sanitize_filename("C:\\Windows\\System32\\cmd.exe"), "cmd.exe")
        # Extension
        self.assertTrue(sds.is_safe_upload_extension("my_video.mp4"))
        self.assertTrue(sds.is_safe_upload_extension("photo.jpg"))
        self.assertFalse(sds.is_safe_upload_extension("script.sh"))
        self.assertFalse(sds.is_safe_upload_extension("virus.exe"))
        self.assertFalse(sds.is_safe_upload_extension("exploit.php"))
        self.assertFalse(sds.is_safe_upload_extension("macro.docm"))
        # Magic bytes
        self.assertTrue(sds.validate_media_magic_bytes(b"\x00\x00\x00\x18ftypmp42", "video"))
        self.assertTrue(sds.validate_media_magic_bytes(b"\xff\xd8\xff\xe0", "image"))
        self.assertFalse(sds.validate_media_magic_bytes(b"MZ\x90\x00\x03\x00", "video"))
        self.assertFalse(sds.validate_media_magic_bytes(b"\x7fELF\x02\x01", "image"))

    def test_anti_ssrf_public_url_filtering(self):
        blocked = [
            "http://127.0.0.1:8000/api",
            "http://localhost:3000",
            "http://169.254.169.254/latest/meta-data/",
            "http://10.0.0.1/admin",
            "http://192.168.1.254",
            "http://172.16.0.10",
            "ftp://ftp.example.com/file.mp4",
            "file:///etc/passwd"
        ]
        for u in blocked:
            self.assertFalse(sds.is_safe_public_url(u), f"Must block SSRF target: {u}")

        allowed = [
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            "https://vimeo.com/123456789",
            "https://tiktok.com/@user/video/123456",
            "https://api.shopaikey.com/v1/video/status"
        ]
        for u in allowed:
            self.assertTrue(sds.is_safe_public_url(u), f"Must allow public URL: {u}")

    def test_rate_limiter_bounds(self):
        limiter = sds.SlidingWindowRateLimiter(max_requests=5, window_seconds=2)
        for _ in range(5):
            self.assertTrue(limiter.allow("user_123"))
        self.assertFalse(limiter.allow("user_123"))
        # Different user is unaffected
        self.assertTrue(limiter.allow("user_456"))

if __name__ == "__main__":
    unittest.main()
