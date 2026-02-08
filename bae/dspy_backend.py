"""DSPy-based LLM backend.

Uses dspy.Predict with generated Signatures for structured LLM calls.
Implements self-correction on parse failures and API error retry.
"""

from __future__ import annotations

import json
import time
import types
from typing import TYPE_CHECKING, Any, TypeVar, get_args, get_type_hints

import dspy
from pydantic import ValidationError
from pydantic_ai import format_as_xml

from bae.compiler import node_to_signature
from bae.exceptions import BaeLMError, BaeParseError

if TYPE_CHECKING:
    from bae.node import Node

T = TypeVar("T", bound="Node")

# API exceptions that should trigger retry
try:
    from litellm.exceptions import (
        APIConnectionError,
        APIError,
        RateLimitError,
        ServiceUnavailableError,
        Timeout,
    )

    API_RETRY_EXCEPTIONS = (
        APIError,
        APIConnectionError,
        Timeout,
        RateLimitError,
        ServiceUnavailableError,
    )
except ImportError:
    API_RETRY_EXCEPTIONS = ()


class DSPyBackend:
    """LLM backend using DSPy Predict with generated Signatures.

    Features:
    - Uses node_to_signature() to create DSPy Signatures from Node classes
    - Self-correction on parse failures (retry once with error hint)
    - API failure handling (retry once with 1s delay, then raise BaeLMError)
    - Two-step decide pattern for union return types
    """

    def __init__(self, max_retries: int = 1):
        """Initialize backend.

        Args:
            max_retries: Number of retries for parse/API failures (default 1).
        """
        self.max_retries = max_retries

    def _build_inputs(self, node: Node, **deps: Any) -> dict[str, Any]:
        """Build input dict from node fields and deps."""
        inputs = {name: getattr(node, name) for name in node.__class__.model_fields}
        inputs.update(deps)
        return inputs

    def _parse_output(self, output: str, target: type[T]) -> T:
        """Parse dspy output string into target Pydantic model."""
        # Handle direct JSON output
        try:
            data = json.loads(output)
            return target.model_validate(data)
        except (json.JSONDecodeError, ValidationError):
            pass

        # Try to extract JSON from output if embedded
        try:
            # Find JSON object in output
            start = output.find("{")
            end = output.rfind("}") + 1
            if start != -1 and end > start:
                json_str = output[start:end]
                data = json.loads(json_str)
                return target.model_validate(data)
        except (json.JSONDecodeError, ValidationError):
            pass

        # Raise with original output for debugging
        raise ValueError(f"Cannot parse output as {target.__name__}: {output}")

    def _call_with_retry(
        self,
        predictor: dspy.Predict,
        inputs: dict[str, Any],
        error_hint: str | None = None,
    ) -> dspy.Prediction:
        """Call predictor with API error retry logic.

        Args:
            predictor: The dspy.Predict instance.
            inputs: Input kwargs for prediction.
            error_hint: Optional hint about previous parse error.

        Returns:
            The prediction result.

        Raises:
            BaeLMError: If API fails after retry.
        """
        if error_hint:
            inputs = {**inputs, "parse_error": error_hint}

        last_error = None
        for attempt in range(self.max_retries + 1):
            try:
                return predictor(**inputs)
            except API_RETRY_EXCEPTIONS as e:
                last_error = e
                if attempt < self.max_retries:
                    time.sleep(1)
                    continue
                raise BaeLMError(str(e), cause=e) from e

        # Should not reach here
        raise BaeLMError("Unexpected error", cause=last_error)

    def make(self, node: Node, target: type[T], **deps: Any) -> T:
        """Produce an instance of target type using dspy.Predict.

        Args:
            node: The current node providing context.
            target: The target Node type to produce.
            **deps: Additional Dep values to pass as inputs.

        Returns:
            An instance of the target type.

        Raises:
            BaeParseError: If parsing fails after retry.
            BaeLMError: If API fails after retry.
        """
        signature = node_to_signature(target)
        predictor = dspy.Predict(signature)
        inputs = self._build_inputs(node, **deps)

        last_error = None
        for attempt in range(self.max_retries + 1):
            error_hint = str(last_error) if last_error else None

            try:
                result = self._call_with_retry(predictor, inputs, error_hint)
                output = result.output
                return self._parse_output(output, target)
            except ValueError as e:
                last_error = e
                if attempt < self.max_retries:
                    continue
                raise BaeParseError(str(e), cause=e) from e

        # Should not reach here
        raise BaeParseError("Unexpected parse failure", cause=last_error)

    def _get_return_types(self, node: Node) -> tuple[list[type], bool]:
        """Get return types from node's __call__ method.

        Returns:
            Tuple of (list of concrete types, is_terminal flag).
        """
        hints = get_type_hints(node.__call__)
        return_hint = hints.get("return")

        if return_hint is None or return_hint is type(None):
            return [], True

        # Handle union types (X | Y | None)
        if isinstance(return_hint, types.UnionType):
            args = get_args(return_hint)
            concrete_types = [arg for arg in args if arg is not type(None) and isinstance(arg, type)]
            is_terminal = type(None) in args
            return concrete_types, is_terminal

        # Single type
        if isinstance(return_hint, type):
            return [return_hint], False

        return [], True

    def _predict_choice(
        self,
        node: Node,
        choices: list[type],
        is_terminal: bool,
    ) -> str:
        """Predict which type to produce from choices.

        Args:
            node: The current node.
            choices: List of possible target types.
            is_terminal: Whether None is a valid choice.

        Returns:
            The name of the chosen type, or "None".
        """
        # Build choice enum
        type_names = [t.__name__ for t in choices]
        if is_terminal:
            type_names.append("None")

        # Create signature for choice
        fields = {
            "context": (str, dspy.InputField(desc="Current node state")),
            "choice": (str, dspy.OutputField(desc=f"Choose one: {', '.join(type_names)}")),
        }

        choice_signature = dspy.make_signature(fields, "DecideNextStep")
        predictor = dspy.Predict(choice_signature)

        # Build context from node as XML
        context = format_as_xml(node.model_dump(), root_tag=node.__class__.__name__)

        result = predictor(context=context)
        chosen = result.choice.strip()

        # Validate choice
        if chosen in type_names:
            return chosen

        # Try to match partial/case-insensitive
        for name in type_names:
            if name.lower() in chosen.lower():
                return name

        # Default to first option if unclear
        return type_names[0]

    def decide(self, node: Node) -> Node | None:
        """Decide which successor to produce based on return type hint.

        Uses two-step pattern for union types:
        1. Predict which type to choose
        2. Call make() to produce the chosen type

        Args:
            node: The current node.

        Returns:
            The next node instance, or None if terminal.

        Raises:
            BaeParseError: If parsing fails.
            BaeLMError: If API fails.
        """
        types_list, is_terminal = self._get_return_types(node)

        # No types and terminal -> return None
        if not types_list and is_terminal:
            return None

        # No types and not terminal -> error
        if not types_list:
            raise ValueError(f"{node.__class__.__name__} has no return types")

        # Single type -> skip choice, just make
        if len(types_list) == 1 and not is_terminal:
            return self.make(node, types_list[0])

        # Multiple types or optional -> two-step
        choice = self._predict_choice(node, types_list, is_terminal)

        if choice == "None":
            return None

        # Find the chosen type
        target = next((t for t in types_list if t.__name__ == choice), None)
        if target is None:
            target = types_list[0]  # Fallback

        return self.make(node, target)

    def choose_type(
        self,
        types: list[type],
        context: dict[str, Any],
    ) -> type:
        """Pick successor type from candidates using dspy.Predict.

        For single-type lists, returns the type directly without an LLM call.

        Args:
            types: List of candidate Node types.
            context: Resolved field values (from resolve_fields).

        Returns:
            One of the types from the list.
        """
        if len(types) == 1:
            return types[0]

        type_names = [t.__name__ for t in types]

        # Build choice signature with context as InputField
        fields = {
            "context": (str, dspy.InputField(desc="Resolved context fields")),
            "choice": (str, dspy.OutputField(desc=f"Choose one: {', '.join(type_names)}")),
        }

        choice_signature = dspy.make_signature(fields, "ChooseNextType")
        predictor = dspy.Predict(choice_signature)

        # Format context for the LLM
        context_str = format_as_xml(context, root_tag="context")

        # Add type docstrings to context
        for t in types:
            if t.__doc__:
                context_str += f"\n- {t.__name__}: {t.__doc__}"

        result = predictor(context=context_str)
        chosen = result.choice.strip()

        # Map name back to type
        for t in types:
            if t.__name__ == chosen:
                return t

        # Fallback: partial/case-insensitive match
        for t in types:
            if t.__name__.lower() in chosen.lower():
                return t

        return types[0]

    def fill(
        self,
        target: type[T],
        resolved: dict[str, Any],
        instruction: str,
        source: "Node | None" = None,
    ) -> T:
        """Populate a node's plain fields using dspy.Predict.

        Uses node_to_signature(target, is_start=False) so plain fields
        become OutputFields (LLM fills them) and Dep/Recall fields become
        InputFields (provided via resolved dict).

        Args:
            target: The Node type to instantiate.
            resolved: Only the target's resolved dep/recall values.
            instruction: Class name + optional docstring for the LLM.
            source: The previous node (context frame). Not yet used by DSPy.

        Returns:
            An instance of target with all fields populated.

        Raises:
            BaeParseError: If parsing fails after retry.
            BaeLMError: If API fails after retry.
        """
        signature = node_to_signature(target, is_start=False)
        predictor = dspy.Predict(signature)

        # resolved dict provides InputField values; LLM generates OutputField values
        result = self._call_with_retry(predictor, resolved)

        # Collect all field values: resolved (InputFields) + LM output (OutputFields)
        all_fields = dict(resolved)
        # Extract OutputField values from prediction
        for key in result.keys():
            if key not in resolved:
                all_fields[key] = getattr(result, key)

        return target.model_construct(**all_fields)
