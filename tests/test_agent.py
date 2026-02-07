"""Tests for the Agent abstraction layer."""

import pytest

from claude_agent_sdk.agent import (
    Agent,
    AgentError,
    AgentResult,
    AgentSession,
    PermissionDenied,
    SessionError,
    StreamMessage,
    ToolError,
)
from claude_agent_sdk.agent.hooks import HookRegistry
from claude_agent_sdk.agent.tool_registry import ToolRegistry
from claude_agent_sdk.types import (
    AssistantMessage,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
)


class TestToolRegistry:
    """Tests for ToolRegistry."""

    def test_register_tool(self) -> None:
        """Test basic tool registration."""
        registry = ToolRegistry()

        async def my_tool(x: int, y: str) -> str:
            """A test tool."""
            return f"{x}: {y}"

        registry.register(my_tool)

        assert "my_tool" in registry.tool_names

    def test_register_tool_with_custom_name(self) -> None:
        """Test tool registration with custom name."""
        registry = ToolRegistry()

        async def my_tool(x: int) -> str:
            return str(x)

        registry.register(my_tool, name="custom_name")

        assert "custom_name" in registry.tool_names
        assert "my_tool" not in registry.tool_names

    def test_infer_schema_basic_types(self) -> None:
        """Test schema inference for basic types."""
        registry = ToolRegistry()

        async def typed_tool(s: str, i: int, f: float, b: bool) -> str:
            return "ok"

        registry.register(typed_tool)
        tools = registry.build_sdk_tools()

        assert len(tools) == 1
        schema = tools[0].input_schema
        assert schema["type"] == "object"
        assert schema["properties"]["s"]["type"] == "string"
        assert schema["properties"]["i"]["type"] == "integer"
        assert schema["properties"]["f"]["type"] == "number"
        assert schema["properties"]["b"]["type"] == "boolean"

    def test_infer_schema_required_params(self) -> None:
        """Test that required parameters are correctly identified."""
        registry = ToolRegistry()

        async def mixed_tool(required: str, optional: str = "default") -> str:
            return required + optional

        registry.register(mixed_tool)
        tools = registry.build_sdk_tools()

        schema = tools[0].input_schema
        assert "required" in schema["required"]
        assert "optional" not in schema["required"]

    def test_extract_description_from_docstring(self) -> None:
        """Test description extraction from docstring."""
        registry = ToolRegistry()

        async def documented_tool(x: int) -> str:
            """This is the tool description.

            More details here.
            """
            return str(x)

        registry.register(documented_tool)
        tools = registry.build_sdk_tools()

        assert tools[0].description == "This is the tool description."

    @pytest.mark.anyio
    async def test_handler_wraps_string_result(self) -> None:
        """Test that string results are wrapped in MCP format."""
        registry = ToolRegistry()

        async def string_tool(x: int) -> str:
            return f"Result: {x}"

        registry.register(string_tool)
        tools = registry.build_sdk_tools()

        result = await tools[0].handler({"x": 42})
        assert result == {"content": [{"type": "text", "text": "Result: 42"}]}

    @pytest.mark.anyio
    async def test_handler_passes_through_mcp_format(self) -> None:
        """Test that MCP-formatted results pass through unchanged."""
        registry = ToolRegistry()

        async def mcp_tool(x: int) -> dict:
            return {"content": [{"type": "text", "text": f"MCP: {x}"}]}

        registry.register(mcp_tool)
        tools = registry.build_sdk_tools()

        result = await tools[0].handler({"x": 42})
        assert result == {"content": [{"type": "text", "text": "MCP: 42"}]}


