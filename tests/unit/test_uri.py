"""Tests for photo_memex.core.uri (R5: URI resolution surface)."""

from __future__ import annotations

import pytest

from photo_memex.core.uri import (
    InvalidUriError,
    ParsedUri,
    build_marginalia_uri,
    build_photo_uri,
    parse_uri,
)

SHA = "a" * 64


class TestBuild:
    def test_build_photo_uri(self):
        assert build_photo_uri(SHA) == f"photo-memex://photo/{SHA}"

    def test_build_marginalia_uri_accepts_int(self):
        assert build_marginalia_uri(7) == "photo-memex://marginalia/7"

    def test_build_rejects_empty(self):
        with pytest.raises(ValueError):
            build_photo_uri("")


class TestParse:
    def test_parse_photo(self):
        p = parse_uri(f"photo-memex://photo/{SHA}")
        assert p == ParsedUri("photo-memex", "photo", SHA, None)

    def test_parse_marginalia(self):
        p = parse_uri("photo-memex://marginalia/42")
        assert p.kind == "marginalia"
        assert p.id == "42"
        assert p.fragment is None

    def test_parse_fragment_is_split_and_returned(self):
        p = parse_uri(f"photo-memex://photo/{SHA}#region=0,0,10,10")
        assert p.id == SHA
        assert p.fragment == "region=0,0,10,10"

    def test_wrong_scheme_raises(self):
        with pytest.raises(InvalidUriError):
            parse_uri("llm-memex://conversation/abc")

    def test_unknown_kind_raises(self):
        with pytest.raises(InvalidUriError):
            parse_uri("photo-memex://widget/abc")

    def test_empty_id_raises(self):
        with pytest.raises(InvalidUriError):
            parse_uri("photo-memex://photo/")

    def test_not_a_uri_raises(self):
        with pytest.raises(InvalidUriError):
            parse_uri("just-a-string")
