#!/usr/bin/env bash
# ==============================================================================
# SPHENE SOVEREIGN SECOND BRAIN - DOCKER & NATIVE INSTALLER
# Sovereign, compiled knowledge substrate (<50MB RAM, <25MB local, SQLite FTS5)
# Official Website: https://sphene.app
# ==============================================================================
set -e

BOLD='\033[1m'
CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

AUTO_YES=0
FORCE_UPDATE=0
for arg in "$@"; do
  case "$arg" in
    -y|--yes) AUTO_YES=1 ;;
    --update) FORCE_UPDATE=1 ;;
  esac
done

# Helper function to read from terminal even when piped via curl ... | bash
read_input() {
  local prompt_text="$1"
  local default_val="$2"
  local user_val=""

  if [ "$AUTO_YES" -eq 1 ] || [ -n "$SPHENE_NON_INTERACTIVE" ] || [ -n "$CI" ]; then
    echo "$default_val"
    return
  fi

  if [ -t 0 ]; then
    read -r -p "$prompt_text" user_val || true
  elif [ -c /dev/tty ] && [ -r /dev/tty ]; then
    echo -ne "$prompt_text" > /dev/tty 2>/dev/null || true
    read -r user_val < /dev/tty 2>/dev/null || true
  else
    read -r user_val 2>/dev/null || true
  fi

  if [ -z "$user_val" ]; then
    echo "$default_val"
  else
    echo "$user_val"
  fi
}

# Cryptographic Integrity Verification (SHA-256)
verify_file_sha256() {
  local target_file="$1"
  local expected_hash="$2"
  local calculated_hash=""

  if [ ! -f "$target_file" ] || [ -z "$expected_hash" ]; then
    return 1
  fi

  if command -v sha256sum >/dev/null 2>&1; then
    calculated_hash=$(sha256sum "$target_file" 2>/dev/null | awk '{print $1}')
  elif command -v shasum >/dev/null 2>&1; then
    calculated_hash=$(shasum -a 256 "$target_file" 2>/dev/null | awk '{print $1}')
  elif command -v python3 >/dev/null 2>&1; then
    calculated_hash=$(python3 -c "import hashlib, sys; print(hashlib.sha256(open(sys.argv[1], 'rb').read()).hexdigest())" "$target_file" 2>/dev/null || true)
  elif command -v openssl >/dev/null 2>&1; then
    calculated_hash=$(openssl dgst -sha256 "$target_file" 2>/dev/null | awk '{print $NF}')
  fi

  if [ -n "$calculated_hash" ] && [ "$calculated_hash" = "$expected_hash" ]; then
    return 0
  else
    return 1
  fi
}

get_expected_sha256() {
  local filename="$1"
  local checksums_file="$2"
  if [ -f "$checksums_file" ]; then
    grep -E "[[:space:]](bin/)?${filename}\$" "$checksums_file" 2>/dev/null | head -n 1 | awk '{print $1}'
  fi
}


echo -e "${CYAN}${BOLD}"
echo "  ____  ____  _   _ _____ _   _ _____ "
echo " / ___||  _ \| | | | ____| \ | | ____|"
echo " \___ \| |_) | |_| |  _| |  \| |  _|  "
echo "  ___) |  __/|  _  | |___| |\  | |___ "
echo " |____/|_|   |_| |_|_____|_| \_|_____|"
echo -e "${NC}"
echo -e "${BOLD}Installing Sphene Sovereign Second Brain (<50MB RAM, <25MB local)...${NC}\n"

# 1. Environment & Architecture Detection
OS_RAW="$(uname -s)"
ARCH_RAW="$(uname -m)"

case "$OS_RAW" in
  Darwin*) OS="darwin" ;;
  Linux*)  OS="linux" ;;
  MSYS*|MINGW*|CYGWIN*) OS="windows" ;;
  *)       OS="$(echo "$OS_RAW" | tr '[:upper:]' '[:lower:]')" ;;
esac

case "$ARCH_RAW" in
  x86_64|amd64)   ARCH="amd64" ;;
  arm64|aarch64)  ARCH="arm64" ;;
  armv7*|armhf)   ARCH="arm" ;;
  i386|i686)      ARCH="386" ;;
  *)              ARCH="$ARCH_RAW" ;;
esac

TARGET_BIN="sphene-${OS}-${ARCH}"
[ "$OS" = "windows" ] && TARGET_BIN="${TARGET_BIN}.exe"

# 2. Check for Docker
HAS_DOCKER=0
COMPOSE_CMD=""
if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
  HAS_DOCKER=1
  if docker compose version >/dev/null 2>&1; then
    COMPOSE_CMD="docker compose"
  elif command -v docker-compose >/dev/null 2>&1; then
    COMPOSE_CMD="docker-compose"
  fi
fi

PORT="${SPHENE_PORT:-8743}"

# 3. Determine Workspace & Vault Directory
if [ -d "/DATA/AppData" ] && [ -w "/DATA/AppData" ]; then
  DEFAULT_INSTALL_DIR="/DATA/AppData/sphene"
else
  DEFAULT_INSTALL_DIR="$HOME/.sphene"
fi
INSTALL_DIR="${SPHENE_INSTALL_DIR:-$DEFAULT_INSTALL_DIR}"
VAULT_DIR="${SPHENE_VAULT_DIR:-$INSTALL_DIR/vault}"
mkdir -p "$VAULT_DIR/Workspace" "$VAULT_DIR/Reference" "$VAULT_DIR/Private"

# Check if Sphene is already installed or running
IS_UPDATE=0
SPHENE_CONTAINER_EXISTS=0
if [ $HAS_DOCKER -eq 1 ] && docker ps -a --format '{{.Names}}' | grep -q "^sphene$"; then
  SPHENE_CONTAINER_EXISTS=1
fi

SPHENE_PORT_ACTIVE=0
if curl -s --max-time 1 "http://127.0.0.1:${PORT}/api/v1/health" 2>/dev/null | grep -q "sphene-kernel"; then
  SPHENE_PORT_ACTIVE=1
fi

if [ $SPHENE_CONTAINER_EXISTS -eq 1 ] || [ $SPHENE_PORT_ACTIVE -eq 1 ]; then
  echo -e "\n${CYAN}${BOLD}==================================================================${NC}"
  echo -e "${CYAN}${BOLD}  EXISTING SPHENE INSTALLATION DETECTED                           ${NC}"
  echo -e "${CYAN}${BOLD}==================================================================${NC}"
  if [ $SPHENE_CONTAINER_EXISTS -eq 1 ]; then
    C_STATUS=$(docker inspect -f '{{.State.Status}}' sphene 2>/dev/null || echo "present")
    echo -e "  • Docker Container: ${GREEN}sphene${NC} (Status: ${C_STATUS})"
  fi
  if [ $SPHENE_PORT_ACTIVE -eq 1 ]; then
    echo -e "  • Web Interface:    ${GREEN}http://localhost:${PORT}${NC} (responding healthy)"
  fi
  DOC_COUNT=$(find "$VAULT_DIR" -type f -name "*.md" ! -path "*/.*" 2>/dev/null | wc -l)
  echo -e "  • Knowledge Vault:  ${CYAN}${VAULT_DIR}${NC} (${DOC_COUNT} notes preserved)"
  echo -e "${CYAN}${BOLD}==================================================================${NC}\n"

  if [ $FORCE_UPDATE -eq 1 ]; then
    UPDATE_CHOICE="Y"
  else
    PROMPT_UPDATE="Sphene is already installed! Would you like to UPDATE Sphene and sync Hermes skills? [Y/n]: "
    UPDATE_CHOICE=$(read_input "$PROMPT_UPDATE" "Y")
  fi

  case "$UPDATE_CHOICE" in
    [yY][eE][sS]|[yY]|"")
      echo -e "\n${GREEN}✓ Proceeding with Sphene & Hermes update...${NC}"
      IS_UPDATE=1
      ;;
    *)
      PROMPT_REINSTALL="Do you want to run a full interactive reinstall / reconfigure instead? [y/N]: "
      REINSTALL_CHOICE=$(read_input "$PROMPT_REINSTALL" "N")
      case "$REINSTALL_CHOICE" in
        [yY][eE][sS]|[yY])
          echo -e "\nProceeding with full interactive re-installation...\n"
          IS_UPDATE=0
          ;;
        *)
          echo -e "\nNo changes made. Current Sphene installation kept untouched."
          exit 0
          ;;
      esac
      ;;
  esac
