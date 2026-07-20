import type {
  AgentContext,
  AgentMemoryReference,
  AgentPlan,
  AgentPlanningResponse,
  AgentMatch,
  AgentPlanStep,
  AuditEvent,
  ExecutionRecord,
  ExecutionStatus,
  JsonScalar,
  JsonValue,
  PlanReadiness,
  PlanReview,
  PlanReviewStatus,
  StepExecutionRecord,
  StepExecutionStatus,
  ToolReadiness,
  ToolResult,
  MutationPreview,
  MutationPreviewStatus,
} from "./types";

const REVIEW_STATUSES = new Set<PlanReviewStatus>([
  "pending_review",
  "approved",
  "rejected",
  "cancelled",
  "expired",
]);
const EXECUTION_STATUSES = new Set<ExecutionStatus>([
  "pending_execution",
  "running",
  "completed",
  "failed",
  "cancelled",
]);
const STEP_STATUSES = new Set<StepExecutionStatus>([
  "pending",
  "running",
  "completed",
  "failed",
  "skipped",
  "cancelled",
]);

export function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function stringValue(record: Record<string, unknown>, key: string): string {
  const value = record[key];
  if (typeof value !== "string") invalid(key);
  return value;
}

function nullableString(record: Record<string, unknown>, key: string): string | null {
  const value = record[key];
  if (value !== null && typeof value !== "string") invalid(key);
  return value;
}

function booleanValue(record: Record<string, unknown>, key: string): boolean {
  const value = record[key];
  if (typeof value !== "boolean") invalid(key);
  return value;
}

function numberValue(record: Record<string, unknown>, key: string): number {
  const value = record[key];
  if (typeof value !== "number" || !Number.isFinite(value)) invalid(key);
  return value;
}

function nullableNumber(record: Record<string, unknown>, key: string): number | null {
  const value = record[key];
  if (value !== null && (typeof value !== "number" || !Number.isInteger(value))) invalid(key);
  return value;
}

function timestamp(record: Record<string, unknown>, key: string): string {
  const value = stringValue(record, key);
  if (Number.isNaN(Date.parse(value))) invalid(key);
  return value;
}

function nullableTimestamp(record: Record<string, unknown>, key: string): string | null {
  const value = nullableString(record, key);
  if (value !== null && Number.isNaN(Date.parse(value))) invalid(key);
  return value;
}

function stringArray(value: unknown, key: string): readonly string[] {
  if (!Array.isArray(value) || !value.every((item) => typeof item === "string")) invalid(key);
  return Object.freeze([...value]);
}

function safeRelative(value: string | null, key: string): string | null {
  if (
    value !== null &&
    (value.startsWith("/") ||
      value.startsWith("\\") ||
      /^[A-Za-z]:[\\/]/.test(value) ||
      value.split(/[\\/]/).includes(".."))
  ) {
    invalid(key);
  }
  return value;
}

function scalarRecord(value: unknown, key: string): Readonly<Record<string, JsonScalar>> {
  if (!isRecord(value)) invalid(key);
  const result: Record<string, JsonScalar> = {};
  for (const [name, item] of Object.entries(value)) {
    if (item !== null && !["string", "number", "boolean"].includes(typeof item)) invalid(key);
    result[name] = item as JsonScalar;
  }
  return Object.freeze(result);
}

function jsonValue(value: unknown, depth = 0): JsonValue {
  if (depth > 5) throw new Error("The core returned overly nested result data.");
  if (value === null || ["string", "number", "boolean"].includes(typeof value)) {
    if (typeof value === "number" && !Number.isFinite(value)) invalid("structured_data");
    return value as JsonScalar;
  }
  if (Array.isArray(value)) return Object.freeze(value.slice(0, 1000).map((item) => jsonValue(item, depth + 1)));
  if (!isRecord(value)) invalid("structured_data");
  const result: Record<string, JsonValue> = {};
  for (const [key, item] of Object.entries(value).slice(0, 100)) {
    result[key] = jsonValue(item, depth + 1);
  }
  return Object.freeze(result);
}

