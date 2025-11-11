from datetime import datetime as real_datetime

from dictforge.kaikki_utils import LANG_MAP, lang_meta, make_defaults, normalize_input_name


def test_normalize_input_name_alias_and_whitespace() -> None:
    assert normalize_input_name("  sr  ") == "Serbo-Croatian"
    assert normalize_input_name("English") == "English"


def test_lang_meta_known_and_unknown() -> None:
    code, native = lang_meta("Serbo-Croatian")
    assert code == "sr"
    assert native == LANG_MAP["Serbo-Croatian"][1]

    code, native = lang_meta("Esperanto")
    assert code == "es"
    assert native == "Esperanto"


def test_make_defaults_generates_expected_fields(monkeypatch) -> None:
    class DummyDatetime:
        @classmethod
        def utcnow(cls) -> real_datetime:
            return real_datetime(2024, 1, 2)

    monkeypatch.setattr("dictforge.kaikki_utils.datetime", DummyDatetime)

    defaults = make_defaults("Serbo-Croatian", "English")
    assert defaults["title"].startswith("Srpsko-hrvatski → English")
    assert defaults["shortname"] == "SR→EN"
    assert defaults["outdir"] == "./build/sr-en-20240102"
    assert defaults["in_code"] == "sr"
    assert defaults["out_code"] == "en"