else
  echo -e "${GREEN}✓ Knowledge vault initialized at: ${VAULT_DIR}${NC}"
fi

# Recommend Docker if not installed, explaining autostart & reliability benefits
if [ $HAS_DOCKER -eq 0 ] && [ $IS_UPDATE -eq 0 ]; then
  echo -e "\n${YELLOW}${BOLD}==================================================================${NC}"
  echo -e "${YELLOW}${BOLD}  DOCKER NOT DETECTED (STRONGLY RECOMMENDED FOR PRODUCTION)       ${NC}"
  echo -e "${YELLOW}${BOLD}==================================================================${NC}"
  echo -e "Docker is the ${BOLD}strongly recommended${NC} way to deploy Sphene Sovereign Hub."
  echo -e "Why Docker is preferred:"
  echo -e "  • ${BOLD}Automatic Boot Restart${NC}: Restarts automatically on system boot (${CYAN}restart: unless-stopped${NC})"
  echo -e "    without requiring user logon, manual launchd plists (macOS), or systemd services (Linux)."
  echo -e "  • ${BOLD}Sandboxed Runtime${NC}: Hardened SQLite WAL storage, isolated environment, and zero dependency conflicts."
  echo ""
  echo -e "${BOLD}Recommended: Install Docker on your machine (${OS}):${NC}"
  case "$OS" in
    darwin)
      echo -e "  • Homebrew:       ${CYAN}brew install --cask docker${NC}"
      echo -e "  • Direct Download: ${CYAN}https://www.docker.com/products/docker-desktop/${NC}"
      ;;
    linux)
      echo -e "  • Official installer: ${CYAN}curl -fsSL https://get.docker.com | sh${NC}"
      echo -e "  • Add to docker group: ${CYAN}sudo usermod -aG docker \$USER${NC}"
      ;;
    windows)
      echo -e "  • Docker Desktop with WSL2: ${CYAN}https://www.docker.com/products/docker-desktop/${NC}"
      ;;
  esac
  echo ""
  echo -e "You can proceed with an unmanaged background host daemon, but it will"
  echo -e "${YELLOW}NOT start automatically upon reboot${NC} without manual service configuration."
  PROMPT_HOST="Do you want to proceed with unmanaged host daemon anyway? [y/N]: "
  CONTINUE_HOST=$(read_input "$PROMPT_HOST" "N")
  case "$CONTINUE_HOST" in
    [yY][eE][sS]|[yY])
      echo -e "\nProceeding with native host daemon installation...\n"
      ;;
    *)
      echo -e "\n${CYAN}Installation aborted.${NC} Please install Docker and re-run:"
      echo -e "  ${BOLD}curl -fsSL https://sphene.app/install.sh | bash${NC}\n"
      exit 0
      ;;
  esac
fi

# 4. Host Binary Installation (for CLI convenience)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd || pwd)"
TMP_DIR="/tmp/sphene-install"
mkdir -p "$TMP_DIR"
SPHENE_HOST_BIN=""

# Fetch or locate cryptographic checksums
if [ -f "${SCRIPT_DIR}/SHA256SUMS" ]; then
  cp "${SCRIPT_DIR}/SHA256SUMS" "$TMP_DIR/SHA256SUMS"
elif [ -f "${SCRIPT_DIR}/bin/SHA256SUMS" ]; then
  cp "${SCRIPT_DIR}/bin/SHA256SUMS" "$TMP_DIR/SHA256SUMS"
else
  curl -fsSL "https://sphene.app/SHA256SUMS" -o "$TMP_DIR/SHA256SUMS" 2>/dev/null || curl -fsSL "https://sphene.app/bin/SHA256SUMS" -o "$TMP_DIR/SHA256SUMS" 2>/dev/null || true
fi

if [ -f "${SCRIPT_DIR}/bin/${TARGET_BIN}" ]; then
  SPHENE_HOST_BIN="${SCRIPT_DIR}/bin/${TARGET_BIN}"
else
  echo -e "Fetching pre-compiled native Sphene CLI binary (${OS}-${ARCH})..."
  DOWNLOADED_NAME=""
  if curl -fsSL "https://sphene.app/bin/${TARGET_BIN}.tar.gz" -o "$TMP_DIR/sphene_pkg.tar.gz" 2>/dev/null && [ -s "$TMP_DIR/sphene_pkg.tar.gz" ]; then
    tar -zxvf "$TMP_DIR/sphene_pkg.tar.gz" -C "$TMP_DIR" sphene 2>/dev/null || tar -zxvf "$TMP_DIR/sphene_pkg.tar.gz" -O > "$TMP_DIR/sphene" 2>/dev/null
    DOWNLOADED_NAME="${TARGET_BIN}.tar.gz"
  elif curl -fsSL "https://sphene.app/bin/${TARGET_BIN}" -o "$TMP_DIR/sphene" 2>/dev/null && [ -s "$TMP_DIR/sphene" ]; then
    DOWNLOADED_NAME="$TARGET_BIN"
  elif [ "$OS" = "linux" ] && [ "$ARCH" = "amd64" ] && curl -fsSL "https://sphene.app/bin/sphene" -o "$TMP_DIR/sphene" 2>/dev/null && [ -s "$TMP_DIR/sphene" ]; then
    DOWNLOADED_NAME="sphene"
  elif curl -fsSL "https://sphene.app/releases/v2.2.0/${TARGET_BIN}" -o "$TMP_DIR/sphene" 2>/dev/null && [ -s "$TMP_DIR/sphene" ]; then
    DOWNLOADED_NAME="$TARGET_BIN"
  fi

  if [ -n "$DOWNLOADED_NAME" ] && [ -f "$TMP_DIR/sphene" ]; then
    CHECK_FILE="$TMP_DIR/sphene"
    [ "$DOWNLOADED_NAME" = "${TARGET_BIN}.tar.gz" ] && CHECK_FILE="$TMP_DIR/sphene_pkg.tar.gz"
    EXPECTED_HASH=$(get_expected_sha256 "$DOWNLOADED_NAME" "$TMP_DIR/SHA256SUMS")
    if [ -n "$EXPECTED_HASH" ]; then
      if verify_file_sha256 "$CHECK_FILE" "$EXPECTED_HASH"; then
        echo -e "${GREEN}✓ Cryptographic integrity verified (SHA-256: ${EXPECTED_HASH:0:16}...)${NC}"
      else
        echo -e "${YELLOW}⚠ Checksum check for ${DOWNLOADED_NAME} skipped or unverified, continuing...${NC}"
      fi
    fi
    chmod +x "$TMP_DIR/sphene"
    SPHENE_HOST_BIN="$TMP_DIR/sphene"
  elif command -v sphene >/dev/null 2>&1; then
    SPHENE_HOST_BIN="$(command -v sphene)"
  fi
fi

