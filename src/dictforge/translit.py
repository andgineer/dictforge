"""Serbian Cyrillic/Latin transliteration."""

import unicodedata

_PAIR = {
    "dj": "ђ",
    "dž": "џ",
    "lj": "љ",
    "nj": "њ",
    "tj": "ћ",
    "đ": "ђ",
}

_LAT_TO_CYR = {
    "a": "а",
    "b": "б",
    "c": "ц",
    "č": "ч",
    "ć": "ћ",
    "d": "д",
    "đ": "ђ",
    "e": "е",
    "f": "ф",
    "g": "г",
    "h": "х",
    "i": "и",
    "j": "ј",
    "k": "к",
    "l": "л",
    "m": "м",
    "n": "н",
    "o": "о",
    "p": "п",
    "r": "р",
    "s": "с",
    "š": "ш",
    "t": "т",
    "u": "у",
    "v": "в",
    "z": "з",
    "ž": "ж",
}

_CYR_TO_LAT = {value: key for key, value in _LAT_TO_CYR.items() if len(key) == 1}
_CYR_TO_LAT.update({"ђ": "đ", "ћ": "ć", "љ": "lj", "њ": "nj", "џ": "dž"})
_CYR_TO_LAT.update({"Ђ": "Đ", "Љ": "Lj", "Њ": "Nj", "Џ": "Dž", "Ћ": "Ć"})


def lat_to_cyr(text: str) -> str:
    normalized = unicodedata.normalize("NFC", text)
    chars: list[str] = []
    i = 0
    length = len(normalized)
    while i < length:
        chunk = normalized[i : i + 2]
        lower_chunk = chunk.lower()
        if lower_chunk in ("dž", "dj", "lj", "nj"):
            converted = _PAIR.get(lower_chunk)
            if converted:
                if chunk.isupper() or chunk[0].isupper():
                    chars.append(converted.upper())
                else:
                    chars.append(converted)
                i += 2
                continue
        letter = normalized[i]
        lower = letter.lower()
        converted = _LAT_TO_CYR.get(lower)
        if converted:
            chars.append(converted.upper() if letter.isupper() else converted)
        else:
            chars.append(letter)
        i += 1
    return "".join(chars)


def cyr_to_lat(text: str) -> str:
    normalized = unicodedata.normalize("NFC", text)
    result: list[str] = []
    for letter in normalized:
        lower = letter.lower()
        base = _CYR_TO_LAT.get(lower)
        if base is None:
            result.append(letter)
            continue
        if letter.isupper():
            if lower in {"љ", "њ", "џ"}:
                result.append(base.capitalize())
            else:
                result.append(base.upper())
        else:
            result.append(base)
    return "".join(result)


__all__ = ["lat_to_cyr", "cyr_to_lat"]