function parseContextReference(value: unknown): AgentMemoryReference {
  if (!isRecord(value)) invalid("memory reference");
  return Object.freeze({
    memory_id: stringValue(value, "memory_id"),
    name: stringValue(value, "name"),
    kind: stringValue(value, "kind"),
    layer: stringValue(value, "layer"),
    title: stringValue(value, "title"),
    relative_path: safeRelative(stringValue(value, "relative_path"), "relative_path") ?? "",
    reason_selected: stringValue(value, "reason_selected"),
    excerpt: stringValue(value, "excerpt"),
    excerpt_truncated: booleanValue(value, "excerpt_truncated"),
    modified_at: nullableString(value, "modified_at"),
    excerpt_strategy: stringValue(value, "excerpt_strategy"),
    selected_headings: stringArray(value.selected_headings, "selected_headings"),
  });
}

function parseContext(value: unknown): AgentContext {
  if (!isRecord(value) || !Array.isArray(value.memory_references)) invalid("context");
  return Object.freeze({
    agent_id: stringValue(value, "agent_id"),
    instruction: stringValue(value, "instruction"),
    resolved_intent: nullableString(value, "resolved_intent"),
    memory_references: Object.freeze(value.memory_references.map(parseContextReference)),
    context_summary: stringValue(value, "context_summary"),
    limitations: stringArray(value.limitations, "limitations"),
    metadata: scalarRecord(value.metadata, "context metadata"),
  });
}

function parsePlanStep(value: unknown): AgentPlanStep {
  if (!isRecord(value) || !isRecord(value.tool_reference)) invalid("plan step");
  const reference = value.tool_reference;
  return Object.freeze({
    order: numberValue(value, "order"),
    title: stringValue(value, "title"),
    description: stringValue(value, "description"),
    source_memory_ids: stringArray(value.source_memory_ids, "source_memory_ids"),
    proposed_action: stringValue(value, "proposed_action"),
    requires_confirmation: booleanValue(value, "requires_confirmation"),
    execution_available: booleanValue(value, "execution_available"),
    warnings: stringArray(value.warnings, "step warnings"),
    tool_reference: Object.freeze({
      tool_id: stringValue(reference, "tool_id"),
      operation_id: stringValue(reference, "operation_id"),
      target: safeRelative(nullableString(reference, "target"), "target"),
    }),
    operation_input:
      value.operation_input == null
        ? null
        : (jsonValue(value.operation_input) as Readonly<Record<string, JsonValue>>),
  });
}

function parsePlan(value: unknown): AgentPlan {
  if (!isRecord(value) || !Array.isArray(value.steps)) invalid("plan");
  return Object.freeze({
    agent_id: stringValue(value, "agent_id"),
    agent_name: stringValue(value, "agent_name"),
    status: stringValue(value, "status"),
    objective: stringValue(value, "objective"),
    context_used: booleanValue(value, "context_used"),
    steps: Object.freeze(value.steps.map(parsePlanStep)),
    open_questions: stringArray(value.open_questions, "open_questions"),
    warnings: stringArray(value.warnings, "plan warnings"),
    requires_confirmation: booleanValue(value, "requires_confirmation"),
    execution_performed: booleanValue(value, "execution_performed"),
    metadata: scalarRecord(value.metadata, "plan metadata"),
  });
}