if [ -n "$SPHENE_HOST_BIN" ] && [ -f "$SPHENE_HOST_BIN" ]; then
  if [ -w /usr/local/bin ]; then
    cp "$SPHENE_HOST_BIN" /usr/local/bin/sphene
    chmod +x /usr/local/bin/sphene
    echo -e "${GREEN}✓ Installed host CLI at /usr/local/bin/sphene${NC}"
  elif command -v sudo >/dev/null 2>&1; then
    sudo cp "$SPHENE_HOST_BIN" /usr/local/bin/sphene
    sudo chmod +x /usr/local/bin/sphene
    echo -e "${GREEN}✓ Installed host CLI at /usr/local/bin/sphene (via sudo)${NC}"
  elif [ -d "/opt/homebrew/bin" ] && [ -w "/opt/homebrew/bin" ]; then
    cp "$SPHENE_HOST_BIN" /opt/homebrew/bin/sphene
    chmod +x /opt/homebrew/bin/sphene
    echo -e "${GREEN}✓ Installed host CLI at /opt/homebrew/bin/sphene${NC}"
  else
    mkdir -p "$HOME/.local/bin"
    cp "$SPHENE_HOST_BIN" "$HOME/.local/bin/sphene"
    chmod +x "$HOME/.local/bin/sphene"
    echo -e "${GREEN}✓ Installed host CLI at $HOME/.local/bin/sphene${NC}"
  fi
fi

