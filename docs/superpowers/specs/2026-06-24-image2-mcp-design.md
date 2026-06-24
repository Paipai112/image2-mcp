# Image2 MCP Server — Design Spec

**Date:** 2026-06-24
**Status:** Approved
**Author:** @m / brainstorming session

## 1. 概述

### 1.1 背景

公司统一大模型平台接入了 image2（openai/gpt-image-2）文生图模型，对外开放 OpenAI Images 兼容接口。公司每人分配了 API Key，希望能在 Claude Code 和 Codex 等 AI 编程工具中直接调用生图。

### 1.2 目标

开发一个 MCP Server，让 Claude Code / Codex 能以**原生工具调用**的方式使用 image2 生图，支持团队各人用自己的 API Key，生成图片可指定存储目录。

### 1.3 非目标

- 不修改公司统一 API 平台
- 不提供 Web UI 或前端界面
- 不支持提示词翻译/增强（由 AI 直接生成英文 prompt）

---

## 2. 方案选择

选择 **MCP Server**（方案 A）而非 CLI 工具或纯 Skill，理由：

| 维度 | MCP Server | CLI + Skill | 纯 Skill |
|------|-----------|-------------|----------|
| AI 原生工具调用 | ✅ 带 Schema 约束 | ⚠️ 走 Bash | ❌ |
| 图片直接显示 | ✅ MCP image content | ❌ | ❌ |
| Codex 兼容 | ✅ | ⚠️ | ❌ |
| 团队分发 | ✅ pip install | ✅ | ⚠️ |

---

## 3. 架构

```
┌──────────────┐     MCP协议      ┌─────────────────┐    HTTP POST     ┌──────────────┐
│  Claude Code │ ◄──────────────► │  image2-mcp     │ ───────────────► │ 公司统一API   │
│  / Codex     │   JSON-RPC       │  (本地进程)       │  Base64 JSON    │ image2 接口   │
└──────────────┘                  └─────────────────┘                  └──────────────┘
                                           │
                                           ▼
                                  ┌─────────────────┐
                                  │  本地文件系统     │
                                  │  output_dir/     │
                                  │  xxxx.png        │
                                  └─────────────────┘
```

### 3.1 核心流程

```
1. AI 调用 generate_image(prompt, size, quality, output_dir?, filename?)
2. MCP Server 校验参数
3. MCP Server POST 公司 API
4. 公司 API 返回 { data: [{ b64_json: "..." }], usage, ... }
5. MCP Server 解码 Base64 → PNG 写入磁盘
6. MCP Server 返回给 AI：图片内容(MCP image) + 路径 + usage
```

---

## 4. 工具接口定义

### 4.1 `generate_image`

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `prompt` | string | ✅ | 文生图 prompt，最多 32000 字符 |
| `size` | string | ✅ | 见 4.2 可用尺寸 |
| `quality` | string | ❌ | 默认 `auto`，可选 `low` / `medium` / `high` / `auto` |
| `output_dir` | string | ❌ | 自定义输出目录，不填用默认 |
| `filename` | string | ❌ | 自定义文件名（不含 .png），不填自动生成 |

### 4.2 可用尺寸

| 预设值 | 分辨率 | 方向 |
|--------|--------|------|
| `1024x1024` | 1K | Square |
| `1536x1024` | 1.5K | Landscape |
| `1024x1536` | 1.5K | Portrait |
| `2048x2048` | 2K | Square |
| `2048x1152` | 2K | Landscape |
| `3840x2160` | 4K | Landscape |
| `2160x3840` | 4K | Portrait |
| `auto` | 自动 | - |

### 4.3 返回值

MCP 协议返回，包含两个 content 块：

1. **image** — `image/png` MIME 类型，AI 可直接看到图片
2. **text** — JSON 文本，包含文件路径和 usage

```json
{
  "path": "/Users/xxx/output/generated-20260624-a1b2c3.png",
  "url": "file:///Users/xxx/output/generated-20260624-a1b2c3.png",
  "usage": {
    "total_tokens": 210,
    "input_tokens": 24,
    "output_tokens": 186
  }
}
```

---

## 5. 配置项

用户通过环境变量配置，在 Claude Code / Codex 的 MCP 设置中填入：

| 环境变量 | 必填 | 默认值 | 说明 |
|----------|------|--------|------|
| `MAGENE_API_KEY` | ✅ | - | 公司分配的个人 API Key |
| `MAGENE_API_BASE_URL` | ❌ | `http://tops.magene.cn:11636/api/v1/images/generations` | API 地址 |
| `IMAGE2_OUTPUT_DIR` | ❌ | 系统临时目录 `/image2-output` | 默认图片输出目录 |

