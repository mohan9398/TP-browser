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
import os
import sys
import base64
import hashlib

# Key material is split so the full passphrase never appears as one literal.
_PARTS = ("Tele", "Secure", "Exam", "Browser", "2026")


def _running_under_bare_python() -> bool:
    """True only for the copy-the-dist-and-import attack.

    A shipped build compiles this module to a binary ``.pyd``. If someone
    copies that build and does ``python -c "import ...secrets; secrets.decrypt(...)"``
    to pull the key straight out, then (a) the module file is a ``.pyd`` and
    (b) the host interpreter is ``python.exe`` — this returns True and the
    sensitive calls refuse to run.

    Both legitimate contexts return False, so nothing legitimate breaks:
      * dev / source runs load this file as ``.py`` (compiled is False);
      * the real packaged app is hosted by ``SecureBrowser.exe`` (host is
        not python).
    """
    try:
        compiled = not __file__.endswith(".py")
    except NameError:
        compiled = True
    host = os.path.basename(sys.executable).lower()
    host_is_python = host.startswith("python") or host in ("py.exe", "pythonw.exe")
    return compiled and host_is_python


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
    if _running_under_bare_python():
        # Refuse to hand the key to a standalone-Python import of the shipped
        # binary. This raises the bar from a one-line import to real RE work.
        raise RuntimeError("secure runtime required")
    return _fernet().decrypt(token.encode("ascii")).decode("utf-8")