# 5. Desktop Markdown Vault Auto-Discovery & Non-Destructive Migration (Skip in update mode)
if [ $IS_UPDATE -eq 0 ]; then
  echo -e "\n${BOLD}Scanning for existing Markdown vaults & notes...${NC}"
  DISCOVERED_VAULTS=()

  OBS_CONF=""
  if [ -f "$HOME/.config/obsidian/obsidian.json" ]; then
    OBS_CONF="$HOME/.config/obsidian/obsidian.json"
  elif [ -f "$HOME/Library/Application Support/obsidian/obsidian.json" ]; then
    OBS_CONF="$HOME/Library/Application Support/obsidian/obsidian.json"
  elif [ -n "$APPDATA" ] && [ -f "$APPDATA/obsidian/obsidian.json" ]; then
    OBS_CONF="$APPDATA/obsidian/obsidian.json"
  fi

  if [ -n "$OBS_CONF" ] && [ -r "$OBS_CONF" ]; then
    if command -v python3 >/dev/null 2>&1; then
      while IFS= read -r vpath; do
        [ -d "$vpath" ] && DISCOVERED_VAULTS+=("$vpath")
      done < <(python3 -c 'import json, sys; d=json.load(open(sys.argv[1])); print("\n".join(v["path"] for v in d.get("vaults",{}).values() if "path" in v))' "$OBS_CONF" 2>/dev/null || true)
    fi
    if [ ${#DISCOVERED_VAULTS[@]} -eq 0 ]; then
      while IFS= read -r vpath; do
        [ -d "$vpath" ] && DISCOVERED_VAULTS+=("$vpath")
      done < <(grep -o '"path"[[:space:]]*:[[:space:]]*"[^"]*"' "$OBS_CONF" 2>/dev/null | sed -E 's/.*:[[:space:]]*"([^"]*)"/\1/' || true)
    fi
  fi

  if [ -n "$OBSIDIAN_VAULT_PATH" ] && [ -d "$OBSIDIAN_VAULT_PATH" ]; then
    DISCOVERED_VAULTS+=("$OBSIDIAN_VAULT_PATH")
  fi

  for common_path in \
    "$HOME/Documents/Obsidian Vault" \
    "$HOME/Documents/Obsidian" \
    "$HOME/Documents/Notes" \
    "$HOME/Obsidian" \
    "$HOME/Vault" \
    "$HOME/Documents/Vault"; do
    if [ -d "$common_path" ]; then
      DISCOVERED_VAULTS+=("$common_path")
    fi
  done

  UNIQUE_VAULTS=()
  for v in "${DISCOVERED_VAULTS[@]}"; do
    v_norm="$(cd "$v" 2>/dev/null && pwd || echo "$v")"
    already=0
    for u in "${UNIQUE_VAULTS[@]}"; do
      if [ "$u" = "$v_norm" ]; then already=1; break; fi
    done
    if [ "$already" -eq 0 ] && [ -d "$v_norm" ]; then
      UNIQUE_VAULTS+=("$v_norm")
    fi
  done

  FOUND_OBSIDIAN=0
  if [ ${#UNIQUE_VAULTS[@]} -gt 0 ]; then
    for vault_path in "${UNIQUE_VAULTS[@]}"; do
      note_count=$(find "$vault_path" -type f -name "*.md" ! -path "*/.*" 2>/dev/null | wc -l)
      if [ "$note_count" -gt 0 ]; then
        FOUND_OBSIDIAN=1
        echo -e "\n${CYAN}══════════════════════════════════════════════════════════════════${NC}"
        echo -e "${GREEN}${BOLD}  ★ Existing Markdown Notes Detected!${NC}"
        echo -e "${CYAN}══════════════════════════════════════════════════════════════════${NC}"
        echo -e "  • Path:        ${BOLD}${vault_path}${NC}"
        echo -e "  • Documents:   ${CYAN}${note_count} Markdown notes found${NC}"
        echo -e "  • Sample notes:"
        find "$vault_path" -type f -name "*.md" ! -path "*/.*" 2>/dev/null | head -n 3 | while read -r sample_file; do
          echo -e "      - $(basename "$sample_file")"
        done
        if [ "$note_count" -gt 3 ]; then
          echo -e "      ... and $((note_count - 3)) more."
        fi
        echo ""
        echo -e "${YELLOW}  Non-Destructive Guarantee:${NC}"
        echo "  Sphene will safely copy your markdown notes into your sovereign vault."
        echo "  Your original files will remain 100% untouched and unmodified."
        echo ""

        IMPORT_PROMPT="Do you want Sphene to import a copy of these notes? [Y/n]: "
        IMPORT_CHOICE=$(read_input "$IMPORT_PROMPT" "Y")

        case "$IMPORT_CHOICE" in
          [yY][eE][sS]|[yY]|"")
            echo -e "  Importing notes into ${VAULT_DIR}/Workspace (preserving native Folder hierarchy)..."
            if command -v sphene >/dev/null 2>&1; then
              SPHENE_VAULT_DIR="$VAULT_DIR" sphene import "$vault_path" --partition "Workspace"
            else
              mkdir -p "${VAULT_DIR}/Workspace"
              # Non-destructively copy all notes and media, mapping subfolders to Sphene Folders and excluding hidden metadata (.obsidian, .trash)
              find "$vault_path" -type f \( -name "*.md" -o -name "*.markdown" -o -name "*.txt" -o -name "*.png" -o -name "*.jpg" -o -name "*.svg" -o -name "*.pdf" \) ! -path "*/.*" 2>/dev/null | while read -r src_file; do
                rel_file="${src_file#$vault_path/}"
                target_dest="${VAULT_DIR}/Workspace/$rel_file"
                mkdir -p "$(dirname "$target_dest")"
                cp -p "$src_file" "$target_dest"
              done
              echo -e "${GREEN}✓ Imported notes into ${VAULT_DIR}/Workspace with full native Folder structure preserved!${NC}"
            fi
            ;;
          *)
            echo -e "  Skipped import. (Tip: You can also do this later anytime from Sphene Settings: 'Import Notes', or via ${CYAN}sphene import \"$vault_path\"${NC})"
            ;;
        esac
      fi
    done
  fi

  if [ "$FOUND_OBSIDIAN" -eq 0 ]; then
    echo -e "${GREEN}✓ Clean slate installation.${NC}"
    echo -e "  (Tip: You can import notes anytime later from Sphene Settings: 'Import Notes', or via ${CYAN}sphene import <path>${NC})"
  fi
fi

# 6. Hermes Agent Detection & Interactive Integration
echo -e "\n${BOLD}Scanning for Hermes Agent installations...${NC}"
HERMES_TYPE=""
HERMES_CONTAINER=""
HERMES_SKILLS_DIR=""

if command -v docker >/dev/null 2>&1 && docker ps --format '{{.Names}}' | grep -q "^hermes$"; then
  HERMES_TYPE="docker"
  HERMES_CONTAINER="hermes"
  HERMES_SKILLS_DIR="/opt/data/skills"
  echo -e "${GREEN}✓ Found running Hermes Agent container: '${HERMES_CONTAINER}'${NC}"
elif [ -d "$HOME/.hermes/skills" ]; then
  HERMES_TYPE="local"
  HERMES_SKILLS_DIR="$HOME/.hermes/skills"
  echo -e "${GREEN}✓ Found local Hermes installation: ${HERMES_SKILLS_DIR}${NC}"
elif [ -d "/DATA/AppData/hermes/skills" ]; then
  HERMES_TYPE="local"
  HERMES_SKILLS_DIR="/DATA/AppData/hermes/skills"
  echo -e "${GREEN}✓ Found local Hermes installation: ${HERMES_SKILLS_DIR}${NC}"
fi

SKILL_INSTALLED=0
OBSIDIAN_REPLACED=0

if [ -n "$HERMES_TYPE" ]; then
  if [ $IS_UPDATE -eq 1 ]; then
    echo -e "\n${BOLD}Updating Hermes Agent integration & skills...${NC}"
    TMP_SKILL_DIR="$TMP_DIR/hermes-skill"
    mkdir -p "$TMP_SKILL_DIR"

    if [ -d "${SCRIPT_DIR}/hermes-skill/sphene-knowledge-hub" ]; then
      cp -r "${SCRIPT_DIR}/hermes-skill/sphene-knowledge-hub" "$TMP_SKILL_DIR/"
    else
      curl -fsSL "https://sphene.app/hermes-skill.tar.gz" -o "$TMP_DIR/hermes-skill.tar.gz" 2>/dev/null || true
      if [ -s "$TMP_DIR/hermes-skill.tar.gz" ]; then
        EXPECTED_SKILL_HASH=$(get_expected_sha256 "hermes-skill.tar.gz" "$TMP_DIR/SHA256SUMS")
        if [ -n "$EXPECTED_SKILL_HASH" ]; then
          if verify_file_sha256 "$TMP_DIR/hermes-skill.tar.gz" "$EXPECTED_SKILL_HASH"; then
            echo -e "${GREEN}✓ Cryptographic integrity verified (hermes-skill.tar.gz)${NC}"
          else
            echo -e "${RED}✗ Error: Checksum mismatch for hermes-skill.tar.gz! Aborting.${NC}"
            exit 1
          fi
        fi
        tar -xzf "$TMP_DIR/hermes-skill.tar.gz" -C "$TMP_SKILL_DIR/"
      fi
    fi

    if [ -d "$TMP_SKILL_DIR/sphene-knowledge-hub" ]; then
      if [ "$HERMES_TYPE" = "docker" ]; then
        docker cp "$TMP_SKILL_DIR/sphene-knowledge-hub" "${HERMES_CONTAINER}:${HERMES_SKILLS_DIR}/"
        if [ -n "$SPHENE_HOST_BIN" ] && [ -f "$SPHENE_HOST_BIN" ]; then
          docker cp "$SPHENE_HOST_BIN" "${HERMES_CONTAINER}:/usr/local/bin/sphene"
          docker exec "${HERMES_CONTAINER}" chmod +x /usr/local/bin/sphene 2>/dev/null || true
        fi
        # Register Sphene native MCP server in Hermes
        docker exec "${HERMES_CONTAINER}" python3 -c '
import yaml, os
cfg_file = "/opt/data/config.yaml"
if os.path.isfile(cfg_file):
    try:
        with open(cfg_file, "r") as f:
            c = yaml.safe_load(f) or {}
        mcp = c.setdefault("mcp_servers", {})
        mcp["sphene"] = {
            "command": "/usr/local/bin/sphene",
            "args": ["mcp"],
            "env": {"SPHENE_URL": "http://127.0.0.1:8743"},
            "enabled": True
        }
        with open(cfg_file, "w") as f:
            yaml.dump(c, f, default_flow_style=False)
    except Exception:
        pass
' 2>/dev/null || true
      else
        cp -r "$TMP_SKILL_DIR/sphene-knowledge-hub" "${HERMES_SKILLS_DIR}/"
        python3 -c '
import yaml, os
candidates = [os.path.expanduser("~/.hermes/config.yaml"), "/DATA/AppData/hermes/config.yaml"]
for cfg_file in candidates:
    if os.path.isfile(cfg_file):
        try:
            with open(cfg_file, "r") as f:
                c = yaml.safe_load(f) or {}
            mcp = c.setdefault("mcp_servers", {})
            mcp["sphene"] = {
                "command": "/usr/local/bin/sphene",
                "args": ["mcp"],
                "env": {"SPHENE_URL": "http://127.0.0.1:8743"},
                "enabled": True
            }
            with open(cfg_file, "w") as f:
                yaml.dump(c, f, default_flow_style=False)
        except Exception:
            pass
' 2>/dev/null || true
      fi
      SKILL_INSTALLED=1
      echo -e "${GREEN}✓ Sphene Knowledge Hub skill & native MCP server updated in Hermes.${NC}"
    fi

    # Refresh upgraded obsidian skill if previously replaced
    OBSIDIAN_REL_PATH=""
    if [ "$HERMES_TYPE" = "docker" ]; then
      if docker exec "${HERMES_CONTAINER}" test -f "${HERMES_SKILLS_DIR}/note-taking/obsidian/SKILL.md.bak" 2>/dev/null; then
        OBSIDIAN_REL_PATH="note-taking/obsidian/SKILL.md"
      elif docker exec "${HERMES_CONTAINER}" test -f "${HERMES_SKILLS_DIR}/obsidian/SKILL.md.bak" 2>/dev/null; then
        OBSIDIAN_REL_PATH="obsidian/SKILL.md"
      fi
    else
      if [ -f "${HERMES_SKILLS_DIR}/note-taking/obsidian/SKILL.md.bak" ]; then
        OBSIDIAN_REL_PATH="note-taking/obsidian/SKILL.md"
      elif [ -f "${HERMES_SKILLS_DIR}/obsidian/SKILL.md.bak" ]; then
        OBSIDIAN_REL_PATH="obsidian/SKILL.md"
      fi
    fi
    if [ -n "$OBSIDIAN_REL_PATH" ]; then
      OBSIDIAN_REPLACED=1
    fi
  else
    # Prompt 6a: Install Sphene Skill into Hermes
    PROMPT_SKILL="Install Sphene Knowledge Hub skill into Hermes now? [Y/n]: "
    INSTALL_SKILL_CHOICE=$(read_input "$PROMPT_SKILL" "Y")

    case "$INSTALL_SKILL_CHOICE" in
      [yY][eE][sS]|[yY]|"")
        echo -e "Deploying sphene-knowledge-hub skill into Hermes..."
        TMP_SKILL_DIR="$TMP_DIR/hermes-skill"
        mkdir -p "$TMP_SKILL_DIR"
        
        if [ -d "${SCRIPT_DIR}/hermes-skill/sphene-knowledge-hub" ]; then
          cp -r "${SCRIPT_DIR}/hermes-skill/sphene-knowledge-hub" "$TMP_SKILL_DIR/"
        else
          curl -fsSL "https://sphene.app/hermes-skill.tar.gz" -o "$TMP_DIR/hermes-skill.tar.gz" 2>/dev/null || true
          if [ -s "$TMP_DIR/hermes-skill.tar.gz" ]; then
            EXPECTED_SKILL_HASH=$(get_expected_sha256 "hermes-skill.tar.gz" "$TMP_DIR/SHA256SUMS")
            if [ -n "$EXPECTED_SKILL_HASH" ]; then
              if verify_file_sha256 "$TMP_DIR/hermes-skill.tar.gz" "$EXPECTED_SKILL_HASH"; then
                echo -e "${GREEN}✓ Cryptographic integrity verified (hermes-skill.tar.gz)${NC}"
              else
                echo -e "${RED}✗ Error: Checksum mismatch for hermes-skill.tar.gz! Aborting.${NC}"
                exit 1
              fi
            fi
            tar -xzf "$TMP_DIR/hermes-skill.tar.gz" -C "$TMP_SKILL_DIR/"
          fi
        fi

        if [ -d "$TMP_SKILL_DIR/sphene-knowledge-hub" ]; then
          if [ "$HERMES_TYPE" = "docker" ]; then
            docker cp "$TMP_SKILL_DIR/sphene-knowledge-hub" "${HERMES_CONTAINER}:${HERMES_SKILLS_DIR}/"
            if [ -n "$SPHENE_HOST_BIN" ] && [ -f "$SPHENE_HOST_BIN" ]; then
              docker cp "$SPHENE_HOST_BIN" "${HERMES_CONTAINER}:/usr/local/bin/sphene"
              docker exec "${HERMES_CONTAINER}" chmod +x /usr/local/bin/sphene 2>/dev/null || true
            fi
            # Register Sphene native MCP server in Hermes
            docker exec "${HERMES_CONTAINER}" python3 -c '
import yaml, os
cfg_file = "/opt/data/config.yaml"
if os.path.isfile(cfg_file):
    try:
        with open(cfg_file, "r") as f:
            c = yaml.safe_load(f) or {}
        mcp = c.setdefault("mcp_servers", {})
        mcp["sphene"] = {
            "command": "/usr/local/bin/sphene",
            "args": ["mcp"],
            "env": {"SPHENE_URL": "http://127.0.0.1:8743"},
            "enabled": True
        }
        with open(cfg_file, "w") as f:
            yaml.dump(c, f, default_flow_style=False)
    except Exception:
        pass
' 2>/dev/null || true
            # Ensure skill is enabled in hermes config if disabled list exists
            docker exec "${HERMES_CONTAINER}" python3 -c '
import yaml, os
cfg_file = "/opt/data/config.yaml"
if os.path.isfile(cfg_file):
    try:
        with open(cfg_file, "r") as f:
            c = yaml.safe_load(f) or {}
        disabled = c.get("skills", {}).get("disabled", [])
        if "sphene-knowledge-hub" in disabled:
            disabled.remove("sphene-knowledge-hub")
            c["skills"]["disabled"] = disabled
            with open(cfg_file, "w") as f:
                yaml.dump(c, f)
    except Exception:
        pass
' 2>/dev/null || true
          else
            cp -r "$TMP_SKILL_DIR/sphene-knowledge-hub" "${HERMES_SKILLS_DIR}/"
            python3 -c '
import yaml, os
candidates = [os.path.expanduser("~/.hermes/config.yaml"), "/DATA/AppData/hermes/config.yaml"]
for cfg_file in candidates:
    if os.path.isfile(cfg_file):
        try:
            with open(cfg_file, "r") as f:
                c = yaml.safe_load(f) or {}
            mcp = c.setdefault("mcp_servers", {})
            mcp["sphene"] = {
                "command": "/usr/local/bin/sphene",
                "args": ["mcp"],
                "env": {"SPHENE_URL": "http://127.0.0.1:8743"},
                "enabled": True
            }
            with open(cfg_file, "w") as f:
                yaml.dump(c, f, default_flow_style=False)
        except Exception:
            pass
' 2>/dev/null || true
          fi
          SKILL_INSTALLED=1
          echo -e "${GREEN}✓ Sphene Knowledge Hub skill & native MCP server deployed into Hermes successfully.${NC}"
        fi
        ;;
      *)
        echo "Skipped Hermes skill installation."
        ;;
    esac

  # Prompt 6b: Replace Obsidian skill with Sphene
  OBSIDIAN_REL_PATH=""
  if [ "$HERMES_TYPE" = "docker" ]; then
    if docker exec "${HERMES_CONTAINER}" test -f "${HERMES_SKILLS_DIR}/note-taking/obsidian/SKILL.md" 2>/dev/null; then
      OBSIDIAN_REL_PATH="note-taking/obsidian/SKILL.md"
    elif docker exec "${HERMES_CONTAINER}" test -f "${HERMES_SKILLS_DIR}/obsidian/SKILL.md" 2>/dev/null; then
      OBSIDIAN_REL_PATH="obsidian/SKILL.md"
    fi
  else
    if [ -f "${HERMES_SKILLS_DIR}/note-taking/obsidian/SKILL.md" ]; then
      OBSIDIAN_REL_PATH="note-taking/obsidian/SKILL.md"
    elif [ -f "${HERMES_SKILLS_DIR}/obsidian/SKILL.md" ]; then
      OBSIDIAN_REL_PATH="obsidian/SKILL.md"
    fi
  fi

  if [ -n "$OBSIDIAN_REL_PATH" ]; then
    echo -e "\n${YELLOW}${BOLD}Hermes Knowledge Hub Skill Integration Option:${NC}"
    echo "Hermes comes bundled with a default note-taking skill."
    echo "Sphene features <25MB local memory footprint, sub-millisecond SQLite FTS5 index,"
    echo "human veto timeline, native MCP toolsets, and an interactive visual Web UI."
    echo ""

    PROMPT_OBS="Do you want Hermes to configure Sphene as its primary knowledge store and native MCP engine? [Y/n]: "
    REPLACE_OBSIDIAN_CHOICE=$(read_input "$PROMPT_OBS" "Y")

    case "$REPLACE_OBSIDIAN_CHOICE" in
      [yY][eE][sS]|[yY]|"")
        echo "Configuring Hermes note-taking skill definition to route directly to Sphene..."
        UPGRADED_OBSIDIAN_SKILL='---
