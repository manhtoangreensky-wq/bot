import re
from pathlib import Path
from types import SimpleNamespace


BOT_SOURCE = (Path(__file__).resolve().parents[1] / "bot.py").read_text(encoding="utf-8")


def _source_function(name):
    start = BOT_SOURCE.index(f"async def {name}(")
    end = BOT_SOURCE.find("\nasync def ", start + 1)
    return BOT_SOURCE[start:] if end < 0 else BOT_SOURCE[start:end]


def _run_no_io(coroutine):
    try:
        coroutine.send(None)
    except StopIteration as completed:
        return completed.value
    coroutine.close()
    raise AssertionError("Knowledge Vault callback fixture unexpectedly yielded I/O")


class _Query:
    def __init__(self, data):
        self.data = data
        self.from_user = SimpleNamespace(id=700501)
        self.answers = []
        self.edits = []
        self.message = SimpleNamespace(reply_text=self._reply_text)

    async def answer(self, *args, **kwargs):
        self.answers.append((args, kwargs))

    async def _reply_text(self, *args, **kwargs):
        self.edits.append((args, kwargs))

    async def edit_message_text(self, *args, **kwargs):
        self.edits.append((args, kwargs))


class _Vault:
    def __init__(self):
        self.calls = []

    def get_prompt(self, prompt_id, **kwargs):
        self.calls.append(("get_prompt", prompt_id, kwargs))
        return {"id": prompt_id, "prompt_text": "fixture prompt"}

    def approve_prompt(self, prompt_id, **kwargs):
        self.calls.append(("approve_prompt", prompt_id, kwargs))
        return {"id": prompt_id, "status": "approved"}

    def approve_asset(self, asset_id, **kwargs):
        self.calls.append(("approve_asset", asset_id, kwargs))
        return {"id": asset_id, "status": "approved"}

    def search_prompt(self, **kwargs):
        return []

    def list_assets(self, **kwargs):
        return []


def _load_handler(vault, factory_calls):
    namespace = {
        "Update": object,
        "ContextTypes": SimpleNamespace(DEFAULT_TYPE=object),
        "is_admin_user": lambda _uid: True,
        "toan_knowledge_vault": lambda: (factory_calls.append("factory") or vault),
        "vault_json_block": lambda value: f"JSON:{value}",
        "vault_admin_keyboard": lambda: "ADMIN_KEYBOARD",
        "vault_prompt_list_text": lambda *args, **kwargs: "PROMPTS",
        "vault_asset_list_text": lambda *args, **kwargs: "ASSETS",
        "InlineKeyboardButton": object,
        "InlineKeyboardMarkup": object,
        "html": SimpleNamespace(escape=lambda value: str(value)),
    }
    exec(compile(_source_function("handle_knowledge_vault_callback"), "bot.py:vault", "exec"), namespace)
    return namespace["handle_knowledge_vault_callback"]


def _registered_pattern():
    match = re.search(
        r"CallbackQueryHandler\(\s*handle_knowledge_vault_callback\s*,\s*pattern\s*=\s*r(['\"])(.*?)\1\s*\)",
        BOT_SOURCE,
    )
    assert match, "Knowledge Vault callback registration is missing"
    return re.compile(match.group(2))


def test_malformed_or_out_of_range_vault_ids_alert_once_before_vault_call():
    for action in ("use", "approve_prompt", "approve_asset"):
        for item_id in ("١", "9223372036854775808", "10000000000000000000"):
            query = _Query(f"vault|{action}|{item_id}")
            assert _registered_pattern().match(query.data)
            vault = _Vault()
            factory_calls = []
            handler = _load_handler(vault, factory_calls)

            _run_no_io(handler(SimpleNamespace(callback_query=query), SimpleNamespace()))

            assert query.answers == [(("Mã kho không hợp lệ.",), {"show_alert": True})]
            assert factory_calls == []
            assert vault.calls == []


def test_valid_vault_ids_keep_one_ack_and_existing_branches():
    for action, expected_call in (
        ("use", "get_prompt"),
        ("approve_prompt", "approve_prompt"),
        ("approve_asset", "approve_asset"),
    ):
        query = _Query(f"vault|{action}|441")
        vault = _Vault()
        factory_calls = []
        handler = _load_handler(vault, factory_calls)

        _run_no_io(handler(SimpleNamespace(callback_query=query), SimpleNamespace()))

        assert query.answers == [((), {})]
        assert factory_calls == ["factory"]
        assert vault.calls[0][0] == expected_call
        assert vault.calls[0][1] == 441
