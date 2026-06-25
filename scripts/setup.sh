#!/usr/bin/env bash
set -euo pipefail

# ──────────────────────────────────────────────
#  Image2 MCP — One-Click Setup
#  Usage: bash scripts/setup.sh
# ──────────────────────────────────────────────

BOLD="\033[1m"
GREEN="\033[32m"
RED="\033[31m"
CYAN="\033[36m"
YELLOW="\033[33m"
RESET="\033[0m"

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$HOME/.claude/.env"
MCP_FILE="$HOME/.claude/.mcp.json"

echo ""
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo -e "${BOLD}  Image2 MCP — One-Click Setup${RESET}"
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
echo ""

# ── 1. Check uv ────────────────────────────
echo -e "${BOLD}[1/5]${RESET} Checking uv is installed..."
if command -v uv &>/dev/null; then
    echo -e "  ${GREEN}✓${RESET} uv $(uv --version)"
else
    echo -e "  ${RED}✗${RESET} uv is not installed."
    echo ""
    echo "  Install uv first:"
    echo "    curl -LsSf https://astral.sh/uv/install.sh | sh"
    echo ""
    exit 1
fi

# ── 2. Install dependencies ────────────────
echo -e "${BOLD}[2/5]${RESET} Installing Python dependencies..."
cd "$PROJECT_DIR"
uv sync
echo -e "  ${GREEN}✓${RESET} Dependencies installed"

# ── 3. API Key ─────────────────────────────
echo ""
echo -e "${BOLD}[3/5]${RESET} Configuring API key..."

MAGENE_API_KEY="${MAGENE_API_KEY:-}"

if [ -n "${MAGENE_API_KEY:-}" ]; then
    echo -e "  ${GREEN}✓${RESET} MAGENE_API_KEY already set in environment"
elif [ -f "$ENV_FILE" ] && grep -q "^MAGENE_API_KEY=" "$ENV_FILE" 2>/dev/null; then
    EXISTING_KEY=$(grep "^MAGENE_API_KEY=" "$ENV_FILE" | head -1 | cut -d'=' -f2-)
    if [ -n "$EXISTING_KEY" ] && [ "$EXISTING_KEY" != "sk-your-api-key-here" ]; then
        MAGENE_API_KEY="$EXISTING_KEY"
        echo -e "  ${GREEN}✓${RESET} MAGENE_API_KEY found in $ENV_FILE"
    else
        echo -n "  Enter your MAGENE_API_KEY: "
        read -r MAGENE_API_KEY
    fi
else
    echo -n "  Enter your MAGENE_API_KEY: "
    read -r MAGENE_API_KEY
fi

if [ -z "$MAGENE_API_KEY" ]; then
    echo -e "  ${RED}✗${RESET} No API key provided. Setup aborted."
    exit 1
fi

# ── 4. Write ~/.claude/.env ────────────────
echo ""
echo -e "${BOLD}[4/5]${RESET} Writing environment config..."

mkdir -p "$HOME/.claude"

if [ -f "$ENV_FILE" ]; then
    # Only update MAGENE_API_KEY line if it exists; otherwise append
    if grep -q "^MAGENE_API_KEY=" "$ENV_FILE" 2>/dev/null; then
        if [[ "$OSTYPE" == "darwin"* ]]; then
            sed -i '' "s|^MAGENE_API_KEY=.*|MAGENE_API_KEY=$MAGENE_API_KEY|" "$ENV_FILE"
        else
            sed -i "s|^MAGENE_API_KEY=.*|MAGENE_API_KEY=$MAGENE_API_KEY|" "$ENV_FILE"
        fi
        echo -e "  ${GREEN}✓${RESET} Updated MAGENE_API_KEY in $ENV_FILE"
    else
        echo "MAGENE_API_KEY=$MAGENE_API_KEY" >> "$ENV_FILE"
        echo -e "  ${GREEN}✓${RESET} Added MAGENE_API_KEY to $ENV_FILE"
    fi
else
    echo "MAGENE_API_KEY=$MAGENE_API_KEY" > "$ENV_FILE"
    echo -e "  ${GREEN}✓${RESET} Created $ENV_FILE"
fi

# Add default output dir if not present
if ! grep -q "^IMAGE2_OUTPUT_DIR=" "$ENV_FILE" 2>/dev/null; then
    echo "IMAGE2_OUTPUT_DIR=$HOME/.claude/Pictures" >> "$ENV_FILE"
    echo -e "  ${GREEN}✓${RESET} Default IMAGE2_OUTPUT_DIR=$HOME/.claude/Pictures"
fi

# ── 5. Configure MCP server ────────────────
echo ""
echo -e "${BOLD}[5/5]${RESET} Configuring Claude Code MCP server..."

MCP_ENTRY=$(cat <<EOF
{
      "command": "bash",
      "args": ["-c", "set -a; [ -f ~/.claude/.env ] && . ~/.claude/.env; [ -f .env ] && . ./.env; set +a; uv run --directory ${PROJECT_DIR} python -m image2_mcp"],
      "description": "文生图 — 调用公司统一 API 平台 image2 模型生成图片"
    }
EOF
)

uv run python -c "
import json, sys, os

mcp_file = os.path.expanduser('$MCP_FILE')
entry = json.loads(r'''$MCP_ENTRY''')

if os.path.exists(mcp_file):
    with open(mcp_file) as f:
        data = json.load(f)
else:
    data = {}

if 'mcpServers' not in data:
    data['mcpServers'] = {}

if 'image2' in data['mcpServers']:
    print('  ! image2 entry already exists in $MCP_FILE')
    sys.exit(0)

data['mcpServers']['image2'] = entry

with open(mcp_file, 'w') as f:
    json.dump(data, f, indent=2, ensure_ascii=False)
    f.write('\n')

print('  ✓ Added image2 to $MCP_FILE')
"

if [ $? -eq 0 ]; then
    echo -e "  ${GREEN}✓${RESET} MCP configuration updated"
else
    echo -e "  ${YELLOW}!${RESET} MCP configuration may already exist or failed to update"
fi

# ── Health Check ───────────────────────────
echo ""
echo -e "${BOLD}Running health check...${RESET}"
echo ""

# Source env file for health check
set +u
if [ -f "$ENV_FILE" ]; then
    set -a
    . "$ENV_FILE"
    set +a
fi
set -u

if uv run --directory "$PROJECT_DIR" python -m image2_mcp --health-check; then
    echo ""
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
    echo -e "${GREEN}${BOLD}  ✓ Setup complete!${RESET}"
    echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}"
    echo ""
    echo -e "  ${BOLD}Next:${RESET} Restart Claude Code, then try:"
    echo -e '    "帮我生成一张图片..."'
    echo ""
else
    echo ""
    echo -e "${YELLOW}${BOLD}  Setup finished with warnings.${RESET}"
    echo "  Check the output above for details."
    echo "  You may need to:"
    echo "    1. Verify your API key is valid"
    echo "    2. Check your network/VPN connection"
    echo "    3. Run: uv run --directory $PROJECT_DIR python -m image2_mcp --health-check"
    echo ""
fi