### 5.1 Claude Code 配置示例（`settings.local.json` 或全局 MCP 配置）

```json
{
  "mcpServers": {
    "image2": {
      "command": "python",
      "args": ["-m", "image2_mcp"],
      "env": {
        "MAGENE_API_KEY": "sk-xxxxxxxxxxxxxxxx",
        "IMAGE2_OUTPUT_DIR": "/Users/xxx/Pictures/image2-output"
      }
    }
  }
}
```

---

## 6. 错误处理

| 场景 | 分类 | 处理方式 |
|------|------|----------|
| `MAGENE_API_KEY` 未设置 | 启动失败 | 进程退出，输出明确错误提示 |
| `prompt` 为空 | 参数错误 | 返回错误信息，提示填写 prompt |
| `size` 不在合法列表 | 参数错误 | 返回支持的 size 列表 + 自定义规则 |
| 网络/连接错误 | 临时错误 | 最多重试 1 次（共 2 次），超时 60s |
| HTTP 4xx | 客户端错误 | 不重试，透传错误信息 |
| HTTP 5xx | 服务端错误 | 重试 1 次后返回错误 |
| Base64 解码失败 | 数据错误 | 返回错误，提示 API 返回异常 |
| 磁盘写入失败 | 系统错误 | 返回错误，含目标目录路径 |
| 自定义 size 不合法 | 参数错误 | 返回规则说明（边长 ≤ 3840，16px 倍数，比例 ≤ 3:1，像素范围） |

---

## 7. 技术选型

**语言：Python 3.10+**

理由：
- MCP Python SDK 是 Anthropic 官方维护
- 公司 API 文档示例为 Python，团队更熟悉
- 依赖少，安装轻量

**核心依赖：**
- `mcp` — MCP Server SDK
- `httpx` — 异步 HTTP 客户端
- `pydantic` — 参数校验和模型

---

## 8. 项目结构

```
image2-mcp/
├── pyproject.toml
├── README.md
├── src/
│   └── image2_mcp/
│       ├── __init__.py
│       ├── __main__.py       # 入口：python -m image2_mcp
│       ├── server.py         # MCP Server 主体，注册工具
│       ├── client.py         # 公司 API HTTP 异步客户端
│       ├── config.py         # 环境变量读取 + 默认值
│       ├── schemas.py        # Pydantic 参数/响应模型
│       └── errors.py         # 自定义异常类
└── tests/
    ├── test_client.py
    ├── test_schemas.py
    └── test_integration.py
```

### 8.1 模块职责

| 模块 | 职责 | 依赖 |
|------|------|------|
| `__main__.py` | 入口，调用 server.run() | server |
| `server.py` | 创建 MCP Server，注册 `generate_image` 工具 | client, config, schemas, errors |
| `client.py` | 封装 HTTP POST 请求、重试、Base64 解码 | httpx, errors |
| `config.py` | 读取 `MAGENE_API_KEY` 等环境变量，提供默认值 | - |
| `schemas.py` | Pydantic 模型：GenerateImageInput、ApiResponse、工具返回 | - |
| `errors.py` | `Image2Exception` 及其子类：`NetworkError`, `AuthError`, `ValidationError` | - |

---

## 9. 分发方案

### 方式一：pip install（推荐）

```
pip install git+https://git.company.com/platform/image2-mcp.git
```

### 方式二：uvx 免安装直接运行

```json
{
  "mcpServers": {
    "image2": {
      "command": "uvx",
      "args": ["--from", "git+https://git.company.com/platform/image2-mcp.git", "image2-mcp"],
      "env": {
        "MAGENE_API_KEY": "sk-xxxxxxxxxxxxxxxx"
      }
    }
  }
}
```

---

## 10. 测试计划

| 层级 | 内容 | 工具 |
|------|------|------|
| 单元测试 | 参数校验（schemas）、配置读取（config）、API 客户端 mock | pytest |
| 集成测试 | 用测试 API Key 调真实接口、验证图片落地、验证返回格式 | pytest |
| MCP 协议测试 | Claude Code 本地配置 MCP Server、实际对话请求生图 | 手动 |

---

## 11. 自检清单

- [X] 无 TBD / TODO
- [X] 接口与文档一致（size 为必填，quality 可选）
- [X] 架构与模块职责无矛盾
- [X] 环境变量与配置方式一致
- [X] 错误处理覆盖全面
