"""Optimization utilities for bae graphs.

Provides functions for converting execution traces to DSPy training format,
metrics for evaluating node transition predictions, save/load for
optimized predictors, and BootstrapFewShot optimization.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import dspy
from dspy.teleprompt import BootstrapFewShot

from bae.compiler import node_to_signature
from bae.node import Node


def trace_to_examples(trace: list[Node]) -> list[dspy.Example]:
    """Convert an execution trace to DSPy training examples.

    Each example represents a node transition: given the current node's
    state (fields), predict the next node type.

    Args:
        trace: List of nodes in execution order (from GraphResult.trace).

    Returns:
        List of dspy.Example objects, one per transition.
        Empty list if trace has fewer than 2 nodes.

    Example:
        >>> trace = [StartNode(request="hi"), EndNode(result="bye")]
        >>> examples = trace_to_examples(trace)
        >>> len(examples)
        1
        >>> examples[0].node_type
        'StartNode'
        >>> examples[0].next_node_type
        'EndNode'
    """
    if len(trace) < 2:
        return []

    examples = []
    for i in range(len(trace) - 1):
        input_node = trace[i]
        output_node = trace[i + 1]

        # Build example from input node's fields
        example_data = input_node.model_dump()

        # Add node type information
        example_data["node_type"] = type(input_node).__name__
        example_data["next_node_type"] = type(output_node).__name__

        # Create example
        example = dspy.Example(**example_data)

        # Mark input fields (all node fields + node_type, but not next_node_type)
        input_field_names = list(type(input_node).model_fields.keys()) + ["node_type"]
        example = example.with_inputs(*input_field_names)

        examples.append(example)

    return examples


def node_transition_metric(
    example: dspy.Example,
    pred,
    trace=None,
) -> float | bool:
    """Evaluate a node transition prediction.

    Compares the predicted next node type against the expected type
    from the example. Uses case-insensitive substring matching to be
    flexible with LLM output variations.

    Args:
        example: Training example with expected next_node_type.
        pred: Prediction object with predicted type (next_node_type or output attribute).
        trace: If not None, we're in bootstrap mode (returns bool).
               If None, we're in evaluation mode (returns float).

    Returns:
        In evaluation mode (trace=None): 1.0 for match, 0.0 for mismatch.
        In bootstrap mode (trace not None): True for match, False for mismatch.

    Example:
        >>> ex = dspy.Example(next_node_type="EndNode")
        >>> pred = Mock(next_node_type="EndNode")
        >>> node_transition_metric(ex, pred, trace=None)
        1.0
        >>> node_transition_metric(ex, pred, trace=[])
        True
    """
    expected = example.next_node_type

    # Get predicted value from pred object
    if hasattr(pred, "next_node_type"):
        predicted = pred.next_node_type
    elif hasattr(pred, "output"):
        predicted = pred.output
    else:
        predicted = ""

    # Normalize for comparison
    expected_norm = expected.lower().strip() if expected else ""
    predicted_norm = str(predicted).lower().strip() if predicted else ""

    # Substring match (either direction) for flexible LLM output
    match = expected_norm in predicted_norm or predicted_norm in expected_norm

    # Return type depends on mode
    if trace is None:
        # Evaluation mode: return float
        return 1.0 if match else 0.0
    else:
        # Bootstrap mode: return bool
        return match


def save_optimized(
    optimized: dict[type[Node], dspy.Predict],
    path: str | Path,
) -> None:
    """Save optimized predictors to a directory.

    Creates one JSON file per node class, named {NodeClassName}.json.
    Uses DSPy's native save with save_program=False for JSON format.

    Args:
        optimized: Dict mapping node classes to their optimized predictors.
        path: Directory to save the predictor files.

    Example:
        >>> save_optimized({MyNode: predictor}, "/tmp/compiled")
        # Creates /tmp/compiled/MyNode.json
    """
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)

    for node_cls, predictor in optimized.items():
        predictor.save(
            str(path / f"{node_cls.__name__}.json"),
            save_program=False,
        )


def load_optimized(
    node_classes: list[type[Node]],
    path: str | Path,
) -> dict[type[Node], dspy.Predict]:
    """Load optimized predictors from a directory.

    For each node class, creates a predictor with the correct signature
    and loads state from the corresponding JSON file if it exists.
    Missing files result in fresh (unoptimized) predictors.

    Args:
        node_classes: List of node classes to load predictors for.
        path: Directory containing the predictor JSON files.

    Returns:
        Dict mapping node classes to their predictors.

    Example:
        >>> loaded = load_optimized([MyNode], "/tmp/compiled")
        >>> predictor = loaded[MyNode]
    """
    path = Path(path)
    loaded: dict[type[Node], dspy.Predict] = {}

    for node_cls in node_classes:
        sig_path = path / f"{node_cls.__name__}.json"
        predictor = dspy.Predict(node_to_signature(node_cls))

        if sig_path.exists():
            predictor.load(str(sig_path))

        loaded[node_cls] = predictor

    return loaded


def optimize_node(
    node_cls: type[Node],
    trainset: list[dspy.Example],
    metric: Callable | None = None,
) -> dspy.Predict:
    """Optimize a node predictor using BootstrapFewShot.

    Filters trainset to examples matching this node type, then runs
    BootstrapFewShot to select high-quality demonstrations for the predictor.
    Returns unoptimized predictor if trainset has fewer than 10 examples.

    Args:
        node_cls: The node class to optimize.
        trainset: Training examples (from trace_to_examples).
        metric: Optional metric function for optimization.
                Defaults to node_transition_metric.

    Returns:
        Optimized dspy.Predict if sufficient examples,
        otherwise unoptimized dspy.Predict.

    Example:
        >>> examples = trace_to_examples(trace)
        >>> optimized = optimize_node(MyNode, examples)
    """
    # Filter trainset to examples for this node type
    node_examples = [ex for ex in trainset if ex.node_type == node_cls.__name__]

    # Create signature for this node
    signature = node_to_signature(node_cls)

    # Early return if not enough examples
    if len(node_examples) < 10:
        return dspy.Predict(signature)

    # Create student predictor
    student = dspy.Predict(signature)

    # Create optimizer with BootstrapFewShot
    optimizer = BootstrapFewShot(
        metric=metric or node_transition_metric,
        max_bootstrapped_demos=4,  # Generated from teacher
        max_labeled_demos=8,  # From trainset directly
        max_rounds=1,  # Single bootstrap iteration
    )

    # Compile and return optimized predictor
    return optimizer.compile(student, trainset=node_examples)
