"""Unit tests for FreeDict dictionary source."""

import gzip
import struct
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from dictforge.source_freedict import (
    FreeDictSource,
    FreeDictParseError,
)
from dictforge.translit import cyr_to_lat


@pytest.fixture
def freedict_source(tmp_path: Path) -> FreeDictSource:
    """Create a FreeDictSource instance for testing."""
    session = MagicMock()
    progress_factory = lambda **kwargs: MagicMock(
        __enter__=lambda s: lambda x: None, __exit__=lambda *a: None
    )
    return FreeDictSource(
        cache_dir=tmp_path,
        session=session,
        progress_factory=progress_factory,
    )


def test_ensure_download_dirs(freedict_source: FreeDictSource, tmp_path: Path) -> None:
    """Test that cache directory structure is created."""
    freedict_source.ensure_download_dirs()

    freedict_root = tmp_path / "freedict"
    assert freedict_root.exists()
    assert (freedict_root / "filtered").exists()
    assert (freedict_root / "downloads").exists()


def test_serbian_cyrillic_transliteration(freedict_source: FreeDictSource) -> None:
    """Test Serbian Cyrillic to Latin transliteration."""
    # Test lowercase
    assert cyr_to_lat("здраво") == "zdravo"
    assert cyr_to_lat("људи") == "ljudi"
    assert cyr_to_lat("њега") == "njega"
    assert cyr_to_lat("џеп") == "džep"

    # Test uppercase
    assert cyr_to_lat("ЗДРАВО") == "ZDRAVO"
    assert cyr_to_lat("Људи") == "Ljudi"
    assert cyr_to_lat("Њега") == "Njega"
    assert cyr_to_lat("Џеп") == "Džep"

    # Test mixed
    assert cyr_to_lat("Ћирилица") == "Ćirilica"
    assert cyr_to_lat("Ђорђе") == "Đorđe"


def test_transliteration_preserves_non_cyrillic(freedict_source: FreeDictSource) -> None:
    """Test that transliteration preserves non-Cyrillic text."""
    # Latin text should pass through unchanged
    assert cyr_to_lat("hello") == "hello"
    assert cyr_to_lat("test123") == "test123"

    # Mixed Cyrillic and Latin
    assert cyr_to_lat("test здраво") == "test zdravo"

    # Numbers and punctuation
    assert cyr_to_lat("123,.!?") == "123,.!?"


def test_apply_transliteration_to_serbian_entry(freedict_source: FreeDictSource) -> None:
    """Test that transliteration is applied to Serbian entries."""
    entry = {
        "word": "здраво",
        "senses": [
            {"glosses": ["поздрав", "greeting"]},
            {"glosses": "људи"},
        ],
    }

    result = freedict_source._apply_transliteration(entry, "Serbian")

    assert result["word"] == "zdravo"
    assert result["senses"][0]["glosses"] == ["pozdrav", "greeting"]
    assert result["senses"][1]["glosses"] == "ljudi"


def test_apply_transliteration_skips_non_serbian(freedict_source: FreeDictSource) -> None:
    """Test that transliteration is not applied to non-Serbian entries."""
    entry = {"word": "здраво", "senses": [{"glosses": ["поздрав"]}]}

    result = freedict_source._apply_transliteration(entry, "Croatian")

    # Should remain unchanged
    assert result["word"] == "здраво"
    assert result["senses"][0]["glosses"] == ["поздрав"]


def test_get_related_languages_serbian(freedict_source: FreeDictSource) -> None:
    """Test that Serbian returns Croatian as related language."""
    assert freedict_source._get_related_languages("Serbian") == ["Croatian"]


def test_get_related_languages_others(freedict_source: FreeDictSource) -> None:
    """Test that other languages return empty list."""
    assert freedict_source._get_related_languages("English") == []
    assert freedict_source._get_related_languages("Russian") == []
    assert freedict_source._get_related_languages("Croatian") == []


def test_entry_has_content_with_valid_entry(freedict_source: FreeDictSource) -> None:
    """Test that valid entries are recognized."""
    entry = {"senses": [{"glosses": ["meaning"]}]}
    assert freedict_source.entry_has_content(entry)

    entry = {"senses": [{"glosses": "single meaning"}]}
    assert freedict_source.entry_has_content(entry)


