"""FastAPI backend for Claude Agent Web UI."""

import asyncio
import json
import logging
import uuid
from contextlib import asynccontextmanager
from datetime import datetime

import redis.asyncio as redis

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

# Add parent path for imports
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from claude_agent_sdk import (
    ClaudeSDKClient,
    ClaudeAgentOptions,
    PermissionResultAllow,
    PermissionResultDeny,
    AssistantMessage,
    UserMessage,
    TextBlock,
    ThinkingBlock,
    ToolUseBlock,
    ToolResultBlock,
    ResultMessage,
    ToolPermissionContext,
)

# Redis 配置
REDIS_URL = "redis://localhost:6379"
SESSION_TTL = 6 * 60 * 60  # 6 hours in seconds

# Redis 客户端
redis_client: redis.Redis | None = None


async def get_redis() -> redis.Redis:
    """Get Redis client."""
    global redis_client
    if redis_client is None:
        redis_client = redis.from_url(REDIS_URL, decode_responses=True)
    return redis_client


def get_session_key(session_id: str) -> str:
    """Get Redis key for session messages."""
    return f"session:{session_id}:messages"


def get_session_meta_key(session_id: str) -> str:
    """Get Redis key for session metadata."""
    return f"session:{session_id}:meta"


class MessageType(str, Enum):
    """WebSocket message types."""
    # Client -> Server
    USER_MESSAGE = "user_message"
    APPROVAL_RESPONSE = "approval_response"
    INTERRUPT = "interrupt"
    CLEAR_SESSION = "clear_session"  # 清理会话

    # Server -> Client
    ASSISTANT_TEXT = "assistant_text"
    THINKING = "thinking"  # Extended thinking block
    TOOL_USE = "tool_use"
    TOOL_RESULT = "tool_result"
    APPROVAL_REQUEST = "approval_request"
    RESULT = "result"
    ERROR = "error"
    STATUS = "status"
    HISTORY = "history"  # 历史消息


@dataclass
class PendingApproval:
    """Pending tool approval request."""
    tool_name: str
    tool_input: dict[str, Any]
    event: asyncio.Event = field(default_factory=asyncio.Event)
    approved: bool = False
    modified_input: dict[str, Any] | None = None
    deny_reason: str | None = None


class SessionManager:
    """Manages WebSocket sessions and their agents."""

    def __init__(self):
        self.sessions: dict[str, "AgentSession"] = {}

    async def create_session(self, websocket: WebSocket, session_id: str | None = None) -> "AgentSession":
        """Create or restore a session."""
        r = await get_redis()

        if session_id:
            # 检查 session 是否存在于 Redis
            meta_key = get_session_meta_key(session_id)
            exists = await r.exists(meta_key)
            if exists:
                logger.info(f"Restoring session: {session_id}")
            else:
                logger.info(f"Session {session_id} not found in Redis, creating new")
                session_id = str(uuid.uuid4())
        else:
            session_id = str(uuid.uuid4())

        session = AgentSession(session_id, websocket, self)
        self.sessions[session_id] = session

        # 更新 session 元数据
        meta_key = get_session_meta_key(session_id)
        await r.hset(meta_key, mapping={
            "created_at": datetime.now().isoformat(),
            "last_active": datetime.now().isoformat(),
        })
        await r.expire(meta_key, SESSION_TTL)

        logger.info(f"Session created/restored: {session_id}, total sessions: {len(self.sessions)}")
        return session

    def remove_session(self, session_id: str):
        if session_id in self.sessions:
            del self.sessions[session_id]
            logger.info(f"Session removed: {session_id}, total sessions: {len(self.sessions)}")


