"""Namespace tab completer wrapping rlcompleter for namespace-aware completion.

The Completer ABC from prompt_toolkit serves as the provider interface
for future LSP integration.
"""

from __future__ import annotations

import rlcompleter

from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.document import Document


class NamespaceCompleter(Completer):
    """Tab completion on a live namespace dict via rlcompleter."""

    def __init__(self, namespace: dict) -> None:
        self._completer = rlcompleter.Completer(namespace)

    def get_completions(self, document: Document, complete_event) -> list[Completion]:
        text = document.get_word_before_cursor(WORD=True)
        if not text:
            return
        i = 0
        while (match := self._completer.complete(text, i)) is not None:
            yield Completion(match, start_position=-len(text))
            i += 1
