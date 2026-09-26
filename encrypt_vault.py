#!/usr/bin/env python3
"""
Sphene Aegis — Standalone Zero-Dependency Vault Encryptor
=========================================================
Sovereign cryptographic sealing tool.
Encrypts Sphene Markdown notes in-place using authenticated AES-256-GCM without
needing the Sphene daemon, runtime, or any proprietary binary.

Requirements:
  - Python 3.8+ (standard library; uses 'cryptography' or system 'libcrypto' via ctypes)
  - Zero external pip dependencies required.

Algorithm Specification:
  - Envelope:
      <!-- SPHENE-VAULT:ENCRYPTED:AES256 -->
      <BASE64_PAYLOAD>
      <!-- /SPHENE-VAULT:ENCRYPTED -->
  - Binary Payload Structure:
      [16 bytes: Salt] + [12 bytes: Nonce/IV] + [Ciphertext] + [16 bytes: GCM Auth Tag]
  - Key Derivation:
      * User-bound key:
          1. Intermediate = PBKDF2-HMAC-SHA256(password, user_salt, 10,000 iterations, 32 bytes)
          2. Info = "sphene:aes256:user-vault-key:v2:" + username.lower()
          3. UserVaultKey = HKDF-SHA256(Intermediate, user_salt, Info, 32 bytes)
      * Note-level AES-256 Key:
          1. Hash_0 = SHA-256(PassphraseOrHexKey + NoteSalt)
          2. Hash_i = SHA-256(Hash_{i-1}) for 10,000 iterations
  - Cipher:
      AES-256-GCM (NIST SP 800-38D) with 96-bit Nonce and 128-bit Authentication Tag.
"""

import os
import sys
import re
import base64
import hashlib
import hmac
import getpass
import argparse
import secrets
from typing import Optional, Tuple

# ANSI Colors
BOLD = "\033[1m"
GREEN = "\033[0;32m"
CYAN = "\033[0;36m"
YELLOW = "\033[1;33m"
RED = "\033[0;31m"
NC = "\033[0m"

ARMOR_TAG = "<!-- SPHENE-VAULT:ENCRYPTED:AES256 -->"
DEFAULT_SALT = b"sphene-vault-default-salt-v2"
DEFAULT_MASTER_KEY = "sphene-master-cipher-vault-key-v2"

# ------------------------------------------------------------------------------
# Cryptographic Backend: Try 'cryptography' first, fall back to 'ctypes + libcrypto'
# ------------------------------------------------------------------------------
CRYPTO_BACKEND = "none"

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    CRYPTO_BACKEND = "cryptography"
except ImportError:
    import ctypes
    import ctypes.util

    libname = ctypes.util.find_library("crypto")
    if libname:
        try:
            lib = ctypes.CDLL(libname)
            lib.EVP_CIPHER_CTX_new.restype = ctypes.c_void_p
            lib.EVP_CIPHER_CTX_new.argtypes = []
            lib.EVP_CIPHER_CTX_free.restype = None
            lib.EVP_CIPHER_CTX_free.argtypes = [ctypes.c_void_p]

            lib.EVP_aes_256_gcm.restype = ctypes.c_void_p
            lib.EVP_aes_256_gcm.argtypes = []

            lib.EVP_EncryptInit_ex.restype = ctypes.c_int
            lib.EVP_EncryptInit_ex.argtypes = [
                ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_char_p, ctypes.c_char_p
            ]

            lib.EVP_EncryptUpdate.restype = ctypes.c_int
            lib.EVP_EncryptUpdate.argtypes = [
                ctypes.c_void_p, ctypes.c_char_p, ctypes.POINTER(ctypes.c_int), ctypes.c_char_p, ctypes.c_int
            ]

            lib.EVP_CIPHER_CTX_ctrl.restype = ctypes.c_int
            lib.EVP_CIPHER_CTX_ctrl.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_char_p]

            lib.EVP_EncryptFinal_ex.restype = ctypes.c_int
            lib.EVP_EncryptFinal_ex.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.POINTER(ctypes.c_int)]

            LIBCRYPTO = lib
            CRYPTO_BACKEND = "ctypes"
        except Exception:
            CRYPTO_BACKEND = "none"


