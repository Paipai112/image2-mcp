# image2-mcp

MCP Server for the company image2 text-to-image API. Allows Claude Code, Codex,
and other MCP-compatible AI tools to generate images directly.

## 🚀 Quick Start (One Command)

```bash
git clone <repo-url>
cd image2-mcp
bash scripts/setup.sh
```

The script will:
1. Check that `uv` is installed
2. Install Python dependencies (`uv sync`)
3. Ask for your API key (or reuse from `~/.claude/.env`)
4. Write `~/.claude/.env` with your key
5. Add `image2` to your `~/.claude/.mcp.json`
6. Run a health check to verify everything works

Then restart Claude Code and try: "帮我生成一张图片..."

---

## 📦 Manual Setup

### Prerequisites

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) (Python package manager)
- A company API Key for the unified AI platform

### Install

```bash
uv sync
```

### Configuration

Copy the environment template and fill in your API key:

```bash
cp .env.example ~/.claude/.env
# Edit ~/.claude/.env and set MAGENE_API_KEY
```

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `MAGENE_API_KEY` | **Yes** | — | Your company API key |
| `MAGENE_API_BASE_URL` | No | `http://localhost:11636/api/v1/images/generations` (set via env) | API endpoint |
| `IMAGE2_OUTPUT_DIR` | No | System temp dir `/image2-output` | Default image save location |
| `IMAGE2_MODEL` | No | `openai/gpt-image-2` | Model name override |

### MCP Configuration

Add to `~/.claude/.mcp.json`:

```json
{
  "mcpServers": {
    "image2": {
      "command": "bash",
      "args": [
        "-c",
        "set -a; [ -f ~/.claude/.env ] && . ~/.claude/.env; [ -f .env ] && . ./.env; set +a; uv run --directory /path/to/image2-mcp python -m image2_mcp"
      ],
      "description": "文生图 — 调用公司统一 API 平台 image2 模型生成图片"
    }
  }
}
```

### Health Check

```bash
uv run python -m image2_mcp --health-check
```

---

## 🔧 How It Works

The AI calls `generate_image` as a native tool:

```
AI: generate_image(prompt="a cat in a garden", size="1024x1024")
    → Server validates parameters
    → POST to company API
    → Decodes Base64 response
    → Saves PNG to disk
    → Returns image + file path + usage stats to AI
```

## 📐 Tool Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `prompt` | string | **Yes** | — | Text description of the image (max 32000 chars) |
| `size` | string | **Yes** | — | Image size (see below) |
| `quality` | string | No | `auto` | `low`, `medium`, `high`, or `auto` |
| `output_dir` | string | No | From env | Custom output directory |
| `filename` | string | No | Auto-generated | Custom filename (without `.png`) |

### Available Sizes

| Value | Resolution |
|-------|-----------|
| `1024x1024` | 1K Square |
| `1536x1024` | 1.5K Landscape |
| `1024x1536` | 1.5K Portrait |
| `2048x2048` | 2K Square |
| `2048x1152` | 2K Landscape |
| `3840x2160` | 4K Landscape |
| `2160x3840` | 4K Portrait |
| `auto` | Automatic |

Custom sizes supported: `WxH` format, max 3840px per side, multiples of 16,
aspect ratio ≤ 3:1, total pixels 655,360–8,294,400.

---

## 🧪 Development

```bash
uv sync --group dev
uv run pytest --cov=src --cov-report=term-missing
```