class TestHookRegistry:
    """Tests for HookRegistry."""

    def test_add_pre_tool_hook(self) -> None:
        """Test adding PreToolUse hook."""
        registry = HookRegistry()

        async def my_hook(tool_name: str, tool_input: dict) -> None:
            pass

        registry.add_pre_tool_use("Bash", my_hook)
        hooks = registry.build_hooks()

        assert hooks is not None
        assert "PreToolUse" in hooks
        assert len(hooks["PreToolUse"]) == 1
        assert hooks["PreToolUse"][0].matcher == "Bash"

    def test_add_post_tool_hook(self) -> None:
        """Test adding PostToolUse hook."""
        registry = HookRegistry()

        async def my_hook(tool_name: str, tool_input: dict, output: str) -> None:
            pass

        registry.add_post_tool_use("Write", my_hook)
        hooks = registry.build_hooks()

        assert hooks is not None
        assert "PostToolUse" in hooks

    def test_add_prompt_hook(self) -> None:
        """Test adding UserPromptSubmit hook."""
        registry = HookRegistry()

        async def my_hook(prompt: str) -> str | None:
            return "extra context"

        registry.add_user_prompt_submit(my_hook)
        hooks = registry.build_hooks()

        assert hooks is not None
        assert "UserPromptSubmit" in hooks

    def test_empty_registry_returns_none(self) -> None:
        """Test that empty registry returns None."""
        registry = HookRegistry()
        hooks = registry.build_hooks()
        assert hooks is None

    @pytest.mark.anyio
    async def test_pre_tool_hook_permission_denied(self) -> None:
        """Test that PermissionDenied is converted to deny decision."""
        registry = HookRegistry()

        async def blocking_hook(tool_name: str, tool_input: dict) -> None:
            raise PermissionDenied("Not allowed")

        registry.add_pre_tool_use("Bash", blocking_hook)
        hooks = registry.build_hooks()

        # Get the wrapped callback
        wrapped = hooks["PreToolUse"][0].hooks[0]

        # Call it with mock input
        result = await wrapped(
            {"tool_name": "Bash", "tool_input": {"command": "ls"}},
            None,
            {"signal": None},
        )

        assert "hookSpecificOutput" in result
        assert result["hookSpecificOutput"]["permissionDecision"] == "deny"
        assert "Not allowed" in result["hookSpecificOutput"]["permissionDecisionReason"]


class TestAgentResult:
    """Tests for AgentResult."""

    def test_from_messages_extracts_text(self) -> None:
        """Test text extraction from messages."""
        messages = [
            AssistantMessage(
                content=[TextBlock(text="Hello"), TextBlock(text="World")],
                model="claude-3",
            )
        ]

        result = AgentResult.from_messages(messages)
        assert result.text == "Hello\nWorld"

    def test_from_messages_extracts_tool_calls(self) -> None:
        """Test tool call extraction from messages."""
        messages = [
            AssistantMessage(
                content=[
                    ToolUseBlock(id="1", name="my_tool", input={"x": 1}),
                    TextBlock(text="Done"),
                ],
                model="claude-3",
            )
        ]

        result = AgentResult.from_messages(messages)
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0]["name"] == "my_tool"
        assert result.tool_calls[0]["input"] == {"x": 1}

    def test_from_messages_extracts_cost(self) -> None:
        """Test cost extraction from ResultMessage."""
        messages = [
            AssistantMessage(content=[TextBlock(text="Hi")], model="claude-3"),
            ResultMessage(
                subtype="result",
                duration_ms=1000,
                duration_api_ms=800,
                is_error=False,
                num_turns=1,
                session_id="test",
                total_cost_usd=0.001,
            ),
        ]

        result = AgentResult.from_messages(messages)
        assert result.cost == 0.001
        assert result.duration_ms == 1000


class TestStreamMessage:
    """Tests for StreamMessage."""

    def test_from_text_message(self) -> None:
        """Test StreamMessage from text content."""
        msg = AssistantMessage(
            content=[TextBlock(text="Hello")],
            model="claude-3",
        )

        stream_msg = StreamMessage.from_message(msg)
        assert stream_msg.is_text is True
        assert stream_msg.text == "Hello"
        assert stream_msg.is_tool_use is False

    def test_from_tool_use_message(self) -> None:
        """Test StreamMessage from tool use content."""
        msg = AssistantMessage(
            content=[ToolUseBlock(id="1", name="my_tool", input={"x": 1})],
            model="claude-3",
        )

        stream_msg = StreamMessage.from_message(msg)
        assert stream_msg.is_tool_use is True
        assert stream_msg.tool_name == "my_tool"
        assert stream_msg.tool_input == {"x": 1}
        assert stream_msg.is_text is False

    def test_from_result_message(self) -> None:
        """Test StreamMessage from result message."""
        msg = ResultMessage(
            subtype="result",
            duration_ms=1000,
            duration_api_ms=800,
            is_error=False,
            num_turns=1,
            session_id="test",
            total_cost_usd=0.002,
        )

        stream_msg = StreamMessage.from_message(msg)
        assert stream_msg.is_result is True
        assert stream_msg.cost == 0.002


