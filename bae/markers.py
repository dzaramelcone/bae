"""Annotation markers for bae Node fields.

Dep, Recall, and Effect markers for annotating Node fields, dep function
parameters, and return type hints. The resolver uses these markers for
dependency injection, trace recall, and transition effects.
"""

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class Dep:
    """Marker for field-level dependency injection.

    Dep(callable) stores a callable whose return value populates the
    field before node execution. The resolver calls fn() during
    resolve_fields and caches the result per graph run.

    Usage:
        class MyNode(Node):
            data: Annotated[str, Dep(get_data)]
    """

    fn: Callable | None = None


@dataclass(frozen=True)
class Recall:
    """Marker for fields populated from the execution trace.

    Recall() searches backward through the execution trace for the most
    recent node whose type matches (via MRO) and copies the field value.

    Usage:
        class ReviewCode(Node):
            prev_analysis: Annotated[str, Recall()]
    """

    pass


@dataclass(frozen=True)
class Gate:
    """Marker for fields requiring human input during graph execution.

    Gate() suspends graph execution at resolve time until the user
    provides a value. The field name, type, and description are
    displayed as a prompt.

    Usage:
        class ConfirmDeploy(Node):
            approved: Annotated[bool, Gate(description="Deploy to prod?")]
    """

    description: str = ""


@dataclass(frozen=True)
class Effect:
    """Marker for side effects on graph transitions.

    Annotate a return type hint to fire a callable after the target node
    is produced. The callable receives the produced node instance.

    Usage:
        # One-off effect on a single edge
        async def __call__(self) -> Annotated[CommitTask, Effect(vcs_commit)]: ...

        # Type alias for reuse across edges
        Committed = Annotated[CommitTask, Effect(vcs_commit)]
    """

    fn: Callable
