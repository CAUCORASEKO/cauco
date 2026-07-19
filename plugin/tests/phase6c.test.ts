import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { ExecutionApiClient, type CoreTransport } from "../src/execution/api";
import {
  parseExecutionRecord,
  parseMutationPreview,
  parsePlanningResponse,
  parsePlanReview,
  safeDisplayText,
} from "../src/execution/contracts";
import {
  acceptNewPlan,
  armStepConfirmation,
  beginNewPlan,
  initialExecutionUiState,
  mayCancelExecution,
  mayCreateExecution,
  mayCreateReview,
  mayExecuteStep,
  maySubmitConfirmedStep,
  readinessForStep,
} from "../src/execution/state";
import { executionErrorMessage } from "../src/execution/errors";

const now = "2026-07-19T10:00:00+00:00";

function context() {
  return {
    agent_id: "git",
    instruction: "Inspect git status",
    resolved_intent: "git",
    memory_references: [
      {
        memory_id: "memory_123",
        name: "Projects.md",
        kind: "projects",
        layer: "operational",
        title: "Projects",
        relative_path: "Projects.md",
        reason_selected: "Relevant project context.",
        excerpt: "Cauco project",
        excerpt_truncated: false,
        modified_at: now,
        excerpt_strategy: "section",
        selected_headings: ["Active"],
      },
    ],
    context_summary: "One context item selected.",
    limitations: [],
    metadata: {},
  };
}

function readiness(executable = true) {
  return {
    ready: executable,
    execution_enabled: false,
    references: [
      {
        tool_id: "git",
        operation_id: "status",
        target: null,
        registered: true,
        enabled: true,
        safe: true,
        confirmation_required: false,
        operation_exists: true,
        runtime_execution_allowed: executable,
        adapter_available: executable,
        executable_now: executable,
        execution_enabled: false,
      },
    ],
  };
}

function plan() {
  return {
    agent_id: "git",
    agent_name: "Git Agent",
    status: "proposal_only",
    objective: "Inspect safely",
    context_used: true,
    steps: [
      {
        order: 1,
        title: "Inspect status",
        description: "Inspect the configured repository.",
        source_memory_ids: ["memory_123"],
        proposed_action: "Read Git status.",
        requires_confirmation: false,
        execution_available: false,
        warnings: [],
        tool_reference: { tool_id: "git", operation_id: "status", target: null },
      },
    ],
    open_questions: [],
    warnings: ["No commands were executed."],
    requires_confirmation: true,
    execution_performed: false,
    metadata: { framework_phase: "6B" },
  };
}

function planning() {
  return {
    status: "planned",
    routing: {
      selected_agent: { id: "git", name: "Git Agent" },
      match: null,
      matches: [],
      preferred_agent_rejected: false,
    },
    context: context(),
    plan: plan(),
    readiness: readiness(),
  };
}

function review(status = "approved") {
  return {
    review_id: "planrev_abcdefghijklmnop",
    status,
    created_at: now,
    expires_at: "2099-07-19T10:30:00+00:00",
    updated_at: now,
    instruction: "Inspect git status",
    selected_agent_id: "git",
    routing: {
      request: {
        instruction: "Inspect git status",
        intent: null,
        context: {},
        preferred_agent_id: null,
        allow_execution: false,
      },
      selected_agent: { id: "git", name: "Git Agent" },
      match: {
        agent_id: "git",
        matched: true,
        score: 40,
        matched_signals: ["git"],
        reasoning: ["Matched git."],
        priority: 20,
      },
      matches: [
        {
          agent_id: "git",
          matched: true,
          score: 40,
          matched_signals: ["git"],
          reasoning: ["Matched git."],
          priority: 20,
        },
      ],
      result: {
        agent_id: "git",
        agent_name: "Git Agent",
        status: "proposal_only",
        summary: "Git inspection proposal.",
        proposed_actions: ["Inspect status."],
        warnings: [],
        requires_confirmation: true,
        execution_performed: false,
        metadata: {},
      },
      preferred_agent_rejected: false,
    },
    context: context(),
    plan: plan(),
    snapshot_digest: "a".repeat(64),
    execution_authorized: status === "approved",
    execution_performed: false,
    approved_at: status === "approved" ? now : null,
    rejected_at: null,
    cancelled_at: null,
    expired_at: null,
    reviewer_note: null,
    rejection_reason: null,
    cancellation_reason: null,
    approval_warning: status === "approved" ? "Approval does not execute tools." : null,
    metadata: { contract_version: "phase_5c" },
    readiness: readiness(),
  };
}

