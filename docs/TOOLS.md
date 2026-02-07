# Claude Agent SDK 工具参考文档

本文档描述了 Claude Agent SDK 中所有可用的工具，包括内置工具、MCP 工具和 SDK MCP 工具。

---

## 一、内置工具 (CLI Built-in)

这些工具由 Claude Code CLI 内置提供，无需额外配置即可使用。

### 文件操作工具

#### Read
读取本地文件系统中的文件内容。

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `file_path` | string | ✅ | 文件的绝对路径 |
| `offset` | integer | ❌ | 起始行号（从该行开始读取） |
| `limit` | integer | ❌ | 读取的行数限制 |

**示例：**
```
Read file_path="/path/to/file.py"
Read file_path="/path/to/file.py" offset=10 limit=50
```

**说明：**
- 默认读取最多 2000 行
- 支持读取图片、PDF、Jupyter notebook
- 超过 2000 字符的行会被截断

---

#### Write
创建或覆盖文件内容。

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `file_path` | string | ✅ | 文件的绝对路径 |
| `content` | string | ✅ | 要写入的内容 |

**示例：**
```
Write file_path="/path/to/file.txt" content="Hello, World!"
```

**注意：** 如果文件已存在，必须先使用 Read 工具读取，否则会失败。

---

#### Edit
对文件进行精确的字符串替换编辑。

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `file_path` | string | ✅ | 文件的绝对路径 |
| `old_string` | string | ✅ | 要替换的原始文本 |
| `new_string` | string | ✅ | 替换后的新文本 |
| `replace_all` | boolean | ❌ | 是否替换所有匹配项（默认 false） |

**示例：**
```
Edit file_path="/path/to/file.py" old_string="old_code" new_string="new_code"
```

**注意：**
- `old_string` 必须在文件中唯一，否则需要提供更多上下文
- 使用前必须先 Read 文件

---

#### NotebookEdit
编辑 Jupyter Notebook (.ipynb) 文件的单元格。

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `notebook_path` | string | ✅ | notebook 文件的绝对路径 |
| `cell_id` | string | ❌ | 要编辑的单元格 ID |
| `cell_type` | string | ❌ | 单元格类型：`code` 或 `markdown` |
| `new_source` | string | ✅ | 新的单元格内容 |
| `edit_mode` | string | ❌ | 编辑模式：`replace`、`insert`、`delete` |

---

### 搜索工具

#### Glob
快速的文件模式匹配工具。

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `pattern` | string | ✅ | glob 模式，如 `**/*.py`、`src/**/*.ts` |
| `path` | string | ❌ | 搜索的目录路径（默认当前目录） |

**示例：**
```
Glob pattern="**/*.py"
Glob pattern="src/**/*.tsx" path="/path/to/project"
```

---

#### Grep
使用正则表达式搜索文件内容（基于 ripgrep）。

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `pattern` | string | ✅ | 正则表达式模式 |
| `path` | string | ❌ | 搜索的文件或目录 |
| `glob` | string | ❌ | 文件过滤模式，如 `*.py` |
| `type` | string | ❌ | 文件类型，如 `py`、`js`、`rust` |
| `output_mode` | string | ❌ | 输出模式：`content`、`files_with_matches`、`count` |
| `-A` | number | ❌ | 显示匹配后的 N 行 |
| `-B` | number | ❌ | 显示匹配前的 N 行 |
| `-C` | number | ❌ | 显示匹配前后各 N 行 |
| `-i` | boolean | ❌ | 忽略大小写 |

**示例：**
```
Grep pattern="def main" glob="*.py"
Grep pattern="TODO" path="/path/to/project" -C=3
```

---

### 执行工具

#### Bash
执行 bash 命令。

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `command` | string | ✅ | 要执行的命令 |
| `description` | string | ❌ | 命令描述（5-10 字） |
| `timeout` | number | ❌ | 超时时间（毫秒，最大 600000） |
| `run_in_background` | boolean | ❌ | 是否在后台运行 |

**示例：**
```
Bash command="git status" description="Show git status"
Bash command="npm install" timeout=120000
```

**注意：**
- 文件路径含空格时需要双引号
- 避免使用 `cat`、`grep`、`find` 等，应使用专用工具

---

### 网络工具

#### WebFetch
获取 URL 内容并使用 AI 处理。

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `url` | string | ✅ | 要获取的 URL |
| `prompt` | string | ✅ | 处理内容的提示词 |

**示例：**
```
WebFetch url="https://example.com" prompt="提取主要内容"
```

---

#### WebSearch
搜索网络获取最新信息。

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `query` | string | ✅ | 搜索查询 |
| `allowed_domains` | array | ❌ | 只搜索指定域名 |
| `blocked_domains` | array | ❌ | 排除指定域名 |

**示例：**
```
WebSearch query="Python 3.12 新特性"
```

---

### 代理工具

#### Task
启动子代理处理复杂任务。

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `description` | string | ✅ | 任务简短描述（3-5 字） |
| `prompt` | string | ✅ | 详细任务说明 |
| `subagent_type` | string | ✅ | 代理类型 |
| `run_in_background` | boolean | ❌ | 是否后台运行 |

**可用代理类型：**
- `general-purpose` - 通用研究和多步骤任务
- `Explore` - 快速探索代码库
- `Plan` - 设计实现方案

---

