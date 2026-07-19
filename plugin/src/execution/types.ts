export type JsonScalar = string | number | boolean | null;
export type JsonValue = JsonScalar | readonly JsonValue[] | { readonly [key: string]: JsonValue };

export interface AgentToolReference {
  readonly tool_id: string;
  readonly operation_id: string;
  readonly target: string | null;
}

export interface AgentPlanStep {
  readonly order: number;
  readonly title: string;
  readonly description: string;
  readonly source_memory_ids: readonly string[];
  readonly proposed_action: string;
  readonly requires_confirmation: boolean;
  readonly execution_available: boolean;
  readonly warnings: readonly string[];
  readonly tool_reference: AgentToolReference;
  readonly operation_input: Readonly<Record<string, JsonValue>> | null;
}

export interface AgentPlan {
  readonly agent_id: string;
  readonly agent_name: string;
  readonly status: string;
  readonly objective: string;
  readonly context_used: boolean;
  readonly steps: readonly AgentPlanStep[];
  readonly open_questions: readonly string[];
  readonly warnings: readonly string[];
  readonly requires_confirmation: boolean;
  readonly execution_performed: boolean;
  readonly metadata: Readonly<Record<string, JsonScalar>>;
}

export interface AgentMemoryReference {
  readonly memory_id: string;
  readonly name: string;
  readonly kind: string;
  readonly layer: string;
  readonly title: string;
  readonly relative_path: string;
  readonly reason_selected: string;
  readonly excerpt: string;
  readonly excerpt_truncated: boolean;
  readonly modified_at: string | null;
  readonly excerpt_strategy: string;
  readonly selected_headings: readonly string[];
}

export interface AgentContext {
  readonly agent_id: string;
  readonly instruction: string;
  readonly resolved_intent: string | null;
  readonly memory_references: readonly AgentMemoryReference[];
  readonly context_summary: string;
  readonly limitations: readonly string[];
  readonly metadata: Readonly<Record<string, JsonScalar>>;
}

export interface SelectedAgent {
  readonly id: string;
  readonly name: string;
}

export interface AgentMatch {
  readonly agent_id: string;
  readonly matched: boolean;
  readonly score: number;
  readonly matched_signals: readonly string[];
  readonly reasoning: readonly string[];
  readonly priority: number;
}

export interface AgentRequestSnapshot {
  readonly instruction: string;
  readonly intent: string | null;
  readonly context: Readonly<Record<string, JsonScalar>>;
  readonly preferred_agent_id: string | null;
  readonly allow_execution: boolean;
}

export interface AgentResultSnapshot {
  readonly agent_id: string;
  readonly agent_name: string;
  readonly status: string;
  readonly summary: string;
  readonly proposed_actions: readonly string[];
  readonly warnings: readonly string[];
  readonly requires_confirmation: boolean;
  readonly execution_performed: boolean;
  readonly metadata: Readonly<Record<string, JsonScalar>>;
}

export interface PlanningRouting {
  readonly selected_agent: SelectedAgent | null;
  readonly match: AgentMatch | null;
  readonly matches: readonly AgentMatch[];
  readonly preferred_agent_rejected: boolean;
}

export interface ReviewRouting {
  readonly request: AgentRequestSnapshot;
  readonly selected_agent: SelectedAgent;
  readonly match: AgentMatch;
  readonly matches: readonly AgentMatch[];
  readonly result: AgentResultSnapshot;
  readonly preferred_agent_rejected: boolean;
}

export interface ToolReadiness {
  readonly tool_id: string;
  readonly operation_id: string;
  readonly target: string | null;
  readonly registered: boolean;
  readonly enabled: boolean;
  readonly safe: boolean | null;
  readonly confirmation_required: boolean | null;
  readonly operation_exists: boolean;
  readonly runtime_execution_allowed: boolean;
  readonly adapter_available: boolean;
  readonly executable_now: boolean;
  readonly mutation_confirmation_required: boolean;
  readonly preview_required: boolean;
  readonly execution_enabled: boolean;
}

export interface PlanReadiness {
  readonly ready: boolean;
  readonly references: readonly ToolReadiness[];
  readonly execution_enabled: boolean;
}

