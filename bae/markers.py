"""Annotation markers for bae Node fields.

These markers are used with typing.Annotated to add metadata to Node fields.
The compiler uses these markers to generate DSPy Signatures.
"""

from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class Context:
    """Marker for Node fields that should become DSPy InputFields.

    Usage:
        class MyNode(Node):
            data: Annotated[str, Context(description="The data to process")]
    """

    description: str = ""


@dataclass(frozen=True)
class Dep:
    """Marker for dependency-injected fields and parameters.

    v2 (field annotation): Dep(callable) stores a callable whose return value
    populates the field before node execution.

    v1 (call parameter annotation): Dep(description="...") annotates __call__
    parameters for DSPy Signature generation. Deprecated; will be removed in
    Phase 8 cleanup.

    Usage (v2):
        class MyNode(Node):
            data: Annotated[str, Dep(get_data)]

    Usage (v1, deprecated):
        class MyNode(Node):
            def __call__(
                self,
                lm,
                db: Annotated[str, Dep(description="Database connection")],
            ) -> NextNode | None:
                ...
    """

    fn: Callable | None = None
    description: str = ""


@dataclass(frozen=True)
class Bind:
    """Marker for Node fields that should be available to downstream nodes.

    Bind-annotated fields expose their values for downstream type-based
    dependency injection. Only one Bind per type is allowed across the
    entire graph (enforced by Graph.validate()).

    Usage:
        class MyNode(Node):
            conn: Annotated[DatabaseConn, Bind()]

        class DownstreamNode(Node):
            def __call__(
                self,
                lm,
                conn: Annotated[DatabaseConn, Dep(description="DB connection")],
            ) -> None:
                # conn will be injected from MyNode's Bind field
                ...
    """

    pass


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
