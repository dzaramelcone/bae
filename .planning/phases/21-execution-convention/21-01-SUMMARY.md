# Plan 21-01 Summary: Eval Harness — Convention Selection

## Result

**Winner: xml_tag** — `<run>code</run>` for executable, regular fences for illustrative.

Selected by Dzara after reviewing full 6-convention eval results.

## What Was Built

Pytest eval harness testing 6 code-block convention candidates across 3 Claude tiers (Opus, Sonnet, Haiku) with 5 scenarios x 3 repetitions = 270 total test cases.

### Conventions Tested

| Convention | Syntax | Convention Compliance |
|---|---|---|
| **xml_tag** | `<run>code</run>` | **100%** |
| fence_annotation | `` ```python:exec `` | 97.2% |
| wrapper_marker | `<exec>```python```</exec>` | 94.4% |
| json_tool | `{"execute": "code"}` | 94.4% |
| yaml_meta | `# %% exec` comment | 94.4% |
| inverse | `python:example` for illustrative | 83.3% |

Convention compliance measured excluding the ambiguous `no_code` scenario ("What is a Graph in bae?") where all conventions fail equally — models choose to run code to inspect rather than answer from knowledge. This is a model judgment call, not convention compliance.

### Key Findings

1. xml_tag is the only convention with 0 convention-specific failures
2. inverse confirms the silent failure prediction — bare fences leak execution
3. json_tool has practical issues with multiline code needing `\n` escaping
4. Lean prompts (2 fewshot examples) work as well as verbose (5 examples) for convention compliance
5. The NL-only fewshot example matters — without it, models use code for conceptual questions

## Self-Check: PASSED

- [x] All 6 conventions tested across Opus, Sonnet, and Haiku
- [x] Each combination ran 3 times for confidence
- [x] Results clearly show xml_tag achieves 100% convention compliance
- [x] Eval uses identical prompts across conventions
- [x] Convention winner confirmed by Dzara

## Key Files

### key-files.created
- `evals/__init__.py` — Package init
- `evals/conftest.py` — e2e marker registration
- `evals/prompts.py` — 6 system prompts, regexes, validation, eval_send
- `evals/test_convention.py` — Parametrized 270-test matrix

### key-files.modified
None (new directory)

## Decisions

- **xml_tag selected over fence_annotation**: Despite fence_annotation having syntax highlighting, xml_tag's 100% compliance and clean separation (no fence = no execution ambiguity) won out.
- **Lean prompts validated**: 2 fewshot examples sufficient for convention compliance. Production prompt should add NL-only example to prevent unnecessary code execution on conceptual questions.

## Data Artifacts

- `evals/results_xml.txt` — xml_tag raw results
- `evals/results_fence.txt` — fence_annotation raw results
- `evals/results_wrapper.txt` — wrapper_marker raw results
- `evals/results_json.txt` — json_tool raw results
- `evals/results_yaml.txt` — yaml_meta raw results
- `evals/results_inverse.txt` — inverse raw results