function execution(status = "pending_execution", stepStatus = "pending") {
  return {
    execution_id: "exec_abcdefghijklmnop",
    review_id: "planrev_abcdefghijklmnop",
    snapshot_digest: "a".repeat(64),
    status,
    created_at: now,
    started_at: status === "pending_execution" ? null : now,
    completed_at: status === "completed" || status === "failed" || status === "cancelled" ? now : null,
    current_step_index: null,
    total_steps: 1,
    step_records: [
      {
        step_index: 1,
        tool_id: "git",
        operation_id: "status",
        target: null,
        status: stepStatus,
        started_at: null,
        completed_at: null,
        result: null,
        error: null,
        execution_performed: false,
      },
    ],
    execution_performed: false,
    failure_reason: null,
    audit_events: [
      {
        event_id: "audit_2",
        event_type: "integrity_verified",
        timestamp: "2026-07-19T10:00:02+00:00",
        execution_id: "exec_abcdefghijklmnop",
        review_id: "planrev_abcdefghijklmnop",
        step_index: null,
        tool_id: null,
        operation_id: null,
        outcome: "success",
        safe_message: "Snapshot verified.",
        metadata: {},
      },
      {
        event_id: "audit_1",
        event_type: "execution_created",
        timestamp: "2026-07-19T10:00:01+00:00",
        execution_id: "exec_abcdefghijklmnop",
        review_id: "planrev_abcdefghijklmnop",
        step_index: null,
        tool_id: null,
        operation_id: null,
        outcome: "success",
        safe_message: "Execution created.",
        metadata: {},
      },
    ],
    warning: "Execution is step controlled.",
  };
}

function mutationPreview() {
  return {
    preview_id: "mutprev_abcdefghijklmnopqrstuv",
    execution_id: "exec_abcdefghijklmnop",
    review_id: "planrev_abcdefghijklmnop",
    step_index: 3,
    tool_id: "filesystem",
    operation_id: "write_text_file",
    target: "notes.txt",
    normalized_arguments: {
      relative_path: "notes.txt",
      content: "approved content",
      overwrite_policy: "create_only",
      expected_before_digest: null,
    },
    before_state: { exists: false, digest: null },
    proposed_after_state: { exists: true, characters: 16 },
    diff_preview: "+approved content",
    preview_digest: "b".repeat(64),
    confirmation_phrase: "WRITE WORKSPACE FILE",
    created_at: now,
    expires_at: "2099-07-19T10:10:00+00:00",
    status: "pending_confirmation",
    warning: "Preview creation performs no mutation.",
  };
}

test("strict contracts accept real planning, review, and execution shapes", () => {
  assert.equal(parsePlanningResponse(planning()).plan?.steps.length, 1);
  assert.equal(parsePlanReview(review()).execution_authorized, true);
  assert.equal(parseExecutionRecord(execution()).step_records[0]?.tool_id, "git");
});

test("contracts reject malformed essential fields and unsafe returned paths", () => {
  assert.throws(() => parsePlanningResponse({ status: "planned" }), /invalid planning response/);
  assert.throws(() => parsePlanReview({ ...review(), snapshot_digest: 42 }), /snapshot_digest/);
  const unsafe = execution();
  unsafe.step_records[0]!.target = "/Users/person/secret";
  assert.throws(() => parseExecutionRecord(unsafe), /execution target/);
});

