"""LLM abstraction layer.

Provides a clean interface over different LLM backends.
For now, we lean on pydantic-ai for the heavy lifting.
"""

from typing import Any, Protocol, TypeVar
from pydantic import BaseModel

from bae.node import Node

T = TypeVar("T", bound=Node)


class LM(Protocol):
    """Protocol for language model backends."""

    async def fill_outputs(self, node: T) -> T:
        """Fill output fields of a node using the LLM.

        Args:
            node: Node instance with inputs populated.

        Returns:
            Same node type with outputs filled by LLM.
        """
        ...


class PydanticAIBackend:
    """LLM backend using pydantic-ai.

    Uses pydantic-ai's Agent for structured output generation.
    """

    def __init__(self, model: str = "claude-3-5-sonnet-latest"):
        self.model = model
        self._agents: dict[type[Node], Any] = {}

    def _get_agent(self, node_cls: type[Node]) -> Any:
        """Get or create a pydantic-ai Agent for a node type."""
        if node_cls not in self._agents:
            # Lazy import to avoid circular deps
            from pydantic_ai import Agent

            # Create output model from node's output fields
            output_fields = node_cls.output_fields()

            # Build dynamic output type
            # For now, just use the node class itself as output
            # pydantic-ai will validate the fields

            # Create agent with node's docstring as system prompt
            agent = Agent(
                self.model,
                output_type=node_cls,
                system_prompt=node_cls.__doc__ or f"Fill the outputs for {node_cls.__name__}",
            )
            self._agents[node_cls] = agent

        return self._agents[node_cls]

    async def fill_outputs(self, node: T) -> T:
        """Fill output fields using pydantic-ai."""
        agent = self._get_agent(type(node))

        # Build prompt from input fields
        inputs = {
            name: getattr(node, name)
            for name in node.input_fields()
        }
        prompt = "\n".join(f"{k}: {v}" for k, v in inputs.items())

        # Run agent
        result = await agent.run(prompt)

        return result.output


class ClaudeCLIBackend:
    """LLM backend using Claude CLI subprocess.

    Useful for local development with Claude Code.
    Adapted from ~/lab/rlm/mahtab/llm/claude_cli.py
    """

    def __init__(self, model: str = "claude-sonnet-4-20250514"):
        self.model = model

    async def fill_outputs(self, node: T) -> T:
        """Fill output fields using Claude CLI."""
        import asyncio
        import json

        node_cls = type(node)

        # Build prompt
        inputs = {name: getattr(node, name) for name in node.input_fields()}
        output_schema = {
            name: str(field.annotation)
            for name, field in node.output_fields().items()
        }

        prompt = f"""Given these inputs:
{json.dumps(inputs, indent=2)}

Fill in these output fields:
{json.dumps(output_schema, indent=2)}

{node_cls.__doc__ or ''}

Respond with JSON containing only the output fields."""

        cmd = [
            "claude",
            "-p", prompt,
            "--model", self.model,
            "--output-format", "json",
        ]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            raise RuntimeError(f"Claude CLI failed: {stderr.decode()}")

        # Parse output and update node
        output_data = json.loads(stdout.decode())

        # Create new node with inputs + outputs
        return node_cls(**{**inputs, **output_data})
