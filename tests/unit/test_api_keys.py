"""API key format, hashing and header parsing (pure functions)."""

import pytest

from app.auth.api_keys import (
    display_prefix,
    generate_api_key,
    hash_api_key,
    parse_authorization_header,
)


def test_generated_keys_have_prefix_length_and_are_unique() -> None:
    keys = {generate_api_key() for _ in range(1_000)}

    assert len(keys) == 1_000
    for key in keys:
        assert key.startswith("nxr_")
        assert len(key) == 47  # "nxr_" + 43 base64url chars = 256 bits of randomness


def test_hash_is_deterministic_32_bytes_and_not_the_key() -> None:
    key = generate_api_key()

    digest = hash_api_key(key)

    assert digest == hash_api_key(key)
    assert len(digest) == 32
    assert key.encode() not in digest


def test_display_prefix_reveals_only_a_small_part() -> None:
    key = generate_api_key()

    assert display_prefix(key) == key[:12]


def test_parses_a_valid_header_case_insensitively() -> None:
    key = generate_api_key()

    assert parse_authorization_header(f"ApiKey {key}") == key
    assert parse_authorization_header(f"apikey   {key}  ") == key


@pytest.mark.parametrize(
    "header",
    [
        None,
        "",
        "ApiKey",
        "Bearer nxr_" + "a" * 43,  # wrong scheme
        "ApiKey abc",  # wrong format
        "ApiKey nxr_" + "a" * 42,  # too short
        "ApiKey nxr_" + "a" * 43 + "\nX-Injected: 1",  # header smuggling attempt
        "ApiKey sk_live_" + "a" * 43,  # someone else's key format
    ],
)
def test_rejects_missing_or_malformed_headers(header: str | None) -> None:
    assert parse_authorization_header(header) is None
