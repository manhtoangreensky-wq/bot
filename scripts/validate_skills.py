#!/usr/bin/env python3
import sys
import os
import re
import hashlib

def sha256_file(filepath):
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()

def validate_skill_dir(skill_dir):
    skill_md = os.path.join(skill_dir, "SKILL.md")
    if not os.path.exists(skill_md):
        return False, f"Missing SKILL.md in {skill_dir}"
    
    with open(skill_md, "r", encoding="utf-8") as f:
        content = f.read()

    # Check frontmatter
    if not (content.startswith("---") and "---" in content[3:]):
        return False, f"Invalid YAML frontmatter in {skill_md}"

    if "name:" not in content or "description:" not in content:
        return False, f"Frontmatter missing name or description in {skill_md}"

    # Check relative links
    links = re.findall(r"\[.*?\]\((.*?)\)", content)
    for link in links:
        if link.startswith("http") or link.startswith("#"):
            continue
        target = os.path.join(skill_dir, link)
        if not os.path.exists(target):
            return False, f"Broken relative link '{link}' in {skill_md}"

    return True, f"Skill {os.path.basename(skill_dir)} is valid!"

def validate_all(canonical_dir):
    errors = []
    for item in os.listdir(canonical_dir):
        p = os.path.join(canonical_dir, item)
        if os.path.isdir(p):
            ok, msg = validate_skill_dir(p)
            print(f"[{'PASS' if ok else 'FAIL'}] {msg}")
            if not ok:
                errors.append(msg)
    return len(errors) == 0

if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else r"C:\Users\toann\Documents\Codex\2026-08-16\codex-native2-app-asdk-app-6a81c45077b08191a008f1138b563004-3\work\video-route1-ai-real\.agents\skills"
    ok = validate_all(target)
    sys.exit(0 if ok else 1)
