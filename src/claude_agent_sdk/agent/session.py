"""Session management for interactive agent conversations."""

from typing import TYPE_CHECKING, Any

from ..client import ClaudeSDKClient
from ..types import Message
from .exceptions import SessionError
from .result import AgentResult

if TYPE_CHECKING:
    from .agent import Agent


class AgentSession:
    """Interactive session for multi-turn conversations.

    Use with async context manager:

        async with agent.session() as session:
            response = await session.chat("Hello")
            response = await session.chat("Follow up")

    Attributes:
        agent: The parent Agent instance.
    """

    def __init__(self, agent: "Agent") -> None:
        """Initialize session.

        Args:
            agent: Parent Agent instance.
        """
        self._agent = agent
        self._client: ClaudeSDKClient | None = None
        self._options = agent._build_options()

    async def __aenter__(self) -> "AgentSession":
        """Enter async context and connect to Claude."""
        self._client = ClaudeSDKClient(options=self._options)
        await self._client.connect()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> bool:
        """Exit async context and disconnect."""
        if self._client:
            await self._client.disconnect()
        return False

    def _ensure_connected(self) -> ClaudeSDKClient:
        """Ensure client is connected.

        Returns:
            Connected ClaudeSDKClient.

        Raises:
            SessionError: If session is not started.
        """
        if not self._client:
            raise SessionError(
                "Session not started. Use 'async with agent.session() as session:'"
            )
        return self._client

    async def chat(self, message: str) -> AgentResult:
        """Send a message and get response.

        Args:
            message: User message to send.

        Returns:
            AgentResult with the response.

        Raises:
            SessionError: If session is not started.
        """
        client = self._ensure_connected()

        await client.query(message)

        messages: list[Message] = []
        async for msg in client.receive_response():
            messages.append(msg)

        return AgentResult.from_messages(messages)

    async def set_permission_mode(self, mode: str) -> None:
        """Change permission mode during session.

        Args:
            mode: Permission mode ("default", "acceptEdits", "plan", "bypassPermissions").

        Raises:
            SessionError: If session is not started.
        """
        client = self._ensure_connected()
        await client.set_permission_mode(mode)

    async def set_model(self, model: str) -> None:
        """Change model during session.

        Args:
            model: Model identifier.

        Raises:
            SessionError: If session is not started.
        """
        client = self._ensure_connected()
        await client.set_model(model)

    async def interrupt(self) -> None:
        """Interrupt current operation.

        Raises:
            SessionError: If session is not started.
        """
        client = self._ensure_connected()
        await client.interrupt()
