#!/usr/bin/env bash
# ==============================================================================
#  SPHENE AEGIS — ZERO-LOCK-IN IN-PLACE VAULT DECRYPTOR
#  Sovereign, open-source bash recovery tool.
#  Decrypts all hardware-sealed AES-256-GCM notes in your vault back to plain Markdown.
#  Can be run on ANY OS (Linux, macOS, WSL) even if Sphene is completely deleted!
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
echo -e "${CYAN}${BOLD}     SPHENE AEGIS — SOVEREIGN ZERO-LOCK-IN VAULT DECRYPTOR (BASH)     ${NC}"
echo -e "${CYAN}${BOLD}==============================================================================${NC}"
echo -e "Your data is 100% self-sovereign. If you stop using Sphene or uninstall the app,"
echo -e "this script decrypts all your notes back to open standard Markdown in-place."
echo -e ""

# Verify Python 3 presence
if ! command -v python3 >/dev/null 2>&1; then
  echo -e "${RED}[FATAL ERROR] python3 is required to run the AES-256-GCM cryptographic routines.${NC}"
  echo "Please install python3 on your system (standard on macOS, Ubuntu, Debian, Fedora, Arch)."
  exit 1
fi

VAULT_DIR="${1}"
USERNAME="${2}"
PASSWORD="${3}"

if [ -z "$VAULT_DIR" ]; then
  read -r -p "Enter path to Sphene vault directory [default: ./vault]: " INPUT_VAULT
  VAULT_DIR="${INPUT_VAULT:-./vault}"
fi

if [ ! -d "$VAULT_DIR" ]; then
  echo -e "${RED}[ERROR] Vault directory '${VAULT_DIR}' does not exist.${NC}"
  exit 1
fi

if [ -z "$USERNAME" ]; then
  read -r -p "Enter Sphene Username (or press Enter to skip): " USERNAME
fi

if [ -z "$PASSWORD" ]; then
  read -s -p "Enter Sphene Password / Vault Passphrase: " PASSWORD
  echo ""
fi

# Run the standalone open-source Python cryptographic recovery engine
exec python3 "${SCRIPT_DIR}/decrypt_vault.py" \
  --vault "${VAULT_DIR}" \
  --username "${USERNAME}" \
  --password "${PASSWORD}" \
  --yes
