"""LLM abstraction layer.

Provides a clean interface for LLM backends to produce typed node instances.
"""

from __future__ import annotations

import enum
from typing import (
    TYPE_CHECKING,
    Annotated,
    Any,
    Protocol,
    TypeVar,
    get_args,
    get_origin,
    get_type_hints,
    runtime_checkable,
)

from anthropic import transform_schema
from pydantic import BaseModel, create_model
from pydantic_ai import Agent

from bae.resolver import classify_fields

if TYPE_CHECKING:
    from bae.node import Node

T = TypeVar("T", bound="Node")


# ── Fill helpers ─────────────────────────────────────────────────────────


def _get_base_type(hint: Any) -> Any:
    """Extract base type from Annotated wrapper."""
    if get_origin(hint) is Annotated:
        return get_args(hint)[0]
    return hint


def _build_plain_model(target_cls: type) -> type[BaseModel]:
    """Create a dynamic Pydantic model with only plain fields from target.

    Used to constrain LLM output to only the fields it should generate
    (not dep/recall fields). Works for both JSON schema generation and
    pydantic-ai output_type.
    """
    fields = classify_fields(target_cls)
    hints = get_type_hints(target_cls, include_extras=True)

    # Collect plain fields with their types
    plain_fields: dict[str, Any] = {}
    for name in target_cls.model_fields:
        if fields.get(name, "plain") == "plain":
            base_type = _get_base_type(hints.get(name))
            field_info = target_cls.model_fields[name]
            if field_info.default is not None:
                plain_fields[name] = (base_type, field_info.default)
            else:
                plain_fields[name] = (base_type, ...)

    return create_model(
        f"{target_cls.__name__}Plain",
        **plain_fields,
    )


def validate_plain_fields(
    raw: dict[str, Any],
    target_cls: type,
) -> dict[str, Any]:
    """Validate only LLM-generated plain fields through Pydantic.

    Builds a dynamic model from target_cls's plain fields, validates the raw
    dict through it, and returns the validated+coerced values as a dict.

    This is the LLM validation boundary — dep/recall fields are validated
    separately at resolve time. Errors here are FillError, not DepError.

    Args:
        raw: Dict of raw parsed values for plain fields only.
        target_cls: The target Node class (used to build the plain model).

    Returns:
        Dict of validated, type-coerced plain field values.

    Raises:
        FillError: If any plain field fails Pydantic validation.
    """
    from bae.exceptions import FillError

    PlainModel = _build_plain_model(target_cls)

    try:
        validated = PlainModel.model_validate(raw)
        return validated.model_dump()
    except Exception as e:
        raise FillError(
            f"Plain field validation failed for {target_cls.__name__}",
            node_type=target_cls,
            validation_errors=str(e),
            attempts=0,
            cause=e,
        ) from e


def _build_fill_prompt(
    target: type,
    resolved: dict[str, object],
    instruction: str,
    source: "Node | None" = None,
) -> str:
    """Build the prompt for fill() — shared across backends.

    Prompt structure (all JSON):
    1. Input schema (transform_schema of source class, so LLM understands structure)
    2. Source node data (previous node as JSON)
    3. Resolved dep/recall values (as JSON under "context" key)
    4. Output schema (transform_schema of target's plain model)
    5. Instruction (class name + optional docstring)

    JSON input avoids CLI agent mode (XML triggers it).
    Output constrained by --json-schema via constrained decoding.
    """
    import json

    parts: list[str] = []

    if source is not None:
        source_schema = transform_schema(type(source))
        parts.append(f"Input schema:\n{json.dumps(source_schema, indent=2)}")

        source_data = source.model_dump(mode="json")
        parts.append(f"Input data:\n{json.dumps(source_data, indent=2)}")

    if resolved:
        context: dict[str, object] = {}
        for k, v in resolved.items():
            context[k] = v.model_dump(mode="json") if isinstance(v, BaseModel) else v
        parts.append(f"Context:\n{json.dumps(context, indent=2)}")

    output_schema = transform_schema(_build_plain_model(target))
    parts.append(f"Output schema:\n{json.dumps(output_schema, indent=2)}")

    parts.append(instruction)

    return "\n\n".join(parts)


def _build_choice_schema(type_names: list[str]) -> dict:
    """Build a JSON schema for picking one of N type names.

    Uses a dynamic Pydantic model + transform_schema for constrained decoding.
    """
    ChoiceEnum = enum.Enum("ChoiceEnum", {n: n for n in type_names})
    ChoiceModel = create_model("Choice", choice=(ChoiceEnum, ...))
    return transform_schema(ChoiceModel)


