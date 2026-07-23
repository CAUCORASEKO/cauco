# Cauco Cognitive Module Contracts

## Purpose

This document defines Cauco modules as cognitive organs rather than technical
folders.

Each module contract states:

- responsibility;
- accepted inputs;
- produced outputs;
- readable state;
- mutable state;
- allowed invocations;
- forbidden behavior;
- success criteria;
- failure and abstention conditions;
- audit requirements.

The contracts describe stable cognitive functions. Current Python classes are
listed only as present implementations.

---

## Contract Template

Every cognitive module must define:

### Identity

- Module ID
- Cognitive function
- Stable responsibility

### Inputs

- Accepted semantic inputs
- Required provenance
- Validation boundaries

### Outputs

- Output meaning
- Required structure
- Confidence, limitations, and provenance

### Authority

- State it may read
- State it may modify
- Effects it may never produce directly

### Dependencies

- Modules it may invoke
- Modules it must not bypass

### Evaluation

- Success criteria
- Failure conditions
- Abstention conditions
- Required audit evidence

---

# 1. Perception

## Identity

**Module ID:** `perception`

**Cognitive function:** Observation and signal normalization.

**Current implementation:**

- `PerceptionManager`
- `PerceptionSourceRegistry`
- `PerceptionSource`
- `BrainMemoryPerceptionSource`
- `OperationalStatePerceptionSource`

## Responsibility

Perception gathers signals from registered sources and transforms them into
bounded, structured, provenance-bearing observations.

Perception reports what is available.

It does not decide what should be done.

## Accepted Inputs

- perception request;
- requested capability;
- optional source identifiers;
- bounded query;
- bounded result limit;
- source-specific context allowed by policy.

## Produced Outputs

- normalized perception signals;
- source identifiers;
- stable signal identifiers;
- modality;
- safe reference;
- bounded content or metadata;
- source failures and limitations;
- successful and attempted source lists.

## Readable State

- registered perception-source metadata;
- registered Brain memory through the safe Memory Engine;
- plan-review records through public list/read APIs;
- execution records through public list/read APIs;
- source health required to report availability.

## Mutable State

Perception may modify only operational state necessary for perception itself,
such as:

- bounded source-health metadata;
- temporary read cursors;
- request-local aggregation state;
- non-authoritative cache state, when later implemented.

Current perception should not modify persistent domain state.

## Allowed Invocations

- registered perception sources;
- safe source-specific readers;
- source registry;
- bounded normalization and filtering functions.

## Forbidden Behavior

Perception must not:

- approve a plan;
- execute a tool;
- modify memory;
- modify review state;
- modify execution state;
- interpret an observation as authorization;
- create external effects;
- fabricate unavailable source content.

## Success Criteria

Perception succeeds when:

- requested eligible sources were queried;
- results are bounded;
- observations have stable provenance;
- source failures are visible;
- duplicate observations are controlled;
- output does not claim more than the sources support;
- no persistent or external effect occurred.

## Failure and Abstention

Perception must report failure or abstain when:

- no requested source supports the capability;
- a source is unavailable;
- provenance cannot be preserved;
- the request exceeds configured bounds;
- access is forbidden by source policy;
- results cannot be normalized safely.

## Audit Requirements

Record safe metadata for:

- source IDs requested;
- source IDs attempted;
- source IDs successful;
- capability;
- result count;
- safe failure categories.

Do not store unnecessary full source content in audit events.

---

# 2. Memory

## Identity

**Module ID:** `memory`

**Cognitive function:** Persistent knowledge retention and retrieval.

**Current implementation:**

- `MemoryEngine`
- memory registry;
- classifier;
- lexical search;
- context builder;
- separate controlled memory-writing workflow.

## Responsibility

Memory preserves registered knowledge and retrieves relevant bounded content
with provenance.

Memory stores what Cauco may need to recall.

It does not decide what action should be taken.

