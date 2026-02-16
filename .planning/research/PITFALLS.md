# Domain Pitfalls

**Domain:** Hypermedia resourcespace and context-scoped tools added to existing async REPL (cortex) with AI agent
**Researched:** 2026-02-16
**Confidence:** HIGH -- grounded in direct codebase analysis of bae v6.0, verified against Manus context engineering lessons, JetBrains context management research, and LangChain context engineering docs

---

## Critical Pitfalls

Mistakes that cause the AI agent to malfunction, lose state, or require architectural rewrites.

---

### Pitfall 1: Navigation State Desync -- AI Loses Track of Where It Is

**What goes wrong:** The AI agent operates through a Claude CLI subprocess with session persistence (`ai.py:95`, `_session_id`). The resourcespace navigation state lives in Python (cortex's namespace or a dedicated state object). When the AI navigates to a resource (e.g., `cd /tasks/`), the Python side updates the current resource pointer, but the AI's understanding of "where I am" is only maintained through its conversation history in the Claude CLI session. If the conversation context drifts, gets truncated by the CLI's own context management, or if tool output is pruned aggressively, the AI acts on resource A while believing it is at resource B.

**Why it happens:** The AI's model of navigation state is reconstructed from conversation history -- it has no persistent state register. The current `_build_context()` (`ai.py:464-526`) sends a snapshot of the REPL namespace on each first message, but subsequent messages in the eval loop (`ai.py:117-186`) only send tool outputs and feedback. If the AI navigates three resources deep and then a pruned tool output omits the navigation breadcrumb, the AI's internal model diverges from the actual Python state.

This is compounded by the session architecture: `AI._send()` (`ai.py:188-243`) uses `--resume` for subsequent calls in a session, meaning the AI carries forward ALL prior conversation context from the Claude CLI session. But the resourcespace navigation state can change between AI invocations (Dzara navigates manually in PY mode). The AI resumes with stale navigation assumptions from its last conversation turn.

**Consequences:** The AI reads files from the wrong resource, writes to the wrong task, searches the wrong scope. Worse: operations succeed silently because the tools execute against the actual state (Python-side), not the AI's believed state. The AI reports "I updated task X" when it actually updated task Y because its context said it was in `/tasks/X` but the Python state had moved to `/tasks/Y`.

**Prevention:**
1. Every AI invocation MUST include the current resource path in the context preamble. Not just on first call -- on EVERY `_send()`. The resource path is cheap (one line) and eliminates drift. Modify `_build_context()` to always prepend `[Location: /tasks/active/]` or equivalent.
2. Tool outputs MUST echo the resource context they operated in: `"[/source/bae/repl/ai.py] Read 527 lines"` not just `"Read 527 lines"`. This keeps the AI grounded even after pruning.
3. Navigation operations must be idempotent and explicit. `cd /tasks/` is absolute (safe). `cd ../` is relative (dangerous -- AI must reconstruct parent from memory). Prefer absolute paths in the resource tree.
4. Add a `where` affordance that the AI can call at zero cost to re-anchor itself. Make it always available regardless of resource context.

**Detection:** In testing, have the AI navigate to resource A, then manually change the Python-side resource to B (simulating Dzara navigating in PY mode), then ask the AI to "read the current file." If it reads from B but says "reading from A," desync is occurring.

**Phase relevance:** Must be solved in the resourcespace core phase. This is the foundational invariant -- every other feature assumes the AI knows where it is.

---

### Pitfall 2: Tool Scoping Leak -- Operations Escape Resource Boundary

**What goes wrong:** Context-scoped tools change behavior based on navigation state. `<R:main.py>` should read from the current resource's scope (e.g., `/source/bae/repl/main.py` if navigated there). But the current tool implementations (`ai.py:271-345`) operate on raw filesystem paths. If the scoping layer wraps these tools but has gaps -- absolute paths bypass scoping, `../` traversal escapes the boundary, or a tool tag format isn't intercepted -- the AI operates outside the intended resource boundary.

**Why it happens:** The existing tool call system (`run_tool_calls`, `ai.py:393-456`) dispatches based on regex matching of tags in the AI's prose output. It matches `<R:path>`, `<W:path>content</W>`, etc. The tool functions (`_exec_read`, `_exec_write`, etc.) take raw string arguments and pass them directly to `Path()`. There is no path validation, no sandbox, no scope restriction.

When resourcespace scoping is added, it must intercept EVERY tool call and rewrite paths relative to the current resource. But the AI can emit any path format -- absolute (`/etc/passwd`), relative (`../../../etc/passwd`), home-relative (`~/secrets`). Each format needs different handling. Missing even one format creates a scoping leak.

The `_TOOL_TAG_RE` regex (`ai.py:38-41`) and `_WRITE_TAG_RE` (`ai.py:43-46`) parse tool arguments as opaque strings. The scoping layer must parse these BEFORE dispatch, not after. If scoping is implemented as a wrapper around `_exec_read` etc., it runs too late -- the AI has already specified the path.

**Consequences:** The AI reads or writes files outside the resource boundary. In the source resourcespace, this means editing files the resource doesn't own. In the memory resourcespace, this means accessing raw SQLite files instead of going through the SessionStore API. Security is not the primary concern (this is a local REPL), but correctness is -- the AI bypasses the resource's intended operations and produces results the resource doesn't know about.

**Prevention:**
1. Tool scoping MUST happen at the dispatch layer, not in individual tool functions. `run_tool_calls()` must resolve the current resource, then pass the resource-qualified path to the tool function. The tool function never sees the raw AI argument.
2. Each resource declares which tools it supports and how paths are resolved within its scope. The source resourcespace resolves paths relative to the project root. The memory resourcespace doesn't expose file paths at all -- it exposes session IDs and search queries.
3. Absolute paths that fall outside the current resource scope should be rejected with an explicit error message: `"Path /etc/passwd is outside /source/ scope. Navigate to homespace first."` Do NOT silently redirect or strip the path.
4. The `where` affordance should list available tools in the current scope, not all tools. If the memory resourcespace doesn't support `<W:>`, don't show it. This prevents the AI from attempting operations that would need scoping.
5. Test with adversarial paths: `../`, absolute, symlinks, home-relative. Every one must be caught.

**Detection:** From within the source resourcespace, have the AI attempt `<R:/etc/hosts>`. If it succeeds, scoping is leaking. From within the memory resourcespace, have the AI attempt `<W:~/.bae/store.db>`. If it succeeds, scoping is leaking.

**Phase relevance:** Must be solved in the resourcespace core phase alongside navigation. Tool dispatch modification is the mechanism by which scoping is enforced.

---

### Pitfall 3: Context Pruning Destroys Critical Information

**What goes wrong:** The v7.0 plan calls for pruning tool call history to I/O pairs with a 500 token cap per resourcespace output. This means large tool outputs (file reads, grep results, glob listings) are truncated to ~500 tokens. The AI makes decisions based on this truncated output. If the critical information was in the truncated portion -- a function definition at line 300 of a 500-line file, a grep match at position 95 out of 100 -- the AI proceeds without it and produces incorrect results.

**Why it happens:** The current system already has some truncation (`_MAX_TOOL_OUTPUT = 4000` in `ai.py:36`), but 4000 chars is generous enough that most single-file reads fit. Dropping to ~500 tokens (~2000 chars) is a 5x reduction. The pruning is applied uniformly -- it doesn't know which parts of the output the AI actually needed.

Research from JetBrains (2025) confirms this: "agent-generated context quickly turns into noise instead of being useful information" -- but the fix is NOT aggressive uniform truncation. The Manus team found that externalized memory (keeping full data in files, referencing by path) outperforms lossy compression. Aggressive pruning of tool outputs is the most dangerous form of context compression because tool outputs are the AI's ground truth -- if pruned incorrectly, the AI hallucinates to fill the gap.

The "lost in the middle" effect makes this worse: LLMs process tokens at the beginning and end of context more reliably than the middle. Pruned tool outputs that sit in the middle of a long conversation are doubly vulnerable -- both truncated AND poorly attended to.

**Consequences:** The AI generates code that references variables it didn't see in the truncated read. It proposes edits to line ranges it didn't actually examine. It reports "no matches found" when the matches were truncated from the grep output. These errors are silent and confident -- the AI has no way to know what it didn't see.

**Prevention:**
1. Prune I/O pairs to SUMMARIES, not truncated raw output. `"Read bae/repl/ai.py: 527 lines, defines AI class with __call__, _send, fill, choose_type, run_tool_calls"` is more useful than the first 500 tokens of the file. The summary should be generated at prune time, not by truncation.
2. Keep the FULL output available in externalized storage (the SessionStore already exists for this). The pruned context includes a reference: `"[full output in store, 527 lines]"`. The AI can re-read if needed.
3. Prune by recency, not by size. Keep the last N tool call pairs at full fidelity, summarize older ones. This leverages the LLM's stronger attention to recent context. The 500 token cap should apply to the SUMMARY of old calls, not to recent calls.
4. Never prune error outputs. If a tool call failed, the full error message must survive pruning. Manus's finding: "leaving wrong turns in the context is one of the most effective ways to improve agent behavior."
5. Test pruning impact: run the same task with and without pruning. If pruned runs fail where unpruned succeed, the pruning strategy is too aggressive.

**Detection:** Have the AI read a large file, then ask it about content that was in the file but beyond the 500-token cap. If it hallucinates or says "I don't see that," pruning destroyed critical information.

**Phase relevance:** Should be addressed in the tool call pruning phase (likely first phase). Getting this wrong poisons all subsequent resourcespace features because the AI operates on incomplete information.

---

### Pitfall 4: Context Poisoning from Stale Resource State

**What goes wrong:** The AI navigates to a resource, reads its state, performs operations, and accumulates context about that resource. Then Dzara modifies the resource state externally (edits a file in PY mode, updates a task from another tool, the resource's underlying data changes). The AI's context still contains the old state. It makes decisions based on stale data that is now actively wrong in context -- not just missing, but contradictory to reality.

**Why it happens:** Unlike missing information (which the AI can notice), stale information is indistinguishable from current information in the AI's context. The AI read the file 5 turns ago and "knows" its contents. It does not re-read because it "already has" the information. This is context poisoning -- false information in context that the model trusts and acts on.

The current architecture makes this likely because the REPL namespace is shared between the AI and Dzara (`shell.py:209`, `self.namespace: dict = seed()`). Dzara can modify any namespace object in PY mode while the AI is mid-conversation. The AI's Claude CLI session preserves conversation history including old tool outputs that no longer reflect reality.

**Consequences:** The AI proposes edits to a file based on a stale read, clobbering Dzara's recent changes. It reports task status based on a stale query. It navigates based on stale link lists, hitting 404-equivalent errors when resources have been deleted or moved.

**Prevention:**
1. Resource representations MUST include a version or timestamp. When the AI acts on a resource, the tool call includes the version. If the version has changed since the AI last read it, the operation fails with an explicit message: `"Resource /tasks/42 has changed since you last read it (your version: 3, current: 4). Re-read before modifying."`
2. Navigation affordances should be regenerated on each AI invocation, not cached from a previous turn. The `_build_context()` function already rebuilds context each time -- extend this pattern to resource affordances.
3. For the source resourcespace specifically, file modification times are cheap to check. Before applying an edit, compare `mtime` against the value when the file was last read in this AI session.
4. Consider a "stale context" warning when the AI references data from more than N turns ago. This is a heuristic, not a guarantee, but it prompts the AI to re-read.

**Detection:** Have the AI read a file, then modify the file in PY mode, then ask the AI to edit it. If the AI's edit is based on the old content (overwrites your changes), context poisoning is occurring.

**Phase relevance:** Must be considered in every resourcespace implementation. Each resource needs its own staleness detection mechanism. The source resourcespace uses mtime, the task resourcespace uses version numbers, the memory resourcespace uses session IDs.

---

## Moderate Pitfalls

---

### Pitfall 5: Tool Proliferation Degrades Agent Performance

**What goes wrong:** Each resourcespace introduces its own tools (navigate, list, read, write, search, tag, etc.). With 5-6 resourcespaces, each exposing 3-5 operations, the AI faces 15-30 tools. Research consistently shows that more tools make agents worse -- "each new tool dilutes the probability the agent selects the right one" (Manus team). The AI starts calling wrong tools, passing malformed parameters, or skipping tools entirely.

**Why it happens:** The current tool system is simple: 5 tools (R, W, E, G, Grep) with consistent single-argument syntax. The AI has near-100% accuracy with this set. Adding resourcespace-specific tools with different argument formats, different scoping rules, and context-dependent behavior significantly increases the decision space.

The Manus team's solution -- masking token logits to constrain available actions -- is not available in the Claude CLI subprocess architecture. The AI sees all tool descriptions in the system prompt regardless of context.

**Consequences:** The AI calls `task.create()` when it means `task.update()`. It passes a task ID to a memory search function. It attempts file operations inside the memory resourcespace. Error rates increase, requiring more eval loop iterations, consuming more tokens and time.

**Prevention:**
1. Follow Manus's principle: don't add/remove tools dynamically, instead scope what's VISIBLE. In the system prompt, only describe tools available in the current resource context. Since the system prompt is set on first call (`ai.py:206`), this means the system prompt must be resource-context-aware, or a context preamble must override the generic tool list.
2. Keep the tool count low by making tools polymorphic. `read` reads whatever the current resource exposes. `list` lists whatever the current resource contains. Same tool names, different behavior per resource. This keeps the AI's tool vocabulary at 5-7 verbs, not 30.
3. Avoid tool-per-resource-type. Do NOT create `task_create`, `task_update`, `memory_search`, `memory_tag` as separate tools. Instead, resources expose CRUD operations under consistent names.
4. The navigation affordance should list exactly what operations are valid, with one-line descriptions. This is the HATEOAS principle applied: the response tells the AI what it can do next.

**Detection:** Count tool call errors across a session. If error rate exceeds 10% of tool calls, tool proliferation is likely the cause. Compare error rates between sessions with fewer vs. more resourcespaces active.

**Phase relevance:** Architecture decision that must be settled in the resourcespace core phase before any specific resourcespaces are implemented. Changing the tool contract later requires updating all resourcespaces and retraining the AI's behavior.

---

### Pitfall 6: Homespace Navigation Affordances Become Stale

**What goes wrong:** The homespace (root resource) presents a list of available resourcespaces with navigation links and summaries (e.g., "3 active tasks", "last session 2h ago"). These summaries are computed when the homespace is rendered. If the AI caches this in its context and navigates away, then returns to the homespace, it sees the cached (stale) summaries unless the homespace is explicitly re-rendered.

**Why it happens:** The AI's conversation context is append-only within a Claude CLI session. When the AI first sees the homespace, those tokens persist in context. Returning to the homespace means the AI sees BOTH the old rendering (from earlier in context) AND a new rendering (from the current tool output). The "lost in the middle" effect means the old rendering (earlier in context) may be attended to less, but it is still present and can influence decisions.

**Consequences:** The AI navigates to a task resourcespace expecting 3 active tasks (from the old rendering) but finds 5 (one was added, one was completed and replaced). The mismatch causes confusion but not failure. More subtly, the AI may skip re-reading affordances because it "already knows" what is available, missing newly added resourcespaces or changed capabilities.

**Prevention:**
1. Homespace rendering should be lightweight and always fresh. Include a `[rendered at: HH:MM:SS]` timestamp so the AI can recognize stale vs. fresh.
2. When the AI navigates back to the homespace, the system should automatically generate a fresh rendering and inject it as a tool output, not rely on the AI requesting it.
3. Keep homespace summaries minimal (counts, not content). `"tasks: 3 active"` not `"tasks: fix login bug, add search, refactor DB"`. Less content means less stale detail to conflict with reality.

**Detection:** Navigate to homespace, note the summary, create a task in PY mode, navigate back to homespace. If the AI references the old task count, staleness is occurring.

---

### Pitfall 7: Cross-Resource Search Returns Unnavigable Results

**What goes wrong:** The search resourcespace performs cross-resourcespace search (e.g., searching "login" across tasks, memory, and source). Results include items from multiple resourcespaces. The AI needs to navigate to a specific result to act on it, but the search result format doesn't include navigation affordances. The AI knows a task exists but not how to get there. It attempts to construct a navigation path from memory, gets it wrong, and either errors or operates on the wrong resource.

**Why it happens:** Search results are a projection -- they extract matching content from various resources and present them in a flat list. But the resourcespace model requires navigation to act on resources. The gap between "I found it" and "I can reach it" is exactly the problem HATEOAS solves in web APIs -- but only if search results include hypermedia links.

**Consequences:** The AI finds a relevant task via search, then attempts `navigate /tasks/42` but the task's actual path is `navigate /tasks/active/42`. The navigation fails, the AI retries with variations, consuming eval loop iterations. Or worse, it falls back to operating on the search result text directly, bypassing the resource's tools.

**Prevention:**
1. Every search result MUST include a navigable path: `{ "match": "fix login bug", "resource": "/tasks/active/42", "navigate": "cd /tasks/active/42" }`. The AI can copy-paste the navigation command.
2. Search results should be actionable without navigation where possible. If the AI just needs to read a task, the search result should include enough detail. Only require navigation for write operations.
3. The search affordance should list what actions are available on each result inline: `"[navigate] [mark-done] [tag]"`. This prevents the AI from attempting unsupported operations on search results.

**Detection:** Search for a term that matches items in multiple resourcespaces. Ask the AI to act on a specific result. If it fails to navigate or takes more than 1 attempt, the affordances are insufficient.

---

### Pitfall 8: Session Boundary Breaks Resource Context

**What goes wrong:** The AI's Claude CLI session persists across REPL invocations via `--resume` (`ai.py:209`). But the resourcespace state is in-memory (Python objects in the REPL namespace). When Dzara restarts cortex, the AI resumes its Claude CLI session with full conversation history, including references to resources, navigation state, and cached tool outputs. But the Python-side resourcespace state has been reset to defaults (homespace). The AI thinks it is in `/tasks/active/42` because its last conversation turn was there. The Python state says it is at `/`.

**Why it happens:** The Claude CLI session is external to the REPL process. `AI._reset_session()` (`ai.py:245-248`) only fires on cancellation or lock errors, not on REPL restart. The session ID persists in the Claude CLI backend. The conversation history includes resource navigation that is no longer valid.

Actually, looking at the code more carefully: `AI.__init__()` generates a new `_session_id = str(uuid.uuid4())` on every instantiation (`ai.py:95`). So each `CortexShell()` creation generates a new AI session. The risk is within a single long-running session, not across restarts. However, if session persistence is added (v7.0 task resourcespace with cross-session persistence), old sessions may be resumed with stale resource context.

**Consequences:** Within a long session, if `AI._reset_session()` fires (cancellation, lock error), the new session starts fresh but the Python-side resource state is unchanged. The AI loses all conversation context (new session) but the resource state still points to wherever Dzara last navigated. The first AI invocation in the new session gets a `_build_context()` that includes the current resource location, which may be confusing without the prior conversation explaining how it got there.

**Prevention:**
1. When the AI session resets, also reset the resource navigation to homespace. The AI should start fresh in both conversation and navigation state.
2. The context preamble (first message of a new session) must include full resource state: where we are, what is available, what was the last action. This gives the AI a cold-start context that is self-contained.
3. For cross-session task persistence, tasks are stored in SQLite (SessionStore), not in conversation history. The AI re-queries tasks, not recalls them from memory. This makes session boundaries transparent to task management.
4. Add a `_on_session_reset` hook in the AI class that notifies the resourcespace to provide a full re-orientation prompt.

**Detection:** Trigger a session reset (cancel mid-conversation), then immediately ask the AI about the current resource state. If it is disoriented, the reset handler is insufficient.

---

### Pitfall 9: Pruning Removes Error Context That Prevents Retry Loops

**What goes wrong:** The pruning system (500 token cap) removes old tool call outputs, including error outputs. The AI encounters an error, the error is recorded in context, the AI adjusts its approach. Later, the error output is pruned. The AI encounters the same situation, has no memory of the previous failure, and repeats the exact same error. This creates retry loops that waste tokens and eval iterations.

**Why it happens:** Manus's key finding: "erasing failure removes evidence... leaving wrong turns in the context is one of the most effective ways to improve agent behavior." Uniform pruning treats error outputs the same as success outputs. But errors are disproportionately valuable because they constrain future behavior.

In the current eval loop (`ai.py:117-186`), errors from code execution are fed back as `feedback = f"[Output]\n{combined}"` (`ai.py:179`). This feedback is in the Claude CLI conversation history. When pruning is applied, old error feedback gets the same 500-token treatment as old success feedback. The error detail that would prevent repetition is lost.

**Consequences:** The AI attempts the same failing operation 3-4 times before the eval loop cap (`_max_eval_iters`) stops it. Each attempt consumes a Claude CLI call (API cost, latency). The user sees repeated failures with no learning.

**Prevention:**
1. Error outputs must be marked as non-prunable. Add metadata `{"prunable": false}` to error-type tool outputs and eval loop error feedback.
2. Alternatively, maintain a separate "lessons learned" context section that persists across pruning. When an error occurs, generate a one-line lesson: `"LESSON: <E:foo.py:1-10> fails when file doesn't exist -- check existence first."` This lesson survives pruning because it is in the persistent context, not in the prunable tool history.
3. Cap retry attempts per unique operation. If `<R:nonexistent.py>` fails twice, block further attempts and surface the error to Dzara rather than looping.

**Detection:** Cause a tool error (read a nonexistent file), let the AI recover, then force pruning of old context, then trigger the same situation. If the AI repeats the error, pruning removed critical context.

---

### Pitfall 10: Resource Persistence Corruption from Concurrent Access

**What goes wrong:** The task resourcespace stores tasks in SQLite (via SessionStore or a new table). The AI agent modifies tasks through tool calls (`task.update(42, status="done")`). Dzara modifies tasks through PY mode (`task.update(42, status="blocked")`). If both happen concurrently (AI is in an eval loop while Dzara types in PY mode), the last write wins. There is no conflict detection.

**Why it happens:** The `SessionStore` uses synchronous SQLite with per-call commits (`store.py:89`). The AI eval loop and PY mode dispatch both execute on the same event loop thread, so true concurrency (simultaneous writes) is impossible. However, logical concurrency is real: the AI reads a task, Dzara updates it, the AI writes based on stale read. This is a classic TOCTOU (time-of-check-to-time-of-use) race.

With the eval loop, the AI can perform multiple round-trips within a single user input cycle. Between AI turns (while waiting for Claude CLI response), Dzara can type and execute in PY mode. This creates an interleaving window.

**Consequences:** Task state is inconsistent. Dzara marks a task as blocked, the AI marks it as done (based on a stale read), the task ends up in an impossible state. The user sees confusing state that neither they nor the AI intended.

**Prevention:**
1. Use optimistic concurrency control. Each resource has a version number. Read operations return the version. Write operations include the version. If the version has changed since the read, the write fails: `"Conflict: task 42 was modified since you last read it (version 3 -> 4)."`
2. For the eval loop specifically, re-read resources before write operations. The AI should `read` then `write` in the same eval iteration, not rely on reads from previous iterations.
3. The resource API should expose `read-then-update` as an atomic operation where possible, avoiding the TOCTOU window entirely.
4. SQLite's WAL mode already provides atomic writes, but the conflict detection must happen at the application layer because the "conflict" is between the AI's stale context and the current DB state, not between two simultaneous SQL statements.

**Detection:** Start an AI task that reads and then modifies a resource. While the AI is waiting for the Claude CLI response, quickly modify the same resource in PY mode. Check whether the AI's subsequent write clobbers your change.

---

## Minor Pitfalls

---

### Pitfall 11: System Prompt Bloat from Resource Descriptions

**What goes wrong:** The system prompt (`ai_prompt.md`, 38 lines currently) needs to describe how resourcespace navigation works, what tools are available per resource, what affordances look like, and how to interpret navigation output. With 5-6 resourcespaces, each with its own tool documentation, the system prompt grows to hundreds of lines. Claude CLI charges per-token for the system prompt on every call, and a bloated system prompt pushes important information into the "lost in the middle" zone.

**Prevention:** Keep the system prompt minimal -- describe the navigation mechanics (5-10 lines) and let each resource's response include its own tool descriptions inline. The resource teaches the AI how to use it when the AI arrives, not upfront. This is the HATEOAS principle: discovery at interaction time, not documentation time.

### Pitfall 12: Affordance Format Inconsistency Across Resourcespaces

**What goes wrong:** If each resourcespace team (or each implementation phase) defines affordances differently -- one uses `[action: navigate /tasks/]`, another uses `-> /memory/ (explore)`, a third uses `cd /source/` -- the AI must learn multiple formats. Inconsistency increases error rates.

**Prevention:** Define an affordance format protocol ONCE in the resourcespace core phase. All resources must emit affordances in the same format. Suggested: `[verb: argument] -- description`. Examples: `[cd: /tasks/] -- navigate to tasks`, `[read: 42] -- read task 42`, `[search: "login"] -- search across all resources`. Test affordance parsing in isolation before building any specific resourcespace.

### Pitfall 13: Memory Resourcespace Exposes Raw Store Internals

**What goes wrong:** The memory resourcespace wraps `SessionStore` for AI exploration. The temptation is to expose `store.search()` and `store.recent()` directly, letting the AI write arbitrary FTS5 queries. But FTS5 syntax is finicky (requires MATCH, has its own query syntax), and the AI will write malformed queries that produce errors or incorrect results.

**Prevention:** The memory resourcespace should expose semantic operations (`search("login")`, `sessions()`, `tag(session_id, "important")`) not raw store methods. The resourcespace translates semantic operations to store queries internally. The AI never writes SQL or FTS5 syntax.

### Pitfall 14: eval Loop Iteration Inflation from Navigation

**What goes wrong:** Every navigation step is an eval loop iteration (AI says "cd /tasks/", tool responds with resource representation, AI processes). A workflow that requires navigating to homespace, then tasks, then a specific task, then back to homespace, then to source -- that is 5 navigation turns before any real work happens. With `_max_eval_iters` constraining total iterations, navigation overhead steals iterations from productive work.

**Prevention:** Navigation should be O(1), not O(depth). `cd /tasks/active/42` should work as a single step, not require `cd /tasks/` then `cd active/` then `cd 42/`. The resource tree should support absolute paths. Also consider whether navigation turns should count against the eval loop iteration limit or be tracked separately.

---

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|---------------|------------|
| Tool call pruning | #3 (critical info destruction), #9 (error context removal) | Summary-based pruning not truncation, mark errors as non-prunable, keep full output in store |
| Resourcespace core | #1 (navigation desync), #2 (tool scoping leak), #5 (tool proliferation), #12 (affordance inconsistency) | Location in every context preamble, scope at dispatch layer, polymorphic tools not per-resource tools, define affordance protocol once |
| Source resourcespace | #2 (path escaping scope), #4 (stale file reads) | Path validation against resource boundary, mtime checks before writes |
| Task resourcespace | #4 (stale task state), #10 (concurrent access corruption), #8 (session boundary reset) | Optimistic versioning, re-read before write, store in SQLite not conversation |
| Memory resourcespace | #13 (raw store exposure), #6 (stale summaries) | Semantic API not raw store, always-fresh affordances |
| Search resourcespace | #7 (unnavigable results) | Include navigable paths in every search result |
| Cross-cutting | #4 (context poisoning), #14 (eval iteration inflation) | Version/timestamp on all resources, absolute path navigation |

---

## Evidence Base

| Finding | Source | Confidence |
|---------|--------|------------|
| `_build_context()` only runs on first prompt, not on subsequent eval loop feedback | Direct code: `ai.py:106-108` -- context is prepended to `full_prompt` before first `_send()` only | HIGH |
| Tool functions take raw paths with no validation | Direct code: `ai.py:271-345` -- `Path(arg)` with no scope check | HIGH |
| `_MAX_TOOL_OUTPUT` is 4000 chars; 500-token cap is ~5x reduction | Direct code: `ai.py:36`; token estimate ~4 chars/token | HIGH |
| Claude CLI session persists via `--resume` with full conversation history | Direct code: `ai.py:209` | HIGH |
| AI session resets on cancellation but not on resource state change | Direct code: `ai.py:245-248` | HIGH |
| Shared namespace between AI and user enables concurrent modification | Direct code: `shell.py:209`, `ai.py:89` | HIGH |
| SessionStore commits synchronously per write | Direct code: `store.py:89` | HIGH |
| Dynamic tool loading destroys KV cache and confuses models | [Manus context engineering lessons](https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus) | HIGH |
| Leaving failed actions visible improves agent behavior | [Manus context engineering lessons](https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus) | HIGH |
| More tools degrade agent selection accuracy | [Manus context engineering](https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus), [LangChain context engineering docs](https://docs.langchain.com/oss/python/langchain/context-engineering) | HIGH |
| Agent context bloat does not proportionally improve performance | [JetBrains context management research](https://blog.jetbrains.com/research/2025/12/efficient-context-management/) | HIGH |
| LLMs attend poorly to middle-of-context information | [JetBrains research](https://blog.jetbrains.com/research/2025/12/efficient-context-management/), [dbreunig.com](https://www.dbreunig.com/2025/06/26/how-to-fix-your-context.html) | HIGH |
| State corruption from variable passing failures in multi-step agents | [Nanonets AI agent state management guide](https://nanonets.com/blog/ai-agents-state-management-guide-2026/) | MEDIUM |
| Externalized memory (filesystem as context store) outperforms lossy compression | [Manus context engineering lessons](https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus) | HIGH |
| HATEOAS enables dynamic discoverability, reduces navigation ambiguity | [Nordic APIs HATEOAS for AI](https://nordicapis.com/hateoas-the-api-design-style-that-was-waiting-for-ai/) | MEDIUM |
| Summarization-using agents ran ~15% longer without solving more problems | [JetBrains research](https://blog.jetbrains.com/research/2025/12/efficient-context-management/) | MEDIUM |

---

*Pitfalls researched: 2026-02-16 for v7.0 Hypermedia Resourcespace milestone*
*Previous version: v6.0 Graph Runtime pitfalls (2026-02-15) -- that file covered concurrent graph execution, input gates, subprocess orphans, and event loop starvation. This file covers hypermedia navigation, context-scoped tools, pruning, and resource persistence.*
