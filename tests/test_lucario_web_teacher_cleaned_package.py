from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path


CANDIDATE_MAIN = Path("artifacts/submission_lucario_web_teacher_cleaned/main.py")


def _load_main_module():
    spec = importlib.util.spec_from_file_location("lucario_web_teacher_cleaned_main_under_test", CANDIDATE_MAIN)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _pop_runtime_modules() -> None:
    for name in list(sys.modules):
        if name == "cg" or name.startswith("cg.") or name == "policy_agent":
            sys.modules.pop(name)


def test_lazy_policy_import_survives_package_path_reset():
    module = _load_main_module()
    package_dir = str(CANDIDATE_MAIN.parent.resolve())

    assert len(module.agent({}, None)) == 60

    while package_dir in sys.path:
        sys.path.remove(package_dir)
    _pop_runtime_modules()

    policy_module = module._load_policy_module()

    assert callable(policy_module.agent)
    assert package_dir in sys.path


def test_raw_exec_without_file_can_lazy_load_policy_module():
    code = (
        "import sys\n"
        "from pathlib import Path\n"
        f"main_path = Path({str(CANDIDATE_MAIN.resolve())!r})\n"
        "package_dir = str(main_path.parent)\n"
        "while package_dir in sys.path:\n"
        "    sys.path.remove(package_dir)\n"
        "for name in list(sys.modules):\n"
        "    if name == 'cg' or name.startswith('cg.') or name == 'policy_agent':\n"
        "        del sys.modules[name]\n"
        "env = {'__name__': 'lucario_web_teacher_raw_exec_under_test'}\n"
        "exec(compile(main_path.read_text(encoding='utf-8'), str(main_path), 'exec'), env)\n"
        "assert len(env['agent']({}, None)) == 60\n"
        "while package_dir in sys.path:\n"
        "    sys.path.remove(package_dir)\n"
        "for name in list(sys.modules):\n"
        "    if name == 'cg' or name.startswith('cg.') or name == 'policy_agent':\n"
        "        del sys.modules[name]\n"
        "policy_module = env['_load_policy_module']()\n"
        "assert callable(policy_module.agent)\n"
        "assert package_dir in sys.path\n"
    )

    completed = subprocess.run(["python", "-c", code], capture_output=True, text=True)

    assert completed.returncode == 0, completed.stderr + completed.stdout