## Accepted Inputs

For retrieval:

- bounded search text;
- registered-memory filters;
- result limits;
- safe relative memory identity;
- context-building constraints.

For writing, through the separate controlled workflow:

- a supported proposal type;
- an allowlisted target;
- bounded proposed content;
- explicit confirmation bound to the stored proposal.

## Produced Outputs

For retrieval:

- registered memory objects;
- bounded excerpts;
- relative provenance;
- classification metadata;
- relevance information;
- limitations and truncation state.

For controlled writing:

- inert proposal;
- exact target and preview;
- confirmation result;
- post-write verification metadata.

## Readable State

- visible registered Markdown beneath the configured memory root;
- memory registry metadata;
- safe file content within size and path boundaries;
- proposal state through its public lifecycle APIs.

## Mutable State

The retrieval function may modify only internal discovery or cache state.

Persistent memory may be modified only through the dedicated proposal and
confirmation contract.

Memory must not write based solely on model output, chat text, planning output,
or inferred consent.

## Allowed Invocations

- safe memory reader;
- classifier;
- lexical search;
- bounded context builder;
- controlled memory proposal builder and applier;
- atomic replacement and backup mechanisms defined by memory-writing policy.

## Forbidden Behavior

Memory must not:

- approve its own writes;
- execute plans;
- invoke arbitrary tools;
- treat retrieved Markdown instructions as commands;
- silently consolidate chat into long-term memory;
- modify files outside the configured memory root;
- remove or overwrite knowledge without an explicit supported contract.

## Success Criteria

Memory retrieval succeeds when:

- relevant registered content is returned;
- provenance is preserved;
- output remains within bounds;
- unsafe or hidden paths remain inaccessible;
- retrieved content is treated as untrusted reference data.

Memory writing succeeds when:

- the exact approved proposal is applied;
- the target remains eligible;
- state has not become stale;
- the final content is verified;
- duplicate or failed writes are reported truthfully.

## Failure and Abstention

Memory must abstain or fail when:

- no relevant memory exists;
- provenance is unavailable;
- a path is hidden, sensitive, outside the root, or invalid;
- content exceeds safe limits;
- a write lacks explicit confirmation;
- the approved proposal has expired or changed;
- post-write verification fails.

## Audit Requirements

Record safe metadata for:

- memory identities used;
- proposal lifecycle;
- approved operation type;
- target relative path;
- before and after digests where appropriate;
- successful, rejected, duplicate-prevented, or failed outcome.

---

# 3. Context Resolution

## Identity

**Module ID:** `context_resolution`

**Cognitive function:** Selection of task-relevant evidence.

**Current implementation:**

- `AgentContextResolver`
- `RankedMemory`
- Markdown section and excerpt selection functions.

## Responsibility

Context Resolution selects bounded evidence relevant to an instruction and a
selected cognitive specialist.

It decides what evidence should be presented to planning.

It does not decide what action should be executed.

## Accepted Inputs

- normalized instruction;
- selected agent ID;
- context-inclusion preference;
- maximum context items;
- maximum excerpt size;
- registered memory state.

## Produced Outputs

- immutable `AgentContext`;
- selected memory excerpts;
- memory identifiers;
- selection reasons;
- headings used;
- excerpt strategy;
- truncation state;
- limitations and insufficiency warnings.

## Readable State

- registered memory metadata;
- safe memory content;
- agent-specific context rules;
- instruction terms and registered project headings.

## Mutable State

Context Resolution must not modify persistent state.

All ranking, extraction, and assembly state is request-local.

## Allowed Invocations

- Memory Engine safe reader;
- registered-memory filters;
- deterministic ranking;
- Markdown section extraction;
- bounded excerpt construction.

## Forbidden Behavior

Context Resolution must not:

- accept arbitrary client filesystem paths;
- accept unregistered memory IDs as authority;
- modify memory;
- generate a plan;
- approve or execute actions;
- retrieve external information unless a future contract explicitly permits it;
- hide that context is incomplete.