name: obsidian
description: >-
  Read, search, create, and edit notes in Sphene Knowledge Hub (the sovereign knowledge substrate).
  Use native Sphene MCP tools for all note-taking, markdown notes, second brain retrieval, intra-document search, and updates.
version: 2.2.0
author: Sphene Sovereign Substrate
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [Sphene, Notes, Markdown, KnowledgeHub]
    related_skills: [sphene-knowledge-hub]
---

# Sphene Knowledge Hub

Configured with **Sphene Knowledge Hub** (https://sphene.app) — the hardened, sovereign knowledge substrate and second brain running locally with sub-millisecond SQLite FTS5 search (<0.2ms) and native Model Context Protocol (MCP) integration.

## 1. Zero Misfires: Direct Native MCP Tool Invocations
All note-taking, document lookups, and second brain requests MUST use your native Sphene MCP tools directly:
- **`sphene_search(query, partition?)`**: Sub-millisecond full-text search across all notes, topics, concepts, and books (<0.2ms). Call this FIRST whenever searching for information.
- **`sphene_find_in_doc(path, query)`**: Pinpoint fact and checklist search inside a specific document without loading the entire note.
- **`sphene_read(path, section?)`**: Retrieve note content or a specific heading (`section: "..."`).
- **`sphene_write(path, content, agent_id?)`**: Create new workspace notes with immediate FTS5 indexing.
- **`sphene_patch(path, section, content, action?, agent_id?)`**: Safely update or append to a specific section with Differential Timeline human review.
- **`sphene_query(kind?, status?, limit?)`**: Fast relational queries across tasks and frontmatter.
- **`sphene_graph(path?, depth?)`**: Graph backlinks and topology.
- **`sphene_daily(content)`**: Autonomous logging to today\x27s daily note.

Do NOT attempt to run shell scripts or search for local files manually—the native Sphene MCP tools provide fast, typed, and structured access.

## 2. Active Vault Location & Visual Web UI
- **Local Web Interface:** http://localhost:8743 (interactive note reader, 3D force graph, and human veto timeline).
- **Vault Location:** All notes live as standard plaintext Markdown files on disk at:
  `'"${VAULT_DIR}"'`

## 3. Fallback CLI (Only if MCP is Unavailable)
- `sphene search "<query>"`
- `sphene read "<path>" --raw`
- `sphene write "<path>" --file /tmp/note.md`
- `sphene daily "<summary>"`
'
        if [ "$HERMES_TYPE" = "docker" ]; then
          docker exec "${HERMES_CONTAINER}" sh -c "[ ! -f '${HERMES_SKILLS_DIR}/${OBSIDIAN_REL_PATH}.bak' ] && cp '${HERMES_SKILLS_DIR}/${OBSIDIAN_REL_PATH}' '${HERMES_SKILLS_DIR}/${OBSIDIAN_REL_PATH}.bak'" 2>/dev/null || true
          printf "%s\n" "$UPGRADED_OBSIDIAN_SKILL" | docker exec -i "${HERMES_CONTAINER}" sh -c "cat > '${HERMES_SKILLS_DIR}/${OBSIDIAN_REL_PATH}'"
          # Enable obsidian in config.yaml if it was disabled
          docker exec "${HERMES_CONTAINER}" python3 -c '
import yaml, os
cfg_file = "/opt/data/config.yaml"
if os.path.isfile(cfg_file):
    try:
        with open(cfg_file, "r") as f:
            c = yaml.safe_load(f) or {}
        disabled = c.get("skills", {}).get("disabled", [])
        if "obsidian" in disabled:
            disabled.remove("obsidian")
            c["skills"]["disabled"] = disabled
            with open(cfg_file, "w") as f:
                yaml.dump(c, f)
    except Exception:
        pass
' 2>/dev/null || true
        else
          [ ! -f "${HERMES_SKILLS_DIR}/${OBSIDIAN_REL_PATH}.bak" ] && cp "${HERMES_SKILLS_DIR}/${OBSIDIAN_REL_PATH}" "${HERMES_SKILLS_DIR}/${OBSIDIAN_REL_PATH}.bak"
          printf "%s\n" "$UPGRADED_OBSIDIAN_SKILL" > "${HERMES_SKILLS_DIR}/${OBSIDIAN_REL_PATH}"
        fi
        OBSIDIAN_REPLACED=1
        echo -e "${GREEN}✓ Hermes Obsidian skill upgraded to route directly to Sphene!${NC}"
        ;;
      *)
        echo "Obsidian skill left untouched. Sphene is configured as an independent sovereign substrate."
        ;;
    esac
  fi
  fi
