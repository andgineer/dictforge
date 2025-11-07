import os
from pathlib import Path
from typing import Any

try:
    import tomllib  # py>=3.11
except ModuleNotFoundError:
    import tomli as tomllib  # type: ignore[no-redef]  # py 3.9–3.10

DEFAULTS = {
    "default_out_lang": "English",  # changed via `wikidict-kindle init`
    "merge_in_langs": "",  # e.g. "Serbian,Croatian"
    "include_pos": False,
    "try_fix_inflections": False,
    "cache_dir": ".wiktex-cache",
    "kindlegen_path": "",
}


def config_dir() -> Path:
    """Return the per-user configuration directory for DictForge settings."""
    cfg_home = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return cfg_home / "wikidict-kindle"


def config_path() -> Path:
    """Return the full filesystem path to the DictForge TOML config file."""
    return config_dir() / "config.toml"


def load_config() -> dict[str, Any]:
    """Load configuration values, overlaying user overrides on top of defaults."""
    path = config_path()
    if path.exists():
        with path.open("rb") as f:
            data = tomllib.load(f) or {}
        out = DEFAULTS.copy()
        out.update(data)
        return out
    return DEFAULTS.copy()


def save_config(data: dict[str, Any]) -> None:
    """Persist configuration values to TOML without relying on extra deps."""
    # minimal TOML writer (no extra deps for writing)
    dir_ = config_dir()
    dir_.mkdir(parents=True, exist_ok=True)
    lines = []
    for k, v in data.items():
        if isinstance(v, bool):
            val = "true" if v else "false"
        elif isinstance(v, int | float):
            val = str(v)
        else:
            s = str(v).replace("\\", "\\\\").replace('"', '\\"')
            val = f'"{s}"'
        lines.append(f"{k} = {val}")
    content = "\n".join(lines) + "\n"
    with config_path().open("w", encoding="utf-8") as f:
        f.write(content)