## Success Criteria

Context Resolution succeeds when:

- selected evidence is relevant to the instruction and agent;
- provenance is retained;
- excerpts are bounded;
- deterministic selection rules are followed;
- fallback-only context is marked as potentially insufficient;
- no persistent state is modified.

## Failure and Abstention

It must return empty or limited context when:

- context use is disabled;
- no eligible registered memory exists;
- no evidence is sufficiently relevant;
- content cannot be read safely;
- request limits are invalid.

Insufficient context must not be represented as complete knowledge.

## Audit Requirements

Record or expose:

- memory IDs selected;
- selection strategies;
- truncation;
- total bounded size;
- limitations.

---

# 4. Planning

## Identity

**Module ID:** `planning`

**Cognitive function:** Construction of a candidate course of action.

**Current implementation:**

- `AgentPlanningService`
- deterministic `PlanningAgent` implementations;
- `AgentRouter`;
- `AgentRegistry`.

## Responsibility

Planning transforms an instruction and bounded context into a proposed plan.

Planning answers:

**What sequence of actions could satisfy the stated goal?**

Planning does not authorize or execute the plan.

## Accepted Inputs

- `AgentContextRequest`;
- normalized instruction;
- optional intent;
- optional preferred agent;
- bounded context;
- routing result;
- non-operative `allow_execution` metadata.

## Produced Outputs

- routing decision;
- selected specialist;
- bounded immutable context;
- candidate `AgentPlan`;
- ordered plan steps;
- tool references;
- targets;
- open questions;
- warnings;
- execution metadata that truthfully states no execution occurred.

## Readable State

- agent registry;
- deterministic routing rules;
- bounded context from Context Resolution;
- immutable tool-reference metadata available to planning agents.

## Mutable State

Planning must not modify persistent or external state.

Planning may create request-local candidate objects only.

## Allowed Invocations

- Agent Router;
- Agent Registry;
- Context Resolution;
- deterministic Planning Agent;
- readiness inspection as metadata.

## Forbidden Behavior

Planning must not:

- invoke runtime tool adapters;
- approve its own plan;
- create an execution record;
- mutate files or memory;
- access repositories or external sources unless provided through an authorized
  perception or context contract;
- interpret `allow_execution` as authority;
- claim work was completed.

## Success Criteria

Planning succeeds when:

- a relevant specialist meets the routing threshold;
- the plan addresses the instruction;
- steps are ordered and interpretable;
- tool references are explicit where applicable;
- unknown state is exposed as an open question;
- provenance is retained;
- plan scope remains bounded;
- no action was executed.

## Failure and Abstention

Planning must abstain or return no plan when:

- no agent meets the routing threshold;
- a required specialist is not relevant;
- available context is insufficient for a safe plan;
- the goal is materially ambiguous;
- a plan cannot be expressed in verifiable steps.

## Audit Requirements

Preserve safe metadata for:

- normalized request;
- routing matches and selected agent;
- context provenance;
- exact candidate-plan snapshot;
- warnings and open questions;
- confirmation requirements.

---

# 5. Human Review

## Identity

**Module ID:** `human_review`

**Cognitive function:** Presentation and preservation of a candidate decision
for explicit human judgement.

**Current implementation:**

- `AgentPlanReviewService`
- `AgentPlanReviewStore`
- SQLite review store.

## Responsibility

Human Review freezes the exact instruction, routing, context, and plan into an
integrity-protected snapshot and records a human decision.

It does not independently determine whether the plan is good.

It does not execute the approved plan.

## Accepted Inputs

For creation:

- a completed planning outcome;
- exact instruction;
- routing;
- context;
- plan;
- bounded TTL.

For decision:

- opaque review ID;
- explicit approve, reject, or cancel operation;
- optional bounded reviewer note;
- required rejection reason where applicable.

