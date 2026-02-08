"""Tests for NodeConfig redesign and _wants_lm helper.

NodeConfig is a standalone TypedDict (not extending ConfigDict).
node_config is a ClassVar on Node, separate from model_config.
_wants_lm detects whether a method declares an lm parameter.
"""

from __future__ import annotations

import inspect
from typing import ClassVar, get_type_hints
from unittest.mock import MagicMock

from pydantic import ConfigDict

from bae.lm import LM
from bae.node import Node, NodeConfig, _wants_lm


# =============================================================================
# Test: NodeConfig TypedDict
# =============================================================================


class TestNodeConfigTypedDict:
    """NodeConfig is a standalone TypedDict, not extending ConfigDict."""

    def test_empty_node_config(self):
        """NodeConfig() creates an empty dict."""
        config = NodeConfig()
        assert config == {}
        assert isinstance(config, dict)

    def test_node_config_with_lm(self):
        """NodeConfig(lm=mock_lm) stores lm value."""
        mock_lm = MagicMock()
        config = NodeConfig(lm=mock_lm)
        assert config["lm"] is mock_lm

    def test_node_config_is_not_config_dict(self):
        """NodeConfig is NOT a subclass of ConfigDict."""
        # TypedDict doesn't support issubclass, so check __bases__ directly
        assert ConfigDict not in NodeConfig.__bases__


# =============================================================================
# Test: Node.node_config ClassVar
# =============================================================================


class TestNodeConfigClassVar:
    """node_config is a ClassVar on Node, separate from model_config."""

    def test_node_has_default_empty_node_config(self):
        """Node.node_config defaults to empty NodeConfig()."""
        assert Node.node_config == {}

    def test_node_model_config_is_standard_config_dict(self):
        """Node.model_config is standard ConfigDict (not NodeConfig)."""
        # model_config should have arbitrary_types_allowed=True
        assert Node.model_config.get("arbitrary_types_allowed") is True

    def test_subclass_inherits_node_config(self):
        """Subclass without node_config inherits parent's empty NodeConfig()."""

        class ChildNode(Node):
            value: str

            def __call__(self, lm: LM) -> None: ...

        assert ChildNode.node_config == {}

    def test_subclass_overrides_node_config(self):
        """Subclass can override node_config with NodeConfig(lm=mock_lm)."""
        mock_lm = MagicMock()

        class CustomNode(Node):
            value: str
            node_config: ClassVar[NodeConfig] = NodeConfig(lm=mock_lm)

            def __call__(self, lm: LM) -> None: ...

        assert CustomNode.node_config["lm"] is mock_lm

    def test_override_does_not_leak_to_parent(self):
        """Override does not affect parent class."""
        mock_lm = MagicMock()

        class OverrideNode(Node):
            value: str
            node_config: ClassVar[NodeConfig] = NodeConfig(lm=mock_lm)

            def __call__(self, lm: LM) -> None: ...

        assert Node.node_config == {}

    def test_override_does_not_leak_to_sibling(self):
        """Override does not affect sibling classes."""
        mock_lm = MagicMock()

        class SiblingA(Node):
            value: str
            node_config: ClassVar[NodeConfig] = NodeConfig(lm=mock_lm)

            def __call__(self, lm: LM) -> None: ...

        class SiblingB(Node):
            value: str

            def __call__(self, lm: LM) -> None: ...

        assert SiblingB.node_config == {}
        assert SiblingA.node_config["lm"] is mock_lm


# =============================================================================
# Test: _wants_lm helper
# =============================================================================


class TestWantsLm:
    """_wants_lm detects whether __call__ declares an lm parameter."""

    def test_wants_lm_with_typed_lm_param(self):
        """Returns True for def __call__(self, lm: LM)."""

        class NodeWithLM(Node):
            value: str

            def __call__(self, lm: LM) -> None: ...

        assert _wants_lm(NodeWithLM.__call__) is True

    def test_wants_lm_with_untyped_lm_param(self):
        """Returns True for def __call__(self, lm)."""

        class NodeWithUntypedLM(Node):
            value: str

            def __call__(self, lm) -> None: ...

        assert _wants_lm(NodeWithUntypedLM.__call__) is True

    def test_wants_lm_without_lm_param(self):
        """Returns False for def __call__(self)."""

        class NodeWithoutLM(Node):
            value: str

            def __call__(self) -> None: ...

        assert _wants_lm(NodeWithoutLM.__call__) is False

    def test_wants_lm_with_different_param_name(self):
        """Returns False for def __call__(self, other_param)."""

        class NodeWithOtherParam(Node):
            value: str

            def __call__(self, other_param) -> None: ...

        assert _wants_lm(NodeWithOtherParam.__call__) is False

    def test_wants_lm_base_node(self):
        """Base Node.__call__ has lm parameter, returns True."""
        assert _wants_lm(Node.__call__) is True
