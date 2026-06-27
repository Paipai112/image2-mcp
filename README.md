# image2-mcp

MCP Server for the company image2 text-to-image API. Allows Claude Code, Codex,
and other MCP-compatible AI tools to generate images directly.

## 🚀 Quick Start

### 自动安装（推荐）

```bash
git clone <repo-url>
cd image2-mcp
bash scripts/setup.sh
```

脚本会自动完成：
1. 检查/安装 `uv`
2. 安装 Python 依赖（`uv sync`）
3. 引导你输入 API Key（或从 `~/.claude/.env` 复用已有 key）
4. 写入 `~/.claude/.env` 环境配置
5. 将 `image2` 注册到 `~/.claude.json`（Claude Code 的 MCP 配置）
6. 运行健康检查验证一切正常

> 完成后重启 Claude Code，说「帮我生成一张图片」即可。

### 手动安装

```bash
# 1. 安装依赖
uv sync

# 2. 配置环境变量
cp .env.example ~/.claude/.env
# 编辑 ~/.claude/.env，将 MAGENE_API_KEY 改为你的真实 key：
#   MAGENE_API_KEY=user_xxxxxxxx

# 3. 健康检查
uv run python -m image2_mcp --health-check
```

MCP 配置需要手动添加到 `~/.claude.json` 的顶层 `mcpServers` 字段：

```json
{
  "mcpServers": {
    "image2": {
      "command": "bash",
      "args": [
        "-c",
        "set -a; [ -f ~/.claude/.env ] && . ~/.claude/.env; [ -f .env ] && . ./.env; set +a; exec /Users/你的用户名/.local/bin/uv run --directory /path/to/image2-mcp python -m image2_mcp"
      ],
      "env": {
        "PATH": "/Users/你的用户名/.local/bin:/usr/local/bin:/usr/bin:/bin",
        "HOME": "/Users/你的用户名"
      },
      "description": "文生图 — 调用公司统一 API 平台 image2 模型生成图片",
      "type": "stdio"
    }
  }
}
```

> ⚠️ 注意将 `/Users/你的用户名/` 替换为实际路径。`uv` 的路径可通过 `which uv` 获取。

---

## ⚙️ 环境变量

| 变量 | 必填 | 默认值 | 说明 |
|------|:--:|------|------|
| `MAGENE_API_KEY` | **是** | — | 公司 API 平台的 key |
| `MAGENE_API_BASE_URL` | 否 | `http://tops.magene.cn:11636/api/v1/images/generations` | API 地址 |
| `IMAGE2_OUTPUT_DIR` | 否 | 自动检测（项目 `/output`） | 图片保存路径 |
| `IMAGE2_MODEL` | 否 | `openai/gpt-image-2` | 模型名称 |

**图片输出目录的优先级**：
1. 显式参数
2. `IMAGE2_OUTPUT_DIR` 环境变量
3. `CLAUDE_PROJECT_DIR` → `<项目>/output/`（Claude Code 自动设）
4. `IMAGE2_PROJECT_DIR` → `<项目>/output/`（legacy）
5. 当前工作目录 `/output`
6. 系统临时目录 `/image2-output`

> 💡 通常无需手动设置任何目录变量——如果你在某个项目中用 Claude Code 打开，图片会自动存到那个项目的 `output/` 文件夹。

---

## 📐 工具参数

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|:--:|------|------|
| `prompt` | string | **是** | — | 图片描述（最长 32000 字符） |
| `size` | string | **是** | — | 尺寸，见下方 |
| `quality` | string | 否 | `auto` | `low` / `medium` / `high` / `auto` |
| `filename` | string | 否 | 自动生成 | 自定义文件名（不含 `.png`） |

**可用尺寸**：

| 值 | 分辨率 |
|----|--------|
| `1024x1024` | 1K 方形 |
| `1536x1024` | 1.5K 横版 |
| `1024x1536` | 1.5K 竖版 |
| `2048x2048` | 2K 方形 |
| `2048x1152` | 2K 横版 |
| `3840x2160` | 4K 横版 |
| `2160x3840` | 4K 竖版 |
| `auto` | 自动 |

自定义尺寸：`WxH` 格式，每边 ≤ 3840px，16 的倍数，宽高比 ≤ 3:1，总像素 655,360–8,294,400。

---

## 🧪 开发

```bash
uv sync --group dev
uv run pytest --cov=src --cov-report=term-missing
```

---

## 🔧 工作原理

```
AI: generate_image(prompt="a cat in a garden", size="1024x1024")
    → 服务端校验参数
    → POST 到公司 API
    → 解码 Base64 响应
    → 写入 PNG 到磁盘
    → 返回图片 + 路径 + 用量统计
```

生成是异步的——AI 调用后立即返回，图片就绪后会通过日志通知。多张图片可并行生成。
