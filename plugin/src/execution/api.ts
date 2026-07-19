import { parseExecutionRecord, parseMutationPreview, parsePlanningResponse, parsePlanReview } from "./contracts";
import type {
  AgentPlanningResponse,
  ExecutionRecord,
  PlanReview,
  StepExecutionControls,
  MutationPreview,
} from "./types";

export type CoreMethod = "GET" | "POST";
export type CoreTransport = (
  path: string,
  method: CoreMethod,
  body: Readonly<Record<string, unknown>> | undefined,
  timeoutMs: number,
) => Promise<unknown>;

export class ExecutionApiClient {
  constructor(
    private readonly transport: CoreTransport,
    private readonly timeoutMs = 10_000,
  ) {}

  async generatePlan(instruction: string): Promise<AgentPlanningResponse> {
    return parsePlanningResponse(
      await this.transport(
        "/api/agents/plan",
        "POST",
        { instruction, include_context: true, allow_execution: false },
        this.timeoutMs,
      ),
    );
  }

  async createReview(instruction: string): Promise<PlanReview> {
    return parsePlanReview(
      await this.transport(
        "/api/agents/plan-reviews",
        "POST",
        { instruction, include_context: true, allow_execution: false },
        this.timeoutMs,
      ),
    );
  }

  async getReview(reviewId: string): Promise<PlanReview> {
    return parsePlanReview(
      await this.transport(`/api/agents/plan-reviews/${encodeURIComponent(reviewId)}`, "GET", undefined, this.timeoutMs),
    );
  }

  async approveReview(reviewId: string): Promise<PlanReview> {
    return this.reviewAction(reviewId, "approve", {});
  }

  async rejectReview(reviewId: string, reason: string): Promise<PlanReview> {
    return this.reviewAction(reviewId, "reject", { reason });
  }

  async cancelReview(reviewId: string): Promise<PlanReview> {
    return this.reviewAction(reviewId, "cancel", {});
  }

  async createExecution(reviewId: string): Promise<ExecutionRecord> {
    return parseExecutionRecord(
      await this.transport("/api/executions", "POST", { review_id: reviewId }, this.timeoutMs),
    );
  }

  async getExecution(executionId: string): Promise<ExecutionRecord> {
    return parseExecutionRecord(
      await this.transport(`/api/executions/${encodeURIComponent(executionId)}`, "GET", undefined, this.timeoutMs),
    );
  }

  async executeStep(
    executionId: string,
    stepIndex: number,
    controls: StepExecutionControls,
  ): Promise<ExecutionRecord> {
    return parseExecutionRecord(
      await this.transport(
        `/api/executions/${encodeURIComponent(executionId)}/steps/${stepIndex}/execute`,
        "POST",
        {
          timeout_seconds: controls.timeout_seconds,
          max_output_chars: controls.max_output_chars,
        },
        Math.max(this.timeoutMs, Math.ceil(controls.timeout_seconds * 1000) + 2000),
      ),
    );
  }

  async cancelExecution(executionId: string): Promise<ExecutionRecord> {
    return parseExecutionRecord(
      await this.transport(
        `/api/executions/${encodeURIComponent(executionId)}/cancel`,
        "POST",
        {},
        this.timeoutMs,
      ),
    );
  }

  async createMutationPreview(executionId: string, stepIndex: number): Promise<MutationPreview> {
    return parseMutationPreview(await this.transport(
      `/api/executions/${encodeURIComponent(executionId)}/steps/${stepIndex}/mutation-preview`,
      "POST", {}, this.timeoutMs,
    ));
  }

  async confirmMutation(
    executionId: string,
    stepIndex: number,
    preview: MutationPreview,
    confirmationPhrase: string,
  ): Promise<ExecutionRecord> {
    return parseExecutionRecord(await this.transport(
      `/api/executions/${encodeURIComponent(executionId)}/steps/${stepIndex}/confirm-mutation`,
      "POST",
      {
        preview_id: preview.preview_id,
        preview_digest: preview.preview_digest,
        confirmation_phrase: confirmationPhrase,
      },
      this.timeoutMs,
    ));
  }

  async cancelMutationPreview(executionId: string, stepIndex: number): Promise<MutationPreview> {
    return parseMutationPreview(await this.transport(
      `/api/executions/${encodeURIComponent(executionId)}/steps/${stepIndex}/cancel-mutation-preview`,
      "POST", {}, this.timeoutMs,
    ));
  }

  private async reviewAction(
    reviewId: string,
    action: "approve" | "reject" | "cancel",
    body: Readonly<Record<string, unknown>>,
  ): Promise<PlanReview> {
    return parsePlanReview(
      await this.transport(
        `/api/agents/plan-reviews/${encodeURIComponent(reviewId)}/${action}`,
        "POST",
        body,
        this.timeoutMs,
      ),
    );
  }
}
