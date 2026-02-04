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