function parseReadinessReference(value: unknown): ToolReadiness {
  if (!isRecord(value)) invalid("readiness reference");
  const safe = value.safe;
  const confirmation = value.confirmation_required;
  if (safe !== null && typeof safe !== "boolean") invalid("safe");
  if (confirmation !== null && typeof confirmation !== "boolean") invalid("confirmation_required");
  return Object.freeze({
    tool_id: stringValue(value, "tool_id"),
    operation_id: stringValue(value, "operation_id"),
    target: safeRelative(nullableString(value, "target"), "readiness target"),
    registered: booleanValue(value, "registered"),
    enabled: booleanValue(value, "enabled"),
    safe,
    confirmation_required: confirmation,
    operation_exists: booleanValue(value, "operation_exists"),
    runtime_execution_allowed: booleanValue(value, "runtime_execution_allowed"),
    adapter_available: booleanValue(value, "adapter_available"),
    executable_now: booleanValue(value, "executable_now"),
    mutation_confirmation_required:
      value.mutation_confirmation_required === undefined
        ? false
        : booleanValue(value, "mutation_confirmation_required"),
    preview_required:
      value.preview_required === undefined ? false : booleanValue(value, "preview_required"),
    blocking_reasons:
      value.blocking_reasons === undefined
        ? Object.freeze([])
        : stringArray(value.blocking_reasons, "blocking_reasons"),
    execution_enabled: booleanValue(value, "execution_enabled"),
  });
}

function parseReadiness(value: unknown): PlanReadiness {
  if (!isRecord(value) || !Array.isArray(value.references)) invalid("readiness");
  return Object.freeze({
    ready: booleanValue(value, "ready"),
    references: Object.freeze(value.references.map(parseReadinessReference)),
    execution_enabled: booleanValue(value, "execution_enabled"),
  });
}

function parseMatch(value: unknown): AgentMatch {
  if (!isRecord(value)) invalid("agent match");
  return Object.freeze({
    agent_id: stringValue(value, "agent_id"),
    matched: booleanValue(value, "matched"),
    score: numberValue(value, "score"),
    matched_signals: stringArray(value.matched_signals, "matched_signals"),
    reasoning: stringArray(value.reasoning, "match reasoning"),
    priority: numberValue(value, "priority"),
  });
}

function parseSelectedAgent(value: unknown): { readonly id: string; readonly name: string } {
  if (!isRecord(value)) invalid("selected agent");
  return Object.freeze({ id: stringValue(value, "id"), name: stringValue(value, "name") });
}

function parseMatches(value: unknown): readonly AgentMatch[] {
  if (!Array.isArray(value)) invalid("agent matches");
  return Object.freeze(value.map(parseMatch));
}

export function parsePlanningResponse(value: unknown): AgentPlanningResponse {
  if (!isRecord(value) || !isRecord(value.routing)) invalid("planning response");
  const selected = value.routing.selected_agent;
  if (selected !== null && !isRecord(selected)) invalid("selected_agent");
  return Object.freeze({
    status: stringValue(value, "status"),
    routing: Object.freeze({
      selected_agent: selected === null ? null : parseSelectedAgent(selected),
      match: value.routing.match === null ? null : parseMatch(value.routing.match),
      matches: parseMatches(value.routing.matches),
      preferred_agent_rejected: booleanValue(value.routing, "preferred_agent_rejected"),
    }),
    context: value.context === null ? null : parseContext(value.context),
    plan: value.plan === null ? null : parsePlan(value.plan),
    readiness: value.readiness === null ? null : parseReadiness(value.readiness),
  });
}

export function parsePlanReview(value: unknown): PlanReview {
  if (!isRecord(value)) invalid("plan review");
  const status = stringValue(value, "status") as PlanReviewStatus;
  if (!REVIEW_STATUSES.has(status)) invalid("review status");
  return Object.freeze({
    review_id: stringValue(value, "review_id"),
    status,
    created_at: timestamp(value, "created_at"),
    expires_at: timestamp(value, "expires_at"),
    updated_at: timestamp(value, "updated_at"),
    instruction: stringValue(value, "instruction"),
    selected_agent_id: stringValue(value, "selected_agent_id"),
    routing: parseReviewRouting(value.routing),
    context: parseContext(value.context),
    plan: parsePlan(value.plan),
    snapshot_digest: stringValue(value, "snapshot_digest"),
    execution_authorized: booleanValue(value, "execution_authorized"),
    execution_performed: booleanValue(value, "execution_performed"),
    mutation_performed:
      value.mutation_performed === undefined ? false : booleanValue(value, "mutation_performed"),
    approved_at: nullableTimestamp(value, "approved_at"),
    rejected_at: nullableTimestamp(value, "rejected_at"),
    cancelled_at: nullableTimestamp(value, "cancelled_at"),
    expired_at: nullableTimestamp(value, "expired_at"),
    reviewer_note: nullableString(value, "reviewer_note"),
    rejection_reason: nullableString(value, "rejection_reason"),
    cancellation_reason: nullableString(value, "cancellation_reason"),
    approval_warning: nullableString(value, "approval_warning"),
    metadata: scalarRecord(value.metadata, "review metadata"),
    readiness: parseReadiness(value.readiness),
  });
}

