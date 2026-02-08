"""LLM abstraction layer.

Provides a clean interface for LLM backends to produce typed node instances.
"""

from __future__ import annotations

import re
import types
import xml.etree.ElementTree as ET
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
from pydantic_ai import Agent, format_as_xml

from bae.markers import Dep, Recall
from bae.resolver import classify_fields

if TYPE_CHECKING:
    from bae.node import Node

T = TypeVar("T", bound="Node")


# ── XML helpers for fill() ──────────────────────────────────────────────


def _get_type_name(hint: Any) -> str:
    """Get a human-readable type name from a type hint."""
    origin = get_origin(hint)
    if origin is list:
        args = get_args(hint)
        if args:
            return f"list[{_get_type_name(args[0])}]"
        return "list"
    if origin is Annotated:
        return _get_type_name(get_args(hint)[0])
    if isinstance(hint, type):
        return hint.__name__
    return str(hint)


def _get_base_type(hint: Any) -> Any:
    """Extract base type from Annotated wrapper."""
    if get_origin(hint) is Annotated:
        return get_args(hint)[0]
    return hint


def _build_xml_schema(target_cls: type) -> str:
    """Generate XML schema showing field types and source annotations.

    Dep fields get source="dep" with their base type name.
    Plain fields show their type structure (nested model fields or type name).
    """
    fields = classify_fields(target_cls)
    hints = get_type_hints(target_cls, include_extras=True)

    # Build schema tag with optional description
    attrs = f'name="{target_cls.__name__}"'
    if target_cls.__doc__:
        doc = target_cls.__doc__.strip().split("\n")[0]
        attrs += f' description="{doc}"'

    lines = [f"<schema {attrs}>"]

    for name in target_cls.model_fields:
        hint = hints.get(name)
        if hint is None:
            continue

        base = _get_base_type(hint)
        kind = fields.get(name, "plain")

        if kind == "dep":
            type_name = _get_type_name(base)
            lines.append(f'  <{name} source="dep">{type_name}</{name}>')
        elif kind == "recall":
            type_name = _get_type_name(base)
            lines.append(f'  <{name} source="recall">{type_name}</{name}>')
        else:
            # Plain field — show structure for complex types
            if isinstance(base, type) and issubclass(base, BaseModel):
                # Nested model — show inner fields
                lines.append(f"  <{name}>")
                for inner_name, inner_field in base.model_fields.items():
                    inner_hint = get_type_hints(base).get(inner_name)
                    inner_type = _get_type_name(inner_hint) if inner_hint else "string"
                    lines.append(f"    <{inner_name}>{inner_type}</{inner_name}>")
                lines.append(f"  </{name}>")
            else:
                type_name = _get_type_name(base)
                lines.append(f"  <{name}>{type_name}</{name}>")

    lines.append("</schema>")
    return "\n".join(lines)


def _serialize_value(tag: str, value: Any, indent: int = 2) -> str:
    """Serialize a value as XML elements.

    Walks BaseModel fields directly (preserving types for nested models
    in lists). Uses typed tags for BaseModel list items, <item> for scalars.
    """
    prefix = " " * indent

    if isinstance(value, BaseModel):
        # Walk fields directly — don't model_dump(), which loses class info
        inner_lines = []
        for field_name in value.__class__.model_fields:
            field_val = getattr(value, field_name)
            inner_lines.append(_serialize_value(field_name, field_val, indent + 2))
        inner = "\n".join(inner_lines)
        return f"{prefix}<{tag}>\n{inner}\n{prefix}</{tag}>"
    elif isinstance(value, list):
        lines = [f"{prefix}<{tag}>"]
        for item in value:
            if isinstance(item, BaseModel):
                item_cls = item.__class__.__name__
                inner_lines = []
                for field_name in item.__class__.model_fields:
                    field_val = getattr(item, field_name)
                    inner_lines.append(
                        _serialize_value(field_name, field_val, indent + 4)
                    )
                inner = "\n".join(inner_lines)
                lines.append(f"{prefix}    <{item_cls}>")
                lines.append(inner)
                lines.append(f"{prefix}    </{item_cls}>")
            elif isinstance(item, dict):
                inner = _serialize_dict(item, indent + 4)
                lines.append(f"{prefix}    <item>")
                lines.append(inner)
                lines.append(f"{prefix}    </item>")
            else:
                lines.append(f"{prefix}    <item>{item}</item>")
        lines.append(f"{prefix}</{tag}>")
        return "\n".join(lines)
    elif isinstance(value, dict):
        inner = _serialize_dict(value, indent + 2)
        return f"{prefix}<{tag}>\n{inner}\n{prefix}</{tag}>"
    else:
        return f"{prefix}<{tag}>{value}</{tag}>"


def _serialize_dict(data: dict, indent: int = 2) -> str:
    """Serialize a dict as XML elements (fallback for raw dicts)."""
    lines = []
    for key, value in data.items():
        lines.append(_serialize_value(key, value, indent))
    return "\n".join(lines)


def _build_partial_xml(
    target_cls: type,
    resolved: dict[str, Any],
) -> str:
    """Build partial XML of target with deps serialized, ending at first plain field.

    Walks fields in declaration order. Dep/recall fields are serialized from
    resolved dict. Stops at the first plain field, emitting only its open tag.
    """
    fields = classify_fields(target_cls)

    lines = [f"<{target_cls.__name__}>"]

    # Walk fields in declaration order
    for name in target_cls.model_fields:
        kind = fields.get(name, "plain")

        if kind in ("dep", "recall"):
            # Serialize resolved value
            value = resolved.get(name)
            if value is not None:
                lines.append(_serialize_value(name, value))
        else:
            # First plain field — emit open tag and stop
            lines.append(f"  <{name}>")
            break

    return "\n".join(lines)