def test_entry_has_content_rejects_empty(freedict_source: FreeDictSource) -> None:
    """Test that empty entries are rejected."""
    assert not freedict_source.entry_has_content({})
    assert not freedict_source.entry_has_content({"senses": []})
    assert not freedict_source.entry_has_content({"senses": [{"glosses": []}]})
    assert not freedict_source.entry_has_content({"senses": [{"glosses": [""]}]})
    assert not freedict_source.entry_has_content({"senses": [{"glosses": "   "}]})


def test_read_ifo_metadata(freedict_source: FreeDictSource, tmp_path: Path) -> None:
    """Test parsing of StarDict .ifo metadata file."""
    ifo_path = tmp_path / "test.ifo"
    ifo_path.write_text(
        "StarDict's dict ifo file\n"
        "version=2.4.2\n"
        "bookname=Test Dictionary\n"
        "wordcount=100\n"
        "synwordcount=50\n"
        "idxfilesize=1234\n"
        "sametypesequence=h\n",
        encoding="utf-8",
    )

    metadata = freedict_source._read_ifo_metadata(ifo_path)

    assert metadata["version"] == "2.4.2"
    assert metadata["bookname"] == "Test Dictionary"
    assert metadata["wordcount"] == "100"
    assert metadata["idxfilesize"] == "1234"
    assert metadata["sametypesequence"] == "h"


def test_read_index(freedict_source: FreeDictSource, tmp_path: Path) -> None:
    """Test parsing of StarDict .idx index file."""
    idx_path = tmp_path / "test.idx"

    # Create binary index: word\0 + offset(4B BE) + size(4B BE)
    data = b""
    data += b"hello\x00" + struct.pack(">I", 0) + struct.pack(">I", 10)
    data += b"world\x00" + struct.pack(">I", 10) + struct.pack(">I", 15)
    data += b"test\x00" + struct.pack(">I", 25) + struct.pack(">I", 8)

    idx_path.write_bytes(data)

    index = freedict_source._read_index(idx_path)

    assert len(index) == 3
    assert index[0] == ("hello", 0, 10)
    assert index[1] == ("world", 10, 15)
    assert index[2] == ("test", 25, 8)


def test_read_definitions_plain(freedict_source: FreeDictSource, tmp_path: Path) -> None:
    """Test reading definitions from plain .dict file."""
    dict_path = tmp_path / "test.dict"
    dict_path.write_bytes(b"definition1definition2 longer")

    index = [
        ("word1", 0, 11),
        ("word2", 11, 18),
    ]

    definitions = freedict_source._read_definitions(dict_path, index)

    assert definitions["word1"] == "definition1"
    assert definitions["word2"] == "definition2 longer"


def test_read_definitions_compressed(freedict_source: FreeDictSource, tmp_path: Path) -> None:
    """Test reading definitions from compressed .dict.dz file."""
    dict_path = tmp_path / "test.dict.dz"

    content = b"definition1definition2 longer"
    with gzip.open(dict_path, "wb") as f:
        f.write(content)

    index = [
        ("word1", 0, 11),
        ("word2", 11, 18),
    ]

    definitions = freedict_source._read_definitions(dict_path, index)

    assert definitions["word1"] == "definition1"
    assert definitions["word2"] == "definition2 longer"


def test_extract_glosses_simple(freedict_source: FreeDictSource) -> None:
    """Test extracting glosses from simple text."""
    glosses = freedict_source._extract_glosses("hello; world")
    assert glosses == ["hello", "world"]

    glosses = freedict_source._extract_glosses("one|two|three")
    assert glosses == ["one", "two", "three"]

    glosses = freedict_source._extract_glosses("first\nsecond\nthird")
    assert glosses == ["first", "second", "third"]


def test_extract_glosses_with_html(freedict_source: FreeDictSource) -> None:
    """Test extracting glosses from HTML content."""
    glosses = freedict_source._extract_glosses("<b>hello</b>; <i>world</i>")
    assert glosses == ["hello", "world"]

    glosses = freedict_source._extract_glosses("<p>definition</p>")
    assert glosses == ["definition"]


def test_convert_to_kaikki_format(freedict_source: FreeDictSource) -> None:
    """Test conversion of StarDict entry to Kaikki format."""
    entry = freedict_source._convert_to_kaikki_format(
        "hello", "greeting; salutation", {"sametypesequence": "h"}
    )

    assert entry["word"] == "hello"
    assert len(entry["senses"]) == 1
    assert entry["senses"][0]["glosses"] == ["greeting", "salutation"]
    assert entry["senses"][0]["raw_glosses"] == ["greeting", "salutation"]


