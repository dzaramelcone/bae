"""LLM abstraction layer.

Provides a clean interface for LLM backends to produce typed node instances.
"""

from __future__ import annotations

import types
from typing import TYPE_CHECKING, Protocol, TypeVar, get_args, runtime_checkable

from pydantic_ai import Agent, format_as_xml

if TYPE_CHECKING:
    from bae.node import Node

T = TypeVar("T", bound="Node")


@runtime_checkable
class LM(Protocol):
    """Protocol for language model backends.

    The LM produces typed node instances based on:
    - Current node state (fields)
    - Target type(s) to produce

    v1 methods (make/decide): node-centric, will be removed in Phase 8.
    v2 methods (choose_type/fill): context-dict-centric, used by v2 runtime.
    """

    def make(self, node: Node, target: type[T]) -> T:
        """Produce an instance of a specific node type."""
        ...

    def decide(self, node: Node) -> Node | None:
        """Let LLM decide which successor to produce based on return type hint."""
        ...

    def choose_type(
        self,
        types: list[type[Node]],
        context: dict[str, object],
    ) -> type[Node]:
        """Pick successor type from candidates, given resolved context fields."""
        ...

    def fill(
        self,
        target: type[T],
        context: dict[str, object],
        instruction: str,
    ) -> T:
        """Populate a node's plain fields given resolved context."""
        ...


class PydanticAIBackend:
    """LLM backend using pydantic-ai."""

    def __init__(self, model: str = "anthropic:claude-sonnet-4-20250514"):
        self.model = model
        self._agents: dict[tuple, Agent] = {}

    def _get_agent(self, output_types: tuple[type, ...], allow_none: bool) -> Agent:
        """Get or create an agent for the given output types."""
        cache_key = (output_types, allow_none)
        if cache_key not in self._agents:
            # Build output type list
            type_list = list(output_types)
            if allow_none:
                type_list.append(type(None))

            self._agents[cache_key] = Agent(
                self.model,
                output_type=type_list,  # type: ignore
            )
        return self._agents[cache_key]

    def _node_to_prompt(self, node: Node) -> str:
        """Convert node state to XML prompt string."""
        xml = format_as_xml(node.model_dump(), root_tag=node.__class__.__name__)

        # Add docstring as context
        if node.__class__.__doc__:
            return f"{xml}\n\nContext: {node.__class__.__doc__}"

        return xml

    def make(self, node: Node, target: type[T]) -> T:
        """Produce an instance of target type using pydantic-ai."""
        agent = self._get_agent((target,), allow_none=False)
        prompt = self._node_to_prompt(node)

        # Add instruction about what to produce
        full_prompt = f"{prompt}\n\nProduce a {target.__name__}."
        if target.__doc__:
            full_prompt += f"\n{target.__name__}: {target.__doc__}"

        result = agent.run_sync(full_prompt)
        return result.output

    def decide(self, node: Node) -> Node | None:
        """Let LLM pick successor type and produce it."""
        successors = tuple(node.successors())
        is_terminal = node.is_terminal()

        if not successors and is_terminal:
            return None

        if not successors:
            raise ValueError(f"{node.__class__.__name__} has no successors and is not terminal")

        agent = self._get_agent(successors, allow_none=is_terminal)
        prompt = self._node_to_prompt(node)

        # Add instruction about choices
        type_names = [t.__name__ for t in successors]
        if is_terminal:
            type_names.append("None (terminate)")

        full_prompt = f"{prompt}\n\nDecide the next step. Options: {', '.join(type_names)}"

        # Add docstrings for each option
        for t in successors:
            if t.__doc__:
                full_prompt += f"\n- {t.__name__}: {t.__doc__}"

        result = agent.run_sync(full_prompt)
        return result.output

    def choose_type(
        self,
        types: list[type[Node]],
        context: dict[str, object],
    ) -> type[Node]:
        """Pick successor type from candidates using pydantic-ai."""
        if len(types) == 1:
            return types[0]

        # Ask agent to pick a type name
        agent = self._get_agent((str,), allow_none=False)
        type_names = [t.__name__ for t in types]

        context_xml = format_as_xml(context, root_tag="context")
        prompt = f"{context_xml}\n\nPick one type: {', '.join(type_names)}"

        for t in types:
            if t.__doc__:
                prompt += f"\n- {t.__name__}: {t.__doc__}"

        result = agent.run_sync(prompt)
        chosen = result.output.strip()

        # Map name back to type
        for t in types:
            if t.__name__ == chosen:
                return t

        # Fallback: partial match
        for t in types:
            if t.__name__.lower() in chosen.lower():
                return t

        return types[0]

    def fill(
        self,
        target: type[T],
        context: dict[str, object],
        instruction: str,
    ) -> T:
        """Populate target node fields using pydantic-ai."""
        agent = self._get_agent((target,), allow_none=False)

        context_xml = format_as_xml(context, root_tag="context")
        prompt = f"{context_xml}\n\n{instruction}"

        result = agent.run_sync(prompt)
        return result.output