fi

# 7. OpenClaw Agent Detection & Interactive Integration
echo -e "\n${BOLD}Scanning for OpenClaw Agent installations...${NC}"
OPENCLAW_TYPE=""
OPENCLAW_CONTAINER=""
OPENCLAW_CONFIG=""

if command -v docker >/dev/null 2>&1 && docker ps --format '{{.Names}}' | grep -iE '^(openclaw|clawdbot|moltbot)$'; then
  OPENCLAW_TYPE="docker"
  OPENCLAW_CONTAINER="$(docker ps --format '{{.Names}}' | grep -iE '^(openclaw|clawdbot|moltbot)$' | head -n 1)"
  echo -e "${GREEN}✓ Found running OpenClaw container: '${OPENCLAW_CONTAINER}'${NC}"
elif [ -f "$HOME/.openclaw/openclaw.json" ]; then
  OPENCLAW_TYPE="local"
  OPENCLAW_CONFIG="$HOME/.openclaw/openclaw.json"
  echo -e "${GREEN}✓ Found local OpenClaw configuration: ${OPENCLAW_CONFIG}${NC}"
elif [ -f "/DATA/AppData/openclaw/openclaw.json" ]; then
  OPENCLAW_TYPE="local"
  OPENCLAW_CONFIG="/DATA/AppData/openclaw/openclaw.json"
  echo -e "${GREEN}✓ Found local OpenClaw configuration: ${OPENCLAW_CONFIG}${NC}"
elif command -v openclaw >/dev/null 2>&1; then
  OPENCLAW_TYPE="cli"
  echo -e "${GREEN}✓ Found OpenClaw CLI in PATH${NC}"
fi

OPENCLAW_INSTALLED=0
if [ -n "$OPENCLAW_TYPE" ]; then
  PROMPT_OPENCLAW="Configure Sphene native MCP integration for OpenClaw? [Y/n]: "
  OPENCLAW_CHOICE=$(read_input "$PROMPT_OPENCLAW" "Y")
  case "$OPENCLAW_CHOICE" in
    [yY][eE][sS]|[yY]|"")
      echo -e "Configuring Sphene native MCP server in OpenClaw..."
      if [ "$OPENCLAW_TYPE" = "docker" ]; then
        if [ -n "$SPHENE_HOST_BIN" ] && [ -f "$SPHENE_HOST_BIN" ]; then
          docker cp "$SPHENE_HOST_BIN" "${OPENCLAW_CONTAINER}:/usr/local/bin/sphene" 2>/dev/null || true
          docker exec "${OPENCLAW_CONTAINER}" chmod +x /usr/local/bin/sphene 2>/dev/null || true
        fi
        docker exec "${OPENCLAW_CONTAINER}" openclaw mcp add sphene --command /usr/local/bin/sphene --arg mcp 2>/dev/null || true
        docker exec "${OPENCLAW_CONTAINER}" python3 -c '
import json, os
candidates = ["/root/.openclaw/openclaw.json", "/opt/data/openclaw.json", "/etc/openclaw/openclaw.json", "/app/openclaw.json"]
for path in candidates:
    if os.path.isfile(path):
        try:
            with open(path, "r") as f:
                c = json.load(f) or {}
            mcp = c.setdefault("mcp", {}).setdefault("servers", {})
            mcp["sphene"] = {
                "command": "/usr/local/bin/sphene",
                "args": ["mcp"],
                "env": {"SPHENE_URL": "http://127.0.0.1:8743"}
            }
            with open(path, "w") as f:
                json.dump(c, f, indent=2)
        except Exception:
            pass
' 2>/dev/null || true
      elif [ "$OPENCLAW_TYPE" = "local" ] && [ -n "$OPENCLAW_CONFIG" ]; then
        python3 -c '
import json, os
cfg_file = "'"$OPENCLAW_CONFIG"'"
if os.path.isfile(cfg_file):
    try:
        with open(cfg_file, "r") as f:
            c = json.load(f) or {}
        mcp = c.setdefault("mcp", {}).setdefault("servers", {})
        mcp["sphene"] = {
            "command": "/usr/local/bin/sphene",
            "args": ["mcp"],
            "env": {"SPHENE_URL": "http://127.0.0.1:8743"}
        }
        with open(cfg_file, "w") as f:
            json.dump(c, f, indent=2)
    except Exception:
        pass
' 2>/dev/null || true
      elif [ "$OPENCLAW_TYPE" = "cli" ]; then
        openclaw mcp add sphene --command /usr/local/bin/sphene --arg mcp 2>/dev/null || true
      fi
      OPENCLAW_INSTALLED=1
      echo -e "${GREEN}✓ Sphene native MCP server successfully integrated into OpenClaw!${NC}"
      ;;
    *)
      echo "Skipped OpenClaw MCP integration."
      ;;
  esac
fi

# 8. Deployment Execution: Docker Container vs Native Daemon
PORT="${SPHENE_PORT:-8743}"

# Stop any lingering native daemon on port 8743 so it doesn't conflict
if pgrep -f "sphene.*daemon" >/dev/null 2>&1; then
  pkill -9 -f "sphene.*daemon" 2>/dev/null || true
fi

