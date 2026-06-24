# image2-mcp

MCP Server for the company image2 text-to-image API. Allows Claude Code, Codex,
and other MCP-compatible AI tools to generate images directly.

## Prerequisites

- Python 3.10+
- A company API Key for the unified AI platform

## Installation

```bash
pip install git+https://github.com/magene-platform/image2-mcp.git
```

Or clone and install locally:

```bash
git clone https://github.com/magene-platform/image2-mcp.git
cd image2-mcp
pip install -e .
```

## Configuration

Configure via environment variables:

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `MAGENE_API_KEY` | Yes | — | Your company API key |
| `MAGENE_API_BASE_URL` | No | `http://tops.magene.cn:11636/api/v1/images/generations` | API endpoint |
| `IMAGE2_OUTPUT_DIR` | No | System temp directory `/image2-output` | Default image save location |

## Usage with Claude Code

Add to your Claude Code MCP configuration (`~/.claude/settings.local.json` or project `.claude/settings.local.json`):

```json
{
  "mcpServers": {
    "image2": {
      "command": "python",
      "args": ["-m", "image2_mcp"],
      "env": {
        "MAGENE_API_KEY": "your-api-key-here",
        "IMAGE2_OUTPUT_DIR": "/Users/you/Pictures/image2-output"
      }
    }
  }
}
```

## Usage with Codex

Add to your Codex MCP configuration:

```json
{
  "mcpServers": {
    "image2": {
      "command": "python",
      "args": ["-m", "image2_mcp"],
      "env": {
        "MAGENE_API_KEY": "your-api-key-here"
      }
    }
  }
}
```

## How It Works

The AI calls `generate_image` as a native tool:

```
AI: generate_image(prompt="a cat in a garden", size="1024x1024")
    → Server validates parameters
    → POST to company API
    → Decodes Base64 response
    → Saves PNG to disk
    → Returns image + file path + usage stats to AI
```

## Tool Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `prompt` | string | Yes | — | Text description of the image |
| `size` | string | Yes | — | Image size (see below) |
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
aspect ratio <= 3:1, total pixels 655,360-8,294,400.

## Development

```bash
pip install -e ".[dev]"
pytest
```
