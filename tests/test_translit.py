from dictforge.translit import cyr_to_lat, lat_to_cyr


class TestLatToCyr:
    """Test Latin to Cyrillic transliteration."""

    def test_basic_single_characters(self) -> None:
        assert lat_to_cyr("a") == "а"
        assert lat_to_cyr("b") == "б"
        assert lat_to_cyr("c") == "ц"
        assert lat_to_cyr("č") == "ч"
        assert lat_to_cyr("ć") == "ћ"
        assert lat_to_cyr("d") == "д"
        assert lat_to_cyr("đ") == "ђ"
        assert lat_to_cyr("e") == "е"
        assert lat_to_cyr("š") == "ш"
        assert lat_to_cyr("ž") == "ж"

    def test_two_character_pairs(self) -> None:
        assert lat_to_cyr("dž") == "џ"
        assert lat_to_cyr("dj") == "ђ"
        assert lat_to_cyr("lj") == "љ"
        assert lat_to_cyr("nj") == "њ"

    def test_uppercase_single_characters(self) -> None:
        assert lat_to_cyr("A") == "А"
        assert lat_to_cyr("B") == "Б"
        assert lat_to_cyr("Č") == "Ч"
        assert lat_to_cyr("Ć") == "Ћ"
        assert lat_to_cyr("Đ") == "Ђ"
        assert lat_to_cyr("Š") == "Ш"
        assert lat_to_cyr("Ž") == "Ж"

    def test_uppercase_two_character_pairs(self) -> None:
        assert lat_to_cyr("DŽ") == "Џ"
        assert lat_to_cyr("DJ") == "Ђ"
        assert lat_to_cyr("LJ") == "Љ"
        assert lat_to_cyr("NJ") == "Њ"

    def test_mixed_case_two_character_pairs(self) -> None:
        assert lat_to_cyr("Dž") == "Џ"
        assert lat_to_cyr("Dj") == "Ђ"
        assert lat_to_cyr("Lj") == "Љ"
        assert lat_to_cyr("Nj") == "Њ"
        # When first char is lowercase, result is lowercase
        assert lat_to_cyr("dŽ") == "џ"
        assert lat_to_cyr("dJ") == "ђ"

    def test_words(self) -> None:
        assert lat_to_cyr("zdravo") == "здраво"
        assert lat_to_cyr("ljubav") == "љубав"
        assert lat_to_cyr("njiva") == "њива"
        assert lat_to_cyr("džak") == "џак"
        assert lat_to_cyr("đak") == "ђак"

    def test_mixed_case_words(self) -> None:
        assert lat_to_cyr("Zdravo") == "Здраво"
        assert lat_to_cyr("ZDRAVO") == "ЗДРАВО"
        assert lat_to_cyr("Ljubav") == "Љубав"
        assert lat_to_cyr("NJIVA") == "ЊИВА"

    def test_empty_string(self) -> None:
        assert lat_to_cyr("") == ""

    def test_non_serbian_characters(self) -> None:
        # Note: 'l' and 'o' are Serbian characters, so they get converted
        assert lat_to_cyr("hello") == "хелло"
        assert lat_to_cyr("123") == "123"
        # Note: Most Latin letters are Serbian characters, so they get converted
        # Only symbols like @, ., etc. are preserved
        assert lat_to_cyr("test@example.com") == "тест@еxампле.цом"
        assert lat_to_cyr("a b c") == "а б ц"

    def test_special_characters(self) -> None:
        assert lat_to_cyr("a, b, c") == "а, б, ц"
        assert lat_to_cyr("a.b.c") == "а.б.ц"
        assert lat_to_cyr("a-b-c") == "а-б-ц"

    def test_unicode_normalization(self) -> None:
        # Test that NFC normalization works
        assert lat_to_cyr("a") == "а"
        # Test with precomposed characters
        assert lat_to_cyr("č") == "ч"


