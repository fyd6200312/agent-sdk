"""Hook registry for simplified hook management."""

from collections.abc import Awaitable, Callable
from typing import Any, cast

from ..types import (
    HookCallback,
    HookContext,
    HookEvent,
    HookInput,
    HookJSONOutput,
    HookMatcher,
)
from .exceptions import PermissionDenied

# Simplified callback types
PreToolCallback = Callable[[str, dict[str, Any]], Awaitable[dict[str, Any] | None]]
PostToolCallback = Callable[[str, dict[str, Any], Any], Awaitable[None]]
PromptCallback = Callable[[str], Awaitable[str | None]]


class HookRegistry:
    """Registry for simplified hook callbacks.

    Converts user-friendly callback signatures to the full HookCallback format
    expected by the SDK.
    """

    def __init__(self) -> None:
        self._pre_tool_hooks: list[tuple[str | None, PreToolCallback]] = []
        self._post_tool_hooks: list[tuple[str | None, PostToolCallback]] = []
        self._prompt_hooks: list[PromptCallback] = []

    def add_pre_tool_use(self, matcher: str | None, callback: PreToolCallback) -> None:
        """Add a PreToolUse hook.

        Args:
            matcher: Tool name pattern (e.g., "Bash", "Write|Edit", or None for all).
            callback: Async function(tool_name, tool_input) -> dict | None.
                     Return None to allow, dict to modify input, raise PermissionDenied to block.
        """
        self._pre_tool_hooks.append((matcher, callback))

    def add_post_tool_use(
        self, matcher: str | None, callback: PostToolCallback
    ) -> None:
        """Add a PostToolUse hook.

        Args:
            matcher: Tool name pattern (e.g., "Bash", "*" for all, or None).
            callback: Async function(tool_name, tool_input, tool_output) -> None.
        """
        self._post_tool_hooks.append((matcher, callback))

    def add_user_prompt_submit(self, callback: PromptCallback) -> None:
        """Add a UserPromptSubmit hook.

        Args:
            callback: Async function(prompt) -> str | None.
                     Return additional context to inject, or None.
        """
        self._prompt_hooks.append(callback)

    def _wrap_pre_tool_callback(self, callback: PreToolCallback) -> HookCallback:
        """Wrap simplified PreToolUse callback to full HookCallback format."""

        async def wrapped(
            input_data: HookInput, tool_use_id: str | None, context: HookContext
        ) -> HookJSONOutput:
            tool_name = cast(str, input_data.get("tool_name", ""))
            tool_input = cast(dict[str, Any], input_data.get("tool_input", {}))

            try:
                result = await callback(tool_name, tool_input)

                if result is None:
                    # Allow execution
                    return {}
                # Modified input
                return {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "allow",
                        "updatedInput": result,
                    }
                }

            except PermissionDenied as e:
                return {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "deny",
                        "permissionDecisionReason": str(e),
                    }
                }

        return wrapped

    def _wrap_post_tool_callback(self, callback: PostToolCallback) -> HookCallback:
        """Wrap simplified PostToolUse callback to full HookCallback format."""

        async def wrapped(
            input_data: HookInput, tool_use_id: str | None, context: HookContext
        ) -> HookJSONOutput:
            tool_name = cast(str, input_data.get("tool_name", ""))
            tool_input = cast(dict[str, Any], input_data.get("tool_input", {}))
            tool_response = input_data.get("tool_response", "")

            await callback(tool_name, tool_input, tool_response)
            return {}

        return wrapped

    def _wrap_prompt_callback(self, callback: PromptCallback) -> HookCallback:
        """Wrap simplified UserPromptSubmit callback to full HookCallback format."""

        async def wrapped(
            input_data: HookInput, tool_use_id: str | None, context: HookContext
        ) -> HookJSONOutput:
            prompt = cast(str, input_data.get("prompt", ""))

            additional_context = await callback(prompt)

            if additional_context:
                return {
                    "hookSpecificOutput": {
                        "hookEventName": "UserPromptSubmit",
                        "additionalContext": additional_context,
                    }
                }
            return {}

        return wrapped

    def build_hooks(self) -> dict[HookEvent, list[HookMatcher]] | None:
        """Build hooks configuration for ClaudeAgentOptions.

        Returns:
            Dictionary mapping hook events to HookMatcher lists, or None if no hooks.
        """
        hooks: dict[HookEvent, list[HookMatcher]] = {}

        # Build PreToolUse hooks
        if self._pre_tool_hooks:
            pre_tool_matchers: list[HookMatcher] = []
            for matcher, pre_callback in self._pre_tool_hooks:
                wrapped = self._wrap_pre_tool_callback(pre_callback)
                pre_tool_matchers.append(HookMatcher(matcher=matcher, hooks=[wrapped]))
            hooks["PreToolUse"] = pre_tool_matchers

        # Build PostToolUse hooks
        if self._post_tool_hooks:
            post_tool_matchers: list[HookMatcher] = []
            for matcher, post_callback in self._post_tool_hooks:
                wrapped = self._wrap_post_tool_callback(post_callback)
                # Convert "*" to None for matching all
                actual_matcher = None if matcher == "*" else matcher
                post_tool_matchers.append(
                    HookMatcher(matcher=actual_matcher, hooks=[wrapped])
                )
            hooks["PostToolUse"] = post_tool_matchers

        # Build UserPromptSubmit hooks
        if self._prompt_hooks:
            prompt_matchers: list[HookMatcher] = []
            for prompt_callback in self._prompt_hooks:
                wrapped = self._wrap_prompt_callback(prompt_callback)
                prompt_matchers.append(HookMatcher(matcher=None, hooks=[wrapped]))
            hooks["UserPromptSubmit"] = prompt_matchers

        return hooks if hooks else None