#### Skill
调用预定义的技能。

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `skill` | string | ✅ | 技能名称 |
| `args` | string | ❌ | 可选参数 |

**示例：**
```
Skill skill="commit"
Skill skill="review-pr" args="123"
```

---

### 其他工具

#### LSP
语言服务器协议操作。

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `operation` | string | ✅ | 操作类型 |
| `filePath` | string | ✅ | 文件路径 |
| `line` | integer | ✅ | 行号（1-based） |
| `character` | integer | ✅ | 字符位置（1-based） |

**操作类型：**
- `goToDefinition` - 跳转到定义
- `findReferences` - 查找引用
- `hover` - 获取悬停信息
- `documentSymbol` - 获取文档符号
- `workspaceSymbol` - 搜索工作区符号
- `incomingCalls` / `outgoingCalls` - 调用层次

---

#### TodoWrite
管理结构化任务列表。

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `todos` | array | ✅ | 任务列表 |

每个任务包含：
- `content` - 任务内容
- `status` - 状态：`pending`、`in_progress`、`completed`
- `activeForm` - 进行时描述

---

## 二、MCP 工具 (外部服务器)

MCP (Model Context Protocol) 工具通过外部服务器提供，需要配置后使用。

### 命名规范

MCP 工具的命名格式为：`mcp__<server_name>__<tool_name>`

例如：
- `mcp__finance-tools__get_stock_data`
- `mcp__notion__create_page`

### 配置方式

#### 方式 1：.mcp.json 文件

在项目根目录创建 `.mcp.json`：

```json
{
  "mcpServers": {
    "finance-tools": {
      "command": "python",
      "args": ["mcp_servers/finance.py"]
    },
    "notion": {
      "command": "npx",
      "args": ["-y", "@notionhq/notion-mcp-server"],
      "env": {
        "NOTION_API_TOKEN": "${NOTION_API_TOKEN}"
      }
    }
  }
}
```

#### 方式 2：ClaudeAgentOptions 配置

```python
from claude_agent_sdk import ClaudeAgentOptions

options = ClaudeAgentOptions(
    mcp_servers={
        "calculator": {
            "type": "stdio",
            "command": "python",
            "args": ["-m", "calculator_server"]
        }
    },
    allowed_tools=["mcp__calculator__add", "mcp__calculator__multiply"]
)
```

### MCP 服务器类型

| 类型 | 说明 |
|------|------|
| `stdio` | 标准输入输出（默认） |
| `sse` | Server-Sent Events |
| `http` | HTTP 服务器 |
| `sdk` | 进程内 SDK 服务器 |

---

## 三、SDK MCP 工具 (进程内)

SDK MCP 工具在 Python 进程内运行，无需外部进程管理。

### 创建工具

使用 `@tool` 装饰器定义工具：

```python
from claude_agent_sdk import tool, create_sdk_mcp_server

@tool("add", "Add two numbers", {"a": float, "b": float})
async def add_numbers(args: dict) -> dict:
    result = args["a"] + args["b"]
    return {
        "content": [{"type": "text", "text": f"Result: {result}"}]
    }

@tool("multiply", "Multiply two numbers", {"a": float, "b": float})
async def multiply_numbers(args: dict) -> dict:
    result = args["a"] * args["b"]
    return {
        "content": [{"type": "text", "text": f"Result: {result}"}]
    }
```

### 创建服务器

```python
server = create_sdk_mcp_server(
    name="calculator",
    version="1.0.0",
    tools=[add_numbers, multiply_numbers]
)
```

### 使用服务器

```python
from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient

options = ClaudeAgentOptions(
    mcp_servers={"calc": server},
    allowed_tools=["mcp__calc__add", "mcp__calc__multiply"]
)

async with ClaudeSDKClient(options=options) as client:
    await client.query("Calculate 15 + 27")
    async for msg in client.receive_response():
        print(msg)
```

### 完整示例

参见 `examples/mcp_calculator.py`

---

## 四、工具权限

### allowed_tools

预先批准的工具列表，跳过权限提示：

```python
options = ClaudeAgentOptions(
    allowed_tools=["Read", "Write", "Bash"]
)
```

### disallowed_tools

禁用的工具列表：

```python
options = ClaudeAgentOptions(
    disallowed_tools=["Bash"]  # 禁用 Bash
)
```

### permission_mode

权限模式：

| 模式 | 说明 |
|------|------|
| `default` | 默认，需要确认 |
| `acceptEdits` | 自动接受文件编辑 |
| `plan` | 规划模式，只读 |
| `bypassPermissions` | 跳过所有权限检查 |

```python
options = ClaudeAgentOptions(
    permission_mode="acceptEdits"
)
```

### can_use_tool 回调

自定义权限控制：

```python
async def check_tool(tool_name, tool_input, context):
    if tool_name == "Bash" and "rm" in tool_input.get("command", ""):
        return {"behavior": "deny", "message": "不允许删除命令"}
    return {"behavior": "allow"}

options = ClaudeAgentOptions(
    can_use_tool=check_tool
)
```

---

## 五、参考链接

- [Claude Code 官方文档](https://docs.anthropic.com/en/docs/claude-code/sdk)
- [可用工具列表](https://docs.anthropic.com/en/docs/claude-code/settings#tools-available-to-claude)
- [MCP 协议](https://modelcontextprotocol.io/)
