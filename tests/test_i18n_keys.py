import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_every_python_key_exists_in_all_locales():
    src = "\n".join(p.read_text(encoding="utf-8") for p in (ROOT / "livetranslate").rglob("*.py"))
    used = set(re.findall(r'"((?:status|errors)\.[a-z_]+)"', src))
    assert used, "no keys found"
    for loc in ("en", "zh-Hant", "ja", "ko"):
        data = json.loads((ROOT / f"ui/src/locales/{loc}.json").read_text(encoding="utf-8"))
        flat = {f"{a}.{b}" for a, v in data.items() if isinstance(v, dict) for b in v}
        assert used <= flat, (loc, used - flat)
