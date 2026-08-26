import ast
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]


def _request_params_owner():
    tree = ast.parse((ROOT / "bot.py").read_text(encoding="utf-8"))
    request_params = None
    owner = None
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "AgentDeepgram":
            for child in node.body:
                if (
                    isinstance(child, ast.Assign)
                    and any(isinstance(target, ast.Name) and target.id == "REQUEST_PARAMS" for target in child.targets)
                ):
                    request_params = ast.literal_eval(child.value)
        if isinstance(node, ast.FunctionDef) and node.name == "subdub_deepgram_request_params":
            owner = node
    assert isinstance(request_params, dict)
    assert owner is not None
    namespace = {"AgentDeepgram": SimpleNamespace(REQUEST_PARAMS=request_params)}
    ast.fix_missing_locations(owner)
    exec(compile(ast.Module(body=[owner], type_ignores=[]), "bot.py", "exec"), namespace)
    return namespace["subdub_deepgram_request_params"]


def test_diarized_asr_uses_nova3_without_changing_default_asr():
    request_params = _request_params_owner()

    default_params = request_params()
    diarized_params = request_params(require_diarization=True)

    assert default_params["model"] == "nova-2"
    assert "diarize_model" not in default_params
    assert diarized_params["model"] == "nova-3-general"
    assert diarized_params["diarize_model"] == "latest"
