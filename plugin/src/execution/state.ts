import type {
  AgentPlanningResponse,
  ExecutionRecord,
  PlanReadiness,
  PlanReview,
  StepExecutionRecord,
  ToolReadiness,
  MutationPreview,
} from "./types";

export type PendingAction =
  | "planning"
  | "create-review"
  | "review-decision"
  | "refresh-review"
  | "create-execution"
  | "refresh-execution"
  | "execute-step"
  | "cancel-execution"
  | "create-mutation-preview"
  | "confirm-mutation"
  | "cancel-mutation-preview";

export interface ExecutionUiState {
  instruction: string;
  plan: AgentPlanningResponse | null;
  review: PlanReview | null;
  execution: ExecutionRecord | null;
  pendingAction: PendingAction | null;
  confirmingStep: number | null;
  error: string | null;
  statusMessage: string;
  readinessRefreshedAt: string | null;
  requestGeneration: number;
  mutationPreview: MutationPreview | null;
}

export function initialExecutionUiState(): ExecutionUiState {
  return {
    instruction: "",
    plan: null,
    review: null,
    execution: null,
    pendingAction: null,
    confirmingStep: null,
    error: null,
    statusMessage: "No plan has been generated.",
    readinessRefreshedAt: null,
    requestGeneration: 0,
    mutationPreview: null,
  };
}

export function readinessForStep(
  readiness: PlanReadiness | null,
  step: StepExecutionRecord,
): ToolReadiness | null {
  if (!readiness) return null;
  return (
    readiness.references.find(
      (item) =>
        item.tool_id === step.tool_id &&
        item.operation_id === step.operation_id &&
        item.target === step.target,
    ) ?? null
  );
}

export function mayCreateReview(state: ExecutionUiState): boolean {
  return state.plan?.plan != null && state.review === null && state.pendingAction === null;
}

export function mayCreateExecution(state: ExecutionUiState): boolean {
  return (
    state.review?.status === "approved" &&
    state.review.execution_authorized &&
    reviewHasNotExpired(state.review.expires_at) &&
    state.execution === null &&
    state.pendingAction === null
  );
}

export function mayCancelExecution(state: ExecutionUiState): boolean {
  return state.execution?.status === "pending_execution" && state.pendingAction === null;
}

export function mayExecuteStep(
  state: ExecutionUiState,
  step: StepExecutionRecord,
  readiness: ToolReadiness | null,
): boolean {
  return (
    state.review?.status === "approved" &&
    state.review.execution_authorized &&
    reviewHasNotExpired(state.review.expires_at) &&
    state.execution !== null &&
    state.execution.status !== "cancelled" &&
    state.execution.status !== "completed" &&
    state.execution.status !== "failed" &&
    step.status === "pending" &&
    readiness?.executable_now === true &&
    state.pendingAction === null
  );
}

function reviewHasNotExpired(expiresAt: string): boolean {
  return Date.parse(expiresAt) > Date.now();
}

export function beginNewPlan(state: ExecutionUiState, instruction: string): number {
  state.instruction = instruction;
  state.pendingAction = "planning";
  state.confirmingStep = null;
  state.error = null;
  state.statusMessage = "Generating a plan. No review or execution is being performed.";
  state.requestGeneration += 1;
  return state.requestGeneration;
}

export function acceptNewPlan(
  state: ExecutionUiState,
  generation: number,
  plan: AgentPlanningResponse,
): boolean {
  if (generation !== state.requestGeneration) return false;
  state.plan = plan;
  state.review = null;
  state.execution = null;
  state.mutationPreview = null;
  state.pendingAction = null;
  state.confirmingStep = null;
  state.readinessRefreshedAt = new Date().toISOString();
  state.statusMessage = "Plan generated. It has not been reviewed, approved, or executed.";
  return true;
}

export function clearConfirmation(state: ExecutionUiState): void {
  state.confirmingStep = null;
}

export function armStepConfirmation(state: ExecutionUiState, stepIndex: number): boolean {
  if (state.pendingAction !== null) return false;
  state.confirmingStep = stepIndex;
  return true;
}

export function maySubmitConfirmedStep(state: ExecutionUiState, stepIndex: number): boolean {
  return state.pendingAction === null && state.confirmingStep === stepIndex;
}
