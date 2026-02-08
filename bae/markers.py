"""Annotation markers for bae Node fields.

Dep and Recall markers for annotating Node fields with typing.Annotated.
The resolver uses these markers to classify fields for dependency injection
and trace recall.
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