class AgentSession:
    """Individual agent session with WebSocket connection."""

    def __init__(self, session_id: str, websocket: WebSocket, manager: SessionManager):
        self.session_id = session_id
        self.websocket = websocket
        self.manager = manager
        self.pending_approval: PendingApproval | None = None
        self.interrupted = False
        self._client: ClaudeSDKClient | None = None
        self._client_connected = False
        self._processing = False  # 是否正在处理消息
        self._pending_message: tuple[str, list[str] | None] | None = None  # 待处理的追加消息

    async def _ensure_client(self):
        """Ensure client is connected, create if needed."""
        if self._client is None or not self._client_connected:
            # Create options with permission callback for human-in-the-loop
            # Use resume to restore previous conversation context
            options = ClaudeAgentOptions(
                system_prompt="""# 角色定义
你是一个专家级 AI 智能体 (Autonomous Agent)，专注于解决复杂的编程与系统任务。你不仅仅是回答问题，更是问题的解决者。

# 核心思维模式
在执行任何操作前，必须进行**深度思考 (Chain of Thought)**：
1. **分析**：用户想要达成的最终目标是什么？
2. **拆解**：将目标拆解为原子步骤。
3. **检查**：当前掌握的信息是否足够？如果不足，先使用工具获取信息。
4. **决策**：选择最合适的工具。
5. **反思**：如果上一步操作失败，分析原因并尝试替代方案，而不是重复错误。

# 交互原则
- 使用中文回答。
- **Action-Driven**：除非任务模棱两可，否则不要频繁请求许可，默认你拥有在当前项目目录下执行读取和非破坏性操作的权限。
- 回复结构：先输出思考过程，再执行工具，最后给出完整的总结和解释。

# 工具使用
- 优先使用专用工具（Read/Edit/Write）而非 Bash 命令。
- **文件编辑原子性**：修改文件前，务必先读取原始内容，确保对上下文的理解是准确的。
- 遇到 `Permission Denied` 或 `File Not Found` 等错误时，必须自动分析路径或权限，尝试修复一次后再汇报。

# 安全边界
- 严禁在无明确指令下执行 `rm -rf` 等高风险命令。
- 不读取 `env`、`.ssh` 等敏感路径，除非用户明确要求。

# 输出风格
- 思考过程请包裹在 `<thinking>...</thinking>` 标签中。
- 代码修改请使用 Unified Diff 格式或明确的 Block 替换格式。
""",
                allowed_tools=[
                    "Read", "Write", "Edit", "Bash", "Grep", "Glob",
                    "WebSearch", "WebFetch", "Task", "TaskOutput", "TaskStop",
                    "NotebookEdit", "AskUserQuestion", "Skill",
                    "EnterPlanMode", "ExitPlanMode",
                    "TaskCreate", "TaskGet", "TaskUpdate", "TaskList",
                ],
                can_use_tool=self._permission_callback,
                stderr=lambda line: logger.error(f"[{self.session_id[:8]}] CLI stderr: {line}"),
            )
            self._client = ClaudeSDKClient(options=options)
            await self._client.connect()
            self._client_connected = True
            logger.info(f"[{self.session_id[:8]}] Client connected")

    async def _disconnect_client(self):
        """Disconnect the client if connected."""
        if self._client and self._client_connected:
            try:
                await self._client.disconnect()
            except Exception as e:
                logger.warning(f"[{self.session_id[:8]}] Error disconnecting client: {e}")
            self._client = None
            self._client_connected = False
            logger.info(f"[{self.session_id[:8]}] Client disconnected")

    async def send(self, msg_type: MessageType, data: dict[str, Any] | None = None, save_to_redis: bool = True):
        """Send message to client."""
        message = {"type": msg_type.value, "data": data or {}}
        # 记录所有发送给客户端的消息
        self._log_outgoing_message(msg_type, data)
        await self.websocket.send_json(message)

        # 保存消息到 Redis（排除状态消息和历史消息）
        if save_to_redis and msg_type not in (MessageType.STATUS, MessageType.HISTORY, MessageType.APPROVAL_REQUEST):
            await self._save_message_to_redis(msg_type, data)

    async def _save_message_to_redis(self, msg_type: MessageType, data: dict[str, Any] | None):
        """Save message to Redis for persistence."""
        r = await get_redis()
        key = get_session_key(self.session_id)
        meta_key = get_session_meta_key(self.session_id)

        message = {
            "type": msg_type.value,
            "data": data or {},
            "timestamp": datetime.now().isoformat(),
        }
        await r.rpush(key, json.dumps(message, ensure_ascii=False))
        await r.expire(key, SESSION_TTL)
        await r.hset(meta_key, "last_active", datetime.now().isoformat())
        await r.expire(meta_key, SESSION_TTL)

    async def load_history(self) -> list[dict[str, Any]]:
        """Load message history from Redis."""
        r = await get_redis()
        key = get_session_key(self.session_id)
        messages = await r.lrange(key, 0, -1)
        return [json.loads(msg) for msg in messages]

    async def clear_session(self) -> str:
        """Clear current session and create a new one."""
        r = await get_redis()
        old_session_id = self.session_id

        # 删除旧 session 数据
        await r.delete(get_session_key(old_session_id))
        await r.delete(get_session_meta_key(old_session_id))

        # 生成新 session_id
        new_session_id = str(uuid.uuid4())
        self.session_id = new_session_id

        # 更新 manager 中的引用
        if old_session_id in self.manager.sessions:
            del self.manager.sessions[old_session_id]
        self.manager.sessions[new_session_id] = self

        # 创建新 session 元数据
        meta_key = get_session_meta_key(new_session_id)
        await r.hset(meta_key, mapping={
            "created_at": datetime.now().isoformat(),
            "last_active": datetime.now().isoformat(),
        })
        await r.expire(meta_key, SESSION_TTL)

        logger.info(f"Session cleared: {old_session_id} -> {new_session_id}")
        return new_session_id

    def _log_outgoing_message(self, msg_type: MessageType, data: dict[str, Any] | None):
        """Log outgoing message with appropriate detail level."""
        prefix = f"[{self.session_id[:8]}] -> "

        if msg_type == MessageType.ASSISTANT_TEXT:
            text = data.get("text", "") if data else ""
            # 显示完整文本，但截断过长的内容
            if len(text) > 500:
                logger.info(f"{prefix}ASSISTANT_TEXT: {text[:500]}... (truncated, total {len(text)} chars)")
            else:
                logger.info(f"{prefix}ASSISTANT_TEXT: {text}")

        elif msg_type == MessageType.THINKING:
            thinking = data.get("thinking", "") if data else ""
            if len(thinking) > 300:
                logger.info(f"{prefix}THINKING: {thinking[:300]}... (truncated, total {len(thinking)} chars)")
            else:
                logger.info(f"{prefix}THINKING: {thinking}")

        elif msg_type == MessageType.TOOL_USE:
            tool_name = data.get("tool_name", "") if data else ""
            tool_input = data.get("tool_input", {}) if data else {}
            input_str = json.dumps(tool_input, ensure_ascii=False)
            if len(input_str) > 300:
                logger.info(f"{prefix}TOOL_USE: {tool_name} | input: {input_str[:300]}... (truncated)")
            else:
                logger.info(f"{prefix}TOOL_USE: {tool_name} | input: {input_str}")

        elif msg_type == MessageType.TOOL_RESULT:
            tool_id = data.get("tool_use_id", "") if data else ""
            result = data.get("result", "") if data else ""
            is_error = data.get("is_error", False) if data else False
            status = "ERROR" if is_error else "OK"
            if len(result) > 500:
                logger.info(f"{prefix}TOOL_RESULT [{status}]: {result[:500]}... (truncated, total {len(result)} chars)")
            else:
                logger.info(f"{prefix}TOOL_RESULT [{status}]: {result}")

        elif msg_type == MessageType.APPROVAL_REQUEST:
            tool_name = data.get("tool_name", "") if data else ""
            logger.info(f"{prefix}APPROVAL_REQUEST: {tool_name}")

        elif msg_type == MessageType.RESULT:
            cost = data.get("cost", 0) if data else 0
            logger.info(f"{prefix}RESULT: cost=${cost:.4f}")

        elif msg_type == MessageType.STATUS:
            status = data.get("status", "") if data else ""
            logger.info(f"{prefix}STATUS: {status}")

        elif msg_type == MessageType.ERROR:
            message = data.get("message", "") if data else ""
            logger.error(f"{prefix}ERROR: {message}")

    async def handle_message(self, message: dict[str, Any]):
        """Handle incoming WebSocket message."""
        msg_type = message.get("type")
        data = message.get("data", {})

        if msg_type == MessageType.USER_MESSAGE.value:
            content = data.get("content", "")
            file_paths = data.get("file_paths")

            # 如果正在处理中，设置为待处理消息并中断当前处理
            if self._processing:
                logger.info(f"[{self.session_id[:8]}] Received message during processing, will interrupt and append")
                self._pending_message = (content, file_paths)
                await self.handle_interrupt()
                return

            # 保存用户消息到 Redis
            await self._save_message_to_redis(MessageType.USER_MESSAGE, {"content": content, "file_paths": file_paths})
            await self.handle_user_message(content, file_paths)

        elif msg_type == MessageType.APPROVAL_RESPONSE.value:
            await self.handle_approval_response(data)

        elif msg_type == MessageType.INTERRUPT.value:
            await self.handle_interrupt()

        elif msg_type == MessageType.CLEAR_SESSION.value:
            await self.handle_clear_session()

    async def handle_user_message(self, content: str, file_paths: list[str] | None = None):
        """Process user message and run agent."""
        if not content.strip() and not file_paths:
            return

        logger.info(f"[{self.session_id[:8]}] User message: {content[:100]}{'...' if len(content) > 100 else ''}")
        if file_paths:
            logger.info(f"[{self.session_id[:8]}] File paths: {file_paths}")

        self.interrupted = False
        self._processing = True
        await self.send(MessageType.STATUS, {"status": "thinking"})

        try:
            # Build query content with file paths
            query_content = self._build_query_content(content, file_paths)

            # Ensure client is connected (reuse existing or create new)
            await self._ensure_client()

            # Send query to existing client
            await self._client.query(query_content)

            async for msg in self._client.receive_response():
                if self.interrupted:
                    await self._client.interrupt()
                    await self.send(MessageType.STATUS, {"status": "interrupted"})
                    break

                if isinstance(msg, AssistantMessage):
                    for block in msg.content:
                        if isinstance(block, TextBlock):
                            await self.send(MessageType.ASSISTANT_TEXT, {"text": block.text})
                        elif isinstance(block, ThinkingBlock):
                            logger.info(f"[{self.session_id[:8]}] Thinking block received")
                            await self.send(MessageType.THINKING, {
                                "thinking": block.thinking,
                            })
                        elif isinstance(block, ToolUseBlock):
                            logger.info(f"[{self.session_id[:8]}] Tool use: {block.name}")
                            await self.send(MessageType.TOOL_USE, {
                                "tool_use_id": block.id,
                                "tool_name": block.name,
                                "tool_input": block.input,
                            })

                elif isinstance(msg, UserMessage):
                    # Tool results come in UserMessage
                    if isinstance(msg.content, list):
                        for block in msg.content:
                            if isinstance(block, ToolResultBlock):
                                tool_content = block.content
                                if isinstance(tool_content, list):
                                    # Extract text from content blocks
                                    text_parts = []
                                    for item in tool_content:
                                        if isinstance(item, dict) and item.get("type") == "text":
                                            text_parts.append(item.get("text", ""))
                                    tool_content = "\n".join(text_parts)
                                await self.send(MessageType.TOOL_RESULT, {
                                    "tool_use_id": block.tool_use_id,
                                    "result": str(tool_content) if tool_content else "Done",
                                    "is_error": block.is_error,
                                })
                                if block.is_error:
                                    logger.warning(f"[{self.session_id[:8]}] Tool error: {str(tool_content)[:200]}")

                elif isinstance(msg, ResultMessage):
                    logger.info(f"[{self.session_id[:8]}] Completed, cost: ${msg.total_cost_usd:.4f}")
                    logger.info(f"[{self.session_id[:8]}] Usage details: {msg.usage}")
                    await self.send(MessageType.RESULT, {
                        "cost": msg.total_cost_usd,
                        "usage": msg.usage,
                    })

            if not self.interrupted:
                await self.send(MessageType.STATUS, {"status": "done"})

        except Exception as e:
            import traceback
            logger.error(f"[{self.session_id[:8]}] Error: {e}")
            traceback.print_exc()
            await self.send(MessageType.ERROR, {"message": str(e)})
            await self.send(MessageType.STATUS, {"status": "error"})
            # 出错时断开 client，下次重新连接
            await self._disconnect_client()
        finally:
            self._processing = False

        # 检查是否有待处理的追加消息
        if self._pending_message:
            pending_content, pending_file_paths = self._pending_message
            self._pending_message = None
            logger.info(f"[{self.session_id[:8]}] Processing pending message: {pending_content[:50]}...")
            # 保存用户消息到 Redis
            await self._save_message_to_redis(MessageType.USER_MESSAGE, {"content": pending_content, "file_paths": pending_file_paths})
            await self.handle_user_message(pending_content, pending_file_paths)

    def _build_query_content(self, content: str, file_paths: list[str] | None) -> str:
        """Build query content with file path references for Claude to process via tools."""
        if not file_paths:
            return content

        # Build text message with file references
        parts = []

        # Add file paths for Claude to process
        if file_paths:
            parts.append("用户提供了以下文件，请使用 Read 工具读取并处理：\n")
            for path in file_paths:
                parts.append(f"- {path}")
            parts.append("")

        # Add user's text message
        if content:
            parts.append(content)

        return "\n".join(parts)

    async def _permission_callback(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
        context: ToolPermissionContext,
    ):
        """Permission callback for human-in-the-loop approval."""
        result = await self._request_human_approval(tool_name, tool_input)
        if result is True:
            return PermissionResultAllow()
        else:
            return PermissionResultDeny(message=str(result))

    async def _request_human_approval(self, tool_name: str, tool_input: dict) -> bool | str:
        """Request human approval for tool use."""
        logger.info(f"[{self.session_id[:8]}] Requesting approval for: {tool_name}")
        # Create pending approval
        self.pending_approval = PendingApproval(
            tool_name=tool_name,
            tool_input=tool_input,
        )

        # Send approval request to client
        await self.send(MessageType.APPROVAL_REQUEST, {
            "tool_name": tool_name,
            "tool_input": tool_input,
        })

        # Wait for response (with timeout)
        try:
            await asyncio.wait_for(self.pending_approval.event.wait(), timeout=300)
        except asyncio.TimeoutError:
            return "Approval timeout - user did not respond"

        approval = self.pending_approval
        self.pending_approval = None

        if approval.approved:
            logger.info(f"[{self.session_id[:8]}] Approval granted for: {tool_name}")
            return True
        else:
            logger.info(f"[{self.session_id[:8]}] Approval denied for: {tool_name}, reason: {approval.deny_reason}")
            return approval.deny_reason or "User denied the request"

    async def handle_approval_response(self, data: dict[str, Any]):
        """Handle approval response from client."""
        if not self.pending_approval:
            return

        approved = data.get("approved", False)
        self.pending_approval.approved = approved
        self.pending_approval.deny_reason = data.get("reason")
        self.pending_approval.modified_input = data.get("modified_input")
        self.pending_approval.event.set()

    async def handle_interrupt(self):
        """Handle interrupt request."""
        logger.info(f"[{self.session_id[:8]}] Interrupted by user")
        self.interrupted = True
        if self.pending_approval:
            self.pending_approval.approved = False
            self.pending_approval.deny_reason = "Interrupted by user"
            self.pending_approval.event.set()

    async def handle_clear_session(self):
        """Handle clear session request."""
        # 断开现有 client
        await self._disconnect_client()
        new_session_id = await self.clear_session()
        await self.send(MessageType.STATUS, {
            "status": "session_cleared",
            "session_id": new_session_id,
        }, save_to_redis=False)


