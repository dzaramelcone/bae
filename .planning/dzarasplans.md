  for next phase, we should begin to work on guiding llms through implementing bae graphs.
  agents should be taught that the graph should resemble a conversational flow. a node
  needs to also be added that waits for a user response through some stdin or what have
  you. maybe we can model conversational sessions as bae graphs to begin mapping/exploring
  structured work. LLMs will need to understand that they can call graphs to get
  structured results, just like invoking any other tool call.

  we will need to begin to structure the REPL ns as set of steps/nodes (almost like a b-tree
  of tool calls) that prompt the model to explore it based on what we are trying to do.
  e.g. instead of session and toolbar it should be "CONTINUE_HERE", "PENDING_TASKS",
  "SEARCH_HISTORY", etc.

  we're backed up by feature adds so it would be good to switch over to bae and begin to
  use it to multiplex feature work. therefore getting agentic tool calls functioning is
  our current highest precedence/priority! we want to get a gsd-like structure working in
  bae as soon as we can. this will likely take the form of a bae graph that models the
  engineering method.

  bae is spammy because agentic toolcalls are spammy asf.
  
   Feature: Unified LM Session Management

  Requirements (clear)

  1. Graphs need multi-turn LM calls — some nodes require 40-100+ tool calls (web
  crawling, source grepping, automated RAG) before producing output
  2. Tool calls are Python execution — <run> blocks with <R:>, <G:> etc. already
  work, not a limitation
  3. Not every node needs structured output — some nodes produce free-text context
  dumps, others produce typed fields
  4. The graph runtime and REPL currently use completely separate LLM session
  management — they need to converge into one system
  5. extract_executable and the eval loop logic are shared concerns — both
  consumers need them

  Open Design Questions

  1. Where does node LM behavior get configured? Node class config? Graph-level?
  Backend selection? Per-field annotation?
  2. How do multi-turn graph nodes interact with cortex? Do they go through
  ChannelRouter/TaskManager, or should graphs work standalone without cortex?
  3. Session ownership — does each node get its own Claude CLI session, or does a
  graph run share one session across nodes?
  4. What's the right boundary between "graph infrastructure" and "REPL
  infrastructure"? Graphs should be portable. How much cortex coupling is
  acceptable?
  5. How does a node declare "I don't need structured output validation"? And what
  does fill() return in that case — raw string? Partially filled node?
  6. Does the agentic research happen inside fill(), inside a dep, or as a distinct
   node execution phase?


    python objects with consistent interface would be good. essentially like
  CRUD ops. these are the main REPL objects. so it should be navigable with
  labels. someone with no familiary should be able to immediately get up to
  speed and be guided through the possible tools and operations just from the
   names. e.g.: START_HERE in the ns containing a list of outstanding tasks
  and some tools by category. tools with tags so the agent can follow
  breadcrumbs that lead it into the correct use patterns for whatever it is
  that its trying to do. the helps and strings for these objects should
  probably contain hypermedia-like objects such as ampersand directives to
  goad claude to interact with them depending on some particular workflow or
  state being activated.


  # GSD → Bae Graph Translation

## GSD System Overview

30 workflows in `~/.claude/get-shit-done/workflows/`, 11 specialized agent types in `~/.claude/agents/`.

## All Workflows

### Core Project Lifecycle
1. **new-project.md** — questioning → research (4 parallel agents) → requirements → roadmap
2. **new-milestone.md** — brownfield milestone creation (similar flow for existing projects)
3. **resume-project.md** — session restoration with state reconstruction
4. **progress.md** — status check + intelligent routing to next action
5. **complete-milestone.md** — archive milestone, evolve PROJECT.md, create git tag

### Phase Management
6. **add-phase.md** — append new integer phase to roadmap
7. **insert-phase.md** — add decimal phase (e.g., 5.1) for urgent mid-milestone work
8. **remove-phase.md** — delete future phase and renumber subsequent phases
9. **discuss-phase.md** — extract user vision/decisions → CONTEXT.md
10. **list-phase-assumptions.md** — surface Claude's assumptions before planning
11. **research-phase.md** — comprehensive ecosystem research → RESEARCH.md
12. **plan-phase.md** — create executable PLAN.md files (orchestrates researcher, planner, checker with 3-iteration revision loop)
13. **execute-phase.md** — wave-based parallel execution orchestrator (spawns executors per plan)
14. **execute-plan.md** — single plan execution with TDD, deviation rules, checkpoints

### Quality & Verification
15. **verify-phase.md** — goal-backward verification (truths → artifacts → wiring)
16. **verify-work.md** — conversational UAT → auto-diagnosis → auto-plan fixes
17. **diagnose-issues.md** — parallel debug agents (spawned from verify-work)
18. **audit-milestone.md** — aggregate phase verifications + integration checker

### Gap Closure
19. **plan-milestone-gaps.md** — create phases to close audit gaps

### Discovery
20. **discovery-phase.md** — 3-level discovery (quick verify, standard, deep dive)
21. **map-codebase.md** — 4 parallel mapper agents → 7 codebase docs

