#!/usr/bin/env python3
import sys
import os
import re

REQUIRED_FIELDS = [
    'version', 'task_id', 'repository', 'branch', 'base_sha', 'head_sha',
    'phase', 'goal', 'scope', 'acceptance', 'tests', 'evidence',
    'decisions', 'blockers', 'owner_gates', 'next_action', 'updated_at'
]

VALID_PHASES = ['READ', 'CONTRACT', 'BUILD', 'REVIEW', 'VERIFY', 'REPORT', 'LEARN']

FORBIDDEN_PATTERNS = [
    r'sk-[a-zA-Z0-9]{20,}',
    r'ghp_[a-zA-Z0-9]{20,}',
    r'bearer\s+[a-zA-Z0-9_\-\.]+',
    r'private_key',
    r'BEGIN RSA PRIVATE KEY',
    r'thought:',
    r'thinking:',
    r'chain_of_thought',
]

def validate_state_file(filepath):
    if not os.path.exists(filepath):
        return False, f'File not found: {filepath}'
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    for pat in FORBIDDEN_PATTERNS:
        if re.search(pat, content, re.IGNORECASE):
            return False, f'Forbidden secret/CoT pattern matched: {pat}'

    for field in REQUIRED_FIELDS:
        if f'{field}:' not in content:
            return False, f'Missing required field: {field}'

    phase_match = re.search(r'phase:\s*["\x27]?([A-Z]+)["\x27]?', content)
    if not phase_match:
        return False, 'Could not parse phase field'
    phase = phase_match.group(1)
    if phase not in VALID_PHASES:
        return False, f'Invalid phase {phase}. Must be one of {VALID_PHASES}'

    return True, 'Task state file is valid and compliant!'

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print('Usage: python validate_task_state.py <path_to_state_yaml>')
        sys.exit(1)
    ok, msg = validate_state_file(sys.argv[1])
    print(msg)
    sys.exit(0 if ok else 1)
