"""Pure-logic unit tests for the partner-pack full-install CWICR resolver.

These exercise only the §5.1 slug → ``load-cwicr`` db_id resolution and the
demo install-list ordering. No database, no embedding model, no HTTP — the
functions under test read in-memory registries only.
"""

from __future__ import annotations

import pytest

from app.core.partner_pack.full_install import (
    _build_city_index,
    _demo_install_list,
    _pack_country,
    resolve_cwicr_db_id,
)


class TestCityIndex:
    def test_index_drops_country_prefix(self) -> None:
        idx = _build_city_index()
        # ``DE_BERLIN`` -> token ``berlin`` -> back to the full db_id.
        assert idx["berlin"] == "DE_BERLIN"
        assert idx["london"] == "GB_LONDON"
        assert idx["toronto"] == "CA_TORONTO"
        # National catalogues keep their suffix as the token.
        assert idx["usd"] == "USA_USD"
        # Multi-word city tokens stay joined (no underscores in the suffix).
        assert idx["saopaulo"] == "BR_SAOPAULO"


class TestResolveCwicrDbId:
    @pytest.mark.parametrize(
        ("slug", "expected"),
        [
            ("cwicr-de-berlin", "DE_BERLIN"),
            ("cwicr-eng-toronto", "CA_TORONTO"),
            ("cwicr-eng-london", "GB_LONDON"),
            ("cwicr-eng-sydney", "AU_SYDNEY"),
            ("cwicr-eng-auckland", "NZ_AUCKLAND"),
            ("cwicr-eng-mumbai", "IN_MUMBAI"),
            ("cwicr-eng-riyadh", "SA_RIYADH"),
            ("cwicr-pt-saopaulo", "BR_SAOPAULO"),
            ("cwicr-usa-usd", "USA_USD"),
        ],
    )
    def test_native_city_match(self, slug: str, expected: str) -> None:
        assert resolve_cwicr_db_id(slug) == expected

    @pytest.mark.parametrize(
        ("slug", "expected"),
        [
            # German transliteration mismatch (token ``munich`` vs slug ``muenchen``).
            ("cwicr-de-muenchen", "DE_MUNICH"),
            # UK-wide slug has no city; aliased to the live UK catalogue id.
            ("cwicr-uk-gbp", "GB_LONDON"),
        ],
    )
    def test_alias_match(self, slug: str, expected: str) -> None:
        assert resolve_cwicr_db_id(slug) == expected

    @pytest.mark.parametrize(
        "slug",
        [
            "cwicr-fra-montreal",  # no Montreal CWICR data yet
            "cwicr-eng-wellington",
            "cwicr-eng-christchurch",
            "cwicr-de-duesseldorf",
            "cwicr-eng-melbourne",
            "cwicr-eng-bangalore",
            "",
        ],
    )
    def test_unresolved_returns_none(self, slug: str) -> None:
        assert resolve_cwicr_db_id(slug) is None

    def test_lang_token_is_ignored(self) -> None:
        # ``eng`` and ``fra`` both mean Canada — resolution keys off the city,
        # never the language token.
        assert resolve_cwicr_db_id("cwicr-eng-toronto") == "CA_TORONTO"
        assert resolve_cwicr_db_id("cwicr-fra-toronto") == "CA_TORONTO"


class TestDemoOrdering:
    def test_pack_country_from_flagship(self) -> None:
        # batimatech-ca's flagship is office-montreal (country CA).
        assert _pack_country("batimatech-ca") == "CA"
        assert _pack_country("uk-jct") == "GB"
        assert _pack_country("us-rsmeans") == "US"

    def test_pack_country_unknown_pack(self) -> None:
        assert _pack_country("does-not-exist") is None

    def test_install_list_flagship_first_and_truncated(self) -> None:
        ids = _demo_install_list("uk-jct", 2)
        assert ids  # at least the flagship
        # uk-jct flagship is commercial-london; it must lead.
        assert ids[0] == "commercial-london"
        assert len(ids) <= 2
        assert len(ids) == len(set(ids))  # de-duplicated

    def test_install_list_zero_count(self) -> None:
        assert _demo_install_list("uk-jct", 0) == []

    def test_install_list_unknown_pack(self) -> None:
        assert _demo_install_list("does-not-exist", 2) == []