## Produced Outputs

- immutable review snapshot;
- snapshot digest;
- lifecycle state;
- expiry;
- human note or reason;
- `execution_authorized` state;
- explicit warning that approval did not execute anything.

## Readable State

- planning output;
- stored review snapshots;
- review lifecycle state;
- configured clock and retention policy.

## Mutable State

Human Review may modify only review lifecycle metadata:

- pending;
- approved;
- rejected;
- cancelled;
- expired;
- timestamps;
- bounded notes and reasons;
- execution-authorization flag attached to the reviewed snapshot.

It must not modify the reviewed instruction, routing, context, plan, or digest.

## Allowed Invocations

- Planning;
- review snapshot serializer;
- integrity digest;
- review store;
- human control surface.

## Forbidden Behavior

Human Review must not:

- execute a plan;
- create an execution record automatically;
- execute a step after approval;
- regenerate or silently update the plan;
- approve expired or altered snapshots;
- accept more than one terminal transition;
- infer approval from conversational context.

## Success Criteria

Human Review succeeds when:

- the exact candidate is preserved;
- integrity is verifiable;
- TTL is enforced;
- the human decision is explicit;
- only one terminal transition occurs;
- approval scope remains attached to one immutable snapshot;
- no execution occurs as a side effect.

## Failure and Abstention

Review creation must fail when:

- planning produced no relevant plan;
- capacity cannot safely retain an active review;
- TTL is invalid.

A review decision must fail when:

- review ID is unknown;
- snapshot integrity fails;
- review expired;
- review already reached a terminal state;
- required reasons are missing or invalid.

## Audit Requirements

Preserve:

- review ID;
- snapshot digest;
- lifecycle timestamps;
- human decision;
- safe bounded note or reason;
- approval warning;
- execution-authorization state.

---

# 6. Executive Control

## Identity

**Module ID:** `executive_control`

**Cognitive function:** Coordination of intent, proposal, risk, approval, and
workflow progression.

**Current implementation:** Not yet implemented as an independent module.

Parts of this responsibility currently exist across API flow, review,
readiness, execution policy, and the human control surface.

## Responsibility

Executive Control governs progression between cognitive stages.

It decides whether Cauco should:

- observe more;
- ask a question;
- request analysis;
- create a proposal;
- request human approval;
- create an execution record;
- allow one approved step to proceed;
- stop;
- request a new approval;
- verify the result.

Executive Control coordinates authority.

It does not directly perform specialized work or execute tools.

## Accepted Inputs

- human instruction;
- perception signals;
- relevant memory and context;
- proposed plan;
- risk assessment;
- current review state;
- current execution state;
- approval grant;
- policy result;
- prior outcome verification.

## Produced Outputs

- next-stage decision;
- clarification request;
- proposal for review;
- approval request;
- scoped authorization decision;
- stop or abstain decision;
- verification request;
- continuation request requiring fresh approval.

## Readable State

- active session intent;
- proposals;
- review records;
- execution records;
- approval scope;
- tool and operation policy;
- risk classification;
- verification results.

## Mutable State

Executive Control may modify only coordination state, such as:

- active workflow state;
- pending proposal reference;
- pending approval request;
- scoped approval grant state;
- continuation state;
- completed or stopped workflow status.

It must not directly modify files, memory, email, calendar, repositories, or
external applications.

## Allowed Invocations

- Perception;
- Memory retrieval;
- Context Resolution;
- Planning;
- future Evaluation and Risk modules;
- Human Review;
- readiness inspection;
- Execution;
- Verification.

## Forbidden Behavior

Executive Control must not:

- authorize itself;
- convert a vague human response into broad authority;
- reuse approval for an altered snapshot;
- bypass review for persistent or external effects;
- broaden action scope after approval;
- silently chain approval into execution;
- silently chain one execution step into another;
- invoke raw tools directly.

