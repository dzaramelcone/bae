"""Annotation markers for bae Node fields.

These markers are used with typing.Annotated to add metadata to Node fields.
The compiler uses these markers to generate DSPy Signatures.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Context:
    """Marker for Node fields that should become DSPy InputFields.

    Usage:
        class MyNode(Node):
            data: Annotated[str, Context(description="The data to process")]
    """

    description: str


@dataclass(frozen=True)
class Dep:
    """Marker for __call__ parameters that are injected dependencies.

    Dep-annotated parameters become InputFields in the DSPy Signature,
    making them visible to the LLM during optimization.

    Usage:
        class MyNode(Node):
            def __call__(
                self,
                lm,
                db: Annotated[str, Dep(description="Database connection")],
            ) -> NextNode | None:
                ...
    """

    description: str
