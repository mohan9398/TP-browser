# -*- coding: utf-8 -*-
"""
Lightweight obfuscation-at-rest for embedded secrets.

The deobfuscation key is *derived from constants compiled into the
application*, so this protects secrets from casual inspection — e.g. running
`strings` on the built .exe will no longer reveal the HMAC key in plaintext.

NOTE: this is obfuscation, not key management. A determined attacker with the
binary can still recover the key. For real protection the secret should be
provisioned per-deployment from a server at install/run time.
"""
import base64
import hashlib

# Key material is split so the full passphrase never appears as one literal.
_PARTS = ("Tele", "Secure", "Exam", "Browser", "2026")


def _fernet():
    from cryptography.fernet import Fernet
    passphrase = "::".join(_PARTS).encode("utf-8")
    key = base64.urlsafe_b64encode(hashlib.sha256(passphrase).digest())
    return Fernet(key)


def encrypt(plaintext: str) -> str:
    """Encrypt a string → token (used by tooling to generate the constants)."""
    return _fernet().encrypt(plaintext.encode("utf-8")).decode("ascii")


def decrypt(token: str) -> str:
    """Decrypt a token produced by encrypt(). Raises on tampering/failure."""
    return _fernet().decrypt(token.encode("ascii")).decode("utf-8")