@runtime_checkable
class LM(Protocol):
    """Protocol for language model backends.

    The LM produces typed node instances based on:
    - Current node state (fields)
    - Target type(s) to produce

    v1 methods (make/decide): node-centric, kept for custom __call__ escape-hatch nodes.
    v2 methods (choose_type/fill): context-dict-centric, used by the graph runtime.
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
        resolved: dict[str, object],
        instruction: str,
        source: Node | None = None,
    ) -> T:
        """Populate a node's plain fields given resolved dep/recall values.

        Args:
            target: The Node type to populate.
            resolved: Only the target's resolved dep/recall values.
            instruction: Class name + optional docstring.
            source: The previous node (context frame), serialized in prompt.
        """
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
        """Convert node state to JSON prompt string."""
        import json

        data = {node.__class__.__name__: node.model_dump(mode="json")}
        prompt = json.dumps(data, indent=2)

        if node.__class__.__doc__:
            return f"{prompt}\n\nContext: {node.__class__.__doc__}"

        return prompt

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

        import json

        context_json = json.dumps({"context": {
            k: v.model_dump(mode="json") if isinstance(v, BaseModel) else v
            for k, v in context.items()
        }}, indent=2)
        prompt = f"{context_json}\n\nPick one type: {', '.join(type_names)}"

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
        resolved: dict[str, object],
        instruction: str,
        source: Node | None = None,
    ) -> T:
        """Populate target node fields using pydantic-ai with JSON output."""
        plain_model = _build_plain_model(target)
        agent = self._get_agent((plain_model,), allow_none=False)

        prompt = _build_fill_prompt(target, resolved, instruction, source)

        result = agent.run_sync(prompt)
        # Merge LLM output with resolved deps
        all_fields = dict(resolved)
        plain_output = result.output
        if isinstance(plain_output, BaseModel):
            all_fields.update(plain_output.model_dump())
        return target.model_construct(**all_fields)


class ClaudeCLIBackend:
    """LLM backend using Claude CLI subprocess."""

    def __init__(self, model: str = "claude-sonnet-4-20250514", timeout: int = 20):
        self.model = model
        self.timeout = timeout

    def _node_to_prompt(self, node: Node) -> str:
        """Convert node state to JSON prompt string."""
        import json

        data = {node.__class__.__name__: node.model_dump(mode="json")}
        prompt = json.dumps(data, indent=2)

        if node.__class__.__doc__:
            return f"{prompt}\n\nContext: {node.__class__.__doc__}"

        return prompt

    def make(self, node: Node, target: type[T]) -> T:
        """Produce an instance of target type using Claude CLI."""
        prompt = self._node_to_prompt(node)
        full_prompt = f"{prompt}\n\nProduce a {target.__name__}."
        if target.__doc__:
            full_prompt += f"\n{target.__name__}: {target.__doc__}"

        schema = transform_schema(target)
        data = self._run_cli_json(full_prompt, schema)
        return target.model_validate(data)

    def _run_cli_json(self, prompt: str, schema: dict) -> dict | None:
        """Run Claude CLI with JSON schema and extract structured output."""
        import json
        import subprocess

        cmd = [
            "claude",
            "-p", prompt,
            "--model", self.model,
            "--output-format", "json",
            "--json-schema", json.dumps(schema),
            "--no-session-persistence",
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
            raise RuntimeError(
                f"No structured_output in Claude CLI response: {json.dumps(data, indent=2)[:2000]}"
            )

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

        choice_schema = _build_choice_schema(type_names)

        choice_data = self._run_cli_json(choice_prompt, choice_schema)
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

        import json

        context_json = json.dumps({"context": {
            k: v.model_dump(mode="json") if isinstance(v, BaseModel) else v
            for k, v in context.items()
        }}, indent=2)
        prompt = f"{context_json}\n\nPick one type: {', '.join(type_names)}"

        for t in types:
            if t.__doc__:
                prompt += f"\n- {t.__name__}: {t.__doc__}"

        choice_schema = _build_choice_schema(type_names)

        choice_data = self._run_cli_json(prompt, choice_schema)
        chosen = choice_data["choice"]

        # Map name back to type
        for t in types:
            if t.__name__ == chosen:
                return t

        return types[0]

    def fill(
        self,
        target: type[T],
        resolved: dict[str, object],
        instruction: str,
        source: Node | None = None,
    ) -> T:
        """Populate target node fields via JSON structured output.

        Builds prompt with source context + resolved deps + instruction.
        Output constrained by JSON schema from plain fields model.
        """
        plain_model = _build_plain_model(target)
        plain_fields = list(plain_model.model_fields.keys())

        if not plain_fields:
            # No plain fields — nothing to fill, construct from resolved
            return target.model_construct(**resolved)

        prompt = _build_fill_prompt(target, resolved, instruction, source)

        # Call CLI with JSON schema constraining output to plain fields only
        schema = transform_schema(plain_model)
        data = self._run_cli_json(prompt, schema)

        # Validate plain fields (LLM boundary — FillError on failure)
        validated = validate_plain_fields(data, target)

        # Merge independently-validated halves via model_construct
        all_fields = dict(resolved)
        all_fields.update(validated)
        return target.model_construct(**all_fields)
