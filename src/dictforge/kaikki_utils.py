import re
from datetime import datetime

# Aliases: user input -> Kaikki language names
ALIASES = {
    # South Slavic
    "sr": "Serbo-Croatian",
    "serbian": "Serbian",
    "srpski": "Serbian",
    "sc": "Serbo-Croatian",
    "serbo-croatian": "Serbo-Croatian",
    "hbs": "Serbo-Croatian",
    "hr": "Croatian",
    "croatian": "Croatian",
    "hrvatski": "Croatian",
    # English / Russian (no non-English text in code comments/strings)
    "en": "English",
    "eng": "English",
    "english": "English",
    "ru": "Russian",
    "rus": "Russian",
    "russian": "Russian",
}

# Display metadata for title/shortname (native names kept ASCII where possible)
LANG_MAP = {
    "Serbo-Croatian": ("sr", "Srpsko-hrvatski"),
    "Serbian": ("sr", "Srpski"),
    "Croatian": ("hr", "Hrvatski"),
    "English": ("en", "English"),
    "Russian": ("ru", "Russian"),
}


def normalize_input_name(name: str) -> str:
    """Collapse user input aliases to canonical Kaikki language names."""
    if not name:
        return name
    key = re.sub(r"\s+", " ", name.strip().lower())
    return ALIASES.get(key, name.strip())


def lang_meta(kaikki_name: str) -> tuple[str, str]:
    """Return ISO code and human-readable name for a Kaikki language label."""
    iso2, native = LANG_MAP.get(kaikki_name, (kaikki_name.lower()[:2], kaikki_name))
    return iso2, native


def make_defaults(in_lang_kaikki: str, out_lang_kaikki: str) -> dict[str, str]:
    """Generate default metadata (title, codes, output dir) for CLI invocations."""
    in_code, in_native = lang_meta(in_lang_kaikki)
    out_code, out_native = lang_meta(out_lang_kaikki)
    today = datetime.utcnow().strftime("%Y%m%d")
    title = f"{in_native} → {out_native} (andgineer/dictforge)"
    short = {
        ("sr", "en"): "SR→EN",
        ("sr", "ru"): "SR→RU",
        ("hr", "en"): "HR→EN",
        ("hr", "ru"): "HR→RU",
    }.get((in_code, out_code), f"{in_code.upper()}→{out_code.upper()}")
    outdir = f"./build/{in_code}-{out_code}-{today}"
    return {
        "title": title,
        "shortname": short,
        "outdir": outdir,
        "in_code": in_code,
        "out_code": out_code,
    }
