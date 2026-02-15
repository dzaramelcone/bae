"""Tests for Effect marker — side effects on graph transitions.

Tests:
1. _extract_types_from_hint unwraps Annotated[X, Effect(...)]
2. _get_routing_strategy handles Annotated return types
3. _get_effects extracts effect callables per target type
4. Graph.arun() fires effects after fill (sync and async)
5. Effects fire only for the matched type in a union
6. Type alias form works identically to inline form
"""

from __future__ import annotations

from typing import Annotated
from unittest.mock import AsyncMock, MagicMock

import pytest

from bae import Effect, Graph, Node
from bae.graph import _get_effects, _get_routing_strategy
from bae.lm import LM
from bae.node import _extract_types_from_hint, _hint_includes_none


# =============================================================================
# Test Node Classes
# =============================================================================


class Done(Node):
    summary: str

    async def __call__(self) -> None: ...


class Target(Node):
    value: str

    async def __call__(self) -> Done: ...


class AltTarget(Node):
    option: str

    async def __call__(self) -> Done: ...


# Effect functions
effect_log: list = []


def sync_effect(node):
    effect_log.append(("sync", node.__class__.__name__))


async def async_effect(node):
    effect_log.append(("async", node.__class__.__name__))


# Nodes with Effect annotations
class SingleEffect(Node):
    data: str

    async def __call__(self) -> Annotated[Target, Effect(sync_effect)]: ...


class AsyncEffect(Node):
    data: str

    async def __call__(self) -> Annotated[Target, Effect(async_effect)]: ...


class UnionEffect(Node):
    """Effect on one branch of a union."""

    data: str

    async def __call__(self) -> Annotated[Target, Effect(sync_effect)] | AltTarget: ...


class OptionalEffect(Node):
    data: str

    async def __call__(self) -> Annotated[Target, Effect(sync_effect)] | None: ...


# Type alias form
Effected = Annotated[Target, Effect(sync_effect)]


class AliasEffect(Node):
    data: str

    async def __call__(self) -> Effected: ...


class AliasInUnion(Node):
    data: str

    async def __call__(self) -> Effected | AltTarget: ...


# =============================================================================
# _extract_types_from_hint
# =============================================================================


class TestExtractTypes:
    def test_annotated_single(self):
        hint = Annotated[Target, Effect(sync_effect)]
        assert _extract_types_from_hint(hint) == {Target}

    def test_annotated_in_union(self):
        hint = Annotated[Target, Effect(sync_effect)] | AltTarget
        assert _extract_types_from_hint(hint) == {Target, AltTarget}

    def test_annotated_optional(self):
        hint = Annotated[Target, Effect(sync_effect)] | None
        assert _extract_types_from_hint(hint) == {Target}

    def test_plain_unaffected(self):
        assert _extract_types_from_hint(Target) == {Target}
        assert _extract_types_from_hint(Target | AltTarget) == {Target, AltTarget}


# =============================================================================
# _hint_includes_none
# =============================================================================


class TestHintIncludesNone:
    def test_annotated_not_optional(self):
        assert not _hint_includes_none(Annotated[Target, Effect(sync_effect)])

    def test_annotated_optional(self):
        assert _hint_includes_none(Annotated[Target, Effect(sync_effect)] | None)


# =============================================================================
# _get_routing_strategy
# =============================================================================


class TestRoutingStrategy:
    def test_single_annotated_is_make(self):
        assert _get_routing_strategy(SingleEffect) == ("make", Target)

    def test_union_annotated_is_decide(self):
        strategy = _get_routing_strategy(UnionEffect)
        assert strategy[0] == "decide"
        assert set(strategy[1]) == {Target, AltTarget}

    def test_optional_annotated_is_decide(self):
        strategy = _get_routing_strategy(OptionalEffect)
        assert strategy[0] == "decide"
        assert Target in strategy[1]

    def test_alias_is_make(self):
        assert _get_routing_strategy(AliasEffect) == ("make", Target)


# =============================================================================
# _get_effects
# =============================================================================


class TestGetEffects:
    def test_single_annotated(self):
        hint = Annotated[Target, Effect(sync_effect)]
        assert _get_effects(hint, Target) == [sync_effect]

    def test_no_effect(self):
        assert _get_effects(Target, Target) == []

    def test_union_matched(self):
        hint = Annotated[Target, Effect(sync_effect)] | AltTarget
        assert _get_effects(hint, Target) == [sync_effect]

    def test_union_unmatched(self):
        hint = Annotated[Target, Effect(sync_effect)] | AltTarget
        assert _get_effects(hint, AltTarget) == []

    def test_none_hint(self):
        assert _get_effects(None, Target) == []


# =============================================================================
# Graph topology
# =============================================================================


class TestTopology:
    def test_successors_unwrap_annotated(self):
        assert SingleEffect.successors() == {Target}

    def test_successors_union_unwrap(self):
        assert UnionEffect.successors() == {Target, AltTarget}

    def test_graph_discovers_through_effect(self):
        g = Graph(start=SingleEffect)
        assert Target in g.nodes
        assert Done in g.nodes


# =============================================================================
# Graph.arun() fires effects
# =============================================================================


class TestEffectExecution:
    @pytest.fixture(autouse=True)
    def clear_log(self):
        effect_log.clear()

    @pytest.mark.asyncio
    async def test_sync_effect_fires(self):
        lm = MagicMock(spec=LM)
        lm.fill = AsyncMock(side_effect=[
            Target(value="v"),
            Done(summary="done"),
        ])
        g = Graph(start=SingleEffect)
        await g.arun(SingleEffect(data="x"), lm=lm, max_iters=10)
        assert ("sync", "Target") in effect_log

    @pytest.mark.asyncio
    async def test_async_effect_fires(self):
        lm = MagicMock(spec=LM)
        lm.fill = AsyncMock(side_effect=[
            Target(value="v"),
            Done(summary="done"),
        ])
        g = Graph(start=AsyncEffect)
        await g.arun(AsyncEffect(data="x"), lm=lm, max_iters=10)
        assert ("async", "Target") in effect_log

    @pytest.mark.asyncio
    async def test_effect_only_on_matched_branch(self):
        lm = MagicMock(spec=LM)
        lm.choose_type = AsyncMock(return_value=AltTarget)
        lm.fill = AsyncMock(side_effect=[
            AltTarget(option="b"),
            Done(summary="done"),
        ])
        g = Graph(start=UnionEffect)
        await g.arun(UnionEffect(data="x"), lm=lm, max_iters=10)
        assert effect_log == []  # AltTarget has no effect

    @pytest.mark.asyncio
    async def test_effect_fires_on_matched_branch(self):
        lm = MagicMock(spec=LM)
        lm.choose_type = AsyncMock(return_value=Target)
        lm.fill = AsyncMock(side_effect=[
            Target(value="v"),
            Done(summary="done"),
        ])
        g = Graph(start=UnionEffect)
        await g.arun(UnionEffect(data="x"), lm=lm, max_iters=10)
        assert ("sync", "Target") in effect_log

    @pytest.mark.asyncio
    async def test_alias_effect_fires(self):
        lm = MagicMock(spec=LM)
        lm.fill = AsyncMock(side_effect=[
            Target(value="v"),
            Done(summary="done"),
        ])
        g = Graph(start=AliasEffect)
        await g.arun(AliasEffect(data="x"), lm=lm, max_iters=10)
        assert ("sync", "Target") in effect_log