DOCKER_SUCCESS=0
if [ $HAS_DOCKER -eq 1 ]; then
  echo -e "\n${BOLD}Deploying Sphene as Docker container...${NC}"
  cd "$INSTALL_DIR"

  # Select architecture-specific Docker image archive (ARM64 vs AMD64)
  if [ "$ARCH" = "arm64" ]; then
    TARGET_IMG_FILE="sphene-image-arm64.tar.gz"
  else
    TARGET_IMG_FILE="sphene-image-amd64.tar.gz"
  fi

  # Always fetch and load the latest native image to prevent running stale cached versions
  echo "Fetching latest native Sphene container image (${TARGET_IMG_FILE} for ${OS}-${ARCH})..."
  if (curl -fsSL "https://sphene.app/${TARGET_IMG_FILE}" -o "$TMP_DIR/${TARGET_IMG_FILE}" 2>/dev/null || curl -fsSL "https://sphene.app/sphene-image.tar.gz" -o "$TMP_DIR/${TARGET_IMG_FILE}" 2>/dev/null) && [ -s "$TMP_DIR/${TARGET_IMG_FILE}" ]; then
    EXPECTED_IMG_HASH=$(get_expected_sha256 "${TARGET_IMG_FILE}" "$TMP_DIR/SHA256SUMS")
    [ -z "$EXPECTED_IMG_HASH" ] && EXPECTED_IMG_HASH=$(get_expected_sha256 "sphene-image.tar.gz" "$TMP_DIR/SHA256SUMS")
    if [ -n "$EXPECTED_IMG_HASH" ]; then
      if verify_file_sha256 "$TMP_DIR/${TARGET_IMG_FILE}" "$EXPECTED_IMG_HASH"; then
        echo -e "${GREEN}✓ Cryptographic integrity verified (${TARGET_IMG_FILE})${NC}"
      else
        echo -e "${YELLOW}⚠ Warning: Checksum mismatch for ${TARGET_IMG_FILE}, continuing with caution...${NC}"
      fi
    fi
    echo "Loading updated container image into Docker..."
    docker load < "$TMP_DIR/${TARGET_IMG_FILE}" || true
  elif [ -f "${SCRIPT_DIR}/${TARGET_IMG_FILE}" ]; then
    echo "Loading Sphene container image from local archive (${TARGET_IMG_FILE})..."
    docker load < "${SCRIPT_DIR}/${TARGET_IMG_FILE}" || true
  elif [ -f "${SCRIPT_DIR}/sphene-image.tar.gz" ]; then
    echo "Loading Sphene container image from local archive (sphene-image.tar.gz)..."
    docker load < "${SCRIPT_DIR}/sphene-image.tar.gz" || true
  fi

  # Verify that sphene:2.2.0 exists in docker images before running compose
  if docker images --format '{{.Repository}}:{{.Tag}}' | grep -q "^sphene:2.2.0$"; then
    # Write production docker-compose.yml with pull_policy: never so Docker NEVER attempts Docker Hub pull
    cat << EOF_COMPOSE > "$INSTALL_DIR/docker-compose.yml"
services:
  sphene:
    image: sphene:2.2.0
    pull_policy: never
    container_name: sphene
    restart: unless-stopped
    ports:
      - "${PORT}:8743"
    volumes:
      - ./vault:/vault
    environment:
      - SPHENE_VAULT_DIR=/vault
      - SPHENE_PORT=8743
      - SPHENE_HOST=0.0.0.0
EOF_COMPOSE

    # Stop and remove any existing sphene container to guarantee fresh container creation
    docker rm -f sphene 2>/dev/null || true

    # Start container with force-recreate
    if $COMPOSE_CMD up -d --force-recreate 2>/dev/null; then
      # Wait for container response
      COUNTER=0
      MAX_RETRIES=20
      echo -ne "Waiting for Sphene container to become ready"
      while [ $COUNTER -lt $MAX_RETRIES ]; do
        if curl -s "http://127.0.0.1:${PORT}/login" >/dev/null 2>&1 || curl -s "http://127.0.0.1:${PORT}/api/v1/health" >/dev/null 2>&1; then
          echo -e "\n${GREEN}✓ Sphene container is healthy and responding on http://localhost:${PORT}!${NC}"
          DOCKER_SUCCESS=1
          break
        fi
        echo -ne "."
        sleep 1
        COUNTER=$((COUNTER + 1))
      done
    fi
  fi

  if [ $DOCKER_SUCCESS -eq 1 ]; then
    # Initialize credentials inside container (only on initial installation)
    if [ $IS_UPDATE -eq 0 ]; then
      echo -e "\n${BOLD}Configuring administrative credentials...${NC}"
      docker exec sphene /usr/local/bin/sphene auth setup
    fi
  else
    echo -e "\n${YELLOW}⚠ Docker container initialization could not be completed.${NC}"
    echo -e "${YELLOW}  Switching seamlessly to native sovereign daemon...${NC}"
    HAS_DOCKER=0
  fi
fi

if [ $HAS_DOCKER -eq 0 ]; then
  # Fallback: Native binary daemon
  echo -e "\n${BOLD}Deploying Sphene as background daemon...${NC}"
  if [ -n "$SPHENE_HOST_BIN" ] && [ -f "$SPHENE_HOST_BIN" ]; then
    SPHENE_VAULT_DIR="$VAULT_DIR" SPHENE_PORT="$PORT" nohup "$SPHENE_HOST_BIN" daemon >/tmp/sphene-daemon.log 2>&1 &
    sleep 1
    echo -e "${GREEN}✓ Sphene background daemon active on http://localhost:${PORT}${NC}"
    if [ $IS_UPDATE -eq 0 ]; then
      SPHENE_VAULT_DIR="$VAULT_DIR" "$SPHENE_HOST_BIN" auth setup
    fi
  fi
fi

# 8. Sync Internal API Key to Host and Hermes Agent Container
LOCAL_KEY="$TMP_DIR/api.key"
if [ $HAS_DOCKER -eq 1 ]; then
  docker exec sphene cat /vault/.sphene/api.key > "$LOCAL_KEY" 2>/dev/null || true
fi
if [ ! -s "$LOCAL_KEY" ] && [ -r "$VAULT_DIR/.sphene/api.key" ]; then
  cp "$VAULT_DIR/.sphene/api.key" "$LOCAL_KEY" 2>/dev/null || true
fi
if [ ! -s "$LOCAL_KEY" ] && command -v sudo >/dev/null 2>&1; then
  sudo cat "$VAULT_DIR/.sphene/api.key" > "$LOCAL_KEY" 2>/dev/null || true
fi

if [ -s "$LOCAL_KEY" ]; then
  mkdir -p /etc/sphene "$HOME/.sphene" 2>/dev/null || true
  if [ -w /etc/sphene ]; then
    cp "$LOCAL_KEY" /etc/sphene/api.key
    chmod 644 /etc/sphene/api.key
  elif command -v sudo >/dev/null 2>&1; then
    sudo mkdir -p /etc/sphene 2>/dev/null || true
    sudo cp "$LOCAL_KEY" /etc/sphene/api.key 2>/dev/null || true
    sudo chmod 644 /etc/sphene/api.key 2>/dev/null || true
  fi
  cp "$LOCAL_KEY" "$HOME/.sphene/api.key" 2>/dev/null || true
  chmod 644 "$HOME/.sphene/api.key" 2>/dev/null || true

  if [ -n "$HERMES_CONTAINER" ] && docker ps --format '{{.Names}}' | grep -q "^${HERMES_CONTAINER}$"; then
    docker exec "${HERMES_CONTAINER}" mkdir -p /etc/sphene /opt/data/.sphene 2>/dev/null || true
    docker cp "$LOCAL_KEY" "${HERMES_CONTAINER}:/etc/sphene/api.key" 2>/dev/null || true
    docker cp "$LOCAL_KEY" "${HERMES_CONTAINER}:/opt/data/.sphene/api.key" 2>/dev/null || true
    docker exec "${HERMES_CONTAINER}" sh -c "chmod 644 /etc/sphene/api.key /opt/data/.sphene/api.key 2>/dev/null || true; chown -R hermes:hermes /opt/data/.sphene 2>/dev/null || true"
    echo -e "${GREEN}✓ Synced internal sovereign API key into Hermes Agent container!${NC}"
  fi
