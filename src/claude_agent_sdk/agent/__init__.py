"""Agent abstraction layer for Claude Code SDK.

This module provides a high-level Agent class that simplifies:
- Tool definition with automatic schema inference
- Session management for multi-turn conversations
- Hook configuration with decorator syntax
- Permission handling

Example:
    ```python
    from claude_agent_sdk.agent import Agent, PermissionDenied

    agent = Agent(
        name="my-assistant",
        system_prompt="You are a helpful assistant.",
        allowed_tools=["Read", "Grep"],
    )

    @agent.tool
    async def calculate(a: float, b: float) -> str:
        '''Add two numbers.'''
        return f"{a} + {b} = {a + b}"

    @agent.before_tool("Bash")
    async def check_bash(tool_name: str, tool_input: dict):
        if "rm -rf" in tool_input.get("command", ""):
            raise PermissionDenied("Dangerous command")

    # Single query
    result = await agent.run("What is 15 + 27?")
    print(result.text)

    # Interactive session
    async with agent.session() as session:
        response = await session.chat("Hello")
        response = await session.chat("Follow up")
    ```
"""

from .agent import Agent
from .exceptions import (
    AgentError,
    PermissionDenied,
    PermissionDeniedError,
    SessionError,
    ToolError,
)
from .result import AgentResult, StreamMessage
from .session import AgentSession

__all__ = [
    "Agent",
    "AgentResult",
    "StreamMessage",
    "AgentSession",
    "AgentError",
    "PermissionDenied",
    "PermissionDeniedError",
    "SessionError",
    "ToolError",
]
