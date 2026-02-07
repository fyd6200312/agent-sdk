"""High-level Agent abstraction for Claude Code SDK."""

from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, overload

from ..types import (
    ClaudeAgentOptions,
    HookEvent,
    HookMatcher,
    Message,
    PermissionResult,
    PermissionResultAllow,
    PermissionResultDeny,
    ToolPermissionContext,
)
from .hooks import HookRegistry, PostToolCallback, PreToolCallback, PromptCallback
from .result import AgentResult, StreamMessage
from .session import AgentSession
from .tool_registry import ToolRegistry

# Type for permission handler callback
PermissionHandler = Callable[[str, dict[str, Any]], Awaitable[bool | str]]


@dataclass
class Agent:
    """High-level Agent abstraction for Claude Code SDK.

    Provides a simplified interface for creating agents with custom tools,
    hooks, and permission handling.

    Example:
        ```python
        agent = Agent(
            name="my-assistant",
            system_prompt="You are a helpful assistant.",
            allowed_tools=["Read", "Grep"],
        )

        @agent.tool
        async def calculate(a: float, b: float) -> str:
            '''Add two numbers.'''
            return f"{a} + {b} = {a + b}"

        result = await agent.run("What is 15 + 27?")
        print(result.text)
        ```

    Attributes:
        name: Agent name (used for MCP server naming).
        system_prompt: System prompt for the agent.
        model: Model to use (e.g., "claude-sonnet-4-5-20250929").
        allowed_tools: List of built-in tools to allow.
        auto_approve: List of tools to auto-approve without permission check.
        permission_mode: Permission mode ("default", "acceptEdits", "plan", "bypassPermissions").
        max_turns: Maximum number of turns.
        max_budget_usd: Maximum budget in USD.
        cwd: Working directory for the agent.
    """

    name: str = "agent"
    system_prompt: str | None = None
    model: str | None = None
    allowed_tools: list[str] = field(default_factory=list)
    auto_approve: list[str] = field(default_factory=list)
    permission_mode: str = "default"
    max_turns: int | None = None
    max_budget_usd: float | None = None
    cwd: str | None = None

    def __post_init__(self) -> None:
        """Initialize internal registries."""
        self._tool_registry = ToolRegistry()
        self._hook_registry = HookRegistry()
        self._permission_handler: PermissionHandler | None = None

    # === Tool Registration ===

    @overload
    def tool(
        self, func: Callable[..., Awaitable[Any]]
    ) -> Callable[..., Awaitable[Any]]: ...

    @overload
    def tool(
        self,
        *,
        name: str | None = None,
        description: str | None = None,
        schema: dict[str, Any] | None = None,
    ) -> Callable[[Callable[..., Awaitable[Any]]], Callable[..., Awaitable[Any]]]: ...

    def tool(
        self,
        func: Callable[..., Awaitable[Any]] | None = None,
        *,
        name: str | None = None,
        description: str | None = None,
        schema: dict[str, Any] | None = None,
    ) -> (
        Callable[..., Awaitable[Any]]
        | Callable[[Callable[..., Awaitable[Any]]], Callable[..., Awaitable[Any]]]
    ):
        """Decorator to register a tool.

        Can be used with or without arguments:

            @agent.tool
            async def my_tool(x: int) -> str:
                '''Tool description.'''
                return str(x)

            @agent.tool(name="custom_name", description="Custom description")
            async def another_tool(x: int) -> str:
                return str(x)

        Args:
            func: Function to register (when used without parentheses).
            name: Custom tool name (defaults to function name).
            description: Custom description (defaults to docstring).
            schema: Custom JSON schema (defaults to inferred from signature).

        Returns:
            The original function (for chaining decorators).
        """

        def decorator(
            fn: Callable[..., Awaitable[Any]],
        ) -> Callable[..., Awaitable[Any]]:
            self._tool_registry.register(
                fn, name=name, description=description, schema=schema
            )
            return fn

        if func is not None:
            # Used as @agent.tool without parentheses
            return decorator(func)
        # Used as @agent.tool(...) with arguments
        return decorator

    # === Hook Registration ===

    def before_tool(
        self, *tool_names: str
    ) -> Callable[[PreToolCallback], PreToolCallback]:
        """Decorator for PreToolUse hooks.

        Example:
            @agent.before_tool("Bash")
            async def check_bash(tool_name: str, tool_input: dict):
                if "rm -rf" in tool_input.get("command", ""):
                    raise PermissionDenied("Dangerous command")

        Args:
            tool_names: Tool names to match (e.g., "Bash", "Write").
                       Multiple names create a pattern like "Bash|Write".

        Returns:
            Decorator function.
        """

        def decorator(fn: PreToolCallback) -> PreToolCallback:
            matcher = "|".join(tool_names) if tool_names else None
            self._hook_registry.add_pre_tool_use(matcher, fn)
            return fn

        return decorator

    def after_tool(
        self, *tool_names: str
    ) -> Callable[[PostToolCallback], PostToolCallback]:
        """Decorator for PostToolUse hooks.

        Example:
            @agent.after_tool("*")  # Match all tools
            async def log_tool(tool_name: str, tool_input: dict, tool_output):
                print(f"Tool {tool_name} executed")

        Args:
            tool_names: Tool names to match. Use "*" to match all tools.

        Returns:
            Decorator function.
        """

        def decorator(fn: PostToolCallback) -> PostToolCallback:
            # Handle "*" as match-all
            if tool_names and "*" in tool_names:
                matcher = None
            else:
                matcher = "|".join(tool_names) if tool_names else None
            self._hook_registry.add_post_tool_use(matcher, fn)
            return fn

        return decorator

    def on_prompt(self, fn: PromptCallback) -> PromptCallback:
        """Decorator for UserPromptSubmit hooks.

        Example:
            @agent.on_prompt
            async def inject_context(prompt: str) -> str | None:
                return f"Current time: {datetime.now()}"

        Args:
            fn: Callback function that receives the prompt and returns
                additional context to inject (or None).

        Returns:
            The original function.
        """
        self._hook_registry.add_user_prompt_submit(fn)
        return fn

    def permission_handler(self, fn: PermissionHandler) -> PermissionHandler:
        """Decorator to set custom permission handler.

        Example:
            @agent.permission_handler
            async def check_permission(tool_name: str, tool_input: dict) -> bool | str:
                if tool_name == "Write" and "/etc/" in tool_input.get("file_path", ""):
                    return "Cannot write to system directories"
                return True

        Args:
            fn: Callback that returns True to allow, False to deny,
                or a string with denial reason.

        Returns:
            The original function.
        """
        self._permission_handler = fn
        return fn

    # === Configuration Building ===

    def _build_options(self) -> ClaudeAgentOptions:
        """Build ClaudeAgentOptions from Agent configuration.

        Returns:
            Configured ClaudeAgentOptions instance.
        """
        # Import here to avoid circular import
        from .. import create_sdk_mcp_server

        # Create SDK MCP server for custom tools
        mcp_servers: dict[str, Any] = {}
        sdk_tools = self._tool_registry.build_sdk_tools()
        if sdk_tools:
            server = create_sdk_mcp_server(name=self.name, tools=sdk_tools)
            mcp_servers[self.name] = server

        # Build allowed_tools list (built-in + custom tools)
        all_allowed = list(self.allowed_tools)
        for tool_name in self._tool_registry.tool_names:
            all_allowed.append(f"mcp__{self.name}__{tool_name}")

        # Build hooks configuration
        hooks: dict[HookEvent, list[HookMatcher]] | None = (
            self._hook_registry.build_hooks()
        )

        # Build can_use_tool callback
        can_use_tool = None
        if self._permission_handler or self.auto_approve:
            can_use_tool = self._build_permission_callback()

        return ClaudeAgentOptions(
            system_prompt=self.system_prompt,
            model=self.model,
            allowed_tools=all_allowed,
            permission_mode=self.permission_mode,  # type: ignore[arg-type]
            max_turns=self.max_turns,
            max_budget_usd=self.max_budget_usd,
            cwd=self.cwd,
            mcp_servers=mcp_servers,
            hooks=hooks,
            can_use_tool=can_use_tool,
        )

    def _build_permission_callback(
        self,
    ) -> Callable[
        [str, dict[str, Any], ToolPermissionContext], Awaitable[PermissionResult]
    ]:
        """Build can_use_tool callback from auto_approve and permission_handler.

        Returns:
            Permission callback function.
        """

        async def callback(
            tool_name: str,
            tool_input: dict[str, Any],
            context: ToolPermissionContext,
        ) -> PermissionResult:
            # Check auto-approve list first
            if tool_name in self.auto_approve:
                return PermissionResultAllow()

            # Check custom permission handler
            if self._permission_handler:
                result = await self._permission_handler(tool_name, tool_input)
                if result is True:
                    return PermissionResultAllow()
                elif result is False:
                    return PermissionResultDeny(message="Permission denied")
                elif isinstance(result, str):
                    return PermissionResultDeny(message=result)

            # Default: allow
            return PermissionResultAllow()

        return callback

    # === Execution Methods ===

    async def run(self, prompt: str) -> AgentResult:
        """Run a single query and return the result.

        Args:
            prompt: User prompt to send.

        Returns:
            AgentResult with text response, cost, and tool calls.

        Example:
            result = await agent.run("What is 2 + 2?")
            print(result.text)
            print(f"Cost: ${result.cost:.4f}")
        """
        # Import here to avoid circular import
        from ..query import query

        options = self._build_options()
        messages: list[Message] = []

        async for message in query(prompt=prompt, options=options):
            messages.append(message)

        return AgentResult.from_messages(messages)

    async def stream(self, prompt: str) -> AsyncIterator[StreamMessage]:
        """Stream responses from a query.

        Args:
            prompt: User prompt to send.

        Yields:
            StreamMessage objects for each message received.

        Example:
            async for msg in agent.stream("Explain Python"):
                if msg.is_text:
                    print(msg.text, end="")
        """
        # Import here to avoid circular import
        from ..query import query

        options = self._build_options()

        async for message in query(prompt=prompt, options=options):
            yield StreamMessage.from_message(message)

    def session(self) -> AgentSession:
        """Create an interactive session for multi-turn conversations.

        Returns:
            AgentSession context manager.

        Example:
            async with agent.session() as session:
                response = await session.chat("Hello")
                response = await session.chat("Follow up question")
        """
        return AgentSession(self)
