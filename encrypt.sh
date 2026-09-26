#!/usr/bin/env bash
# ==============================================================================
#  SPHENE AEGIS — IN-PLACE VAULT ENCRYPTOR
#  Sovereign, open-source bash encryption tool.
#  Hardware-seals notes on disk using authenticated AES-256-GCM without Sphene.
# ==============================================================================
set -e

BOLD='\033[1m'
CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo -e "${CYAN}${BOLD}==============================================================================${NC}"
echo -e "${CYAN}${BOLD}     SPHENE AEGIS — SOVEREIGN IN-PLACE VAULT ENCRYPTOR (BASH)     ${NC}"
echo -e "${CYAN}${BOLD}==============================================================================${NC}"

if ! command -v python3 >/dev/null 2>&1; then
  echo -e "${RED}[FATAL ERROR] python3 is required for AES-256-GCM cryptographic routines.${NC}"
  exit 1
fi

VAULT_DIR="${1}"
TARGET_PATH="${2}"
USERNAME="${3}"
PASSWORD="${4}"

if [ -z "$VAULT_DIR" ]; then
  read -r -p "Enter path to Sphene vault directory [default: ./vault]: " INPUT_VAULT
  VAULT_DIR="${INPUT_VAULT:-./vault}"
fi

if [ ! -d "$VAULT_DIR" ]; then
  echo -e "${RED}[ERROR] Vault directory '${VAULT_DIR}' does not exist.${NC}"
  exit 1
fi

if [ -z "$USERNAME" ]; then
  read -r -p "Enter Sphene Username (or press Enter for Master Passphrase mode): " USERNAME
fi

if [ -z "$PASSWORD" ]; then
  read -s -p "Enter Vault Passphrase / Password for Encryption: " PASSWORD
  echo ""
fi

exec python3 "${SCRIPT_DIR}/encrypt_vault.py" \
  --vault "${VAULT_DIR}" \
  --target "${TARGET_PATH}" \
  --username "${USERNAME}" \
  --password "${PASSWORD}" \
  --yes