class TestCyrToLat:
    """Test Cyrillic to Latin transliteration."""

    def test_basic_single_characters(self) -> None:
        assert cyr_to_lat("а") == "a"
        assert cyr_to_lat("б") == "b"
        assert cyr_to_lat("ц") == "c"
        assert cyr_to_lat("ч") == "č"
        assert cyr_to_lat("ћ") == "ć"
        assert cyr_to_lat("д") == "d"
        assert cyr_to_lat("ђ") == "đ"
        assert cyr_to_lat("е") == "e"
        assert cyr_to_lat("ш") == "š"
        assert cyr_to_lat("ж") == "ž"

    def test_special_cyrillic_characters(self) -> None:
        assert cyr_to_lat("ђ") == "đ"
        assert cyr_to_lat("ћ") == "ć"
        assert cyr_to_lat("љ") == "lj"
        assert cyr_to_lat("њ") == "nj"
        assert cyr_to_lat("џ") == "dž"

    def test_uppercase_single_characters(self) -> None:
        assert cyr_to_lat("А") == "A"
        assert cyr_to_lat("Б") == "B"
        assert cyr_to_lat("Ч") == "Č"
        assert cyr_to_lat("Ћ") == "Ć"
        assert cyr_to_lat("Ш") == "Š"
        assert cyr_to_lat("Ж") == "Ž"

    def test_uppercase_special_characters(self) -> None:
        assert cyr_to_lat("Ђ") == "Đ"
        assert cyr_to_lat("Ћ") == "Ć"
        assert cyr_to_lat("Љ") == "Lj"
        assert cyr_to_lat("Њ") == "Nj"
        assert cyr_to_lat("Џ") == "Dž"

    def test_words(self) -> None:
        assert cyr_to_lat("здраво") == "zdravo"
        assert cyr_to_lat("љубав") == "ljubav"
        assert cyr_to_lat("њива") == "njiva"
        assert cyr_to_lat("џак") == "džak"
        assert cyr_to_lat("ђак") == "đak"

    def test_mixed_case_words(self) -> None:
        assert cyr_to_lat("Здраво") == "Zdravo"
        assert cyr_to_lat("ЗДРАВО") == "ZDRAVO"
        assert cyr_to_lat("Љубав") == "Ljubav"
        # Uppercase special characters (Њ) capitalize the result (Nj), rest stays uppercase
        assert cyr_to_lat("ЊИВА") == "NjIVA"

    def test_empty_string(self) -> None:
        assert cyr_to_lat("") == ""

    def test_non_serbian_characters(self) -> None:
        assert cyr_to_lat("123") == "123"
        assert cyr_to_lat("а б ц") == "a b c"
        # Test with English characters mixed in
        assert cyr_to_lat("тест") == "test"

    def test_special_characters(self) -> None:
        assert cyr_to_lat("а, б, ц") == "a, b, c"
        assert cyr_to_lat("а.б.ц") == "a.b.c"
        assert cyr_to_lat("а-б-ц") == "a-b-c"

    def test_unicode_normalization(self) -> None:
        assert cyr_to_lat("а") == "a"
        # Test with precomposed characters
        assert cyr_to_lat("ч") == "č"


class TestRoundTrip:
    """Test round-trip conversions."""

    def test_round_trip_basic_words(self) -> None:
        words = ["zdravo", "ljubav", "njiva", "džak", "đak"]
        for word in words:
            cyr = lat_to_cyr(word)
            lat = cyr_to_lat(cyr)
            # Note: round-trip may not be exact due to multiple representations
            # (e.g., "dj" vs "đ", "dž" vs "џ")
            assert lat.lower() == word.lower() or lat in [word, word.replace("dj", "đ")]

    def test_round_trip_cyrillic_words(self) -> None:
        words = ["здраво", "љубав", "њива", "џак", "ђак"]
        for word in words:
            lat = cyr_to_lat(word)
            cyr = lat_to_cyr(lat)
            assert cyr == word

    def test_round_trip_mixed_case(self) -> None:
        test_cases = [
            ("Zdravo", "Здраво"),
            ("Ljubav", "Љубав"),
            ("Njiva", "Њива"),
            ("Džak", "Џак"),
            ("Đak", "Ђак"),
        ]
        for lat, expected_cyr in test_cases:
            cyr = lat_to_cyr(lat)
            assert cyr == expected_cyr
            back_lat = cyr_to_lat(cyr)
            # Check that case is preserved appropriately
            assert back_lat[0].isupper() == lat[0].isupper()


class TestEdgeCases:
    """Test edge cases and special scenarios."""

    def test_whitespace_handling(self) -> None:
        assert lat_to_cyr("a b c") == "а б ц"
        assert cyr_to_lat("а б ц") == "a b c"
        assert lat_to_cyr("  a  ") == "  а  "
        assert cyr_to_lat("  а  ") == "  a  "

    def test_numbers_and_symbols(self) -> None:
        text = "123 !@#$%^&*()"
        assert lat_to_cyr(text) == text
        assert cyr_to_lat(text) == text

    def test_newlines_and_tabs(self) -> None:
        text = "a\nb\tc"
        assert lat_to_cyr(text) == "а\nб\tц"
        assert cyr_to_lat("а\nб\tц") == "a\nb\tc"

    def test_ambiguous_cases(self) -> None:
        # Both "dj" and "đ" should convert to "ђ"
        assert lat_to_cyr("dj") == "ђ"
        assert lat_to_cyr("đ") == "ђ"
        # But "ђ" should convert back to "đ" (not "dj")
        assert cyr_to_lat("ђ") == "đ"

    def test_long_text(self) -> None:
        lat_text = "Ovo je test transliteracije sa različitim karakterima."
        cyr_text = lat_to_cyr(lat_text)
        assert len(cyr_text) > 0
        assert "тест" in cyr_text
        back_lat = cyr_to_lat(cyr_text)
        assert len(back_lat) > 0