def _parse_xml_completion(
    response: str,
    target_cls: type,
    from_field: str,
) -> dict[str, Any]:
    """Parse LLM XML continuation into a dict of field values.

    The response is the LLM's continuation starting from inside the open tag
    of from_field. Reconstructs the XML by prepending the open tags, then
    parses with ElementTree.
    """
    fields = classify_fields(target_cls)
    hints = get_type_hints(target_cls, include_extras=True)

    # Find all plain fields from from_field onwards
    plain_fields = []
    found_start = False
    for name in target_cls.model_fields:
        if name == from_field:
            found_start = True
        if found_start and fields.get(name, "plain") == "plain":
            plain_fields.append(name)

    # Reconstruct full XML by wrapping the response
    # The response starts inside <from_field> and continues to </target_cls>
    full_xml = f"<{target_cls.__name__}><{from_field}>{response}"

    # Ensure we have a closing root tag
    root_tag = target_cls.__name__
    if f"</{root_tag}>" not in full_xml:
        full_xml += f"\n</{root_tag}>"

    # Parse the XML
    try:
        root = ET.fromstring(full_xml)
    except ET.ParseError:
        # Try to clean up common issues
        full_xml = re.sub(r"&(?!amp;|lt;|gt;|quot;|apos;)", "&amp;", full_xml)
        root = ET.fromstring(full_xml)

    result: dict[str, Any] = {}

    for field_name in plain_fields:
        elem = root.find(field_name)
        if elem is None:
            continue

        base_type = _get_base_type(hints.get(field_name, str))

        # Determine how to parse based on type
        if isinstance(base_type, type) and issubclass(base_type, BaseModel):
            result[field_name] = _element_to_dict(elem)
        elif get_origin(base_type) is list:
            result[field_name] = _element_to_list(elem)
        else:
            result[field_name] = (elem.text or "").strip()

    return result


def _element_to_dict(elem: ET.Element) -> dict[str, Any]:
    """Convert an XML element to a dict (for nested models)."""
    result: dict[str, Any] = {}
    for child in elem:
        if len(child) > 0:
            # Has sub-elements — check if it's a list (has <item> children)
            if child[0].tag == "item":
                result[child.tag] = _element_to_list(child)
            else:
                result[child.tag] = _element_to_dict(child)
        else:
            result[child.tag] = (child.text or "").strip()
    return result


def _element_to_list(elem: ET.Element) -> list[Any]:
    """Convert an XML element with <item> children to a list."""
    items = []
    for child in elem:
        if len(child) > 0:
            items.append(_element_to_dict(child))
        else:
            items.append((child.text or "").strip())
    return items


def _build_plain_model(target_cls: type) -> type[BaseModel]:
    """Create a dynamic Pydantic model with only plain fields from target.

    Used by PydanticAIBackend to constrain LLM output to only the fields
    it should generate (not dep/recall fields).
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
        resolved: dict[str, object],
        instruction: str,
        source: Node | None = None,
    ) -> T:
        """Populate target node fields using pydantic-ai."""
        plain_model = _build_plain_model(target)
        agent = self._get_agent((plain_model,), allow_none=False)

        # Build prompt: source XML + schema + instruction
        parts: list[str] = []
        if source is not None:
            parts.append(format_as_xml(
                source.model_dump(), root_tag=source.__class__.__name__
            ))
        parts.append(_build_xml_schema(target))
        if resolved:
            parts.append(format_as_xml(resolved, root_tag="resolved"))
        parts.append(instruction)

        prompt = "\n\n".join(parts)

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
            raise RuntimeError("No structured_output in Claude CLI response")

        return data

    def _run_cli_text(self, prompt: str) -> str:
        """Run Claude CLI in text mode and return raw output."""
        import subprocess

        cmd = [
            "claude",
            "-p", prompt,
            "--model", self.model,
            "--output-format", "text",
            "--no-session-persistence",
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=self.timeout)
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"Claude CLI timed out after {self.timeout}s")

        if result.returncode != 0:
            raise RuntimeError(f"Claude CLI failed: {result.stderr}")

        return result.stdout

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
        """Populate target node fields via XML next-token completion.

        Builds prompt: source XML + schema + partial XML ending at open tag
        of first plain field. LLM continues the XML document.
        """
        fields = classify_fields(target)
        plain_fields = [n for n in target.model_fields if fields.get(n) == "plain"]

        if not plain_fields:
            # No plain fields — nothing to fill, construct from resolved
            return target.model_construct(**resolved)

        first_plain = plain_fields[0]

        # Build prompt parts
        parts: list[str] = []
        if source is not None:
            parts.append(format_as_xml(
                source.model_dump(), root_tag=source.__class__.__name__
            ))
        parts.append(_build_xml_schema(target))
        parts.append(_build_partial_xml(target, resolved))

        prompt = "\n\n".join(parts)

        # Call CLI in text mode — LLM continues the XML document
        response = self._run_cli_text(prompt)

        # Parse the XML completion into raw dict
        parsed = _parse_xml_completion(response, target, first_plain)

        # Validate plain fields only (LLM boundary — FillError on failure)
        validated = validate_plain_fields(parsed, target)

        # Merge independently-validated halves via model_construct
        all_fields = dict(resolved)
        all_fields.update(validated)
        return target.model_construct(**all_fields)