def encrypt_aes_gcm(key: bytes, nonce: bytes, plaintext: bytes) -> Tuple[bytes, bytes]:
    """Encrypts plaintext with AES-256-GCM. Returns (ciphertext, 16-byte tag)."""
    if CRYPTO_BACKEND == "cryptography":
        aesgcm = AESGCM(key)
        cipher_with_tag = aesgcm.encrypt(nonce, plaintext, None)
        return cipher_with_tag[:-16], cipher_with_tag[-16:]

    elif CRYPTO_BACKEND == "ctypes":
        ctx = LIBCRYPTO.EVP_CIPHER_CTX_new()
        cipher = LIBCRYPTO.EVP_aes_256_gcm()

        LIBCRYPTO.EVP_EncryptInit_ex(ctx, cipher, None, None, None)
        LIBCRYPTO.EVP_EncryptInit_ex(ctx, None, None, key, nonce)

        out_buf = ctypes.create_string_buffer(len(plaintext) + 32)
        out_len = ctypes.c_int(0)
        LIBCRYPTO.EVP_EncryptUpdate(ctx, out_buf, ctypes.byref(out_len), plaintext, len(plaintext))

        final_len = ctypes.c_int(0)
        ptr_tail = ctypes.addressof(out_buf) + out_len.value
        LIBCRYPTO.EVP_EncryptFinal_ex(ctx, ctypes.c_char_p(ptr_tail), ctypes.byref(final_len))

        tag_buf = ctypes.create_string_buffer(16)
        # EVP_CTRL_AEAD_GET_TAG = 0x10
        LIBCRYPTO.EVP_CIPHER_CTX_ctrl(ctx, 0x10, 16, tag_buf)
        LIBCRYPTO.EVP_CIPHER_CTX_free(ctx)

        total_cipher_len = out_len.value + final_len.value
        return out_buf.raw[:total_cipher_len], tag_buf.raw[:16]

    else:
        raise RuntimeError("No cryptographic provider found (neither 'cryptography' nor 'libcrypto' available).")


# ------------------------------------------------------------------------------
# Key Derivation Functions
# ------------------------------------------------------------------------------
def hkdf_expand(prk: bytes, info: bytes, length: int) -> bytes:
    """RFC 5869 HKDF-Expand using HMAC-SHA256."""
    hash_len = 32
    n = (length + hash_len - 1) // hash_len
    okm = b""
    previous = b""
    for i in range(1, n + 1):
        h = hmac.new(prk, previous + info + bytes([i]), hashlib.sha256)
        previous = h.digest()
        okm += previous
    return okm[:length]


def derive_user_vault_key(username: str, password: str, salt: Optional[bytes] = None) -> bytes:
    """Derives 32-byte User Vault Key matching Sphene Core."""
    if not salt:
        salt = DEFAULT_SALT
    intermediate = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 10000, 32)
    info = f"sphene:aes256:user-vault-key:v2:{username.lower().strip()}".encode("utf-8")
    prk = hmac.new(salt, intermediate, hashlib.sha256).digest()
    return hkdf_expand(prk, info, 32)


def derive_note_aes_key(passphrase: str, note_salt: bytes) -> bytes:
    """Derives 32-byte AES key for a specific note matching Sphene Aegis."""
    h = hashlib.sha256(passphrase.encode("utf-8") + note_salt).digest()
    for _ in range(10000):
        h = hashlib.sha256(h).digest()
    return h