# Global session manager
session_manager = SessionManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    yield


app = FastAPI(title="Claude Agent Web UI", lifespan=lifespan)

# CORS for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, session_id: str | None = None):
    """WebSocket endpoint for agent communication."""
    await websocket.accept()
    session = await session_manager.create_session(websocket, session_id)

    try:
        # 发送连接状态和 session_id
        await session.send(MessageType.STATUS, {
            "status": "connected",
            "session_id": session.session_id,
        }, save_to_redis=False)

        # 加载并发送历史消息
        history = await session.load_history()
        if history:
            logger.info(f"[{session.session_id[:8]}] Sending {len(history)} history messages")
            await session.send(MessageType.HISTORY, {
                "messages": history,
            }, save_to_redis=False)

        while True:
            data = await websocket.receive_json()
            await session.handle_message(data)

    except WebSocketDisconnect:
        pass
    finally:
        # 断开 client 连接
        await session._disconnect_client()
        session_manager.remove_session(session.session_id)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok"}


@app.get("/api/status")
async def api_status():
    """API status endpoint."""
    return {"status": "ok", "sessions": len(session_manager.sessions)}


# Serve static files in production (must be last to not override API routes)
static_path = Path(__file__).parent.parent / "frontend" / "dist"
if static_path.exists():
    # Mount at root but API routes take precedence since they're registered first
    from starlette.routing import Mount
    from starlette.staticfiles import StaticFiles as StarletteStaticFiles

    # Use a catch-all approach that doesn't override explicit routes
    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """Serve SPA for all non-API routes."""
        file_path = static_path / full_path
        if file_path.is_file():
            return FileResponse(file_path)
        # Return index.html for SPA routing
        return FileResponse(static_path / "index.html")


if __name__ == "__main__":
    import uvicorn
    logger.info("Starting Agent Web UI backend on http://0.0.0.0:8000")
    uvicorn.run(app, host="0.0.0.0", port=8000)
