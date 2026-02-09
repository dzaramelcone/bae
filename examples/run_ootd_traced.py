"""Run ootd.py with real Claude CLI and capture prompt/response traces."""

from __future__ import annotations

import time
from pathlib import Path

from examples.ootd import IsTheUserGettingDressed, graph
from bae.lm import ClaudeCLIBackend

TRACES_DIR = Path(__file__).parent.parent / "tests" / "traces"


class TracingClaudeCLI(ClaudeCLIBackend):
    """ClaudeCLIBackend that captures prompts, responses, and timestamps."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.turns: list[dict] = []
        self._turn_count = 0
        self._t0 = time.monotonic()

    async def _run_cli_json(self, prompt: str, schema: dict) -> dict | None:
        self._turn_count += 1
        turn_id = self._turn_count
        t_start = time.monotonic() - self._t0
        print(f"  Turn {turn_id}: +{t_start:.2f}s sending prompt ({len(prompt)} chars)...")
        response = await super()._run_cli_json(prompt, schema)
        t_end = time.monotonic() - self._t0
        print(f"  Turn {turn_id}: +{t_end:.2f}s got response ({t_end - t_start:.2f}s)")
        self.turns.append({
            "prompt": prompt,
            "schema": schema,
            "response": response,
            "t_start": round(t_start, 3),
            "t_end": round(t_end, 3),
        })
        return response

    def write_trace(self, path: Path) -> None:
        import json

        path.parent.mkdir(parents=True, exist_ok=True)
        lines: list[str] = []

        for i, turn in enumerate(self.turns, 1):
            t_start = turn["t_start"]
            t_end = turn["t_end"]
            duration = t_end - t_start
            lines.append(f"{'=' * 72}")
            lines.append(f"TURN {i}  [{t_start:.3f}s → {t_end:.3f}s  ({duration:.3f}s)]")
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
    print("Expected flow:")
    print("  1. choose_type: AnticipateUsersDay | No")
    print("  2. fill: AnticipateUsersDay (weather/schedule/location deps + vibe)")
    print("  3. fill: InferUserBackground  ┐ (concurrent Node-as-Dep)")
    print("  4. fill: InferUserPersonality  ┘")
    print("  5. fill: GenerateWardrobe (chained Node-as-Dep)")
    print("  6. fill: RecommendOOTD (final output)")
    print()

    try:
        result = graph.run(
            IsTheUserGettingDressed(
                user_message="ugh i just got up",
                user_info={"name": "Dzara", "gender": "woman"},
            ),
            lm=lm,
        )
        print("\n── Result ──")
        terminal = result.trace[-1]
        print(terminal.model_dump_json(indent=2))

        print("\n── Trace ──")
        for i, node in enumerate(result.trace):
            print(f"  {i}: {node.__class__.__name__}")

        print("\n── Timing ──")
        for i, turn in enumerate(lm.turns, 1):
            t_s = turn["t_start"]
            t_e = turn["t_end"]
            # Extract instruction from prompt (last line)
            prompt_lines = turn["prompt"].strip().splitlines()
            instruction = prompt_lines[-1] if prompt_lines else "?"
            print(f"  Turn {i}: {t_s:6.2f}s → {t_e:6.2f}s  ({t_e - t_s:.2f}s)  {instruction[:60]}")

    except Exception as e:
        import traceback
        print(f"\nERROR: {e}")
        traceback.print_exc()
    finally:
        lm.write_trace(trace_path)
        print(f"\nTrace saved to {trace_path} ({len(lm.turns)} turns captured)")