class ClaudeCLIBackend:
    """LLM backend using Claude CLI subprocess."""

    def __init__(self, model: str = "claude-sonnet-4-20250514", timeout: int = 20):
        self.model = model
        self.timeout = timeout

    def _node_to_prompt(self, node: Node) -> str:
        """Convert node state to XML prompt string."""
        xml = format_as_xml(node.model_dump(), root_tag=node.__class__.__name__)

        if node.__class__.__doc__:
            return f"{xml}\n\nContext: {node.__class__.__doc__}"

        return xml

    def _build_schema(self, types: tuple[type, ...], allow_none: bool) -> dict:
        """Build JSON schema for union of types."""
        schemas = []
        for t in types:
            schema = t.model_json_schema()
            schema["title"] = t.__name__
            schemas.append(schema)

        if allow_none:
            schemas.append({"type": "null", "title": "None"})

        if len(schemas) == 1:
            return schemas[0]
        return {"oneOf": schemas}

    def make(self, node: Node, target: type[T]) -> T:
        """Produce an instance of target type using Claude CLI."""
        prompt = self._node_to_prompt(node)
        full_prompt = f"{prompt}\n\nProduce a {target.__name__}."
        if target.__doc__:
            full_prompt += f"\n{target.__name__}: {target.__doc__}"

        schema = target.model_json_schema()
        data = self._run_cli(full_prompt, schema)
        return target.model_validate(data)

    def _run_cli(self, prompt: str, schema: dict) -> dict | None:
        """Run Claude CLI and extract structured output."""
        import json
        import subprocess

        cmd = [
            "claude",
            "-p", prompt,
            "--model", self.model,
            "--output-format", "json",
            "--json-schema", json.dumps(schema),
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=self.timeout)
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"Claude CLI timed out after {self.timeout}s")

        if result.returncode != 0:
            raise RuntimeError(f"Claude CLI failed: {result.stderr}")

        data = json.loads(result.stdout)

        # Claude CLI returns conversation stream - extract structured_output from result
        if isinstance(data, list):
            for item in reversed(data):
                if item.get("type") == "result" and "structured_output" in item:
                    return item["structured_output"]
            raise RuntimeError("No structured_output in Claude CLI response")

        return data

    def decide(self, node: Node) -> Node | None:
        """Let LLM pick successor type and produce it using Claude CLI.

        Uses two-step approach: first pick type, then fill it.
        This avoids slow oneOf schemas.
        """
        successors = tuple(node.successors())
        is_terminal = node.is_terminal()

        if not successors and is_terminal:
            return None

        if not successors:
            raise ValueError(f"{node.__class__.__name__} has no successors and is not terminal")

        prompt = self._node_to_prompt(node)
        type_names = [t.__name__ for t in successors]
        if is_terminal:
            type_names.append("None")

        # Step 1: Pick the type
        choice_prompt = f"{prompt}\n\nDecide the next step. Pick one: {', '.join(type_names)}"
        for t in successors:
            if t.__doc__:
                choice_prompt += f"\n- {t.__name__}: {t.__doc__}"
        if is_terminal:
            choice_prompt += "\n- None: Terminate processing"

        choice_schema = {
            "type": "object",
            "properties": {"choice": {"type": "string", "enum": type_names}},
            "required": ["choice"],
        }

        choice_data = self._run_cli(choice_prompt, choice_schema)
        chosen = choice_data["choice"]

        if chosen == "None":
            return None

        # Step 2: Fill the chosen type
        target = next(t for t in successors if t.__name__ == chosen)
        return self.make(node, target)

    def choose_type(
        self,
        types: list[type[Node]],
        context: dict[str, object],
    ) -> type[Node]:
        """Pick successor type from candidates using Claude CLI."""
        if len(types) == 1:
            return types[0]

        type_names = [t.__name__ for t in types]

        context_xml = format_as_xml(context, root_tag="context")
        prompt = f"{context_xml}\n\nPick one type: {', '.join(type_names)}"

        for t in types:
            if t.__doc__:
                prompt += f"\n- {t.__name__}: {t.__doc__}"

        choice_schema = {
            "type": "object",
            "properties": {"choice": {"type": "string", "enum": type_names}},
            "required": ["choice"],
        }

        choice_data = self._run_cli(prompt, choice_schema)
        chosen = choice_data["choice"]

        # Map name back to type
        for t in types:
            if t.__name__ == chosen:
                return t

        return types[0]

    def fill(
        self,
        target: type[T],
        context: dict[str, object],
        instruction: str,
    ) -> T:
        """Populate target node fields using Claude CLI."""
        context_xml = format_as_xml(context, root_tag="context")
        prompt = f"{context_xml}\n\n{instruction}"

        schema = target.model_json_schema()
        data = self._run_cli(prompt, schema)
        return target.model_validate(data)