class TestAgent:
    """Tests for Agent class."""

    def test_agent_creation(self) -> None:
        """Test basic agent creation."""
        agent = Agent(
            name="test-agent",
            system_prompt="You are a test agent.",
            allowed_tools=["Read", "Grep"],
        )

        assert agent.name == "test-agent"
        assert agent.system_prompt == "You are a test agent."
        assert agent.allowed_tools == ["Read", "Grep"]

    def test_tool_decorator_without_args(self) -> None:
        """Test @agent.tool decorator without arguments."""
        agent = Agent(name="test")

        @agent.tool
        async def my_tool(x: int) -> str:
            """My tool."""
            return str(x)

        assert "my_tool" in agent._tool_registry.tool_names

    def test_tool_decorator_with_args(self) -> None:
        """Test @agent.tool decorator with arguments."""
        agent = Agent(name="test")

        @agent.tool(name="custom", description="Custom description")
        async def my_tool(x: int) -> str:
            return str(x)

        assert "custom" in agent._tool_registry.tool_names
        assert "my_tool" not in agent._tool_registry.tool_names

    def test_before_tool_decorator(self) -> None:
        """Test @agent.before_tool decorator."""
        agent = Agent(name="test")

        @agent.before_tool("Bash", "Write")
        async def check_tool(tool_name: str, tool_input: dict) -> None:
            pass

        hooks = agent._hook_registry.build_hooks()
        assert hooks is not None
        assert "PreToolUse" in hooks
        assert hooks["PreToolUse"][0].matcher == "Bash|Write"

    def test_after_tool_decorator(self) -> None:
        """Test @agent.after_tool decorator."""
        agent = Agent(name="test")

        @agent.after_tool("*")
        async def log_tool(tool_name: str, tool_input: dict, output: str) -> None:
            pass

        hooks = agent._hook_registry.build_hooks()
        assert hooks is not None
        assert "PostToolUse" in hooks
        # "*" should be converted to None (match all)
        assert hooks["PostToolUse"][0].matcher is None

    def test_on_prompt_decorator(self) -> None:
        """Test @agent.on_prompt decorator."""
        agent = Agent(name="test")

        @agent.on_prompt
        async def inject_context(prompt: str) -> str | None:
            return "extra"

        hooks = agent._hook_registry.build_hooks()
        assert hooks is not None
        assert "UserPromptSubmit" in hooks

    def test_permission_handler_decorator(self) -> None:
        """Test @agent.permission_handler decorator."""
        agent = Agent(name="test")

        @agent.permission_handler
        async def check_permission(tool_name: str, tool_input: dict) -> bool:
            return True

        assert agent._permission_handler is not None

    def test_build_options_includes_custom_tools(self) -> None:
        """Test that _build_options includes custom tools in allowed_tools."""
        agent = Agent(name="myagent", allowed_tools=["Read"])

        @agent.tool
        async def custom_tool(x: int) -> str:
            return str(x)

        options = agent._build_options()

        assert "Read" in options.allowed_tools
        assert "mcp__myagent__custom_tool" in options.allowed_tools

    def test_build_options_creates_mcp_server(self) -> None:
        """Test that _build_options creates MCP server for custom tools."""
        agent = Agent(name="myagent")

        @agent.tool
        async def custom_tool(x: int) -> str:
            return str(x)

        options = agent._build_options()

        assert "myagent" in options.mcp_servers
        assert options.mcp_servers["myagent"]["type"] == "sdk"

    def test_session_returns_agent_session(self) -> None:
        """Test that session() returns AgentSession."""
        agent = Agent(name="test")
        session = agent.session()

        assert isinstance(session, AgentSession)


class TestExceptions:
    """Tests for exception classes."""

    def test_permission_denied_is_agent_error(self) -> None:
        """Test PermissionDenied inherits from AgentError."""
        assert issubclass(PermissionDenied, AgentError)

    def test_tool_error_is_agent_error(self) -> None:
        """Test ToolError inherits from AgentError."""
        assert issubclass(ToolError, AgentError)

    def test_session_error_is_agent_error(self) -> None:
        """Test SessionError inherits from AgentError."""
        assert issubclass(SessionError, AgentError)

    def test_permission_denied_message(self) -> None:
        """Test PermissionDenied stores message."""
        exc = PermissionDenied("Not allowed")
        assert str(exc) == "Not allowed"