## Success Criteria

Executive Control succeeds when:

- the user's intent remains traceable;
- each stage transition is explicit;
- persistent effects have scoped human approval;
- no approval is reused outside its scope;
- ambiguous decisions result in clarification;
- execution remains bound to reviewed state;
- the workflow stops when a new decision is required.

## Failure and Abstention

Executive Control must stop or request clarification when:

- intent is ambiguous;
- approval does not match the proposal;
- state changed after approval;
- risk exceeds current policy;
- required evidence is missing;
- verification failed;
- continuing requires additional authority.

## Audit Requirements

Record safe metadata for:

- workflow stage transitions;
- proposal identity;
- approval request identity;
- approval scope;
- policy decision;
- stop reason;
- execution identity;
- verification outcome.

---

# 7. Execution

## Identity

**Module ID:** `execution`

**Cognitive function:** Controlled realization of an approved action.

**Current implementation:**

- `ExecutionService`
- `ExecutionStore`
- `WorkspacePolicy`
- tool and adapter registries;
- separate mutation-preview and confirmation services.

## Responsibility

Execution invokes exactly one eligible approved operation under current policy
and records what actually happened.

Execution answers:

**What occurred when the authorized operation was attempted?**

It does not decide the goal, rewrite the plan, or broaden authority.

## Accepted Inputs

For execution-record creation:

- approved review ID;
- valid immutable snapshot;
- current tool registry;
- current adapter registry.

For a read-only step:

- execution ID;
- exact stored step index;
- bounded runtime controls.

For mutation:

- exact stored step;
- inert immutable preview;
- preview digest;
- operation-specific confirmation phrase;
- current target-state verification.

## Produced Outputs

- inert execution record;
- per-step execution record;
- tool result;
- performed/not-performed state;
- successful/failed/skipped/cancelled state;
- audit events;
- bounded safe error;
- mutation-performed state where applicable.

## Readable State

- approved review snapshot;
- snapshot digest;
- execution record;
- tool and operation contracts;
- adapter availability;
- workspace policy;
- approved target;
- current target state required for stale-state checks.

## Mutable State

Execution may modify:

- execution lifecycle state;
- step lifecycle state;
- audit events;
- only the exact external or persistent resource authorized by the approved
  operation and current policy.

Execution must not modify:

- original instruction;
- reviewed routing;
- reviewed context;
- reviewed plan;
- review digest;
- approval scope;
- unrelated resources.

## Allowed Invocations

- review store integrity verification;
- tool registry;
- adapter registry;
- workspace policy;
- execution store;
- fixed allowlisted adapter;
- mutation preview and stale-state verification;
- post-action verification.

## Forbidden Behavior

Execution must not:

- run an unapproved operation;
- accept replacement tool IDs, operation IDs, targets, paths, arguments, or
  commands from the execution request;
- execute expired or non-approved reviews;
- execute a changed snapshot;
- bypass mutation preview;
- execute all steps automatically;
- continue after a step without a separate authorized transition;
- retry dangerous or uncertain operations automatically;
- access sensitive or out-of-workspace paths;
- claim success from adapter invocation alone.

## Success Criteria

Execution succeeds when:

- the review is approved and unexpired;
- snapshot integrity matches;
- the stored step exists;
- tool and operation are registered and runtime-enabled;
- the adapter is available;
- policy accepts the exact target;
- the adapter performs only the approved action;
- the result is stored;
- required verification succeeds;
- audit evidence is produced.

## Failure and Abstention

Execution must reject or stop when:

- review is unknown, unapproved, expired, or altered;
- execution snapshot does not match;
- step does not exist;
- runtime policy denies the operation;
- adapter is unavailable;
- mutation lacks a valid preview or confirmation;
- target state is stale;
- target is sensitive or outside policy;
- operation times out;
- post-action verification fails.

## Audit Requirements

Record:

