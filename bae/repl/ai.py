"""AI agent for natural language interaction with bae.

Wraps pydantic-ai Agent for NL conversation, delegates fill/choose_type
to the existing bae LM protocol, and extracts code blocks from responses.
"""

from __future__ import annotations

import inspect
import re
from typing import TYPE_CHECKING

from pydantic_ai import Agent

if TYPE_CHECKING:
    from bae.lm import LM
    from bae.node import Node
    from bae.repl.channels import ChannelRouter

_CODE_BLOCK_RE = re.compile(
    r"```(?:python|py)?\s*\n(.*?)\n```",
    re.DOTALL,
)

MAX_CONTEXT_CHARS = 2000
MAX_HISTORY_MESSAGES = 20


class AI:
    """AI agent for natural language interaction with bae.

    await ai("question")                  -- NL conversation with context
    await ai.fill(NodeClass, context)     -- populate node via LM
    await ai.choose_type([A, B], context) -- pick successor type via LM
    ai.extract_code(text)                 -- extract python code blocks
    """

    def __init__(
        self,
        *,
        lm: LM,
        router: ChannelRouter,
        namespace: dict,
        model: str = "anthropic:claude-sonnet-4-20250514",
    ) -> None:
        self._lm = lm
        self._router = router
        self._namespace = namespace
        self._history: list = []
        self._agent: Agent | None = None
        self._model = model

    def _ensure_agent(self) -> Agent:
        """Lazy-init the pydantic-ai Agent (defers API key check)."""
        if self._agent is None:
            self._agent = Agent(self._model, system_prompt=_system_prompt())
        return self._agent

    async def __call__(self, prompt: str) -> str:
        """NL conversation with namespace context."""
        agent = self._ensure_agent()
        context = _build_context(self._namespace)
        full_prompt = f"{context}\n\n{prompt}" if context else prompt

        result = await agent.run(
            full_prompt,
            message_history=self._history[-MAX_HISTORY_MESSAGES:] or None,
        )
        self._history = result.all_messages()
        response = result.output
        self._router.write("ai", response, mode="NL", metadata={"type": "response"})
        return response

    async def fill(self, target: type[Node], context: dict | None = None) -> Node:
        """Populate a node's plain fields via bae's LM fill."""
        return await self._lm.fill(target, context or {}, target.__name__)

    async def choose_type(
        self, types: list[type[Node]], context: dict | None = None,
    ) -> type[Node]:
        """Pick successor type from candidates via bae's LM choose_type."""
        return await self._lm.choose_type(types, context or {})

    @staticmethod
    def extract_code(text: str) -> list[str]:
        """Extract Python code blocks from markdown-fenced text."""
        return _CODE_BLOCK_RE.findall(text)

    def __repr__(self) -> str:
        n = len(self._history)
        return f"ai -- await ai('question'). {n} messages in history."


def _system_prompt() -> str:
    """Static system prompt for the cortex AI agent."""
    return """\
You are the AI assistant inside cortex, a Python REPL built on bae (a framework for type-driven agent graphs).

Your role:
- Answer questions about the user's namespace, graphs, and code
- Produce correct Python code when asked
- Use bae's API correctly (Node, Graph, Dep, Recall, fill, choose_type)
- When asked to do system operations, suggest appropriate bash commands
- When ambiguous, ask clarifying questions rather than guessing

Context:
- You will receive the current namespace state with each message
- Variables, graphs, traces, and channel objects are all available
- The user can execute any Python you produce via the PY mode
- Code blocks should use ```python fences

bae quick reference:
- Nodes are Pydantic models: class MyNode(Node): field: str
- Graph topology from return types: async def __call__(self) -> NextNode | None: ...
- Dep(fn) for dependency injection, Recall() for trace recall
- graph = Graph(start=MyNode); result = await graph.arun(MyNode(field="value"), lm=lm)
- lm.fill(NodeClass, resolved_context, instruction) populates plain fields
- lm.choose_type([TypeA, TypeB], context) picks a successor type

Rules:
- Be concise. The REPL is a conversation, not documentation.
- When producing code, make it complete and directly executable.
- Use the namespace context to give specific, relevant answers.
- Never fabricate variable values -- only reference what's in the namespace."""


def _build_context(namespace: dict) -> str:
    """Summarize namespace for AI context, truncated to MAX_CONTEXT_CHARS.

    Priority: graph topology first, then trace, then user variables.
    Skips internals, modules, and known bae names.
    """
    from bae.graph import Graph
    from bae.node import Node

    parts: list[str] = []

    # Graph topology (highest priority)
    graph = namespace.get("graph")
    if isinstance(graph, Graph):
        edges = []
        for n in sorted(graph.nodes, key=lambda x: x.__name__):
            succs = graph.edges.get(n, set())
            target = ", ".join(s.__name__ for s in succs) if succs else "(terminal)"
            edges.append(f"  {n.__name__} -> {target}")
        parts.append("Graph:\n" + "\n".join(edges))

    # Recent trace (last 5)
    trace = namespace.get("_trace")
    if isinstance(trace, list) and trace:
        steps = [f"  {i+1}. {type(n).__name__}" for i, n in enumerate(trace[-5:])]
        parts.append("Trace:\n" + "\n".join(steps))

    # User variables (skip internals, modules, bae types)
    _SKIP = {
        "__builtins__", "ai", "ns", "store", "channels",
        "Node", "Graph", "Dep", "Recall", "GraphResult",
        "LM", "NodeConfig", "Annotated", "asyncio", "os",
    }
    user_vars: list[str] = []
    for name, obj in sorted(namespace.items()):
        if name.startswith("_") or name in _SKIP:
            continue
        if inspect.ismodule(obj):
            continue
        if isinstance(obj, type) and issubclass(obj, Node):
            user_vars.append(f"  {name}: Node class")
        elif isinstance(obj, Node):
            user_vars.append(f"  {name}: {type(obj).__name__}")
        elif isinstance(obj, Graph):
            continue  # Already shown above
        elif not callable(obj):
            r = repr(obj)
            if len(r) > 60:
                r = r[:57] + "..."
            user_vars.append(f"  {name} = {r}")
    if user_vars:
        parts.append("Variables:\n" + "\n".join(user_vars))

    result = "\n\n".join(parts)
    if len(result) > MAX_CONTEXT_CHARS:
        result = result[:MAX_CONTEXT_CHARS] + "\n  ... (truncated)"
    return result
