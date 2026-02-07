"""Basic example demonstrating the Agent abstraction layer.

This example shows how to:
1. Create an Agent with custom tools
2. Use hooks for tool interception
3. Run single queries and interactive sessions
"""

import asyncio

from claude_agent_sdk import Agent, PermissionDenied


async def main() -> None:
    # Create an agent with basic configuration
    agent = Agent(
        name="calculator",
        system_prompt="You are a calculator assistant. Use the provided tools for calculations.",
        allowed_tools=["Read"],  # Allow some built-in tools
        auto_approve=["Read"],  # Auto-approve Read tool
    )

    # Define tools using the @agent.tool decorator
    # Schema is automatically inferred from function signature
    @agent.tool
    async def add(a: float, b: float) -> str:
        """Add two numbers together.

        Args:
            a: First number
            b: Second number
        """
        return f"{a} + {b} = {a + b}"

    @agent.tool
    async def multiply(a: float, b: float) -> str:
        """Multiply two numbers.

        Args:
            a: First number
            b: Second number
        """
        return f"{a} × {b} = {a * b}"

    @agent.tool
    async def divide(a: float, b: float) -> str:
        """Divide one number by another.

        Args:
            a: Dividend
            b: Divisor
        """
        if b == 0:
            return "Error: Division by zero"
        return f"{a} ÷ {b} = {a / b}"

    # Add a hook to intercept tool usage
    @agent.before_tool("Bash")
    async def block_dangerous_commands(
        tool_name: str, tool_input: dict
    ) -> dict | None:
        """Block dangerous bash commands."""
        command = tool_input.get("command", "")
        dangerous_patterns = ["rm -rf", "sudo", "> /dev/"]
        for pattern in dangerous_patterns:
            if pattern in command:
                raise PermissionDenied(f"Blocked dangerous pattern: {pattern}")
        return None  # Allow execution

    # Add a hook to log all tool usage
    @agent.after_tool("*")
    async def log_tool_usage(tool_name: str, tool_input: dict, tool_output: str) -> None:
        """Log tool usage for debugging."""
        print(f"[LOG] Tool '{tool_name}' called with input: {tool_input}")

    # Example 1: Single query
    print("=" * 50)
    print("Example 1: Single Query")
    print("=" * 50)

    result = await agent.run("Calculate (15 + 27) * 3")
    print(f"Response: {result.text}")
    print(f"Cost: ${result.cost:.6f}" if result.cost else "Cost: N/A")
    print(f"Tool calls: {len(result.tool_calls)}")
    for call in result.tool_calls:
        print(f"  - {call['name']}: {call['input']}")

    # Example 2: Streaming
    print("\n" + "=" * 50)
    print("Example 2: Streaming")
    print("=" * 50)

    print("Response: ", end="")
    async for msg in agent.stream("What is 100 divided by 4?"):
        if msg.is_text and msg.text:
            print(msg.text, end="", flush=True)
    print()

    # Example 3: Interactive session
    print("\n" + "=" * 50)
    print("Example 3: Interactive Session")
    print("=" * 50)

    async with agent.session() as session:
        # First message
        response = await session.chat("Remember: my favorite number is 42")
        print(f"Response 1: {response.text[:100]}...")

        # Follow-up (context is preserved)
        response = await session.chat("What is my favorite number multiplied by 2?")
        print(f"Response 2: {response.text[:100]}...")


if __name__ == "__main__":
    asyncio.run(main())