test("contracts are frozen and audit events are chronological", () => {
  const parsed = parseExecutionRecord(execution());
  assert.equal(Object.isFrozen(parsed), true);
  assert.equal(Object.isFrozen(parsed.step_records), true);
  assert.deepEqual(parsed.audit_events.map((event) => event.event_id), ["audit_1", "audit_2"]);
});

test("display sanitizer redacts absolute host paths and bounds text", () => {
  const safe = safeDisplayText("read /Users/person/work/private.txt and C:\\Users\\person\\key.txt", 80);
  assert.doesNotMatch(safe, /person/);
  assert.ok(safe.length <= 80);
});

test("planning client sends only supported planning fields", async () => {
  const calls: Array<{ path: string; method: string; body: unknown }> = [];
  const client = clientFor(calls, planning());
  await client.generatePlan("Inspect git status");
  assert.deepEqual(calls, [
    {
      path: "/api/agents/plan",
      method: "POST",
      body: { instruction: "Inspect git status", include_context: true, allow_execution: false },
    },
  ]);
});

test("review actions never call execution endpoints", async () => {
  const calls: Array<{ path: string; method: string; body: unknown }> = [];
  const client = clientFor(calls, review());
  await client.approveReview("planrev_abcdefghijklmnop");
  assert.equal(calls[0]?.path.endsWith("/approve"), true);
  assert.equal(calls.some((call) => call.path.includes("/executions")), false);
  assert.deepEqual(calls[0]?.body, {});
});

test("review creation sends only supported fields", async () => {
  const calls: Array<{ path: string; method: string; body: unknown }> = [];
  const client = clientFor(calls, review("pending_review"));
  await client.createReview("Inspect git status");
  assert.deepEqual(calls[0]?.body, {
    instruction: "Inspect git status",
    include_context: true,
    allow_execution: false,
  });
});

test("execution creation is inert and makes one create call", async () => {
  const calls: Array<{ path: string; method: string; body: unknown }> = [];
  const client = clientFor(calls, execution());
  await client.createExecution("planrev_abcdefghijklmnop");
  assert.deepEqual(calls, [
    { path: "/api/executions", method: "POST", body: { review_id: "planrev_abcdefghijklmnop" } },
  ]);
});

test("step execution targets exact approved index and sends controls only", async () => {
  const calls: Array<{ path: string; method: string; body: unknown }> = [];
  const client = clientFor(calls, execution("completed", "completed"));
  await client.executeStep("exec_abcdefghijklmnop", 3, {
    timeout_seconds: 5,
    max_output_chars: 20000,
  });
  assert.equal(calls[0]?.path, "/api/executions/exec_abcdefghijklmnop/steps/3/execute");
  assert.deepEqual(calls[0]?.body, { timeout_seconds: 5, max_output_chars: 20000 });
  assert.equal(JSON.stringify(calls[0]?.body).includes("tool"), false);
  assert.equal(JSON.stringify(calls[0]?.body).includes("target"), false);
});

test("review and execution identifiers are URL encoded", async () => {
  const calls: Array<{ path: string; method: string; body: unknown }> = [];
  const client = clientFor(calls, review());
  await client.getReview("review/unsafe");
  assert.equal(calls[0]?.path, "/api/agents/plan-reviews/review%2Funsafe");
});

test("empty instructions are not eligible for review creation", () => {
  const state = initialExecutionUiState();
  assert.equal(mayCreateReview(state), false);
});

test("new planning clears old lifecycle only after a matching response", () => {
  const state = initialExecutionUiState();
  const first = beginNewPlan(state, "first");
  const second = beginNewPlan(state, "second");
  assert.equal(acceptNewPlan(state, first, parsePlanningResponse(planning())), false);
  assert.equal(state.plan, null);
  assert.equal(acceptNewPlan(state, second, parsePlanningResponse(planning())), true);
  assert.equal(state.review, null);
  assert.equal(state.execution, null);
});