def test_merge_entries_list_new_words(freedict_source: FreeDictSource) -> None:
    """Test merging entries with different words."""
    target = [{"word": "hello", "senses": [{"glosses": ["greeting"]}]}]
    incoming = [{"word": "world", "senses": [{"glosses": ["world"]}]}]

    freedict_source._merge_entries_list(target, incoming)

    assert len(target) == 2
    assert target[0]["word"] == "hello"
    assert target[1]["word"] == "world"


def test_merge_entries_list_duplicate_words(freedict_source: FreeDictSource) -> None:
    """Test merging entries with same word adds new senses."""
    target = [{"word": "run", "senses": [{"glosses": ["to move quickly"]}]}]
    incoming = [
        {"word": "run", "senses": [{"glosses": ["to operate"]}, {"glosses": ["to move quickly"]}]}
    ]

    freedict_source._merge_entries_list(target, incoming)

    assert len(target) == 1
    assert len(target[0]["senses"]) == 2
    assert target[0]["senses"][0]["glosses"] == ["to move quickly"]
    assert target[0]["senses"][1]["glosses"] == ["to operate"]


def test_merge_entries_list_case_insensitive(freedict_source: FreeDictSource) -> None:
    """Test that merging is case-insensitive."""
    target = [{"word": "Hello", "senses": [{"glosses": ["greeting"]}]}]
    incoming = [{"word": "hello", "senses": [{"glosses": ["hi"]}]}]

    freedict_source._merge_entries_list(target, incoming)

    assert len(target) == 1  # Should merge, not add new
    assert len(target[0]["senses"]) == 2


def test_has_stardict_files(freedict_source: FreeDictSource, tmp_path: Path) -> None:
    """Test detection of StarDict files."""
    # Empty directory
    assert not freedict_source._has_stardict_files(tmp_path)

    # Create StarDict files
    (tmp_path / "test.ifo").touch()
    (tmp_path / "test.idx").touch()
    (tmp_path / "test.dict.dz").touch()

    assert freedict_source._has_stardict_files(tmp_path)


def test_has_stardict_files_with_plain_dict(
    freedict_source: FreeDictSource, tmp_path: Path
) -> None:
    """Test detection with plain .dict file."""
    (tmp_path / "test.ifo").touch()
    (tmp_path / "test.idx").touch()
    (tmp_path / "test.dict").touch()

    assert freedict_source._has_stardict_files(tmp_path)


def test_find_stardict_dir_in_root(freedict_source: FreeDictSource, tmp_path: Path) -> None:
    """Test finding StarDict files in root directory."""
    (tmp_path / "test.ifo").touch()
    (tmp_path / "test.idx").touch()
    (tmp_path / "test.dict.dz").touch()

    result = freedict_source._find_stardict_dir(tmp_path)
    assert result == tmp_path


def test_find_stardict_dir_in_subdirectory(freedict_source: FreeDictSource, tmp_path: Path) -> None:
    """Test finding StarDict files in subdirectory."""
    subdir = tmp_path / "dict" / "files"
    subdir.mkdir(parents=True)

    (subdir / "test.ifo").touch()
    (subdir / "test.idx").touch()
    (subdir / "test.dict.dz").touch()

    result = freedict_source._find_stardict_dir(tmp_path)
    assert result == subdir


def test_create_empty_result(freedict_source: FreeDictSource, tmp_path: Path) -> None:
    """Test creation of empty result file."""
    path, count = freedict_source._create_empty_result("Serbian", "English")

    assert count == 0
    assert path.exists()
    assert path.stat().st_size == 0
    assert "Serbian" in str(path)
    assert "English" in str(path)


def test_parse_stardict_files_integration(freedict_source: FreeDictSource, tmp_path: Path) -> None:
    """Integration test for parsing complete StarDict dictionary."""
    # Create .ifo file
    ifo_path = tmp_path / "test.ifo"
    ifo_path.write_text("version=2.4.2\nwordcount=2\nsametypesequence=h\n", encoding="utf-8")

    # Create .idx file
    idx_path = tmp_path / "test.idx"
    idx_data = b""
    idx_data += b"hello\x00" + struct.pack(">I", 0) + struct.pack(">I", 8)
    idx_data += b"world\x00" + struct.pack(">I", 8) + struct.pack(">I", 5)
    idx_path.write_bytes(idx_data)

    # Create .dict.dz file
    dict_path = tmp_path / "test.dict.dz"
    dict_content = b"greetingworld"
    with gzip.open(dict_path, "wb") as f:
        f.write(dict_content)

    # Parse
    entries = freedict_source._parse_stardict_files(tmp_path)

    assert len(entries) == 2
    assert entries[0]["word"] == "hello"
    assert entries[0]["senses"][0]["glosses"] == ["greeting"]
    assert entries[1]["word"] == "world"
    assert entries[1]["senses"][0]["glosses"] == ["world"]


