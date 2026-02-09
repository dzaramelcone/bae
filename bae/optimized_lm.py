"""Optimized LM backend using pre-loaded predictors.

Extends DSPyBackend to use optimized predictors when available,
falling back to fresh (naive) predictors when not.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, TypeVar

import dspy

from bae.compiler import node_to_signature
from bae.dspy_backend import DSPyBackend
from bae.exceptions import BaeParseError

if TYPE_CHECKING:
    from bae.node import Node

T = TypeVar("T", bound="Node")
logger = logging.getLogger(__name__)


class OptimizedLM(DSPyBackend):
    """DSPyBackend that uses pre-loaded optimized predictors when available.

    For nodes with optimized predictors in the registry, uses the pre-loaded
    predictor (with few-shot demos from BootstrapFewShot). For nodes without
    optimized versions, falls back to creating fresh predictors (naive prompts).

    Tracks usage statistics for observability.
    """

    def __init__(
        self,
        optimized: dict[type[Node], dspy.Predict] | None = None,
        max_retries: int = 1,
    ):
        """Initialize with optional optimized predictors.

        Args:
            optimized: Dict mapping node classes to their optimized predictors.
                       If None or empty, all calls use naive (fresh) predictors.
            max_retries: Number of retries for parse/API failures (default 1).
        """
        super().__init__(max_retries=max_retries)
        self.optimized = optimized or {}
        self.stats = {"optimized": 0, "naive": 0}

    def _get_predictor_for_target(self, target: type[Node]) -> dspy.Predict:
        """Get predictor for target type, preferring optimized.

        Args:
            target: The target Node type.

        Returns:
            Either the pre-loaded optimized predictor or a fresh one.
        """
        if target in self.optimized:
            self.stats["optimized"] += 1
            logger.debug(f"Using optimized predictor for {target.__name__}")
            return self.optimized[target]

        # Fallback to fresh predictor
        self.stats["naive"] += 1
        logger.debug(f"Using naive predictor for {target.__name__}")
        return dspy.Predict(node_to_signature(target))

    async def make(self, node: Node, target: type[T], **deps: Any) -> T:
        """Produce target using optimized predictor if available.

        Overrides DSPyBackend.make() to use pre-loaded predictors from
        the optimized registry when available.

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
        predictor = self._get_predictor_for_target(target)
        inputs = self._build_inputs(node, **deps)

        last_error = None
        for attempt in range(self.max_retries + 1):
            error_hint = str(last_error) if last_error else None

            try:
                result = await self._call_with_retry(predictor, inputs, error_hint)
                output = result.output
                return self._parse_output(output, target)
            except ValueError as e:
                last_error = e
                if attempt < self.max_retries:
                    continue
                raise BaeParseError(str(e), cause=e) from e

        raise BaeParseError("Unexpected parse failure", cause=last_error)

    def get_stats(self) -> dict[str, int]:
        """Return usage statistics.

        Returns:
            Dict with counts of "optimized" and "naive" predictor uses.
        """
        return self.stats.copy()