test("duplicate pending actions block review and execution creation", () => {
  const state = initialExecutionUiState();
  state.plan = parsePlanningResponse(planning());
  state.pendingAction = "planning";
  assert.equal(mayCreateReview(state), false);
  state.review = parsePlanReview(review());
  assert.equal(mayCreateExecution(state), false);
});

test("execution creation requires an approved authorized review", () => {
  const state = initialExecutionUiState();
  state.plan = parsePlanningResponse(planning());
  state.review = parsePlanReview(review("pending_review"));
  assert.equal(mayCreateExecution(state), false);
  state.review = parsePlanReview(review());
  assert.equal(mayCreateExecution(state), true);
  state.review = parsePlanReview({ ...review(), expires_at: "2020-01-01T00:00:00+00:00" });
  assert.equal(mayCreateExecution(state), false);
});

test("step action requires pending state and executable readiness", () => {
  const state = initialExecutionUiState();
  state.review = parsePlanReview(review());
  state.execution = parseExecutionRecord(execution());
  const step = state.execution.step_records[0]!;
  const ready = readinessForStep(state.review.readiness, step);
  assert.equal(mayExecuteStep(state, step, ready), true);
  assert.equal(mayExecuteStep(state, step, { ...ready!, executable_now: false }), false);
  state.pendingAction = "execute-step";
  assert.equal(mayExecuteStep(state, step, ready), false);
});

test("cancel is exposed only for pending execution", () => {
  const state = initialExecutionUiState();
  state.execution = parseExecutionRecord(execution());
  assert.equal(mayCancelExecution(state), true);
  state.execution = parseExecutionRecord(execution("cancelled", "cancelled"));
  assert.equal(mayCancelExecution(state), false);
});

test("terminal executions and steps cannot execute", () => {
  const state = initialExecutionUiState();
  state.review = parsePlanReview(review());
  state.execution = parseExecutionRecord(execution("completed", "completed"));
  const step = state.execution.step_records[0]!;
  assert.equal(mayExecuteStep(state, step, readinessForStep(state.review.readiness, step)), false);
});

test("first step action arms confirmation and only the matching second action may submit", () => {
  const state = initialExecutionUiState();
  assert.equal(armStepConfirmation(state, 2), true);
  assert.equal(maySubmitConfirmedStep(state, 1), false);
  assert.equal(maySubmitConfirmedStep(state, 2), true);
  state.pendingAction = "execute-step";
  assert.equal(armStepConfirmation(state, 3), false);
  assert.equal(maySubmitConfirmedStep(state, 2), false);
});

test("safe error mappings distinguish conflict, validation, forbidden, timeout, and server", () => {
  assert.match(executionErrorMessage("conflict", "already executed"), /Lifecycle conflict/);
  assert.match(executionErrorMessage("validation", "bad controls"), /controls/);
  assert.match(executionErrorMessage("forbidden", "secret"), /denied/);
  assert.match(executionErrorMessage("timeout", "ignored"), /timed out/);
  assert.match(executionErrorMessage("server", "raw stack"), /No automatic retry/);
  assert.doesNotMatch(
    executionErrorMessage("conflict", "/Users/person/project is busy"),
    /\/Users|person/,
  );
});

test("script-like tool output remains an ordinary string in the validated contract", () => {
  const value = execution("completed", "completed");
  value.step_records[0]!.result = {
    tool_id: "filesystem",
    operation_id: "read_file",
    success: true,
    started_at: now,
    completed_at: now,
    duration_ms: 1,
    output: "<script>globalThis.compromised = true</script>",
    structured_data: { path: "README.md", size: 44 },
    error_code: null,
    error_message: null,
    truncated: true,
    execution_performed: true,
  };
  const parsed = parseExecutionRecord(value);
  assert.equal(parsed.step_records[0]?.result?.output.startsWith("<script>"), true);
  const source = readFileSync("src/views/CaucoExecutionResults.ts", "utf8");
  assert.match(source, /text: safeDisplayText\(result\.output\)/);
});