### Utility & Management
22. **add-todo.md** — capture idea as structured todo
23. **check-todos.md** — review/select/act on pending todos
24. **pause-work.md** — create `.continue-here.md` handoff
25. **quick.md** — ad-hoc tasks (planner + executor, no research/verifier)
26. **settings.md** — configure workflow toggles
27. **set-profile.md** — quick model profile switch
28. **update.md** — update GSD with changelog preview
29. **help.md** — display command reference
30. **transition.md** — phase-to-phase transition

## Agent Types

### Execution
- **gsd-executor** — executes PLAN.md, handles TDD/checkpoints/deviations, creates SUMMARY.md
- **gsd-debugger** — scientific method debugging with persistent DEBUG.md state

### Planning
- **gsd-planner** — creates PLAN.md files, dependency graphs, revision mode
- **gsd-plan-checker** — verifies plans achieve phase goals (spawned in revision loop)

### Research
- **gsd-phase-researcher** — phase-specific research → RESEARCH.md
- **gsd-project-researcher** — project-level research (4 dimensions: Stack, Features, Architecture, Pitfalls)
- **gsd-research-synthesizer** — combines 4 research outputs → SUMMARY.md
- **gsd-codebase-mapper** — maps existing codebases (4 focus areas: tech, arch, quality, concerns)

### Analysis
- **gsd-verifier** — goal-backward verification (3 levels: exists, substantive, wired)
- **gsd-integration-checker** — cross-phase wiring verification
- **gsd-roadmapper** — derives phases from requirements, maps requirements to phases

## Orchestration Patterns

### Parallel Spawning (independent work)
- `new-project` → 4 **gsd-project-researcher** agents (Stack, Features, Architecture, Pitfalls)
- `map-codebase` → 4 **gsd-codebase-mapper** agents (tech, arch, quality, concerns)
- `diagnose-issues` → N **gsd-debugger** agents (one per UAT gap)
- `execute-phase` → M **gsd-executor** agents per wave (parallel plans in wave)

### Sequential with Revision Loops
- `plan-phase` → researcher → planner → checker → (if issues) planner revision → checker (max 3)
- `verify-work` → (if gaps) debugger (parallel) → planner (gap mode) → checker → (revision loop)

### Major Cycles
1. **Phase Planning Revision Loop** (max 3) — planner → checker → revise → re-check
2. **GAP Closure Cycle** — verify → diagnose → plan gaps → execute gaps → re-verify
3. **Milestone Audit Loop** — execute phases → audit → plan gap phases → execute → re-audit
4. **Debug Session Continuation** — DEBUG.md survives /clear, resume from exact state

### User Gates
- **checkpoint:human-verify** (90%) — user confirms automated work
- **checkpoint:decision** (9%) — user makes implementation choice
- **checkpoint:human-action** (1%) — user performs manual action

## Shared State

### Persistent Files
- **STATE.md** — living memory (position, decisions, issues, session continuity)
- **PROJECT.md** — vision, requirements (Validated/Active/Out of Scope), key decisions
- **ROADMAP.md** — current milestone phases and objectives
- **REQUIREMENTS.md** — scoped requirements with REQ-IDs and traceability
- **config.json** — workflow mode (yolo/interactive), toggles, model profile

### Phase Artifacts (in `.planning/phases/`)
- **CONTEXT.md** — user vision from discuss-phase (locked decisions)
- **RESEARCH.md** — phase-specific research
- **DISCOVERY.md** — discovery outputs (3 levels)
- **PLAN.md** — executable prompts (frontmatter: wave, depends_on, must_haves)
- **SUMMARY.md** — execution results (files, decisions, deviations, commits)
- **VERIFICATION.md** — goal-backward verification report (gaps in YAML)
- **UAT.md** — user acceptance testing state
- **DEBUG.md** — debug session state (in `.planning/debug/`)

## Key Innovations to Preserve
1. **Goal-backward verification** — start from outcome, derive truths → artifacts → wiring
2. **Deviation rules** — auto-fix bugs, auto-add missing critical, ask about architectural changes
3. **Wave-based parallel execution** — dependency graph → wave assignment → parallel per wave
4. **Persistent debug sessions** — DEBUG.md survives context resets
5. **Conversational UAT** — one test at a time, infer severity, auto-diagnose gaps
6. **Context efficiency** — orchestrators delegate to fresh-context agents, ~10-15% usage

## Translation Status

| Workflow | Status | Bae Module |
|---|---|---|
| new-project | DONE | `bae/work/new_project.py` |
| quick | sketched | `bae/work/quick.py` |
| plan-phase | sketched | `bae/work/plan_phase.py` |
| map-codebase | sketched | `bae/work/map_codebase.py` |
| execute-phase | sketched | `bae/work/execute_phase.py` |
| all others | not started | — |

## Translation Order

### Tier 1 — Simple linear flows
- `quick`, `add-phase`, `remove-phase`, `insert-phase`, `add-todo`, `check-todos`, `pause-work`, `resume-work`, `progress`

### Tier 2 — Revision loops + agent spawning
- `plan-phase`, `map-codebase`, `discuss-phase`

### Tier 3 — Wave execution + checkpoints
- `execute-phase`, `execute-plan`

### Tier 4 — Verification + gap closure
- `verify-work`, `audit-milestone`, `complete-milestone`

### Tier 5 — Composition (workflows calling workflows)
- `new-milestone`, `plan-milestone-gaps`, `diagnose-issues`