function parseReviewRouting(value: unknown): PlanReview["routing"] {
  if (
    !isRecord(value) ||
    !isRecord(value.request) ||
    !isRecord(value.result)
  ) {
    invalid("review routing");
  }
  const request = value.request;
  const result = value.result;
  return Object.freeze({
    request: Object.freeze({
      instruction: stringValue(request, "instruction"),
      intent: nullableString(request, "intent"),
      context: scalarRecord(request.context, "routing context"),
      preferred_agent_id: nullableString(request, "preferred_agent_id"),
      allow_execution: booleanValue(request, "allow_execution"),
    }),
    selected_agent: parseSelectedAgent(value.selected_agent),
    match: parseMatch(value.match),
    matches: parseMatches(value.matches),
    result: Object.freeze({
      agent_id: stringValue(result, "agent_id"),
      agent_name: stringValue(result, "agent_name"),
      status: stringValue(result, "status"),
      summary: stringValue(result, "summary"),
      proposed_actions: stringArray(result.proposed_actions, "proposed_actions"),
      warnings: stringArray(result.warnings, "result warnings"),
      requires_confirmation: booleanValue(result, "requires_confirmation"),
      execution_performed: booleanValue(result, "execution_performed"),
      metadata: scalarRecord(result.metadata, "result metadata"),
    }),
    preferred_agent_rejected: booleanValue(value, "preferred_agent_rejected"),
  });
}

function parseToolResult(value: unknown): ToolResult {
  if (!isRecord(value) || !isRecord(value.structured_data)) invalid("tool result");
  return Object.freeze({
    tool_id: stringValue(value, "tool_id"),
    operation_id: stringValue(value, "operation_id"),
    success: booleanValue(value, "success"),
    started_at: timestamp(value, "started_at"),
    completed_at: timestamp(value, "completed_at"),
    duration_ms: numberValue(value, "duration_ms"),
    output: stringValue(value, "output"),
    structured_data: jsonValue(value.structured_data) as Readonly<Record<string, JsonValue>>,
    error_code: nullableString(value, "error_code"),
    error_message: nullableString(value, "error_message"),
    truncated: booleanValue(value, "truncated"),
    execution_performed: booleanValue(value, "execution_performed"),
    mutation_performed:
      value.mutation_performed === undefined ? false : booleanValue(value, "mutation_performed"),
  });
}

function parseStep(value: unknown): StepExecutionRecord {
  if (!isRecord(value)) invalid("execution step");
  const status = stringValue(value, "status") as StepExecutionStatus;
  if (!STEP_STATUSES.has(status)) invalid("step status");
  return Object.freeze({
    step_index: numberValue(value, "step_index"),
    tool_id: stringValue(value, "tool_id"),
    operation_id: stringValue(value, "operation_id"),
    target: safeRelative(nullableString(value, "target"), "execution target"),
    status,
    started_at: nullableTimestamp(value, "started_at"),
    completed_at: nullableTimestamp(value, "completed_at"),
    result: value.result === null ? null : parseToolResult(value.result),
    error: nullableString(value, "error"),
    execution_performed: booleanValue(value, "execution_performed"),
  });
}

