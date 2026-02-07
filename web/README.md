# Claude Agent Web UI

基于 WebSocket 的 Claude Agent 交互界面，支持：
- 实时流式输出
- Human-in-the-loop 工具审批
- 中断执行

## 快速开始

### 1. 安装后端依赖

```bash
cd web/backend
pip install -r requirements.txt
```

### 2. 安装前端依赖

```bash
cd web/frontend
npm install
```

### 3. 启动开发服务器

**终端 1 - 后端:**
```bash
cd web/backend
python main.py
# 或者
uvicorn main:app --reload --port 8000
```

**终端 2 - 前端:**
```bash
cd web/frontend
npm run dev
```

### 4. 访问

打开浏览器访问 http://localhost:3000

## 架构

```
┌─────────────────────────────────────────────────────────┐
│  Frontend (React + TypeScript + Tailwind)               │
│  - 消息列表 (流式渲染)                                   │
│  - 工具审批弹窗                                          │
│  - 中断按钮                                              │
└─────────────────────────────────────────────────────────┘
                          │ WebSocket (:3000/ws -> :8000/ws)
                          ▼
┌─────────────────────────────────────────────────────────┐
│  Backend (FastAPI)                                      │
│  - WebSocket 消息路由                                    │
│  - Agent 会话管理                                        │
│  - 工具审批等待                                          │
└─────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────┐
│  claude-agent-sdk                                       │
│  - Agent 抽象层                                          │
│  - permission_handler 回调                               │
└─────────────────────────────────────────────────────────┘
```

## WebSocket 消息协议

### Client -> Server

| Type | Data | 说明 |
|------|------|------|
| `user_message` | `{content: string}` | 用户消息 |
| `approval_response` | `{approved: bool, reason?: string}` | 审批响应 |
| `interrupt` | `{}` | 中断执行 |

### Server -> Client

| Type | Data | 说明 |
|------|------|------|
| `assistant_text` | `{text: string}` | 流式文本 |
| `tool_use` | `{tool_name, tool_input}` | 工具调用 |
| `approval_request` | `{tool_name, tool_input}` | 请求审批 |
| `result` | `{cost: number}` | 执行完成 |
| `error` | `{message: string}` | 错误 |
| `status` | `{status: string}` | 状态变更 |

## 生产部署

```bash
# 构建前端
cd web/frontend
npm run build

# 启动后端 (会自动服务静态文件)
cd web/backend
uvicorn main:app --host 0.0.0.0 --port 8000
```
