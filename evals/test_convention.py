"""Parametrized eval: 3 conventions x 3 models x 5 scenarios x 3 reps = 135 test cases.

Tests convention compliance across Claude model tiers.
Each test dispatches a single-shot prompt with a convention-specific system prompt
and validates the response follows the convention correctly.
"""

from __future__ import annotations

import pytest

from evals.prompts import SYSTEM_PROMPTS, eval_send, validate_response

MODELS = [
    "claude-opus-4-6",
    "claude-sonnet-4-5-20250929",
    "claude-haiku-4-5-20251001",
]

SCENARIOS = [
    ("What is a Graph in bae?", "no_code"),
    ("What's 2**100?", "one_exec"),
    ("Explain how Dep works with an example", "no_exec"),
    ("What variables do I have?", "one_exec"),
    ("Show me how to define a Node, then create one for me", "mixed"),
]

CONVENTIONS = ["fence_annotation", "wrapper_marker", "inverse"]


@pytest.mark.e2e
@pytest.mark.asyncio
@pytest.mark.parametrize("rep", range(3))
@pytest.mark.parametrize(
    "scenario_prompt,expected",
    SCENARIOS,
    ids=[s[0][:30] for s in SCENARIOS],
)
@pytest.mark.parametrize("convention", CONVENTIONS)
@pytest.mark.parametrize("model", MODELS)
async def test_convention_compliance(model, convention, scenario_prompt, expected, rep):
    """Dispatch prompt with convention-specific system prompt, validate response."""
    system_prompt = SYSTEM_PROMPTS[convention]
    response = await eval_send(model, system_prompt, scenario_prompt, timeout=30)
    validate_response(response, convention, expected)
