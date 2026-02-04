# Pitfalls Research

**Domain:** DSPy Framework Integration for LLM Agents
**Researched:** 2026-02-04
**Confidence:** HIGH

## Critical Pitfalls

### Pitfall 1: Adapter Format Mismatch

**What goes wrong:**
Choosing the wrong adapter causes LLM parsing failures. ChatAdapter (default) works universally but generates more tokens and can confuse smaller models with format overhead. JSONAdapter has lower latency but requires models with `response_format` support - using it with unsupported models causes silent failures or parsing errors.

**Why it happens:**
Developers pick adapters based on performance metrics without checking model compatibility. JSONAdapter looks attractive for latency but the `response_format` requirement isn't obvious until deployment.

**How to avoid:**
- Start with ChatAdapter (default) for all models
- Only switch to JSONAdapter after confirming model supports `response_format` (OpenAI models, some Azure deployments)
- Validate adapter choice in tests with actual model calls, not mocks
- Document adapter selection rationale in configuration

**Warning signs:**
- Intermittent parsing failures that disappear with different models
- Error logs mentioning "format" or "response_format"
- Higher token usage than expected with ChatAdapter
- Parsing failures only with specific model providers

**Phase to address:**
Phase 1 (Foundation) - Establish adapter selection as part of model configuration. Create validation tests that catch adapter/model mismatches.

---

### Pitfall 2: Async/Threading Confusion

**What goes wrong:**
DSPy 2.5.30+ has threading issues where using Python threading with predictors causes errors. `dspy.asyncify` doesn't allow easy async inside forward methods - you can't use `await` directly. Underlying LLM calls remain synchronous even with async modules, and async can run sequentially instead of in parallel without warning.

**Why it happens:**
Developers assume DSPy's async support is complete and try to use `async/await` patterns familiar from other frameworks. The documentation mentions async support but doesn't clearly explain the limitations.

**How to avoid:**
- Start with synchronous interface (aligns with DSPy best practices)
- Don't use `dspy.asyncify` in early phases - it doesn't provide real parallelism
- If async is required, validate actual concurrency with timing tests
- Avoid Python threading with DSPy predictors in 2.5.30+
- For true parallelism, use process-based concurrency or multiple DSPy instances

**Warning signs:**
- Threading errors in logs when using predictors
- Async code running slower than sync equivalent
- Can't use `await` in forward methods despite async decorator
- Sequential execution despite async/await syntax

**Phase to address:**
Phase 1 (Foundation) - Build with sync-only interface. Phase 3+ (if needed) - Add async after core functionality is proven, with explicit concurrency testing.

---

### Pitfall 3: Premature Signature Optimization

**What goes wrong:**
Developers over-engineer signatures by manually tuning keywords, field names, and prompt fragments when simple class names would work better. DSPy docs explicitly warn: "don't prematurely tune the keywords of your signature by hand. The DSPy optimizers will likely do a better job."

**Why it happens:**
Engineers bring prompt engineering habits from raw LLM work. The urge to "improve" signatures before seeing them fail is strong, especially when you can see the generated prompts.

**How to avoid:**
- Start with minimal signatures: simple class names, basic field descriptions
- Let DSPy optimizers handle keyword tuning after baseline works
- Only hand-tune after measuring specific failure modes
- Establish rule: no signature changes without failing test case demonstrating need

**Warning signs:**
- Complex signature hierarchies before basic functionality works
- Long discussions about "perfect" field names during initial development
- Signatures with extensive keyword arguments before any optimization runs
- Changing signatures without corresponding test failures

**Phase to address:**
Phase 1 (Foundation) - Establish minimal signature convention. Phase 2 (Optimization) - Use DSPy optimizers instead of hand-tuning.

---

### Pitfall 4: Statelessness Surprise

**What goes wrong:**
DSPy is stateless by default - context must be manually managed via retrievers or chained prompts. It's not designed for multi-agent LM pipelines with persistent state. Developers expecting framework-managed conversation history or agent state will build broken systems.

**Why it happens:**
Other LLM frameworks (LangChain, LangGraph) manage state automatically. DSPy's stateless design is architecturally different but not immediately obvious.

