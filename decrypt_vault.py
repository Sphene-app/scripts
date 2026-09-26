#!/usr/bin/env python3
"""
Sphene Aegis — Standalone Zero-Lock-In Vault Decryptor
=====================================================
Sovereign cryptographic emergency recovery tool.
Decrypts all Sphene AES-256-GCM armored Markdown notes in-place without needing
the Sphene daemon, runtime, or any proprietary binary.

Requirements:
  - Python 3.8+ (standard library only; uses 'libcrypto' via ctypes or 'cryptography' if installed)
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
import sqlite3
from typing import Optional, Tuple, List

# ANSI Colors
BOLD = "\033[1m"
GREEN = "\033[0;32m"
CYAN = "\033[0;36m"
YELLOW = "\033[1;33m"
RED = "\033[0;31m"
NC = "\033[0m"

ARMOR_PATTERN = re.compile(
    r"(<!-- SPHENE-VAULT:ENCRYPTED:AES256 -->\s*)([A-Za-z0-9+/=\s]+)(\s*<!-- /SPHENE-VAULT:ENCRYPTED -->)"
)

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

            lib.EVP_DecryptInit_ex.restype = ctypes.c_int
            lib.EVP_DecryptInit_ex.argtypes = [
                ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_char_p, ctypes.c_char_p
            ]

            lib.EVP_DecryptUpdate.restype = ctypes.c_int
            lib.EVP_DecryptUpdate.argtypes = [
                ctypes.c_void_p, ctypes.c_char_p, ctypes.POINTER(ctypes.c_int), ctypes.c_char_p, ctypes.c_int
            ]

            lib.EVP_CIPHER_CTX_ctrl.restype = ctypes.c_int
            lib.EVP_CIPHER_CTX_ctrl.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_char_p]

            lib.EVP_DecryptFinal_ex.restype = ctypes.c_int
            lib.EVP_DecryptFinal_ex.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.POINTER(ctypes.c_int)]

            LIBCRYPTO = lib
            CRYPTO_BACKEND = "ctypes"
        except Exception:
            CRYPTO_BACKEND = "none"


def decrypt_aes_gcm(key: bytes, nonce: bytes, ciphertext: bytes, tag: bytes) -> Optional[bytes]:
    """Decrypts ciphertext with AES-256-GCM using either cryptography or ctypes."""
    if CRYPTO_BACKEND == "cryptography":
        try:
            aesgcm = AESGCM(key)
            return aesgcm.decrypt(nonce, ciphertext + tag, None)
        except Exception:
            return None

    elif CRYPTO_BACKEND == "ctypes":
        try:
            ctx = LIBCRYPTO.EVP_CIPHER_CTX_new()
            cipher = LIBCRYPTO.EVP_aes_256_gcm()

            LIBCRYPTO.EVP_DecryptInit_ex(ctx, cipher, None, None, None)
            LIBCRYPTO.EVP_DecryptInit_ex(ctx, None, None, key, nonce)

            out_buf = ctypes.create_string_buffer(len(ciphertext) + 32)
            out_len = ctypes.c_int(0)
            LIBCRYPTO.EVP_DecryptUpdate(ctx, out_buf, ctypes.byref(out_len), ciphertext, len(ciphertext))

            # EVP_CTRL_AEAD_SET_TAG = 0x11
            LIBCRYPTO.EVP_CIPHER_CTX_ctrl(ctx, 0x11, len(tag), tag)

            final_len = ctypes.c_int(0)
            ptr_tail = ctypes.addressof(out_buf) + out_len.value
            ret = LIBCRYPTO.EVP_DecryptFinal_ex(ctx, ctypes.c_char_p(ptr_tail), ctypes.byref(final_len))
            LIBCRYPTO.EVP_CIPHER_CTX_free(ctx)

            if ret > 0:
                total_len = out_len.value + final_len.value
                return out_buf.raw[:total_len]
            return None
        except Exception:
            return None

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
    """
    Derives 32-byte User Vault Key matching Sphene Core Go implementation:
    1. PBKDF2-HMAC-SHA256 (10,000 rounds)
    2. HKDF-SHA256 expansion bound to 'sphene:aes256:user-vault-key:v2:<username>'
    """
    if not salt:
        salt = DEFAULT_SALT
    intermediate = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 10000, 32)
    info = f"sphene:aes256:user-vault-key:v2:{username.lower().strip()}".encode("utf-8")
    prk = hmac.new(salt, intermediate, hashlib.sha256).digest()
    return hkdf_expand(prk, info, 32)


def derive_note_aes_key(passphrase: str, note_salt: bytes) -> bytes:
    """
    Derives 32-byte AES key for a specific note matching Sphene Aegis:
    Key = SHA-256(passphrase + note_salt) then 10,000 recursive SHA-256 rounds.
    """
    h = hashlib.sha256(passphrase.encode("utf-8") + note_salt).digest()
    for _ in range(10000):
        h = hashlib.sha256(h).digest()
    return h


def lookup_user_salt_from_db(vault_dir: str, username: str) -> Optional[bytes]:
    """Inspects vault/.sphene/index.db for registered user salt if available."""
    db_candidates = [
        os.path.join(vault_dir, ".sphene", "index.db"),
        os.path.join(vault_dir, ".sphene", "auth.db"),
    ]
    for db_path in db_candidates:
        if os.path.isfile(db_path):
            try:
                conn = sqlite3.connect(db_path)
                cur = conn.cursor()
                cur.execute("SELECT salt FROM auth_users WHERE LOWER(username) = LOWER(?)", (username,))
                row = cur.fetchone()
                conn.close()
                if row and row[0]:
                    return bytes.fromhex(row[0])
            except Exception:
                pass
    return None


# ------------------------------------------------------------------------------
# Decryption Routine
# ------------------------------------------------------------------------------
def decrypt_file(file_path: str, candidate_passphrases: List[str], dry_run: bool = False) -> Tuple[bool, str]:
    """Decrypts a single armored markdown file."""
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
    except Exception as e:
        return False, f"Failed to read file: {e}"

    m = ARMOR_PATTERN.search(content)
    if not m:
        return True, "Not armored"

    clean_b64 = "".join(m.group(2).split())
    try:
        raw_payload = base64.b64decode(clean_b64)
    except Exception as e:
        return False, f"Invalid base64 payload: {e}"

    if len(raw_payload) < 44:  # 16 (salt) + 12 (nonce) + 0 (min cipher) + 16 (tag)
        return False, "Ciphertext payload truncated (<44 bytes)"

    note_salt = raw_payload[:16]
    nonce = raw_payload[16:28]
    ciphertext = raw_payload[28:-16]
    tag = raw_payload[-16:]

    decrypted_bytes = None
    successful_candidate = None

    for candidate in candidate_passphrases:
        if not candidate:
            continue
        aes_key = derive_note_aes_key(candidate, note_salt)
        res = decrypt_aes_gcm(aes_key, nonce, ciphertext, tag)
        if res is not None:
            decrypted_bytes = res
            successful_candidate = candidate
            break

    if decrypted_bytes is None:
        return False, "Incorrect credentials or authentication tag verification failed"

    decrypted_text = decrypted_bytes.decode("utf-8", errors="replace")

    # Replace armored block with plaintext
    new_content = content[: m.start()] + decrypted_text + content[m.end() :]

    # Update frontmatter sealed: true -> sealed: false
    new_content = re.sub(r"sealed:\s*true", "sealed: false", new_content)

    if not dry_run:
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(new_content)
        except Exception as e:
            return False, f"Failed to write decrypted file: {e}"

    return True, f"Decrypted ({len(decrypted_bytes)} bytes)"


# ------------------------------------------------------------------------------
# CLI Entrypoint
# ------------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(
        description="Sphene Aegis Sovereign Vault Decryptor — Decrypt notes in-place without Sphene installed."
    )
    parser.add_argument("--vault", "-d", default="./vault", help="Path to Sphene vault directory (default: ./vault)")
    parser.add_argument("--username", "-u", default="", help="Sphene username (e.g. admin, alice)")
    parser.add_argument("--password", "-p", default="", help="Sphene account password or master passphrase")
    parser.add_argument("--master-key", "-m", default="", help="Custom master cipher key (if configured)")
    parser.add_argument("--dry-run", action="store_true", help="Simulate decryption without modifying files")
    parser.add_argument("--yes", "-y", action="store_true", help="Non-interactive mode")
    args = parser.parse_args()

    print(f"{CYAN}{BOLD}=== SPHENE AEGIS: SOVEREIGN IN-PLACE VAULT DECRYPTOR ==={NC}")
    print(f"Target Vault Directory: {BOLD}{args.vault}{NC}")
    print(f"Cryptographic Engine:   {BOLD}{CRYPTO_BACKEND}{NC} (Zero proprietary binary dependencies)")

    if CRYPTO_BACKEND == "none":
        print(f"{RED}[FATAL ERROR] Neither Python 'cryptography' nor system 'libcrypto' (OpenSSL) was found.{NC}")
        print("Please ensure OpenSSL is installed on your OS or run: pip install cryptography")
        sys.exit(1)

    if not os.path.isdir(args.vault):
        print(f"{RED}[ERROR] Directory '{args.vault}' does not exist.{NC}")
        sys.exit(1)

    # Interactive prompts if arguments omitted
    username = args.username.strip()
    password = args.password
    master_key = args.master_key.strip()

    if not args.yes:
        if not username:
            try:
                username = input(f"{BOLD}Enter Sphene Username{NC} (or press Enter to skip): ").strip()
            except (KeyboardInterrupt, EOFError):
                print("\nAborted.")
                sys.exit(1)

        if not password:
            try:
                password = getpass.getpass(f"{BOLD}Enter Sphene Password / Vault Passphrase:{NC} ")
            except (KeyboardInterrupt, EOFError):
                print("\nAborted.")
                sys.exit(1)

    # Assemble candidate passphrases
    candidate_passphrases: List[str] = []

    if username:
        # 1. Fallback username key
        candidate_passphrases.append(f"sphene-vault-user-key:{username.lower()}")

    if password:
        # 2. Raw password as master passphrase
        candidate_passphrases.append(password)

        if username:
            # 3. UserVaultKey with DB salt (if found)
            db_salt = lookup_user_salt_from_db(args.vault, username)
            if db_salt:
                derived_db = derive_user_vault_key(username, password, db_salt)
                candidate_passphrases.append(derived_db.hex())

            # 4. UserVaultKey with default salt
            derived_default = derive_user_vault_key(username, password, DEFAULT_SALT)
            candidate_passphrases.append(derived_default.hex())

    if master_key:
        candidate_passphrases.append(master_key)

    # 5. Default master keys
    candidate_passphrases.append(DEFAULT_MASTER_KEY)
    candidate_passphrases.append("sphene-master-cipher-vault-key")
    candidate_passphrases.append("sphene-vault-default-user-key")

    print(f"\nScanning for armored notes in {args.vault}...")

    total_scanned = 0
    armored_found = 0
    success_count = 0
    failed_count = 0

    for root, _, files in os.walk(args.vault):
        for file in sorted(files):
            if not file.endswith(".md"):
                continue
            total_scanned += 1
            full_path = os.path.join(root, file)
            rel_path = os.path.relpath(full_path, args.vault)

            # Check if file has armor tag
            try:
                with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                    content_head = f.read(512)
            except Exception:
                continue

            if "<!-- SPHENE-VAULT:ENCRYPTED:AES256 -->" in content_head:
                armored_found += 1
                sys.stdout.write(f"  • Decrypting {BOLD}{rel_path}{NC}... ")
                sys.stdout.flush()

                ok, msg = decrypt_file(full_path, candidate_passphrases, dry_run=args.dry_run)
                if ok:
                    print(f"{GREEN}✓ {msg}{NC}")
                    success_count += 1
                else:
                    print(f"{RED}✗ FAILED ({msg}){NC}")
                    failed_count += 1

    print(f"\n{BOLD}=== Decryption Summary ==={NC}")
    print(f"  • Total Markdown notes scanned: {total_scanned}")
    print(f"  • Encrypted notes detected:     {armored_found}")
    print(f"  • Successfully decrypted:       {GREEN}{success_count}{NC}")

    if failed_count > 0:
        print(f"  • Decryption failures:          {RED}{failed_count}{NC}")
        print(f"\n{YELLOW}[TIP] Verify your username and password, or provide custom master key via --master-key.{NC}")
        sys.exit(1)
    elif armored_found == 0:
        print(f"{GREEN}✓ No encrypted notes found. All notes are already plain human-readable Markdown!{NC}")
    else:
        mode_str = " (dry run)" if args.dry_run else ""
        print(f"{GREEN}{BOLD}✓ 100% of encrypted notes successfully decrypted in-place!{mode_str}{NC}")
        print("All notes are now open standard Markdown files accessible by any text editor or tool.")


if __name__ == "__main__":
    main()
