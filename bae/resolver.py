"""Field resolver for Dep and Recall annotations.

Inspects Node subclass type hints to classify each field as 'dep' (populated
by a callable), 'recall' (populated from the execution trace), or 'plain'
(supplied directly by the caller or LLM).
"""

from __future__ import annotations

from typing import Annotated, get_args, get_origin, get_type_hints

from bae.markers import Dep, Recall


def classify_fields(node_cls: type) -> dict[str, str]:
    """Classify each field of a Node subclass by its annotation marker.

    Inspects ``typing.Annotated`` metadata for ``Dep`` or ``Recall`` markers.
    Fields without a recognized marker are classified as ``"plain"``.

    Args:
        node_cls: A Node subclass whose fields to classify.

    Returns:
        Dict mapping field name to ``"dep"``, ``"recall"``, or ``"plain"``.
    """
    hints = get_type_hints(node_cls, include_extras=True)
    result: dict[str, str] = {}

    for name, hint in hints.items():
        if name == "return":
            continue

        if get_origin(hint) is Annotated:
            metadata = get_args(hint)[1:]
            classified = False
            for m in metadata:
                if isinstance(m, Dep):
                    result[name] = "dep"
                    classified = True
                    break
                if isinstance(m, Recall):
                    result[name] = "recall"
                    classified = True
                    break
            if not classified:
                result[name] = "plain"
        else:
            result[name] = "plain"

    return result