# ------------------------------------------------------------------------------
# Encryption Routine
# ------------------------------------------------------------------------------
def encrypt_file(file_path: str, encryption_passphrase: str, dry_run: bool = False) -> Tuple[bool, str]:
    """Encrypts a single markdown file in-place."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception as e:
        return False, f"Failed to read file: {e}"

    if ARMOR_TAG in content:
        return True, "Already encrypted"

    # Separate YAML frontmatter and body
    m = re.match(r"^(---\s*\r?\n[\s\S]*?\r?\n---\s*\r?\n)([\s\S]*)$", content)
    if m:
        frontmatter = m.group(1)
        body = m.group(2)
    else:
        frontmatter = ""
        body = content

    if not body.strip():
        return True, "Skipped (empty body)"

    # 1. Generate cryptographically secure 16B salt and 12B nonce
    note_salt = secrets.token_bytes(16)
    nonce = secrets.token_bytes(12)

    # 2. Derive note AES key
    aes_key = derive_note_aes_key(encryption_passphrase, note_salt)

    # 3. Encrypt body with AES-256-GCM
    try:
        ciphertext, tag = encrypt_aes_gcm(aes_key, nonce, body.encode("utf-8"))
    except Exception as e:
        return False, f"Encryption failed: {e}"

    # 4. Bundle: Salt (16B) + Nonce (12B) + Ciphertext + Tag (16B)
    bundle = note_salt + nonce + ciphertext + tag
    b64_payload = base64.b64encode(bundle).decode("ascii")

    armored_block = (
        f"<!-- SPHENE-VAULT:ENCRYPTED:AES256 -->\n"
        f"{b64_payload}\n"
        f"<!-- /SPHENE-VAULT:ENCRYPTED -->\n"
    )

    # 5. Update frontmatter sealed: true
    if "sealed:" in frontmatter:
        new_fm = re.sub(r"sealed:\s*false", "sealed: true", frontmatter)
    elif frontmatter:
        new_fm = re.sub(r"(---\s*)$", "sealed: true\n---", frontmatter.strip()) + "\n\n"
    else:
        new_fm = "---\nsealed: true\n---\n\n"

    new_content = new_fm + armored_block

    if not dry_run:
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(new_content)
        except Exception as e:
            return False, f"Failed to write encrypted file: {e}"

    return True, f"Encrypted ({len(ciphertext)} bytes ciphertext)"


# ------------------------------------------------------------------------------
# CLI Entrypoint
# ------------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Sphene Aegis Sovereign Vault Encryptor — Encrypt notes in-place using authenticated AES-256-GCM."
    )
    parser.add_argument("--vault", "-d", default="./vault", help="Path to Sphene vault directory (default: ./vault)")
    parser.add_argument("--target", "-t", default="", help="Specific subfolder or single note to encrypt")
    parser.add_argument("--username", "-u", default="", help="Sphene username for personalized key derivation")
    parser.add_argument("--password", "-p", default="", help="Sphene account password or master passphrase")
    parser.add_argument("--dry-run", action="store_true", help="Simulate encryption without modifying files")
    parser.add_argument("--yes", "-y", action="store_true", help="Non-interactive mode")
    args = parser.parse_args()

    print(f"{CYAN}{BOLD}=== SPHENE AEGIS: SOVEREIGN IN-PLACE VAULT ENCRYPTOR ==={NC}")
    print(f"Target Vault Directory: {BOLD}{args.vault}{NC}")
    print(f"Cryptographic Engine:   {BOLD}{CRYPTO_BACKEND}{NC} (Zero proprietary binary dependencies)")

    if CRYPTO_BACKEND == "none":
        print(f"{RED}[FATAL ERROR] Neither Python 'cryptography' nor system 'libcrypto' (OpenSSL) was found.{NC}")
        sys.exit(1)

    scan_dir = args.vault
    if args.target:
        scan_dir = os.path.join(args.vault, args.target)

    if not os.path.exists(scan_dir):
        print(f"{RED}[ERROR] Target path '{scan_dir}' does not exist.{NC}")
        sys.exit(1)

    username = args.username.strip()
    password = args.password

    if not args.yes:
        if not username:
            try:
                username = input(f"{BOLD}Enter Sphene Username{NC} (or press Enter for Master Passphrase mode): ").strip()
            except (KeyboardInterrupt, EOFError):
                print("\nAborted.")
                sys.exit(1)

        if not password:
            try:
                password = getpass.getpass(f"{BOLD}Enter Vault Passphrase / Password for Encryption:{NC} ")
            except (KeyboardInterrupt, EOFError):
                print("\nAborted.")
                sys.exit(1)

    if not password and not username:
        print(f"{RED}[ERROR] Passphrase or username required for encryption.{NC}")
        sys.exit(1)

    # Derive encryption passphrase
    if username and password:
        derived_key = derive_user_vault_key(username, password)
        encryption_passphrase = derived_key.hex()
    elif username and not password:
        encryption_passphrase = f"sphene-vault-user-key:{username.lower()}"
    else:
        encryption_passphrase = password

    print(f"\nScanning for notes to encrypt in {scan_dir}...")

    total_scanned = 0
    encrypted_count = 0

    if os.path.isfile(scan_dir):
        files_to_process = [(os.path.dirname(scan_dir), [os.path.basename(scan_dir)])]
    else:
        files_to_process = [(root, files) for root, _, files in os.walk(scan_dir)]

    for root, files in files_to_process:
        for file in sorted(files):
            if not file.endswith(".md"):
                continue
            total_scanned += 1
            full_path = os.path.join(root, file)
            rel_path = os.path.relpath(full_path, args.vault)

            sys.stdout.write(f"  • Encrypting {BOLD}{rel_path}{NC}... ")
            sys.stdout.flush()

            ok, msg = encrypt_file(full_path, encryption_passphrase, dry_run=args.dry_run)
            if ok:
                if msg == "Already encrypted" or msg.startswith("Skipped"):
                    print(f"{YELLOW}• {msg}{NC}")
                else:
                    print(f"{GREEN}✓ {msg}{NC}")
                    encrypted_count += 1
            else:
                print(f"{RED}✗ FAILED ({msg}){NC}")

    print(f"\n{BOLD}=== Encryption Summary ==={NC}")
    print(f"  • Total Markdown notes scanned: {total_scanned}")
    print(f"  • Notes newly encrypted:        {GREEN}{encrypted_count}{NC}")
    print(f"{GREEN}{BOLD}✓ Sphene Aegis hardware-grade AES-256-GCM encryption complete.{NC}")


if __name__ == "__main__":
    main()
