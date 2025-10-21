from __future__ import annotations


from dictforge import kindle


def test_guess_kindlegen_path_returns_match(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr("platform.system", lambda: "Darwin")
    candidate = "/Applications/Kindle Previewer 3.app/Contents/MacOS/lib/fc/bin/kindlegen"

    monkeypatch.setattr("dictforge.kindle.Path.exists", lambda self: str(self) == candidate)

    assert kindle.guess_kindlegen_path() == candidate


def test_guess_kindlegen_path_empty_when_missing(monkeypatch) -> None:
    monkeypatch.setattr("platform.system", lambda: "Linux")
    assert kindle.guess_kindlegen_path() == ""
