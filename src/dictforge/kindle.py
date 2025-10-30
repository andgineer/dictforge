from __future__ import annotations

KINDLE_SUPPORTED_LANGS = {
    "af",
    "sq",
    "ar",
    "ar-dz",
    "ar-bh",
    "ar-eg",
    "ar-iq",
    "ar-jo",
    "ar-kw",
    "ar-lb",
    "ar-ly",
    "ar-ma",
    "ar-om",
    "ar-qa",
    "ar-sa",
    "ar-sy",
    "ar-tn",
    "ar-ae",
    "ar-ye",
    "hy",
    "az",
    "eu",
    "be",
    "bn",
    "bg",
    "ca",
    "zh",
    "zh-hk",
    "zh-cn",
    "zh-sg",
    "zh-tw",
    "hr",
    "cs",
    "da",
    "nl",
    "nl-be",
    "en",
    "en-au",
    "en-bz",
    "en-ca",
    "en-ie",
    "en-jm",
    "en-nz",
    "en-ph",
    "en-za",
    "en-tt",
    "en-gb",
    "en-us",
    "en-zw",
    "et",
    "fo",
    "fa",
    "fi",
    "fr",
    "fr-be",
    "fr-ca",
    "fr-lu",
    "fr-mc",
    "fr-ch",
    "ka",
    "de",
    "de-at",
    "de-li",
    "de-lu",
    "de-ch",
    "el",
    "gu",
    "he",
    "hi",
    "hu",
    "is",
    "id",
    "it",
    "it-ch",
    "ja",
    "kn",
    "kk",
    "x-kok",
    "ko",
    "lv",
    "lt",
    "mk",
    "ms",
    "ms-bn",
    "ml",
    "mt",
    "mr",
    "ne",
    "no",
    "no-bok",
    "no-nyn",
    "or",
    "pl",
    "pt",
    "pt-br",
    "pa",
    "rm",
    "ro",
    "ro-mo",
    "ru",
    "ru-mo",
    "sz",
    "sa",
    "sr-latn",
    "sk",
    "sl",
    "sb",
    "es",
    "es-ar",
    "es-bo",
    "es-cl",
    "es-co",
    "es-cr",
    "es-do",
    "es-ec",
    "es-sv",
    "es-gt",
    "es-hn",
    "es-mx",
    "es-ni",
    "es-pa",
    "es-py",
    "es-pe",
    "es-pr",
    "es-uy",
    "es-ve",
    "sx",
    "sw",
    "sv",
    "sv-fi",
    "ta",
    "tt",
    "te",
    "th",
    "ts",
    "tn",
    "tr",
    "uk",
    "ur",
    "uz",
    "vi",
    "xh",
    "zu",
}


class KindleBuildError(RuntimeError):
    """Raised when Kindle-specific tooling fails or receives invalid configuration."""


def kindle_lang_code(code: str | None, override: str | None = None) -> str:
    """Return the Kindle locale code for ``code`` or the validated ``override``."""
    if override:
        normalized_override = override.lower()
        if normalized_override in KINDLE_SUPPORTED_LANGS:
            return normalized_override
        raise KindleBuildError(
            (
                f"Kindle language override '{override}' is not supported by Kindle. "
                "Check the supported list and pick a valid code."
            ),
        )

    if not code:
        return "en"

    normalized = code.lower()
    if normalized in KINDLE_SUPPORTED_LANGS:
        return normalized

    overrides = {
        "sr": "hr",
        "en": "en-us",
    }
    normalized = overrides.get(normalized, normalized)

    if normalized == "en":
        return "en-us"

    return normalized if normalized in KINDLE_SUPPORTED_LANGS else "en"