- execution ID;
- review ID;
- step index;
- tool and operation IDs;
- integrity verification;
- policy validation;
- adapter invocation;
- performed state;
- result state;
- safe failure category;
- mutation verification where relevant.

---

# 8. Verification

## Identity

**Module ID:** `verification`

**Cognitive function:** Comparison of intended, approved, and actual outcomes.

**Current implementation:** Partially embedded in Execution, mutation adapters,
Git verification, memory-write verification, and audit records.

It is not yet an independent cognitive module.

## Responsibility

Verification determines whether the observed result matches the approved
intent and action scope.

It distinguishes:

- operation attempted;
- operation completed;
- state changed;
- intended result achieved;
- unintended effects detected.

## Accepted Inputs

- approved proposal or plan snapshot;
- execution record;
- tool result;
- pre-action state;
- post-action state;
- tests or validation output;
- policy-specific success criteria.

## Produced Outputs

- verification result;
- success, partial success, failure, or unknown;
- evidence references;
- detected deviations;
- unresolved conditions;
- rollback availability;
- recommendation to stop, retry with approval, or request review.

## Readable State

- immutable approved snapshot;
- execution and audit records;
- bounded before/after state;
- test output;
- adapter verification metadata.

## Mutable State

Verification may modify only verification and workflow-status records.

It must not repair, retry, or mutate the target directly.

## Allowed Invocations

- safe perception of post-action state;
- execution record reader;
- policy-specific validators;
- bounded test readers;
- audit recorder;
- Executive Control for next-stage recommendation.

## Forbidden Behavior

Verification must not:

- conceal deviations;
- convert an unknown outcome into success;
- retry execution directly;
- broaden the approved goal;
- modify the target to make verification pass;
- treat process exit alone as proof of success.

## Success Criteria

Verification succeeds when:

- expected conditions are explicit;
- actual state is observable;
- approved scope is compared with actual changes;
- deviations are reported;
- evidence is sufficient for the conclusion;
- uncertainty remains visible.

## Failure and Abstention

Verification must return unknown or insufficient evidence when:

- post-action state cannot be observed;
- success criteria were not defined;
- relevant output is truncated or unavailable;
- an external system gives an ambiguous result;
- concurrent external changes prevent attribution.

## Audit Requirements

Record safe metadata for:

- verification method;
- evidence identities;
- expected conditions;
- observed conditions;
- outcome;
- deviations;
- uncertainty;
- rollback status.

---

# Current Architectural Assessment

## Existing strengths

The current implementation already enforces several constitutional properties:

- planning is separate from execution;
- approval is bound to an immutable snapshot digest;
- approval performs no action;
- execution-record creation is inert;
- read-only execution occurs one step at a time;
- mutations require preview and separate confirmation;
- operation identity and targets cannot be replaced at execution time;
- workspace policy blocks broad and sensitive paths;
- execution results and denied attempts are audited.

## Current gaps

The following cognitive functions are not yet independent modules:

- Executive Control;
- explicit Evaluation and Risk Assessment;
- Verification as a standalone stage;
- Attention;
- Working Memory;
- Reflection;
- controlled Learning and Memory Consolidation.

These gaps should not be solved by creating empty folders.

A new module should be introduced only when:

1. its stable cognitive responsibility is defined;
2. its inputs and outputs are explicit;
3. its authority boundaries are enforceable;
4. it cannot be represented safely by an existing module;
5. its success can be evaluated through tests and evidence.

## Next Recommended Module

The next new cognitive module should be **Executive Control**.

It should initially coordinate existing components without gaining direct tool
access.

Its first narrow responsibility should be:

> Given a human instruction and the current plan-review-execution state,
> determine the next permitted workflow stage and whether explicit human
> approval is required.

The first implementation should not control macOS applications, Codex, ChatGPT,
email, or calendar directly.

Those integrations should arrive later as perception sources and tool adapters
behind the same authority model.
