"""Pure unit tests for auth.main helpers — no HTTP, no DB, no fixtures."""
from auth.main import (
    hash_password, check_password, hash_token,
    safe_next, header_safe,
)


# ---------- password hashing ----------

def test_hash_password_verifies():
    h = hash_password("secret")
    assert check_password("secret", h) is True


def test_hash_password_rejects_wrong():
    h = hash_password("secret")
    assert check_password("wrong", h) is False


def test_hash_password_uses_unique_salt():
    assert hash_password("same") != hash_password("same")


def test_check_password_handles_malformed_hash():
    assert check_password("x", "not-a-valid-format") is False
    assert check_password("x", "") is False


# ---------- token hashing ----------

def test_hash_token_is_sha256():
    # sha256("abc") = ba7816bf...
    assert hash_token("abc") == (
        "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )


def test_hash_token_is_deterministic():
    assert hash_token("t") == hash_token("t")
    assert hash_token("t") != hash_token("T")


# ---------- safe_next (open-redirect guard) ----------

def test_safe_next_allows_relative():
    assert safe_next("/dashboard") == "/dashboard"
    assert safe_next("/app1/employees") == "/app1/employees"


def test_safe_next_rejects_protocol_relative():
    assert safe_next("//evil.com") == "/"


def test_safe_next_rejects_backslashes():
    assert safe_next("/foo\\bar") == "/"


def test_safe_next_rejects_absolute_urls():
    assert safe_next("https://evil.com") == "/"


def test_safe_next_handles_empty():
    assert safe_next("") == "/"


# ---------- header_safe ----------

def test_header_safe_strips_non_ascii():
    assert header_safe("José Peña") == "Jose Pena"


def test_header_safe_empty_becomes_unknown():
    assert header_safe("") == "unknown"
    assert header_safe("   ") == "unknown"


def test_header_safe_keeps_ascii():
    assert header_safe("Alice Smith") == "Alice Smith"
