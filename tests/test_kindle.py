from pathlib import Path

from dictforge import kindlegen


def _mock_exists(target: str):
    normalized_target = target.replace("\\", "/")

    def _inner(self: Path) -> bool:
        actual = getattr(self, "as_posix", lambda: str(self))()
        return actual.replace("\\", "/") == normalized_target

    return _inner


def test_guess_kindlegen_path_returns_match(monkeypatch) -> None:
    monkeypatch.setattr("platform.system", lambda: "Darwin")
    candidate = "/Applications/Kindle Previewer 3.app/Contents/MacOS/lib/fc/bin/kindlegen"

    monkeypatch.setattr("dictforge.kindlegen.Path.exists", _mock_exists(candidate))

    assert kindlegen.guess_kindlegen_path() == candidate


def test_guess_kindlegen_path_windows(monkeypatch) -> None:
    monkeypatch.setattr("platform.system", lambda: "Windows")
    home = r"C:\\Users\\TestUser"
    monkeypatch.setenv("USERPROFILE", home)
    monkeypatch.delenv("HOMEPATH", raising=False)

    candidate = str(Path(home) / "AppData/Local/Amazon/Kindle Previewer 3/lib/fc/bin/kindlegen.exe")
    monkeypatch.setattr("dictforge.kindlegen.Path.exists", _mock_exists(candidate))

    result = kindlegen.guess_kindlegen_path()
    assert result.endswith("kindlegen.exe")
    assert "Kindle Previewer 3" in result


def test_guess_kindlegen_path_empty_when_missing(monkeypatch) -> None:
    monkeypatch.setattr("platform.system", lambda: "Linux")
    assert kindlegen.guess_kindlegen_path() == ""
