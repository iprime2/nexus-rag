"""API key format, hashing and header parsing. Pure functions, no I/O.

Format: ``nxr_`` + 43 URL-safe characters (32 random bytes = 256 bits).

* The fixed prefix lets secret scanners (GitHub, gitleaks) recognise a
  leaked key, and lets humans see what kind of secret it is.
* Only a SHA-256 **hash** is stored. If the database leaks, the keys don't.
* SHA-256, not a slow password hash (argon2/bcrypt): slow hashes protect
  *low-entropy* human passwords from guessing. A 256-bit random key can't be
  guessed, and a fast hash keeps per-request authentication cheap.
* The plaintext key is shown once, at creation. It can't be recovered later,
  only revoked and replaced.
"""

import hashlib
import re
import secrets

KEY_PREFIX = "nxr_"
_KEY_PATTERN = re.compile(r"^nxr_[A-Za-z0-9_-]{43}$")
DISPLAY_PREFIX_LENGTH = 12  # "nxr_" + 8 characters: enough to recognise a key in a list


def generate_api_key() -> str:
    return KEY_PREFIX + secrets.token_urlsafe(32)


def hash_api_key(key: str) -> bytes:
    return hashlib.sha256(key.encode("ascii")).digest()


def display_prefix(key: str) -> str:
    return key[:DISPLAY_PREFIX_LENGTH]


def parse_authorization_header(value: str | None) -> str | None:
    """Extract the key from ``Authorization: ApiKey <key>``; None if absent or malformed.

    Malformed values are rejected *before* any database lookup.
    """
    if not value:
        return None
    scheme, _, credential = value.strip().partition(" ")
    credential = credential.strip()
    if scheme.lower() != "apikey" or not _KEY_PATTERN.fullmatch(credential):
        return None
    return credential