test("audit metadata display and structured result lists are explicitly bounded", () => {
  const source = readFileSync("src/views/CaucoExecutionResults.ts", "utf8");
  assert.match(source, /Object\.entries\(event\.metadata\)\.slice\(0, 10\)/);
  assert.match(source, /changed_entries\.slice\(0, 200\)/);
  assert.match(source, /entries\.slice\(0, 1000\)/);
});

test("plugin source contains no execute-all, polling timer, HTML injection, process, or vault write", () => {
  const source = [
    "src/views/CaucoExecutionPanel.ts",
    "src/views/CaucoExecutionResults.ts",
    "src/views/CaucoPlanDetails.ts",
  ].map((path) => readFileSync(path, "utf8")).join("\n");
  assert.doesNotMatch(source, /executeAll|execute-all|setInterval|innerHTML|setHTML|child_process|spawn\(|vault\.(create|modify|append)/);
  assert.match(source, /Review execution/);
  assert.match(source, /Execute approved step/);
});

test("step API surface cannot accept replacement operation data", () => {
  const source = readFileSync("src/execution/api.ts", "utf8");
  const method = source.slice(source.indexOf("async executeStep("), source.indexOf("async cancelExecution("));
  assert.doesNotMatch(method, /tool_id|operation_id|target|command|cwd|relative_path/);
});

test("mutation preview contracts are frozen and reject unsafe targets", () => {
  const parsed = parseMutationPreview(mutationPreview());
  assert.equal(Object.isFrozen(parsed), true);
  assert.equal(Object.isFrozen(parsed.normalized_arguments), true);
  assert.throws(
    () => parseMutationPreview({ ...mutationPreview(), target: "/Users/person/.env" }),
    /mutation target/,
  );
});

test("mutation confirmation sends only preview integrity fields", async () => {
  const calls: Array<{ path: string; method: string; body: unknown }> = [];
  const client = clientFor(calls, execution("completed", "completed"));
  const preview = parseMutationPreview(mutationPreview());
  await client.confirmMutation(
    "exec_abcdefghijklmnop",
    3,
    preview,
    "WRITE WORKSPACE FILE",
  );
  assert.deepEqual(calls[0]?.body, {
    preview_id: preview.preview_id,
    preview_digest: preview.preview_digest,
    confirmation_phrase: "WRITE WORKSPACE FILE",
  });
  const serialized = JSON.stringify(calls[0]?.body);
  assert.doesNotMatch(serialized, /approved content|relative_path|tool_id|operation_id|target/);
});

test("mutation controls never expose the read-only execute button for preview-required steps", () => {
  const source = readFileSync("src/views/CaucoExecutionPanel.ts", "utf8");
  const mutationBranch = source.indexOf("if (item?.preview_required)");
  const normalExecute = source.indexOf("if (!mayExecuteStep", mutationBranch);
  assert.ok(mutationBranch > 0 && normalExecute > mutationBranch);
  assert.match(source, /Create Mutation Preview/);
  assert.match(source, /Confirm and Apply Mutation/);
});

test("memory workflow remains present and separate", () => {
  const dashboard = readFileSync("src/views/CaucoDashboardView.ts", "utf8");
  assert.match(dashboard, /new CaucoExecutionPanel/);
  assert.match(dashboard, /new CaucoMemoryPanel/);
});

function clientFor(
  calls: Array<{ path: string; method: string; body: unknown }>,
  response: unknown,
): ExecutionApiClient {
  const transport: CoreTransport = async (path, method, body) => {
    calls.push({ path, method, body });
    return structuredClone(response);
  };
  return new ExecutionApiClient(transport);
}
