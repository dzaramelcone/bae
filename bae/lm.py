"""LLM abstraction layer.

Provides a clean interface for LLM backends to produce typed node instances.
"""

from __future__ import annotations

import asyncio
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

from pydantic import BaseModel, create_model

from bae.resolver import classify_fields

# String formats Claude's structured output API supports natively.
_SUPPORTED_FORMATS = {
    "email", "ipv4", "date", "uuid", "hostname",
    "duration", "date-time", "uri", "ipv6", "time",
}


def transform_schema(
    json_schema: type[BaseModel] | dict[str, Any],
) -> dict[str, Any]:
    """Convert a Pydantic model or JSON Schema dict for Claude structured output.

    Recursively walks the schema, forces additionalProperties: false on objects,
    and moves unsupported constraints into the description field so the model
    still sees them as hints.
    """
    if isinstance(json_schema, type) and issubclass(json_schema, BaseModel):
        json_schema = json_schema.model_json_schema()

    strict: dict[str, Any] = {}
    schema = {**json_schema}

    ref = schema.pop("$ref", None)
    if ref is not None:
        return {"$ref": ref}

    defs = schema.pop("$defs", None)
    if defs is not None:
        strict["$defs"] = {
            name: transform_schema(s) for name, s in defs.items()
        }

    type_ = schema.pop("type", None)
    any_of = schema.pop("anyOf", None)
    one_of = schema.pop("oneOf", None)
    all_of = schema.pop("allOf", None)

    if isinstance(any_of, list):
        strict["anyOf"] = [transform_schema(v) for v in any_of]
    elif isinstance(one_of, list):
        strict["anyOf"] = [transform_schema(v) for v in one_of]
    elif isinstance(all_of, list):
        strict["allOf"] = [transform_schema(v) for v in all_of]
    else:
        if type_ is None:
            raise ValueError("Schema must have 'type', 'anyOf', 'oneOf', or 'allOf'.")
        strict["type"] = type_

    for key in ("description", "title"):
        val = schema.pop(key, None)
        if val is not None:
            strict[key] = val

    if type_ == "object":
        strict["properties"] = {
            k: transform_schema(v) for k, v in schema.pop("properties", {}).items()
        }
        schema.pop("additionalProperties", None)
        strict["additionalProperties"] = False
        required = schema.pop("required", None)
        if required is not None:
            strict["required"] = required
    elif type_ == "string":
        fmt = schema.pop("format", None)
        if fmt and fmt in _SUPPORTED_FORMATS:
            strict["format"] = fmt
        elif fmt:
            schema["format"] = fmt  # unsupported → append to description below
    elif type_ == "array":
        items = schema.pop("items", None)
        if items is not None:
            strict["items"] = transform_schema(items)
        min_items = schema.pop("minItems", None)
        if min_items is not None and min_items in (0, 1):
            strict["minItems"] = min_items
        elif min_items is not None:
            schema["minItems"] = min_items

    # Unsupported leftover fields → fold into description as hints
    if schema:
        desc = strict.get("description", "")
        extra = "{" + ", ".join(f"{k}: {v}" for k, v in schema.items()) + "}"
        strict["description"] = (desc + "\n\n" + extra) if desc else extra

    return strict

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
    (not dep/recall fields). Preserves Field(description=...) metadata
    so descriptions flow into JSON schemas for constrained decoding.
    """
    fields = classify_fields(target_cls)
    hints = get_type_hints(target_cls, include_extras=True)

    # Collect plain fields with their types and original FieldInfo.
    # Passing FieldInfo preserves description, default, default_factory,
    # json_schema_extra, and all other field metadata.
    plain_fields: dict[str, Any] = {}
    for name in target_cls.model_fields:
        if fields.get(name, "plain") == "plain":
            base_type = _get_base_type(hints.get(name))
            field_info = target_cls.model_fields[name]
            plain_fields[name] = (base_type, field_info)

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
        return {name: getattr(validated, name) for name in PlainModel.model_fields}
    except Exception as e:
        raise FillError(
            f"Plain field validation failed for {target_cls.__name__}",
            node_type=target_cls,
            validation_errors=str(e),
            attempts=0,
            cause=e,
        ) from e


def _dump_plain_fields(node: "BaseModel") -> dict:
    """Serialize only plain fields of a node — skip deps and recalls."""
    plain = {k for k, v in classify_fields(type(node)).items() if v == "plain"}
    return {
        k: v
        for k, v in node.model_dump(mode="json", include=plain).items()
    }


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
    4. Instruction (class name)

    Output schema is NOT included in the prompt — it's passed separately via
    --json-schema for constrained decoding (ClaudeCLIBackend) or as output_type
    constrained decoding. Including it would send it twice.
    """
    import json

    parts: list[str] = []

    if source is not None:
        source_data = _dump_plain_fields(source)
        parts.append(f"Input data:\n{json.dumps(source_data, indent=2)}")

    if resolved:
        context: dict[str, object] = {}
        for k, v in resolved.items():
            if isinstance(v, BaseModel):
                context[k] = _dump_plain_fields(v)
            else:
                context[k] = v
        parts.append(f"Context:\n{json.dumps(context, indent=2)}")

    parts.append(instruction)

    return "\n\n".join(parts)