**How to avoid:**
- Design explicit state management from the start
- For Bae's two-step decide flow (pick type, then fill), chain prompts or use custom state container
- Don't expect DSPy to remember previous interactions
- Consider hybrid approach: DSPy for LM backbone, external state management

**Warning signs:**
- Expecting context to persist between module calls
- Surprised when agent "forgets" previous decisions
- Looking for built-in conversation history features
- Trying to implement multi-turn interactions without explicit state passing

**Phase to address:**
Phase 1 (Foundation) - Design state management for two-step decide flow. Phase 2+ - Integrate with external state if multi-turn interactions needed.

---

### Pitfall 5: Integration Complexity Underestimation

**What goes wrong:**
DSPy enhances LM backbone but doesn't replace orchestration frameworks. Complex workflows require hybrid approaches (DSPy + LangGraph recommended). Custom deployment pipelines needed for optimized prompts. Developers underestimate integration effort.

**Why it happens:**
DSPy marketing emphasizes "replacing prompt engineering" which sounds like it handles everything. The need for orchestration frameworks, deployment infrastructure, and state management isn't obvious until implementation.

**How to avoid:**
- Plan for DSPy as LM layer, not complete solution
- Budget time for integration with Bae's existing make/decide abstraction
- Expect to build custom deployment for optimized prompts
- Evaluate if make/decide abstraction becomes redundant (avoid duplicate layers)

**Warning signs:**
- Assuming DSPy will handle all agent coordination
- No plan for deploying optimized prompts
- Duplicate abstraction layers (make/decide + DSPy modules doing same thing)
- Underestimating time for "integration work"

**Phase to address:**
Phase 1 (Foundation) - Establish integration boundaries with Bae architecture. Phase 2-3 - Refactor redundant abstractions if make/decide is superseded.

---

### Pitfall 6: Two-Step Decide Validation Gap

**What goes wrong:**
Bae's two-step decide pattern (pick type, then fill) may not align naturally with DSPy's signature-based approach. The pattern needs explicit validation with DSPy before assuming it works.

**Why it happens:**
Existing architecture patterns don't always map cleanly to new frameworks. The two-step flow could become one signature with typed outputs, or two chained modules, or need restructuring entirely.

**How to avoid:**
- Prototype two-step decide with DSPy early (Phase 1)
- Validate both approaches: single signature with typed fields vs. chained modules
- Measure which approach produces better results and clearer code
- Be willing to restructure decide pattern if DSPy suggests better architecture

**Warning signs:**
- Forcing two-step pattern without testing if DSPy supports it naturally
- Awkward code trying to fit square peg in round hole
- Better solutions exist but we're preserving old pattern for its own sake

**Phase to address:**
Phase 1 (Foundation) - Explicit validation of two-step decide pattern. Include in early prototypes and make architectural decision based on evidence.

---

## Technical Debt Patterns

Shortcuts that seem reasonable but create long-term problems.

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Skip adapter validation tests | Faster initial development | Silent failures with unsupported models | Never - validation is cheap, debugging is expensive |
| Use async without concurrency tests | Feels modern and scalable | Sequential execution masquerading as parallel | Never - timing tests are trivial |
| Hand-tune signatures before baseline | Feels productive, addresses obvious issues | Harder to optimize, unclear which changes help | Only after failing test demonstrates need |
| Build custom state management before trying stateless | Familiar pattern from other frameworks | Premature complexity, may not be needed | After Phase 1 proves stateless insufficient |
| Keep make/decide abstraction alongside DSPy modules | Preserves existing code | Duplicate logic, harder to maintain | During Phase 1 transition only, must refactor by Phase 2 |

## Integration Gotchas

Common mistakes when connecting DSPy to external systems.

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| Model providers | Assuming all providers support same adapters | Validate adapter compatibility per provider, default to ChatAdapter |
| Existing Bae architecture | Wrapping DSPy modules inside make/decide without evaluating redundancy | Prototype both approaches, remove redundant layer |
| Async code | Using `dspy.asyncify` expecting true parallelism | Start sync-only, add real async (process-based) only if proven necessary |
| Optimized prompts | No deployment plan for optimizer outputs | Design prompt versioning/deployment before running optimizers |
| State management | Expecting DSPy to manage multi-turn context | Explicit state passing or external state store from Phase 1 |

## Performance Traps