export interface AgentPlanningResponse {
  readonly status: string;
  readonly routing: PlanningRouting;
  readonly context: AgentContext | null;
  readonly plan: AgentPlan | null;
  readonly readiness: PlanReadiness | null;
}

export type PlanReviewStatus =
  | "pending_review"
  | "approved"
  | "rejected"
  | "cancelled"
  | "expired";

export interface PlanReview {
  readonly review_id: string;
  readonly status: PlanReviewStatus;
  readonly created_at: string;
  readonly expires_at: string;
  readonly updated_at: string;
  readonly instruction: string;
  readonly selected_agent_id: string;
  readonly routing: ReviewRouting;
  readonly context: AgentContext;
  readonly plan: AgentPlan;
  readonly snapshot_digest: string;
  readonly execution_authorized: boolean;
  readonly execution_performed: boolean;
  readonly mutation_performed: boolean;
  readonly approved_at: string | null;
  readonly rejected_at: string | null;
  readonly cancelled_at: string | null;
  readonly expired_at: string | null;
  readonly reviewer_note: string | null;
  readonly rejection_reason: string | null;
  readonly cancellation_reason: string | null;
  readonly approval_warning: string | null;
  readonly metadata: Readonly<Record<string, JsonScalar>>;
  readonly readiness: PlanReadiness;
}

export type ExecutionStatus =
  | "pending_execution"
  | "running"
  | "completed"
  | "failed"
  | "cancelled";

export type StepExecutionStatus =
  | "pending"
  | "running"
  | "completed"
  | "failed"
  | "skipped"
  | "cancelled";

export interface ToolResult {
  readonly tool_id: string;
  readonly operation_id: string;
  readonly success: boolean;
  readonly started_at: string;
  readonly completed_at: string;
  readonly duration_ms: number;
  readonly output: string;
  readonly structured_data: Readonly<Record<string, JsonValue>>;
  readonly error_code: string | null;
  readonly error_message: string | null;
  readonly truncated: boolean;
  readonly execution_performed: boolean;
}

export interface StepExecutionRecord {
  readonly step_index: number;
  readonly tool_id: string;
  readonly operation_id: string;
  readonly target: string | null;
  readonly status: StepExecutionStatus;
  readonly started_at: string | null;
  readonly completed_at: string | null;
  readonly result: ToolResult | null;
  readonly error: string | null;
  readonly execution_performed: boolean;
}

export interface AuditEvent {
  readonly event_id: string;
  readonly event_type: string;
  readonly timestamp: string;
  readonly execution_id: string;
  readonly review_id: string;
  readonly step_index: number | null;
  readonly tool_id: string | null;
  readonly operation_id: string | null;
  readonly outcome: string;
  readonly safe_message: string;
  readonly metadata: Readonly<Record<string, JsonScalar>>;
}

export interface ExecutionRecord {
  readonly execution_id: string;
  readonly review_id: string;
  readonly snapshot_digest: string;
  readonly status: ExecutionStatus;
  readonly created_at: string;
  readonly started_at: string | null;
  readonly completed_at: string | null;
  readonly current_step_index: number | null;
  readonly total_steps: number;
  readonly step_records: readonly StepExecutionRecord[];
  readonly execution_performed: boolean;
  readonly failure_reason: string | null;
  readonly audit_events: readonly AuditEvent[];
  readonly warning: string;
}

export interface StepExecutionControls {
  readonly timeout_seconds: number;
  readonly max_output_chars: number;
}

export type MutationPreviewStatus =
  | "pending_confirmation"
  | "confirmed"
  | "expired"
  | "cancelled"
  | "consumed";

export interface MutationPreview {
  readonly preview_id: string;
  readonly execution_id: string;
  readonly review_id: string;
  readonly step_index: number;
  readonly tool_id: string;
  readonly operation_id: string;
  readonly target: string | null;
  readonly normalized_arguments: Readonly<Record<string, JsonValue>>;
  readonly before_state: Readonly<Record<string, JsonValue>>;
  readonly proposed_after_state: Readonly<Record<string, JsonValue>>;
  readonly diff_preview: string;
  readonly preview_digest: string;
  readonly confirmation_phrase: string;
  readonly created_at: string;
  readonly expires_at: string;
  readonly status: MutationPreviewStatus;
  readonly warning: string;
}
