"""Tool registry with automatic schema inference."""

import inspect
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, get_type_hints

if TYPE_CHECKING:
    from .. import SdkMcpTool


@dataclass
class ToolDefinition:
    """Internal tool definition."""

    name: str
    description: str
    schema: dict[str, Any]
    handler: Callable[..., Awaitable[Any]]


class ToolRegistry:
    """Registry for agent tools with automatic schema inference.

    This class manages tool registration and converts Python functions
    into SDK MCP tools with automatically inferred JSON schemas.
    """

    # Mapping from Python types to JSON Schema types
    _type_map: dict[type, str] = {
        str: "string",
        int: "integer",
        float: "number",
        bool: "boolean",
        list: "array",
        dict: "object",
    }

    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    @property
    def tool_names(self) -> list[str]:
        """Get list of registered tool names."""
        return list(self._tools.keys())

    def register(
        self,
        func: Callable[..., Awaitable[Any]],
        *,
        name: str | None = None,
        description: str | None = None,
        schema: dict[str, Any] | None = None,
    ) -> None:
        """Register a tool function.

        Args:
            func: Async function to register as a tool.
            name: Tool name (defaults to function name).
            description: Tool description (defaults to first line of docstring).
            schema: JSON Schema for input (defaults to inferred from signature).
        """
        tool_name = name or func.__name__
        tool_desc = description or self._extract_description(func)
        tool_schema = schema or self._infer_schema(func)

        # Wrap handler to adapt to SDK MCP format
        original_func = func

        async def handler(args: dict[str, Any]) -> dict[str, Any]:
            result = await original_func(**args)
            # If already in MCP format, return as-is
            if isinstance(result, dict) and "content" in result:
                return result
            # Otherwise wrap in MCP format
            return {"content": [{"type": "text", "text": str(result)}]}

        self._tools[tool_name] = ToolDefinition(
            name=tool_name,
            description=tool_desc,
            schema=tool_schema,
            handler=handler,
        )

    def _extract_description(self, func: Callable[..., Any]) -> str:
        """Extract description from function docstring."""
        doc = func.__doc__ or ""
        # Get first non-empty line
        for line in doc.split("\n"):
            line = line.strip()
            if line:
                return line
        return f"Tool: {func.__name__}"

    def _infer_schema(self, func: Callable[..., Any]) -> dict[str, Any]:
        """Infer JSON schema from function signature.

        Args:
            func: Function to analyze.

        Returns:
            JSON Schema dictionary.
        """
        try:
            hints = get_type_hints(func)
        except Exception:
            hints = {}

        sig = inspect.signature(func)

        properties: dict[str, Any] = {}
        required: list[str] = []

        for param_name, param in sig.parameters.items():
            if param_name in ("self", "cls"):
                continue

            # Get type from hints or default to string
            py_type = hints.get(param_name, str)
            json_type = self._python_type_to_json(py_type)

            prop: dict[str, Any] = {"type": json_type}

            # Extract parameter description from docstring
            if func.__doc__:
                param_desc = self._extract_param_description(func.__doc__, param_name)
                if param_desc:
                    prop["description"] = param_desc

            properties[param_name] = prop

            # Check if parameter is required (no default value)
            if param.default is inspect.Parameter.empty:
                required.append(param_name)

        return {
            "type": "object",
            "properties": properties,
            "required": required,
        }

    def _python_type_to_json(self, py_type: type) -> str:
        """Convert Python type to JSON schema type.

        Args:
            py_type: Python type to convert.

        Returns:
            JSON Schema type string.
        """
        # Handle Optional types
        origin = getattr(py_type, "__origin__", None)
        if origin is not None:
            # For Union types (including Optional), use the first non-None type
            args = getattr(py_type, "__args__", ())
            for arg in args:
                if arg is not type(None):
                    return self._python_type_to_json(arg)

        return self._type_map.get(py_type, "string")

    def _extract_param_description(self, docstring: str, param_name: str) -> str | None:
        """Extract parameter description from docstring.

        Supports Google-style and Sphinx-style docstrings.

        Args:
            docstring: Function docstring.
            param_name: Parameter name to find.

        Returns:
            Parameter description or None.
        """
        # Google style: "param_name: description"
        pattern = rf"(?:^|\n)\s*{re.escape(param_name)}:\s*(.+?)(?:\n|$)"
        match = re.search(pattern, docstring)
        if match:
            return match.group(1).strip()

        # Sphinx style: ":param param_name: description"
        pattern = rf":param\s+{re.escape(param_name)}:\s*(.+?)(?:\n|$)"
        match = re.search(pattern, docstring)
        if match:
            return match.group(1).strip()

        return None

    def build_sdk_tools(self) -> list["SdkMcpTool[Any]"]:
        """Build SDK MCP tools from registered tools.

        Returns:
            List of SdkMcpTool instances ready for create_sdk_mcp_server.
        """
        # Import here to avoid circular import
        from .. import SdkMcpTool

        sdk_tools: list[SdkMcpTool[Any]] = []

        for tool_def in self._tools.values():
            sdk_tool = SdkMcpTool(
                name=tool_def.name,
                description=tool_def.description,
                input_schema=tool_def.schema,
                handler=tool_def.handler,
            )
            sdk_tools.append(sdk_tool)

        return sdk_tools