Patterns that work at small scale but fail as usage grows.

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| ChatAdapter token bloat | Works fine in dev, cost/latency issues in production | Profile token usage early, switch to JSONAdapter if model supports it | 1k+ requests/day |
| Sequential async | Single user fast enough, concurrency doesn't scale | Timing tests that measure parallel throughput, not just single-request latency | 10+ concurrent users |
| Unoptimized signatures | Acceptable accuracy in testing, poor production results | Plan for DSPy optimizer runs before production | Production traffic patterns differ from tests |
| Stateless context re-passing | Fine for 2-3 turn conversations, slow for longer | Design for explicit state truncation/summarization | Conversations >5 turns |

## Security Mistakes

Domain-specific security issues beyond general web security.

| Mistake | Risk | Prevention |
|---------|------|------------|
| Prompt injection in signatures | User input escapes into system prompts | Input validation, DSPy's signature field types, test with adversarial inputs |
| Exposing optimized prompts | Reveals system design/capabilities to users | Deploy prompts server-side, never expose to client |
| Unvalidated model outputs | LLM generates malicious code/commands | Parse outputs with strict schemas, validate before execution |
| Model provider key leakage | DSPy config exposed in logs/errors | Separate secrets management, sanitize error messages |

## UX Pitfalls

Common user experience mistakes in this domain.

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Inconsistent output formats | User sees raw JSON sometimes, formatted text other times | Enforce output formatting layer on all LLM responses |
| No loading states during LLM calls | Appears frozen, users click multiple times | Explicit loading UI for all DSPy module calls |
| Error messages expose internal details | Confusing errors like "signature field mismatch" | User-friendly error wrapping for DSPy errors |
| Non-deterministic behavior | Same input gives different outputs, users lose trust | Use temperature=0 for consistent flows, or explain variability |

## "Looks Done But Isn't" Checklist

Things that appear complete but are missing critical pieces.

- [ ] **Adapter selection:** Often missing model compatibility validation — verify tests include actual calls with target models
- [ ] **Async implementation:** Often missing concurrency timing tests — verify parallel execution actually happens
- [ ] **Signature design:** Often missing optimizer integration plan — verify signatures are optimization-ready
- [ ] **State management:** Often missing multi-turn conversation testing — verify state persists across interactions
- [ ] **Error handling:** Often missing DSPy-specific error wrapping — verify user-facing errors are comprehensible
- [ ] **Integration with Bae:** Often missing redundancy evaluation — verify make/decide + DSPy aren't duplicating logic

## Recovery Strategies

When pitfalls occur despite prevention, how to recover.

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Adapter mismatch | LOW | Switch adapter in config, add validation test, no code changes |
| Async threading errors | MEDIUM | Revert to sync implementation, costs development time but no architectural impact |
| Over-engineered signatures | MEDIUM | Strip to minimal version, re-run tests, let optimizer handle tuning |
| Stateless surprise | HIGH | Requires architectural changes to add state management, may impact multiple modules |
| Integration complexity | HIGH | May require hybrid framework approach (DSPy + orchestration), significant refactoring |
| Two-step decide pattern broken | MEDIUM | Restructure to single signature or explicit chaining, test-driven refactor |

## Pitfall-to-Phase Mapping

How roadmap phases should address these pitfalls.

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Adapter mismatch | Phase 1 | Validation tests pass with all target model providers |
| Async/threading confusion | Phase 1 | No async used, or timing tests prove actual concurrency |
| Premature optimization | Phase 1-2 | Signatures remain minimal until optimizer runs in Phase 2 |
| Statelessness surprise | Phase 1 | Explicit state management design documented and tested |
| Integration complexity | Phase 1 | Integration boundaries clear, redundancy evaluated |
| Two-step decide validation | Phase 1 | Prototype demonstrates pattern works with DSPy |

## Sources

- DSPy 2.5.30+ release notes (threading issues)
- DSPy documentation (adapter types, async limitations, optimization warnings)
- Community discussions (statelessness, integration patterns)
- Bae architecture analysis (two-step decide, make/decide abstraction)
- DSPy + LangGraph integration recommendations (hybrid approach guidance)

---
*Pitfalls research for: DSPy Framework Integration for LLM Agents*
*Researched: 2026-02-04*