def test_parse_stardict_files_missing_ifo(freedict_source: FreeDictSource, tmp_path: Path) -> None:
    """Test that parsing fails gracefully when .ifo file is missing."""
    with pytest.raises(FreeDictParseError, match="No .ifo file found"):
        freedict_source._parse_stardict_files(tmp_path)


def test_parse_stardict_files_missing_idx(freedict_source: FreeDictSource, tmp_path: Path) -> None:
    """Test that parsing fails when .idx file is missing."""
    (tmp_path / "test.ifo").touch()

    with pytest.raises(FreeDictParseError, match="Missing .idx or .idx.gz file"):
        freedict_source._parse_stardict_files(tmp_path)


def test_parse_stardict_files_missing_dict(freedict_source: FreeDictSource, tmp_path: Path) -> None:
    """Test that parsing fails when .dict file is missing."""
    (tmp_path / "test.ifo").touch()
    (tmp_path / "test.idx").touch()

    with pytest.raises(FreeDictParseError, match="Missing .dict or .dict.dz"):
        freedict_source._parse_stardict_files(tmp_path)


def test_get_entries_creates_cache_structure(
    freedict_source: FreeDictSource, tmp_path: Path
) -> None:
    """Test that get_entries creates proper cache directory structure."""
    # Mock the download to avoid actual HTTP requests
    freedict_source._get_direct_or_chained = MagicMock(
        side_effect=lambda *args: freedict_source._create_empty_result(*args)
    )

    freedict_source.get_entries("Serbian", "English")

    freedict_root = tmp_path / "freedict"
    assert freedict_root.exists()
    assert (freedict_root / "filtered").exists()


def test_find_latest_version_success(freedict_source: FreeDictSource) -> None:
    """Test finding latest version when version exists."""
    # Mock successful response for version 0.2
    freedict_source.session.head = MagicMock(
        side_effect=lambda url, **kwargs: MagicMock(status_code=200 if "0.2" in url else 404)
    )

    version = freedict_source._find_latest_version("srp-eng")
    assert version == "0.2"


def test_find_latest_version_none_found(freedict_source: FreeDictSource) -> None:
    """Test when no version is found."""
    freedict_source.session.head = MagicMock(return_value=MagicMock(status_code=404))

    version = freedict_source._find_latest_version("nonexistent-dict")
    assert version is None


def test_transliteration_applied_in_fetch_and_parse(
    freedict_source: FreeDictSource, tmp_path: Path
) -> None:
    """Test that transliteration is applied during fetch_and_parse for Serbian."""
    # Create mock StarDict files with Cyrillic content
    dict_dir = tmp_path / "dict"
    dict_dir.mkdir()

    # Create minimal StarDict files
    (dict_dir / "test.ifo").write_text("wordcount=1\n", encoding="utf-8")

    # "здраво" in UTF-8 as word
    idx_data = b"\xd0\xb7\xd0\xb4\xd1\x80\xd0\xb0\xd0\xb2\xd0\xbe\x00"
    definition = "поздрав".encode("utf-8")
    idx_data += struct.pack(">I", 0) + struct.pack(">I", len(definition))
    (dict_dir / "test.idx").write_bytes(idx_data)

    with gzip.open(dict_dir / "test.dict.dz", "wb") as f:
        f.write(definition)

    # Mock _download_dictionary to return our test directory
    freedict_source._download_dictionary = MagicMock(return_value=dict_dir)

    entries = freedict_source._fetch_and_parse_dict("Serbian", "English", "srp", "eng")

    # Word and glosses should be transliterated
    assert entries[0]["word"] == "zdravo"
    assert "pozdrav" in entries[0]["senses"][0]["glosses"][0]


def test_cyrillic_to_latin_mapping_complete(freedict_source: FreeDictSource) -> None:
    """Test that all Serbian Cyrillic letters are mapped."""
    cyrillic_alphabet = "абвгдђежзијклљмнњопрстћуфхцчџш"

    result = cyr_to_lat(cyrillic_alphabet)

    # Should have transliteration for all letters
    assert len(result) >= len(cyrillic_alphabet)
    assert "a" in result
    assert "đ" in result
    assert "ž" in result
    assert "č" in result
    assert "ć" in result
    assert "š" in result