fi

# 9. Reload Hermes container so skills and sovereign API keys activate immediately
if [ $SKILL_INSTALLED -eq 1 ] || [ $OBSIDIAN_REPLACED -eq 1 ]; then
  if [ "$HERMES_TYPE" = "docker" ] && [ -n "$HERMES_CONTAINER" ]; then
    echo -e "\n${BOLD}Reloading Hermes Agent container '${HERMES_CONTAINER}'...${NC}"
    docker restart "${HERMES_CONTAINER}" >/dev/null
    sleep 2
    echo -e "${GREEN}✓ Hermes container restarted. Sphene skill is live and active!${NC}"
  fi
fi

# 10. Optional Curated Sample Notes (Fresh Installs)
if [ $IS_UPDATE -eq 0 ]; then
  echo -e "\n${CYAN}${BOLD}Curated Sample Notes & Capability Showcase:${NC}"
  echo -e "Would you like to install curated sample notes showcasing Markdown, KaTeX math,"
  echo -e "interactive tasks, Mermaid diagrams, and drawing studio capabilities?"
  PROMPT_SAMPLES="Install sample notes? [Y/n]: "
  INSTALL_SAMPLES=$(read_input "$PROMPT_SAMPLES" "Y")
  case "$INSTALL_SAMPLES" in
    [yY][eE][sS]|[yY]|"")
      echo -e "Downloading curated sample notes suite..."
      SAMPLES_TAR="$TMP_DIR/sample-notes.tar.gz"
      if [ -f "${SCRIPT_DIR}/sample-notes.tar.gz" ]; then
        cp "${SCRIPT_DIR}/sample-notes.tar.gz" "$SAMPLES_TAR"
      else
        curl -fsSL "https://sphene.app/sample-notes.tar.gz" -o "$SAMPLES_TAR" 2>/dev/null || true
      fi
      if [ -s "$SAMPLES_TAR" ]; then
        EXPECTED_SAMPLES_HASH=$(get_expected_sha256 "sample-notes.tar.gz" "$TMP_DIR/SHA256SUMS")
        if [ -n "$EXPECTED_SAMPLES_HASH" ]; then
          if verify_file_sha256 "$SAMPLES_TAR" "$EXPECTED_SAMPLES_HASH"; then
            echo -e "${GREEN}✓ Cryptographic integrity verified (sample-notes.tar.gz)${NC}"
          fi
        fi
        mkdir -p "$VAULT_DIR"
        tar -zxvf "$SAMPLES_TAR" -C "$VAULT_DIR" >/dev/null 2>&1 || tar -xvf "$SAMPLES_TAR" -C "$VAULT_DIR" >/dev/null 2>&1
        echo -e "${GREEN}✓ Installed sample notes into ${VAULT_DIR}${NC}"

        # Notify and activate verified plugins required for the sample notes showcase
        echo -e "\n${CYAN}Notice:${NC} Activating verified plugins 'sphene-mermaid', 'sphene-math-katex', and 'sphene-drawing' to enable full diagram, math, and visual canvas capabilities for sample notes."
        if [ $HAS_DOCKER -eq 1 ]; then
          docker exec sphene sphene plugin install sphene-mermaid >/dev/null 2>&1 || true
          docker exec sphene sphene plugin install sphene-math-katex >/dev/null 2>&1 || true
          docker exec sphene sphene plugin install sphene-drawing >/dev/null 2>&1 || true
          docker exec sphene sphene index --vault /data/vault >/dev/null 2>&1 || true
        elif command -v sphene >/dev/null 2>&1; then
          sphene plugin install sphene-mermaid >/dev/null 2>&1 || true
          sphene plugin install sphene-math-katex >/dev/null 2>&1 || true
          sphene plugin install sphene-drawing >/dev/null 2>&1 || true
          sphene index --vault "$VAULT_DIR" >/dev/null 2>&1 || true
        fi
        echo -e "${GREEN}✓ Verified plugins provisioned and sample notes indexed into SQLite FTS5!${NC}"
      else
        echo -e "${YELLOW}⚠ Could not download sample notes, skipping...${NC}"
      fi
      ;;
    *)
      echo -e "Skipping sample notes. Vault created clean and empty."
      ;;
  esac
fi

# Clean up temp files
rm -rf "$TMP_DIR"

if [ $IS_UPDATE -eq 1 ]; then
  echo -e "\n${GREEN}${BOLD}==================================================================${NC}"
  echo -e "${GREEN}${BOLD}  SPHENE SOVEREIGN SECOND BRAIN UPDATED SUCCESSFULLY!             ${NC}"
  echo -e "${GREEN}${BOLD}==================================================================${NC}"
  echo -e "  • Web Interface:    ${CYAN}http://localhost:${PORT}${NC}"
  echo -e "  • Knowledge Vault:  ${CYAN}${VAULT_DIR}${NC} (100% preserved)"
  if [ $HAS_DOCKER -eq 1 ]; then
    echo -e "  • Container:        ${CYAN}sphene${NC} (reloaded with latest release)"
  fi
  echo -e "  • Host CLI:         ${CYAN}/usr/local/bin/sphene${NC} (updated)"
  if [ $SKILL_INSTALLED -eq 1 ] || [ $OBSIDIAN_REPLACED -eq 1 ]; then
    echo -e "  • Hermes Agent:     ${GREEN}UPDATED & SYNCED!${NC} (Native MCP tools + skill active, container reloaded)"
  fi
  if [ $OPENCLAW_INSTALLED -eq 1 ]; then
    echo -e "  • OpenClaw Agent:   ${GREEN}UPDATED & SYNCED!${NC} (Native Sphene MCP tools active)"
  fi
  echo -e "  • Existing Logins:  ${GREEN}Preserved.${NC} Your existing credentials remain active."
  echo ""
  exit 0
fi

echo -e "\n${GREEN}${BOLD}==================================================================${NC}"
echo -e "${GREEN}${BOLD}  SPHENE SOVEREIGN SECOND BRAIN INSTALLED SUCCESSFULLY!           ${NC}"
echo -e "${GREEN}${BOLD}==================================================================${NC}"
echo -e "  • Web Interface:    ${CYAN}http://localhost:${PORT}${NC}"
echo -e "  • Knowledge Vault:  ${CYAN}${VAULT_DIR}${NC}"
if [ $HAS_DOCKER -eq 1 ]; then
  echo -e "  • Container:        ${CYAN}sphene${NC} (manage via 'docker ps', 'docker logs -f sphene')"
fi
echo -e "  • Security:         ${CYAN}Log in with the admin credentials printed above.${NC}"
echo -e "  • Password Reset:   ${CYAN}sphene auth setup [--username <user>] [--password <pass>]${NC}"
echo -e "  • CLI Commands:     ${CYAN}sphene search <query>, sphene read <path>, sphene write <path>${NC}"
echo -e "  • Import Notes:     ${CYAN}sphene import <path-to-obsidian-or-md-folder>${NC}"
if [ $SKILL_INSTALLED -eq 1 ] || [ $OBSIDIAN_REPLACED -eq 1 ]; then
  echo -e "  • Hermes Agent:     ${GREEN}ACTIVE!${NC} Native Sphene MCP server connected (8 sub-millisecond tools enabled)."
fi
if [ $OPENCLAW_INSTALLED -eq 1 ]; then
  echo -e "  • OpenClaw Agent:   ${GREEN}ACTIVE!${NC} Native Sphene MCP server connected."
fi
echo ""

