"""Exceptions for Agent abstraction layer."""


class AgentError(Exception):
    """Base exception for Agent errors."""

    pass


class PermissionDeniedError(AgentError):
    """Raised when a tool permission is denied by a hook."""

    pass


# Alias for convenience
PermissionDenied = PermissionDeniedError


class ToolError(AgentError):
    """Raised when a tool execution fails."""

    pass


class SessionError(AgentError):
    """Raised when there's an error with the agent session."""

    pass
