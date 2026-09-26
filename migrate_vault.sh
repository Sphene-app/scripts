#!/usr/bin/env bash
# ==============================================================================
#  SPHENE 1-CLICK VAULT MIGRATION CLI
#  Migrates standard desktop Markdown vaults to Sphene with 100% fidelity.
# ==============================================================================
set -e

BOLD='\033[1m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
RED='\033[0;31m'
NC='\033[0m'

SOURCE="${1}"
DEFAULT_DEST="${SPHENE_VAULT_DIR:-/DATA/AppData/sphene/vault}"
DEST="${2:-$DEFAULT_DEST}"

echo -e "${CYAN}${BOLD}=== SPHENE 1-CLICK VAULT MIGRATION ===${NC}"

if [ -z "$SOURCE" ]; then
  echo -e "${RED}[ERROR] Please provide source directory or .zip file.${NC}"
  echo "Usage: $0 <path_to_vault_or_zip> [destination_vault_dir]"
  exit 1
fi

if [ ! -e "$SOURCE" ]; then
  echo -e "${RED}[ERROR] Source '${SOURCE}' not found.${NC}"
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python3 "$SCRIPT_DIR/migrate_vault.py" "$SOURCE" --dest "$DEST"

# Rebuild search index if sphene CLI is available
if command -v sphene >/dev/null 2>&1; then
  sphene index 2>/dev/null || true
  echo -e "${GREEN}✓ Sphene search index rebuilt.${NC}"
fi

echo -e "${GREEN}${BOLD}✓ Migration complete! Refresh your browser to view your notes.${NC}"