def _strip_format(schema: dict) -> dict:
    """Recursively move 'format' from JSON schema into 'description'.

    Claude CLI silently rejects --json-schema when the schema contains
    'format' constraints (e.g. 'format': 'uri' from HttpUrl). The API
    supports it, but the CLI doesn't create the structured output tool.

    Instead of dropping format entirely, we append it to the description
    so the LLM still knows the semantic type (e.g. "format: uri").
    """
    out: dict = {}
    fmt = schema.get("format")
    for k, v in schema.items():
        if k == "format":
            continue
        if isinstance(v, dict):
            out[k] = _strip_format(v)
        elif isinstance(v, list):
            out[k] = [_strip_format(i) if isinstance(i, dict) else i for i in v]
        else:
            out[k] = v
    if fmt:
        existing = out.get("description", "")
        hint = f"format: {fmt}"
        out["description"] = f"{existing}, {hint}" if existing else hint
    return out


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

    async def make(self, node: Node, target: type[T]) -> T:
        """Produce an instance of a specific node type."""
        ...

    async def decide(self, node: Node) -> Node | None:
        """Let LLM decide which successor to produce based on return type hint."""
        ...

    async def choose_type(
        self,
        types: list[type[Node]],
        context: dict[str, object],
    ) -> type[Node]:
        """Pick successor type from candidates, given resolved context fields."""
        ...

    async def fill(
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
            instruction: Class name.
            source: The previous node (context frame), serialized in prompt.
        """
        ...


class AgenticBackend:
    """LM backend with multi-turn tool use during fill().

    Two-phase fill: agent_loop runs <run> blocks for research,
    then structured extraction produces typed output.
    Delegates choose_type/make/decide to a wrapped ClaudeCLIBackend.
    """

    def __init__(self, model: str = "claude-sonnet-4-20250514", max_iters: int = 5):
        self.model = model
        self.max_iters = max_iters
        self._cli = ClaudeCLIBackend(model=model)

    async def fill(
        self,
        target: type[T],
        resolved: dict[str, object],
        instruction: str,
        source: "Node | None" = None,
    ) -> T:
        """Two-phase fill: agentic research, then structured extraction."""
        import uuid

        from bae.agent import _agent_namespace, _cli_send, agent_loop

        session_id = str(uuid.uuid4())
        call_count = 0

        async def send(text: str) -> str:
            nonlocal call_count
            result = await _cli_send(
                text, model=self.model, session_id=session_id,
                call_count=call_count,
            )
            call_count += 1
            return result

        plain_model = _build_plain_model(target)
        schema = transform_schema(plain_model)

        prompt = _build_fill_prompt(target, resolved, instruction, source)
        import json

        prompt += (
            f"\n\nTarget schema:\n{json.dumps(schema, indent=2)}"
            "\n\nUse Python in <run> tags to research and gather information, then provide your answer."
        )

        namespace = _agent_namespace()

        # Phase 1: Agentic research
        final_response = await agent_loop(
            prompt, send=send, namespace=namespace, max_iters=self.max_iters,
        )

        # Phase 2: Structured extraction
        extraction_prompt = (
            f"Based on your research:\n\n{final_response}\n\n"
            f"Extract the structured data for: {instruction}"
        )
        data = await self._cli._run_cli_json(extraction_prompt, schema)

        validated = validate_plain_fields(data, target)
        all_fields = dict(resolved)
        all_fields.update(validated)
        return target.model_construct(**all_fields)

    async def choose_type(
        self,
        types: list[type["Node"]],
        context: dict[str, object],
    ) -> type["Node"]:
        """Pick successor type -- delegates to CLI backend."""
        return await self._cli.choose_type(types, context)

    async def make(self, node: "Node", target: type[T]) -> T:
        """Produce node instance -- delegates to CLI backend."""
        return await self._cli.make(node, target)

    async def decide(self, node: "Node") -> "Node | None":
        """Decide next node -- delegates to CLI backend."""
        return await self._cli.decide(node)


class ClaudeCLIBackend:
    """LLM backend using Claude CLI subprocess."""

    def __init__(self, model: str = "claude-opus-4-6", timeout: int = 120):
        self.model = model
        self.timeout = timeout

    def _node_to_prompt(self, node: Node) -> str:
        """Convert node state to JSON prompt string."""
        import json

        data = {node.__class__.__name__: node.model_dump(mode="json")}
        return json.dumps(data, indent=2)

    async def make(self, node: Node, target: type[T]) -> T:
        """Produce an instance of target type using Claude CLI."""
        prompt = self._node_to_prompt(node)
        full_prompt = f"{prompt}\n\nProduce a {target.__name__}."

        schema = transform_schema(target)
        data = await self._run_cli_json(full_prompt, schema)
        return target.model_validate(data)

    async def _run_cli_json(self, prompt: str, schema: dict) -> dict | None:
        """Run Claude CLI with JSON schema and extract structured output."""
        import json

        # Strip 'format' fields — CLI silently rejects schemas containing them
        # (e.g. format:uri from HttpUrl). The API supports format but the CLI
        # doesn't create the structured output tool when it's present.
        clean_schema = _strip_format(schema)

        cmd = [
            "claude",
            "-p",
            prompt,  # single-shot prompt mode
            "--model",
            self.model,
            "--output-format",
            "json",  # return conversation as JSON stream
            "--json-schema",
            json.dumps(clean_schema),  # constrained decoding via structured output tool
            "--no-session-persistence",  # don't save to CLI session history
            "--tools",
            "",  # disable built-in tools (Bash, Edit, etc.)
            "--strict-mcp-config",  # disable MCP servers (no --mcp-config = none)
            "--setting-sources",
            "",  # skip loading project/user settings
            "--system-prompt",  # override default system prompt to prevent
            "You are a structured data generator. "  # CLI from leaking cwd/env/project context
            "Be brief and concise. "  # into LLM calls
            "Respond only with the requested data.",
        ]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            start_new_session=True,
        )
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(), timeout=self.timeout
            )
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            raise RuntimeError(f"Claude CLI timed out after {self.timeout}s")
        except asyncio.CancelledError:
            process.kill()
            await process.wait()
            raise

        stdout = stdout_bytes.decode()
        stderr = stderr_bytes.decode()

        if process.returncode != 0:
            raise RuntimeError(f"Claude CLI failed: {stderr}")

        data = json.loads(stdout)

        # Claude CLI returns conversation stream - extract structured_output from result
        if isinstance(data, list):
            for item in reversed(data):
                if item.get("type") == "result" and "structured_output" in item:
                    return item["structured_output"]
            raise RuntimeError(
                f"No structured_output in Claude CLI response: {json.dumps(data, indent=2)[:2000]}"
            )

        return data

    async def decide(self, node: Node) -> Node | None:
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
        if is_terminal:
            choice_prompt += "\n- None: Terminate processing"

        choice_schema = _build_choice_schema(type_names)

        choice_data = await self._run_cli_json(choice_prompt, choice_schema)
        chosen = choice_data["choice"]

        if chosen == "None":
            return None

        # Step 2: Fill the chosen type
        target = next(t for t in successors if t.__name__ == chosen)
        return await self.make(node, target)

    async def choose_type(
        self,
        types: list[type[Node]],
        context: dict[str, object],
    ) -> type[Node]:
        """Pick successor type from candidates using Claude CLI."""
        if len(types) == 1:
            return types[0]

        type_names = [t.__name__ for t in types]

        import json

        context_json = json.dumps(
            {
                "context": {
                    k: v.model_dump(mode="json") if isinstance(v, BaseModel) else v
                    for k, v in context.items()
                }
            },
            indent=2,
        )
        prompt = f"{context_json}\n\nPick one type: {', '.join(type_names)}"

        choice_schema = _build_choice_schema(type_names)

        choice_data = await self._run_cli_json(prompt, choice_schema)
        chosen = choice_data["choice"]

        # Map name back to type
        for t in types:
            if t.__name__ == chosen:
                return t

        return types[0]

    async def fill(
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
        data = await self._run_cli_json(prompt, schema)

        # Validate plain fields (LLM boundary — FillError on failure)
        validated = validate_plain_fields(data, target)

        # Merge independently-validated halves via model_construct
        all_fields = dict(resolved)
        all_fields.update(validated)
        return target.model_construct(**all_fields)
