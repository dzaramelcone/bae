"""Run ootd.py with real Claude CLI and capture prompt/response traces."""

from __future__ import annotations

from pathlib import Path

from examples.ootd import IsTheUserGettingDressed, graph
from bae.lm import ClaudeCLIBackend

TRACES_DIR = Path(__file__).parent.parent / "tests" / "traces"


class TracingClaudeCLI(ClaudeCLIBackend):
    """ClaudeCLIBackend that captures prompts and responses."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.turns: list[dict] = []
        self._turn_count = 0

    def _run_cli_json(self, prompt: str, schema: dict) -> dict | None:
        self._turn_count += 1
        print(f"  Turn {self._turn_count}: sending prompt ({len(prompt)} chars)...")
        response = super()._run_cli_json(prompt, schema)
        print(f"  Turn {self._turn_count}: got response")
        self.turns.append({"prompt": prompt, "schema": schema, "response": response})
        return response

    def write_trace(self, path: Path) -> None:
        import json

        path.parent.mkdir(parents=True, exist_ok=True)
        lines: list[str] = []

        for i, turn in enumerate(self.turns, 1):
            lines.append(f"{'=' * 72}")
            lines.append(f"TURN {i}")
            lines.append(f"{'=' * 72}")
            lines.append("")
            lines.append(f"{'─' * 40} INPUT {'─' * 40}")
            lines.append("")
            lines.append(turn["prompt"])
            lines.append("")
            lines.append(f"{'─' * 39} SCHEMA {'─' * 39}")
            lines.append("")
            lines.append(json.dumps(turn["schema"], indent=2))
            lines.append("")
            lines.append(f"{'─' * 39} OUTPUT {'─' * 39}")
            lines.append("")
            lines.append(json.dumps(turn["response"], indent=2))
            lines.append("")
            lines.append("")

        path.write_text("\n".join(lines))


if __name__ == "__main__":
    lm = TracingClaudeCLI(timeout=60)
    trace_path = TRACES_DIR / "ootd_cli_real.txt"

    print("Running ootd graph with real Claude CLI...")
    try:
        result = graph.run(
            IsTheUserGettingDressed(user_message="ugh i just got up"),
            lm=lm,
        )
        print("\n── Result ──")
        terminal = result.trace[-1]
        print(terminal.model_dump_json(indent=2))
    except Exception as e:
        print(f"\nERROR: {e}")
    finally:
        lm.write_trace(trace_path)
        print(f"\nTrace saved to {trace_path} ({len(lm.turns)} turns captured)")
