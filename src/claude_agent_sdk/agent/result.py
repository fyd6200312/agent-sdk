"""Result types for Agent abstraction layer."""

from dataclasses import dataclass, field
from typing import Any

from ..types import (
    AssistantMessage,
    Message,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
)


@dataclass
class AgentResult:
    """Result from an agent query.

    Attributes:
        text: The final text response from the agent.
        messages: All messages exchanged during the query.
        cost: Total cost in USD (if available).
        duration_ms: Total duration in milliseconds.
        tool_calls: List of tool calls made during the query.
    """

    text: str
    messages: list[Message] = field(default_factory=list)
    cost: float | None = None
    duration_ms: int = 0
    tool_calls: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_messages(cls, messages: list[Message]) -> "AgentResult":
        """Create AgentResult from a list of messages.

        Args:
            messages: List of Message objects from the SDK.

        Returns:
            AgentResult with extracted text, cost, and tool calls.
        """
        text_parts: list[str] = []
        tool_calls: list[dict[str, Any]] = []
        cost: float | None = None
        duration_ms: int = 0

        for msg in messages:
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, TextBlock):
                        text_parts.append(block.text)
                    elif isinstance(block, ToolUseBlock):
                        tool_calls.append(
                            {"name": block.name, "input": block.input, "id": block.id}
                        )
            elif isinstance(msg, ResultMessage):
                cost = msg.total_cost_usd
                duration_ms = msg.duration_ms

        return cls(
            text="\n".join(text_parts),
            messages=messages,
            cost=cost,
            duration_ms=duration_ms,
            tool_calls=tool_calls,
        )


@dataclass
class StreamMessage:
    """Single message in a stream.

    Attributes:
        is_text: Whether this message contains text content.
        text: The text content (if is_text is True).
        is_tool_use: Whether this message is a tool use.
        tool_name: Name of the tool being used (if is_tool_use is True).
        tool_input: Input to the tool (if is_tool_use is True).
        is_result: Whether this is the final result message.
        cost: Cost in USD (if is_result is True).
        raw: The raw Message object from the SDK.
    """

    is_text: bool = False
    text: str | None = None
    is_tool_use: bool = False
    tool_name: str | None = None
    tool_input: dict[str, Any] | None = None
    is_result: bool = False
    cost: float | None = None
    raw: Message | None = None

    @classmethod
    def from_message(cls, msg: Message) -> "StreamMessage":
        """Create StreamMessage from an SDK Message.

        Args:
            msg: Message object from the SDK.

        Returns:
            StreamMessage with extracted information.
        """
        is_text = False
        text = None
        is_tool_use = False
        tool_name = None
        tool_input = None
        is_result = isinstance(msg, ResultMessage)
        cost = msg.total_cost_usd if isinstance(msg, ResultMessage) else None

        if isinstance(msg, AssistantMessage):
            for block in msg.content:
                if isinstance(block, TextBlock):
                    is_text = True
                    text = block.text
                    break
                elif isinstance(block, ToolUseBlock):
                    is_tool_use = True
                    tool_name = block.name
                    tool_input = block.input
                    break

        return cls(
            is_text=is_text,
            text=text,
            is_tool_use=is_tool_use,
            tool_name=tool_name,
            tool_input=tool_input,
            is_result=is_result,
            cost=cost,
            raw=msg,
        )
