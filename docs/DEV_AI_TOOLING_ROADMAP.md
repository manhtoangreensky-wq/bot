# Dev AI Tooling Roadmap

## Roles

- ChatGPT: system architect, task planner, sales strategy
- Codex: primary implementation agent
- GitHub Copilot: IDE/GitHub coding assistant, small fixes, PR review, autocomplete
- Cursor: coding workspace
- Claude: architecture/code review
- Gemini: secondary planning/review

## Copilot Usage

- Use Copilot for IDE suggestions, PR review, small code fixes, documentation help.
- Do not expose repo secrets.
- Do not let Copilot modify production billing/PayOS without review.
- Every Copilot change must pass:

```bash
python -m py_compile bot.py
```

- PayOS/billing changes require manual review.

## Workflow

1. ChatGPT writes task.
2. Codex implements.
3. Copilot helps review/small fixes.
4. Human checks git diff.
5. Run tests.
6. Commit/push.