function parseAuditEvent(value: unknown): AuditEvent {
  if (!isRecord(value)) invalid("audit event");
  return Object.freeze({
    event_id: stringValue(value, "event_id"),
    event_type: stringValue(value, "event_type"),
    timestamp: timestamp(value, "timestamp"),
    execution_id: stringValue(value, "execution_id"),
    review_id: stringValue(value, "review_id"),
    step_index: nullableNumber(value, "step_index"),
    tool_id: nullableString(value, "tool_id"),
    operation_id: nullableString(value, "operation_id"),
    outcome: stringValue(value, "outcome"),
    safe_message: stringValue(value, "safe_message"),
    metadata: scalarRecord(value.metadata, "audit metadata"),
  });
}

export function parseExecutionRecord(value: unknown): ExecutionRecord {
  if (!isRecord(value) || !Array.isArray(value.step_records) || !Array.isArray(value.audit_events)) {
    invalid("execution record");
  }
  const status = stringValue(value, "status") as ExecutionStatus;
  if (!EXECUTION_STATUSES.has(status)) invalid("execution status");
  const steps = value.step_records.map(parseStep);
  const events = value.audit_events.map(parseAuditEvent).sort((a, b) =>
    a.timestamp.localeCompare(b.timestamp),
  );
  const total = numberValue(value, "total_steps");
  if (steps.length !== total) invalid("total_steps");
  return Object.freeze({
    execution_id: stringValue(value, "execution_id"),
    review_id: stringValue(value, "review_id"),
    snapshot_digest: stringValue(value, "snapshot_digest"),
    status,
    created_at: timestamp(value, "created_at"),
    started_at: nullableTimestamp(value, "started_at"),
    completed_at: nullableTimestamp(value, "completed_at"),
    current_step_index: nullableNumber(value, "current_step_index"),
    total_steps: total,
    step_records: Object.freeze(steps),
    execution_performed: booleanValue(value, "execution_performed"),
    failure_reason: nullableString(value, "failure_reason"),
    audit_events: Object.freeze(events),
    warning: stringValue(value, "warning"),
  });
}

export function safeDisplayText(value: string, maximum = 20_000): string {
  return value
    .replace(/(?:\/Users|\/home|\/private|\/var\/folders)\/[\w.@%+~/-]+/g, "[local path redacted]")
    .replace(/[A-Za-z]:\\[^\s"']+/g, "[local path redacted]")
    .slice(0, maximum);
}

const PREVIEW_STATUSES = new Set<MutationPreviewStatus>([
  "pending_confirmation",
  "confirmed",
  "expired",
  "cancelled",
  "consumed",
]);

export function parseMutationPreview(value: unknown): MutationPreview {
  if (
    !isRecord(value) ||
    !isRecord(value.normalized_arguments) ||
    !isRecord(value.before_state) ||
    !isRecord(value.proposed_after_state)
  ) invalid("mutation preview");
  const previewStatus = stringValue(value, "status") as MutationPreviewStatus;
  if (!PREVIEW_STATUSES.has(previewStatus)) invalid("mutation preview status");
  return Object.freeze({
    preview_id: stringValue(value, "preview_id"),
    execution_id: stringValue(value, "execution_id"),
    review_id: stringValue(value, "review_id"),
    step_index: numberValue(value, "step_index"),
    tool_id: stringValue(value, "tool_id"),
    operation_id: stringValue(value, "operation_id"),
    target: safeRelative(nullableString(value, "target"), "mutation target"),
    normalized_arguments: jsonValue(value.normalized_arguments) as Readonly<Record<string, JsonValue>>,
    before_state: jsonValue(value.before_state) as Readonly<Record<string, JsonValue>>,
    proposed_after_state: jsonValue(value.proposed_after_state) as Readonly<Record<string, JsonValue>>,
    diff_preview: stringValue(value, "diff_preview"),
    preview_digest: stringValue(value, "preview_digest"),
    confirmation_phrase: stringValue(value, "confirmation_phrase"),
    created_at: timestamp(value, "created_at"),
    expires_at: timestamp(value, "expires_at"),
    status: previewStatus,
    warning: stringValue(value, "warning"),
  });
}

function invalid(field: string): never {
  throw new Error(`The core returned an invalid ${field}.`);
}
