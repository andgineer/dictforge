import importlib
from types import ModuleType

import pytest


@pytest.fixture
def config_module(monkeypatch, tmp_path) -> ModuleType:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    module = importlib.import_module("dictforge.config")
    return importlib.reload(module)


def test_config_dir_uses_xdg(config_module, tmp_path) -> None:
    expected = tmp_path / "xdg" / "wikidict-kindle"
    assert config_module.config_dir() == expected


def test_save_and_load_roundtrip(config_module) -> None:
    data = config_module.DEFAULTS.copy()
    data.update(
        {
            "default_out_lang": 'English "US"',
            "cache_dir": r"C:\\cache",
            "include_pos": True,
        },
    )
    config_module.save_config(data)

    config_path = config_module.config_path()
    content = config_path.read_text(encoding="utf-8")
    assert "default_out_lang =" in content
    assert "cache_dir =" in content
    assert "include_pos = true" in content

    loaded = config_module.load_config()
    assert loaded["default_out_lang"] == 'English "US"'
    assert loaded["cache_dir"] == r"C:\\cache"
    assert loaded["include_pos"] is True
