# Sphene Sovereign Automation & Cryptographic Toolkit

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Protocol: AES-256-GCM](https://img.shields.io/badge/Security-AES--256--GCM-green.svg)](https://sphene.app)
[![Zero Proprietary Binaries](https://img.shields.io/badge/Dependencies-Zero%20Proprietary%20Binaries-purple.svg)](https://sphene.app)

The official open-source repository hosting the **Sphene Core Installer**, **Sovereign Zero-Lock-In Decryptor**, **In-Place Vault Encryptor**, and **1-Click Vault Migration Tools**.

Sphene Core is a compiled, high-performance private engine. However, **your knowledge and notes are 100% self-sovereign**. This repository ensures that every user and every AI agent can inspect the exact cryptographic algorithms protecting your data, verify data integrity, and decrypt entire vaults back into standard plain Markdown without Sphene installed.

---

## Repository Contents

| Script | Language | Purpose | Zero Binary Dependency |
|---|---|---|---|
| [`install.sh`](install.sh) | Bash | Official 1-click installer and updater for Sphene Core daemon & service | Yes |
| [`decrypt.sh`](decrypt.sh) | Bash | Interactive shell wrapper for in-place emergency vault decryption | Yes |
| [`decrypt_vault.py`](decrypt_vault.py) | Python 3 | Pure Python/ctypes AES-256-GCM decryptor (zero pip dependencies) | Yes |
| [`encrypt.sh`](encrypt.sh) | Bash | Interactive shell wrapper for in-place hardware-grade vault encryption | Yes |
| [`encrypt_vault.py`](encrypt_vault.py) | Python 3 | Pure Python/ctypes AES-256-GCM encryptor (zero pip dependencies) | Yes |
| [`migrate_vault.sh`](migrate_vault.sh) | Bash | 1-click migration wrapper for standard desktop Markdown vaults | Yes |
| [`migrate_vault.py`](migrate_vault.py) | Python 3 | Non-destructive importer preserving wikilinks, tags, and media | Yes |

---

## 1. Quickstart: Install Sphene Core

Install or upgrade Sphene Core on any Linux or macOS machine with a single command:

```bash
curl -fsSL https://raw.githubusercontent.com/Sphene-app/scripts/main/install.sh | bash
```

### What `install.sh` Does:
1. **Hardware & Architecture Detection:** Automatically detects x86_64, aarch64/ARM64, and Apple Silicon.
2. **Environment Selection:** Installs either as a native compiled systemd service (`/usr/local/bin/sphene`) or as an isolated Docker container (`ghcr.io/sphene-org/sphene:latest`).
3. **Non-Destructive Migration:** Detects existing Markdown notes and safely imports a copy into your sovereign knowledge directory.
4. **Agent Integration:** Automatically detects Hermes Agent or MCP-compatible clients and registers native toolsets.
5. **Zero Telemetry:** Configures a private local daemon bound strictly to `127.0.0.1:8743` (<25MB RAM footprint).

To run unattended in CI/CD or automated scripts:
```bash
curl -fsSL https://raw.githubusercontent.com/Sphene-app/scripts/main/install.sh | bash -s -- --yes
```

---

## 2. Zero-Lock-In Guarantee: Standalone Vault Decryption

> [!IMPORTANT]
> **The Desert Island Test:** If Sphene company ceases to exist, our servers vanish, or you are stuck on a deserted island with only a standard Linux/macOS terminal, **you can decrypt all your notes with standard open-source tools.**

You do **NOT** need Sphene installed. You only need:
1. Your Sphene **Username** and **Password** (or your Vault Master Passphrase).
2. Standard Python 3 (installed by default on macOS, Ubuntu, Debian, Fedora, Arch, WSL).

### Usage

Run the interactive Bash decryptor:

```bash
./decrypt.sh
```

Or invoke the Python decryptor directly:

```bash
# Interactive mode (prompts securely for password)
python3 decrypt_vault.py --vault ./vault

# Non-interactive / CLI mode
python3 decrypt_vault.py --vault ./vault --username admin --password "your_password" --yes

# Dry-run mode (verifies authentication and decryptability without modifying files on disk)
python3 decrypt_vault.py --vault ./vault --dry-run
```

### How It Works:
1. Scans the target vault directory for all `.md` files containing armored ciphertext envelopes.
2. Unpacks the 16-byte cryptographic salt, 12-byte nonce, ciphertext, and 16-byte GCM authentication tag.
3. Derives the 256-bit decryption key using the open algorithm defined below.
4. Authenticates the payload with AES-256-GCM.
5. In-place restores the original plain Markdown text, removing armored envelopes and updating frontmatter `sealed: false`.

---

## 3. Cryptographic Specification (Sphene Aegis)

Sphene uses authenticated, hardware-grade encryption based on NIST standards. The entire cryptographic pipeline is open and inspectable.

### 3.1 Armored Envelope Format
Encrypted notes on disk are wrapped in transparent HTML comment boundaries:

```markdown
---
title: Confidential Project
sealed: true
---

<!-- SPHENE-VAULT:ENCRYPTED:AES256 -->
xtiTXxrmNxOFXBVr2RSRf6tf0gtW3iV7o1A4wULN72RXLRkUUVvrHP7MdexjgBOXQMWM+OwFrwTLf911tDI3ZANGf...
<!-- /SPHENE-VAULT:ENCRYPTED -->
```

### 3.2 Binary Payload Layout
Decoding the Base64 content yields a packed binary bundle:

```
+------------------+-------------------+----------------------------+-----------------------+
|  Salt (16 Bytes) |  Nonce (12 Bytes) |  Ciphertext (Var. Length)  |  Auth Tag (16 Bytes)  |
+------------------+-------------------+----------------------------+-----------------------+
| 0.............15 | 16.............27 | 28...................(N-16)| (N-15)..............N |
+------------------+-------------------+----------------------------+-----------------------+
```

- **Salt (16 bytes):** Cryptographically secure pseudorandom salt generated per note via CSPRNG (`crypto/rand`).
- **Nonce/IV (12 bytes):** Unique 96-bit initialization vector required for AES-GCM.
- **Ciphertext:** Plaintext Markdown body encrypted under AES-256-GCM.
- **Authentication Tag (16 bytes):** 128-bit Galois Field GHASH authentication tag verifying integrity. Any single bit modification causes decryption to immediately fail.

### 3.3 Key Derivation Architecture

Sphene employs a two-tier key derivation model ensuring user privacy and cryptographic isolation:

```
[ User Password ] ──┐
                    ├──> [ PBKDF2-HMAC-SHA256 (10,000 Rounds) ] ──> Intermediate Key (32B)
[ User Salt ] ──────┘                                                      │
                                                                           │
[ Info: "sphene:aes256:user-vault-key:v2:<username>" ] ────────────────────┴──> [ HKDF-SHA256 Expand ]
                                                                                       │
                                                                                       ▼
                                                                             User Vault Key (32B)
                                                                                       │
┌──────────────────────────────────────────────────────────────────────────────────────┘
│
▼
[ User Vault Key (Hex) ] ──┐
                           ├──> [ SHA-256(Key + NoteSalt) ] ──> [ 10,000 Recursive SHA-256 Rounds ]
[ Note Salt (16B) ] ───────┘                                                   │
                                                                               ▼
                                                                    Note AES-256 Key (32B)
                                                                               │
                                                                               ▼
                                                                   [ AES-256-GCM Decrypt ]
```

1. **User Key Derivation (PBKDF2 + HKDF):**
   - **Salt:** 16-byte hex salt assigned to the user profile, or default fallback `sphene-vault-default-salt-v2`.
   - **PBKDF2:** 10,000 iterations of HMAC-SHA256 yielding a 32-byte intermediate key.
   - **HKDF Expansion:** Bound cryptographically to the username namespace via info context string `sphene:aes256:user-vault-key:v2:<username>`.
2. **Note Key Derivation:**
   - The user vault key (or master passphrase) is combined with the note-specific 16-byte salt.
   - Passed through 10,000 recursive SHA-256 hashing rounds to produce the final 32-byte AES-256 key.

---

## 4. Standalone Vault Encryptor (`encrypt.sh`)

To encrypt sensitive notes directly on disk using the exact same hardware-grade format:

```bash
./encrypt.sh
```

Or via Python:
```bash
python3 encrypt_vault.py --vault ./vault --target "Private" --username admin --password "secret"
```

---

## 5. 1-Click Vault Migration (`migrate_vault.sh`)

Seamlessly import existing desktop Markdown notes or `.zip` archives into Sphene without modifying original files:

```bash
./migrate_vault.sh /path/to/desktop/vault [destination_sphene_vault]
```

- **Preserves Hierarchy:** Recreates your directory trees inside `Workspace/`.
- **Media Ingestion:** Automatically copies and remaps attachments, images, and PDFs to `attachments/`.
- **Markdown Integrity:** Preserves YAML frontmatter, `#tags`, `[[Wikilinks]]`, and task checklists (`- [ ]`).
- **Index Rebuild:** Triggers an immediate SQLite FTS5 index sync if Sphene CLI is present.

---

## 6. Zero-Dependency Guarantee & Auditability

This repository is designed with zero external third-party requirements:
- No `npm install`, no `cargo build`, no binary compilers needed.
- `decrypt_vault.py` and `encrypt_vault.py` automatically utilize the system C library (`libcrypto.so` on Linux, `libcrypto.dylib` on macOS) via Python's built-in `ctypes` module if `cryptography` is not installed.
- Can be audited, executed, and validated by any human security researcher or autonomous AI agent.

---

## License

This repository is licensed under the **[MIT License](LICENSE)**. You are free to inspect, fork, embed, and redistribute these scripts without restrictions.
