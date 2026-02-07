# Web Backend 架构文档

本文档描述 Claude Agent Web UI 后端的架构设计和核心组件。

## 概述

后端基于 FastAPI 构建，通过 WebSocket 与前端通信，使用 Redis 进行会话持久化，核心功能是管理与 Claude Agent SDK 的交互。

## 架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                         Frontend (Vue)                          │
└─────────────────────────────────────────────────────────────────┘
                              │ WebSocket
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      FastAPI Backend                            │
│  ┌─────────────────┐  ┌─────────────────┐  ┌────────────────┐  │
│  │ SessionManager  │──│  AgentSession   │──│ ClaudeSDKClient│  │
│  └─────────────────┘  └─────────────────┘  └────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                          Redis                                  │
│              (会话持久化 / 消息历史)                              │
└─────────────────────────────────────────────────────────────────┘
```

## 核心组件

### 1. MessageType 枚举

定义 WebSocket 通信的消息类型：

| 方向 | 类型 | 说明 |
|------|------|------|
| Client → Server | `USER_MESSAGE` | 用户发送的消息 |
| Client → Server | `APPROVAL_RESPONSE` | 工具审批响应 |
| Client → Server | `INTERRUPT` | 中断请求 |
| Client → Server | `CLEAR_SESSION` | 清理会话 |
| Server → Client | `ASSISTANT_TEXT` | AI 文本回复 |
| Server → Client | `THINKING` | 思考过程（Extended Thinking） |
| Server → Client | `TOOL_USE` | 工具调用 |
| Server → Client | `TOOL_RESULT` | 工具执行结果 |
| Server → Client | `APPROVAL_REQUEST` | 请求用户审批工具 |
| Server → Client | `RESULT` | 最终结果（含费用） |
| Server → Client | `ERROR` | 错误信息 |
| Server → Client | `STATUS` | 状态更新 |
| Server → Client | `HISTORY` | 历史消息 |

### 2. PendingApproval 数据类

存储待审批的工具调用信息：

```python
@dataclass
class PendingApproval:
    tool_name: str                          # 工具名称
    tool_input: dict[str, Any]              # 工具参数
    event: asyncio.Event                    # 等待用户响应的事件
    approved: bool = False                  # 是否批准
    modified_input: dict[str, Any] | None   # 修改后的参数（可选）
    deny_reason: str | None                 # 拒绝原因
```

### 3. SessionManager 类

管理所有 WebSocket 会话的生命周期。

| 方法 | 说明 |
|------|------|
| `create_session(websocket, session_id)` | 创建新会话或恢复已有会话 |
| `remove_session(session_id)` | 移除会话 |

### 4. AgentSession 类（核心）

每个 WebSocket 连接对应一个 AgentSession 实例，负责：
- 管理 Claude SDK 客户端
- 处理消息收发
- 实现 Human-in-the-loop 审批
- 会话持久化

#### 4.1 客户端管理方法

| 方法 | 说明 |
|------|------|
| `_ensure_client()` | 确保 SDK 客户端已连接，配置系统提示词、工具列表、权限回调 |
| `_disconnect_client()` | 断开客户端连接 |

#### 4.2 消息与持久化方法

| 方法 | 说明 |
|------|------|
| `send(msg_type, data)` | 发送消息到前端，可选保存到 Redis |
| `_save_message_to_redis()` | 将消息持久化到 Redis |
| `load_history()` | 从 Redis 加载历史消息 |
| `clear_session()` | 清空会话，生成新 session_id |
| `_log_outgoing_message()` | 记录发送消息的日志 |

#### 4.3 消息处理方法

| 方法 | 说明 |
|------|------|
| `handle_message()` | 消息路由器，根据类型分发到对应处理方法 |
| `handle_user_message()` | **核心方法**，处理用户消息并运行 Agent |
| `_build_query_content()` | 构建查询内容，将文件路径转换为提示词 |
| `handle_approval_response()` | 处理用户的审批响应 |
| `handle_interrupt()` | 处理中断请求 |
| `handle_clear_session()` | 处理清空会话请求 |

#### 4.4 权限审批方法

| 方法 | 说明 |
|------|------|
| `_permission_callback()` | 工具权限回调，触发人工审批流程 |
| `_request_human_approval()` | 请求用户审批，等待响应（300秒超时） |

## 核心流程

### 用户消息处理流程

```
┌─────────────────────────────────────────────────────────────────┐
│  websocket_endpoint()                                           │
│  1. 接受 WebSocket 连接                                          │
│  2. 创建/恢复 AgentSession                                       │
│  3. 发送历史消息到前端                                            │
│  4. 进入消息循环                                                  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  handle_message() - 消息路由                                     │
│  ├── USER_MESSAGE      → handle_user_message()                  │
│  ├── APPROVAL_RESPONSE → handle_approval_response()             │
│  ├── INTERRUPT         → handle_interrupt()                     │
│  └── CLEAR_SESSION     → handle_clear_session()                 │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  handle_user_message() - 核心处理                                │
│  1. _ensure_client() - 确保 SDK 客户端连接                       │
│  2. _build_query_content() - 构建查询内容                        │
│  3. _client.query() - 发送查询到 Claude                          │
│  4. _client.receive_response() - 流式接收响应                    │
│     ├── AssistantMessage → 发送 TEXT/THINKING/TOOL_USE          │
│     ├── UserMessage      → 发送 TOOL_RESULT                     │
│     └── ResultMessage    → 发送 RESULT                          │
└─────────────────────────────────────────────────────────────────┘
```

### 工具审批流程（Human-in-the-loop）

```
┌─────────────────────────────────────────────────────────────────┐
│  Claude 请求调用工具                                             │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  _permission_callback()                                         │
│  └── _request_human_approval()                                  │
│      1. 创建 PendingApproval 对象                                │
│      2. 发送 APPROVAL_REQUEST 到前端                             │
│      3. await event.wait() - 等待用户响应（300秒超时）           │
└─────────────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┴───────────────┐
              ▼                               ▼
┌─────────────────────────┐     ┌─────────────────────────┐
│  用户批准               │     │  用户拒绝               │
│  返回 PermissionAllow   │     │  返回 PermissionDeny    │
└─────────────────────────┘     └─────────────────────────┘
```

## 关键设计

### 1. 会话持久化

- 使用 Redis 存储消息历史
- 会话 TTL 为 6 小时
- 支持断线重连后恢复上下文

### 2. 客户端复用

- 同一会话复用 Claude SDK 客户端
- 保持对话上下文连续性
- 出错时断开并重新连接

### 3. 追加消息处理

- 如果 Agent 正在处理时收到新消息
- 先中断当前处理
- 将新消息存入 `_pending_message`
- 当前处理结束后自动处理待处理消息

### 4. 中断机制

- 用户可随时发送 INTERRUPT 中断 Agent
- 如果有待审批的工具调用，自动拒绝
- 调用 `_client.interrupt()` 中断 SDK

## API 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/ws` | WebSocket | Agent 通信主端点 |
| `/health` | GET | 健康检查 |
| `/api/status` | GET | API 状态（含活跃会话数） |
| `/{path}` | GET | SPA 静态文件服务 |

## 配置

| 配置项 | 值 | 说明 |
|--------|-----|------|
| `REDIS_URL` | `redis://localhost:6379` | Redis 连接地址 |
| `SESSION_TTL` | 21600 (6小时) | 会话过期时间（秒） |

## 依赖

- FastAPI - Web 框架
- redis.asyncio - Redis 异步客户端
- claude_agent_sdk - Claude Agent SDK
