import type { CaucoCoreClient } from "../services/CaucoCoreClient";
import { CaucoCoreApiError } from "../services/CaucoCoreClient";
import { executionErrorMessage } from "../execution/errors";
import { safeDisplayText } from "../execution/contracts";
import {
  acceptNewPlan,
  armStepConfirmation,
  beginNewPlan,
  clearConfirmation,
  initialExecutionUiState,
  mayCancelExecution,
  mayCreateExecution,
  mayCreateReview,
  mayExecuteStep,
  maySubmitConfirmedStep,
  readinessForStep,
  type ExecutionUiState,
  type PendingAction,
} from "../execution/state";
import type {
  AgentPlan,
  PlanReadiness,
  StepExecutionRecord,
} from "../execution/types";
import { renderAuditTrail, renderToolResult } from "./CaucoExecutionResults";
import { renderPlanContext, renderPlanSteps } from "./CaucoPlanDetails";
import {
  addBadge,
  addDetail,
  formatTimestamp,
  renderSafeError,
  renderWarnings,
  shortId,
  statusLabel,
} from "./executionViewHelpers";

const DEFAULT_TIMEOUT_SECONDS = 5;
const DEFAULT_OUTPUT_CHARS = 20_000;

export class CaucoExecutionPanel {
  private readonly state: ExecutionUiState = initialExecutionUiState();
  private root: HTMLElement | null = null;
  private replacementArmed = false;
  private getGeneration = 0;

  constructor(private readonly client: CaucoCoreClient) {}

  render(container: HTMLElement): void {
    this.root = container.createEl("section", { cls: "cauco-execution-control" });
    this.renderPanel();
  }

  private renderPanel(): void {
    if (!this.root) return;
    const root = this.root;
    root.empty();

    const header = root.createDiv({ cls: "cauco-panel-header" });
    header.createEl("h2", { text: "Plan and execution control" });
    header.createEl("span", { text: "Human-controlled · preview-first mutations" });
    root.createEl("p", {
      text: "Planning, approval, execution-record creation, and executing one step are separate actions. Nothing executes automatically.",
      cls: "cauco-trust-note",
    });

    const live = root.createEl("p", { text: this.state.statusMessage, cls: "cauco-lifecycle-status" });
    live.setAttribute("aria-live", "polite");
    live.setAttribute("aria-atomic", "true");
    if (this.state.error) {
      renderSafeError(root, this.state.error);
      const clear = root.createEl("button", {
        text: "Clear local error",
        attr: { type: "button" },
      });
      clear.addEventListener("click", () => {
        this.state.error = null;
        this.renderPanel();
      });
    }

    this.renderPlanning(root);
    if (this.state.plan?.plan) {
      this.renderPlan(root, this.state.plan.plan, this.currentReadiness());
      const context = this.state.review?.context ?? this.state.plan.context;
      if (context) renderPlanContext(root, context);
      this.renderReview(root);
    }
    if (this.state.review?.status === "approved" && !this.state.execution) this.renderExecutionCreation(root);
    if (this.state.execution) this.renderExecution(root);
  }

  private renderPlanning(root: HTMLElement): void {
    const section = root.createEl("section", { cls: "cauco-control-section" });
    section.createEl("h3", { text: "1. Instruction and planning" });
    const label = section.createEl("label", {
      text: "Instruction",
      cls: "cauco-field-label",
      attr: { for: "cauco-plan-instruction" },
    });
    const input = section.createEl("textarea", {
      cls: "cauco-plan-instruction",
      attr: {
        id: "cauco-plan-instruction",
        rows: "4",
        maxlength: "4000",
        placeholder: "Describe the repository inspection you want Cauco to plan…",
      },
    });
    label.insertAdjacentElement("afterend", input);
    input.value = this.state.instruction;
    input.disabled = this.state.pendingAction !== null;

    const actions = section.createDiv({ cls: "cauco-control-actions" });
    const generate = actions.createEl("button", {
      text: this.generateLabel(),
      cls: "mod-cta",
      attr: { type: "button" },
    });
    generate.disabled = this.state.pendingAction !== null || !input.value.trim();
    input.addEventListener("input", () => {
      this.state.instruction = input.value;
      this.replacementArmed = false;
      generate.disabled = this.state.pendingAction !== null || !input.value.trim();
      generate.setText(this.generateLabel());
    });
    input.addEventListener("keydown", (event) => {
      if (event.key === "Enter" && (event.metaKey || event.ctrlKey) && !generate.disabled) {
        event.preventDefault();
        this.startPlan(input.value.trim());
      }
    });
    generate.addEventListener("click", () => this.startPlan(input.value.trim()));

    if (this.replacementArmed) {
      section.createEl("p", {
        text: "Generating a new plan will replace only this local dashboard view. Existing reviews and executions remain in Core and are not cancelled or executed.",
        cls: "cauco-pending-note",
      });
    }

    const planned = this.state.plan;
    if (planned?.plan) {
      const summary = section.createEl("dl", { cls: "cauco-control-details" });
      addDetail(summary, "Status", planned.status);
      addDetail(summary, "Selected agent", planned.routing.selected_agent?.name ?? planned.plan.agent_name);
      addDetail(summary, "Intent", planned.context?.resolved_intent ?? "Not resolved");
      addDetail(summary, "Confidence score", planned.routing.match ? String(planned.routing.match.score) : "Unavailable");
      addDetail(summary, "Objective", planned.plan.objective);
      addDetail(summary, "Execution performed", planned.plan.execution_performed ? "Yes" : "No");
      renderWarnings(section, planned.plan.warnings);
    }
  }

  private startPlan(instruction: string): void {
    if (!instruction || this.state.pendingAction !== null) return;
    if ((this.state.review || this.state.execution) && !this.replacementArmed) {
      this.replacementArmed = true;
      this.state.statusMessage = "Review the plan-replacement notice, then confirm deliberately.";
      this.renderPanel();
      return;
    }
    this.replacementArmed = false;
    const generation = beginNewPlan(this.state, instruction);
    this.renderPanel();
    void this.client
      .generatePlan(instruction)
      .then((plan) => {
        if (acceptNewPlan(this.state, generation, plan)) this.renderPanel();
      })
      .catch((error: unknown) => this.finishError(generation, error, "planning"));
  }

  private renderPlan(root: HTMLElement, plan: AgentPlan, readiness: PlanReadiness | null): void {
    const section = root.createEl("section", { cls: "cauco-control-section" });
    const header = section.createDiv({ cls: "cauco-panel-header" });
    header.createEl("h3", { text: "2. Plan steps and readiness" });
    const refresh = header.createEl("button", {
      text: this.state.pendingAction === "refresh-review" ? "Refreshing…" : "Refresh readiness",
      attr: { type: "button" },
    });
    refresh.disabled = this.state.pendingAction !== null || this.state.review === null;
    refresh.addEventListener("click", () => void this.refreshReview());

    if (this.state.readinessRefreshedAt) {
      section.createEl("small", {
        text: `Last readiness refresh: ${formatTimestamp(this.state.readinessRefreshedAt)}`,
        cls: "cauco-response-meta",
      });
    }
    renderPlanSteps(section, plan, readiness);
  }

  private renderReview(root: HTMLElement): void {
    const section = root.createEl("section", { cls: "cauco-control-section" });
    section.createEl("h3", { text: "4. Plan review" });
    const review = this.state.review;
    if (!review) {
      section.createEl("p", {
        text: "Creating a review stores a review-only snapshot. It does not approve or execute the plan.",
        cls: "cauco-trust-note",
      });
      const create = section.createEl("button", {
        text: this.state.pendingAction === "create-review" ? "Creating review…" : "Create Review",
        cls: "mod-cta",
        attr: { type: "button" },
      });
      create.disabled = !mayCreateReview(this.state);
      create.addEventListener("click", () => void this.createReview());
      return;
    }

    const details = section.createEl("dl", { cls: "cauco-control-details" });
    addDetail(details, "Review", shortId(review.review_id));
    addDetail(details, "Status", statusLabel(review.status));
    addDetail(details, "Created", formatTimestamp(review.created_at));
    addDetail(details, "Expires", formatTimestamp(review.expires_at));
    addDetail(details, "Snapshot", shortId(review.snapshot_digest));
    addDetail(details, "Execution authorized", review.execution_authorized ? "Yes" : "No");
    addDetail(details, "Execution performed", review.execution_performed ? "Yes" : "No");
    if (review.approval_warning) section.createEl("p", { text: review.approval_warning, cls: "cauco-pending-note" });

    if (review.status === "pending_review") {
      section.createEl("p", {
        text: "Approving this plan authorizes creation of an execution record. It does not execute any tool.",
        cls: "cauco-pending-note",
      });
      const reason = section.createEl("input", {
        type: "text",
        cls: "cauco-review-reason",
        attr: { maxlength: "1000", placeholder: "Reason required when rejecting", "aria-label": "Review rejection reason" },
      });
      const actions = section.createDiv({ cls: "cauco-control-actions" });
      this.actionButton(actions, "Approve", "review-decision", () => this.decideReview("approve"));
      const reject = this.actionButton(actions, "Reject", "review-decision", () => this.decideReview("reject", reason.value.trim()));
      reject.disabled = this.state.pendingAction !== null || !reason.value.trim();
      reason.addEventListener("input", () => {
        reject.disabled = this.state.pendingAction !== null || !reason.value.trim();
      });
      this.actionButton(actions, "Cancel", "review-decision", () => this.decideReview("cancel"));
    }
  }

  private renderExecutionCreation(root: HTMLElement): void {
    const section = root.createEl("section", { cls: "cauco-control-section" });
    section.createEl("h3", { text: "5. Execution record" });
    if (!this.state.execution) {
      section.createEl("p", {
        text: "Creating an execution record performs no tool action.",
        cls: "cauco-pending-note",
      });
      const create = section.createEl("button", {
        text: this.state.pendingAction === "create-execution" ? "Creating record…" : "Create Execution Record",
        cls: "mod-cta",
        attr: { type: "button" },
      });
      create.disabled = !mayCreateExecution(this.state);
      create.addEventListener("click", () => void this.createExecution());
    }
  }

  private renderExecution(root: HTMLElement): void {
    const execution = this.state.execution;
    if (!execution) return;
    const section = root.createEl("section", { cls: "cauco-control-section" });
    const header = section.createDiv({ cls: "cauco-panel-header" });
    header.createEl("h3", { text: "6. Step-level execution" });
    const refresh = header.createEl("button", {
      text: this.state.pendingAction === "refresh-execution" ? "Refreshing…" : "Refresh Execution",
      attr: { type: "button" },
    });
    refresh.disabled = this.state.pendingAction !== null;
    refresh.addEventListener("click", () => void this.refreshExecution());

    const details = section.createEl("dl", { cls: "cauco-control-details" });
    addDetail(details, "Execution", shortId(execution.execution_id));
    addDetail(details, "Review", shortId(execution.review_id));
    addDetail(details, "State", statusLabel(execution.status));
    addDetail(details, "Steps", String(execution.total_steps));
    addDetail(details, "Execution performed", execution.execution_performed ? "Yes" : "No");
    addDetail(details, "Created", formatTimestamp(execution.created_at));
    if (execution.warning) section.createEl("p", { text: execution.warning, cls: "cauco-trust-note" });
    if (execution.failure_reason) renderSafeError(section, execution.failure_reason);

    if (mayCancelExecution(this.state)) {
      section.createEl("p", {
        text: "Cancellation is available only before a step starts in Phase 6C.",
        cls: "cauco-trust-note",
      });
      const cancel = section.createEl("button", { text: "Cancel Execution", attr: { type: "button" } });
      cancel.addEventListener("click", () => void this.cancelExecution());
    }

    const readiness = this.state.review?.readiness ?? null;
    for (const step of execution.step_records) this.renderExecutionStep(section, step, readiness);
    renderAuditTrail(section, execution.audit_events);
  }

  private renderExecutionStep(
    section: HTMLElement,
    step: StepExecutionRecord,
    readiness: PlanReadiness | null,
  ): void {
    const item = readinessForStep(readiness, step);
    const card = section.createEl("article", { cls: "cauco-step-card cauco-execution-step" });
    const heading = card.createDiv({ cls: "cauco-step-heading" });
    heading.createEl("h4", { text: `Step ${step.step_index}: ${step.tool_id}.${step.operation_id}` });
    addBadge(heading, statusLabel(step.status));
    const details = card.createEl("dl", { cls: "cauco-control-details" });
    addDetail(details, "Target", step.target ?? "Configured workspace");
    addDetail(
      details,
      "Readiness",
      item?.preview_required ? "Preview required" : item?.executable_now ? "Ready" : "Blocked",
    );
    addDetail(details, "Execution performed", step.execution_performed ? "Yes" : "No");
    if (item?.blocking_reasons.length) renderWarnings(card, item.blocking_reasons);
    if (step.error) renderSafeError(card, step.error);
    if (step.result) renderToolResult(card, step.result);

    if (item?.preview_required) {
      this.renderMutationControls(card, step);
      return;
    }

    if (!mayExecuteStep(this.state, step, item)) return;
    if (this.state.confirmingStep !== step.step_index) {
      const review = card.createEl("button", { text: "Review execution", attr: { type: "button" } });
      review.addEventListener("click", () => void this.prepareStep(step));
      return;
    }

    const confirmation = card.createDiv({ cls: "cauco-inline-confirmation" });
    confirmation.createEl("p", {
      text: `This will execute the approved read-only operation ${step.tool_id}.${step.operation_id} for this exact plan step.`,
    });
    const timeout = this.numberControl(confirmation, "Timeout seconds", DEFAULT_TIMEOUT_SECONDS, 0.1, 30, 0.1);
    const output = this.numberControl(confirmation, "Maximum output characters", DEFAULT_OUTPUT_CHARS, 100, 100_000, 100);
    const actions = confirmation.createDiv({ cls: "cauco-control-actions" });
    const execute = actions.createEl("button", {
      text: this.state.pendingAction === "execute-step" ? "Executing approved step…" : "Execute approved step",
      cls: "mod-cta",
      attr: { type: "button" },
    });
    execute.disabled = this.state.pendingAction !== null;
    execute.addEventListener("click", () => {
      const timeoutSeconds = Number(timeout.value);
      const maxOutputChars = Number(output.value);
      if (timeoutSeconds < 0.1 || timeoutSeconds > 30 || maxOutputChars < 100 || maxOutputChars > 100_000) {
        this.state.error = "Execution controls are outside the allowed bounds.";
        this.renderPanel();
        return;
      }
      void this.executeStep(step.step_index, timeoutSeconds, maxOutputChars);
    });
    const back = actions.createEl("button", { text: "Back", attr: { type: "button" } });
    back.addEventListener("click", () => {
      clearConfirmation(this.state);
      this.renderPanel();
    });
  }

  private renderMutationControls(card: HTMLElement, step: StepExecutionRecord): void {
    const staging = step.tool_id === "git" && step.operation_id === "add";
    const committing = step.tool_id === "git" && step.operation_id === "commit";
    card.createEl("p", {
      text: staging
        ? "Creating this preview does not modify the Git index."
        : "Mutation requires preview and confirmation. Approval and preview creation do not change persistent state; confirmation is single-use.",
      cls: "cauco-trust-note",
    });
    if (step.status !== "pending") return;
    const preview = this.state.mutationPreview?.step_index === step.step_index
      ? this.state.mutationPreview
      : null;
    if (!preview) {
      const create = card.createEl("button", {
        text: this.state.pendingAction === "create-mutation-preview"
          ? "Creating inert preview…"
          : staging ? "Create Staging Preview" : committing ? "Create Commit Preview" : "Create Mutation Preview",
        attr: { type: "button" },
      });
      create.disabled = this.state.pendingAction !== null;
      create.addEventListener("click", () => void this.createMutationPreview(step.step_index));
      return;
    }
    const details = card.createEl("dl", { cls: "cauco-control-details" });
    const repository = preview.before_state.repository_label;
    addDetail(details, staging ? "Repository" : "Target", staging && typeof repository === "string"
      ? repository
      : preview.target ?? "Controlled memory proposal store");
    addDetail(details, "Status", statusLabel(preview.status));
    addDetail(details, "Expires", formatTimestamp(preview.expires_at));
    addDetail(details, "Preview digest", preview.preview_digest.slice(0, 12));
    if (staging || committing) {
      const paths = staging ? preview.proposed_after_state.paths : preview.proposed_after_state.expected_staged_paths;
      addDetail(details, "Path count", String(preview.proposed_after_state.path_count ?? 0));
      const list = card.createEl("ul", { cls: "cauco-result-list" });
      if (Array.isArray(paths)) for (const path of paths) {
        if (typeof path === "string") list.createEl("li", { text: safeDisplayText(path, 500) });
      }
    }
    if (committing) {
      addDetail(details, "Commit message", String(preview.proposed_after_state.commit_message ?? ""));
      addDetail(details, "Branch", String(preview.before_state.current_branch ?? ""));
      addDetail(details, "Staged tree", String(preview.before_state.staged_tree_id ?? "").slice(0, 12));
      card.createEl("p", { text: "This creates one local Git commit. It does not stage additional files or push to a remote. Local Git hooks may run during commit.", cls: "cauco-trust-note" });
    }
    const policy = preview.proposed_after_state.overwrite_policy;
    if (typeof policy === "string") addDetail(details, "Write policy", policy);
    const characters = preview.proposed_after_state.characters;
    if (typeof characters === "number") addDetail(details, "Characters", String(characters));
    card.createEl("p", { text: preview.warning, cls: "cauco-trust-note" });
    card.createEl("p", {
      text: staging
        ? "This stages only the exact approved files listed above. It does not create a commit or push anything."
        : committing ? "The commit message and staged paths are fixed and cannot be edited during confirmation."
        : "The target and approved content are fixed and cannot be edited during confirmation.",
      cls: "cauco-trust-note",
    });
    const diff = card.createEl("pre", { cls: "cauco-tool-output" });
    diff.createEl("code", { text: preview.diff_preview || "No textual change (duplicate prevention may apply)." });
    const label = card.createEl("label", {
      text: `Enter exactly: ${preview.confirmation_phrase}`,
      cls: "cauco-field-label",
    });
    const phrase = card.createEl("input", {
      attr: { type: "text", autocomplete: "off", spellcheck: "false" },
    });
    label.insertAdjacentElement("afterend", phrase);
    const actions = card.createDiv({ cls: "cauco-control-actions" });
    const confirm = actions.createEl("button", {
      text: this.state.pendingAction === "confirm-mutation"
        ? "Applying exact mutation…"
        : staging ? "Stage Approved Files" : committing ? "Create Approved Commit" : "Confirm and Apply Mutation",
      cls: "mod-cta",
      attr: { type: "button" },
    });
    confirm.disabled = true;
    phrase.addEventListener("input", () => {
      confirm.disabled = phrase.value !== preview.confirmation_phrase || this.state.pendingAction !== null;
    });
    confirm.addEventListener("click", () => void this.confirmMutation(step.step_index, phrase.value));
    const cancel = actions.createEl("button", { text: "Cancel Preview", attr: { type: "button" } });
    cancel.disabled = this.state.pendingAction !== null;
    cancel.addEventListener("click", () => void this.cancelMutationPreview(step.step_index));
  }

  private async createReview(): Promise<void> {
    if (!mayCreateReview(this.state)) return;
    this.beginAction("create-review", "Creating a review snapshot. No approval or execution is occurring.");
    try {
      this.state.review = await this.client.createPlanReview(this.state.instruction);
      this.state.plan = {
        status: "planned",
        routing: {
          selected_agent: { id: this.state.review.selected_agent_id, name: this.state.review.plan.agent_name },
          match: this.state.review.routing.match,
          matches: this.state.review.routing.matches,
          preferred_agent_rejected: false,
        },
        context: this.state.review.context,
        plan: this.state.review.plan,
        readiness: this.state.review.readiness,
      };
      this.state.readinessRefreshedAt = new Date().toISOString();
      this.finishAction("Review created. It remains pending and no tool was executed.");
    } catch (error) {
      this.actionError(error, "The review could not be created.");
    }
  }

  private async decideReview(action: "approve" | "reject" | "cancel", reason = ""): Promise<void> {
    const review = this.state.review;
    if (!review || review.status !== "pending_review" || this.state.pendingAction !== null) return;
    if (action === "reject" && !reason) return;
    this.beginAction("review-decision", `${statusLabel(action)} request in progress. No tool is executing.`);
    try {
      this.state.review =
        action === "approve"
          ? await this.client.approvePlanReview(review.review_id)
          : action === "reject"
            ? await this.client.rejectPlanReview(review.review_id, reason)
            : await this.client.cancelPlanReview(review.review_id);
      this.state.readinessRefreshedAt = new Date().toISOString();
      this.finishAction(
        action === "approve"
          ? "Plan approved. Approval did not execute a tool; execution-record creation is a separate action."
          : `Plan ${action === "reject" ? "rejected" : "cancelled"}. No tool was executed.`,
      );
    } catch (error) {
      this.actionError(error, "The review lifecycle action failed.");
    }
  }

  private async refreshReview(): Promise<void> {
    const review = this.state.review;
    if (!review || this.state.pendingAction !== null) return;
    const generation = ++this.getGeneration;
    this.beginAction("refresh-review", "Refreshing review and readiness from Core.");
    try {
      const refreshed = await this.client.getPlanReview(review.review_id);
      if (generation !== this.getGeneration) return;
      this.state.review = refreshed;
      this.state.readinessRefreshedAt = new Date().toISOString();
      clearConfirmation(this.state);
      this.finishAction("Review and readiness refreshed manually.");
    } catch (error) {
      if (generation === this.getGeneration) this.actionError(error, "Readiness refresh failed.");
    }
  }

  private async createExecution(): Promise<void> {
    const review = this.state.review;
    if (!review || !mayCreateExecution(this.state)) return;
    this.beginAction("create-execution", "Creating an inert execution record. No tool is executing.");
    try {
      this.state.execution = await this.client.createExecution(review.review_id);
      this.finishAction("Execution record created. No tool action was performed.");
    } catch (error) {
      this.actionError(error, "The execution record could not be created.");
    }
  }

  private async refreshExecution(): Promise<void> {
    const execution = this.state.execution;
    if (!execution || this.state.pendingAction !== null) return;
    const generation = ++this.getGeneration;
    this.beginAction("refresh-execution", "Refreshing execution state manually.");
    try {
      const refreshed = await this.client.getExecution(execution.execution_id);
      if (generation !== this.getGeneration) return;
      this.state.execution = refreshed;
      clearConfirmation(this.state);
      this.finishAction("Execution state refreshed manually.");
    } catch (error) {
      if (generation === this.getGeneration) this.actionError(error, "Execution refresh failed.");
    }
  }

  private async prepareStep(step: StepExecutionRecord): Promise<void> {
    const review = this.state.review;
    if (!review || this.state.pendingAction !== null) return;
    this.beginAction("refresh-review", "Rechecking tool readiness before confirmation.");
    try {
      this.state.review = await this.client.getPlanReview(review.review_id);
      this.state.readinessRefreshedAt = new Date().toISOString();
      const readiness = readinessForStep(this.state.review.readiness, step);
      this.state.pendingAction = null;
      if (!mayExecuteStep(this.state, step, readiness)) {
        this.state.statusMessage = "Core reports that this step is not currently executable.";
      } else {
        armStepConfirmation(this.state, step.step_index);
        this.state.statusMessage = "Review the exact read-only operation, then confirm with the second button.";
      }
      this.renderPanel();
    } catch (error) {
      this.actionError(error, "Readiness could not be verified before execution.");
    }
  }

  private async executeStep(stepIndex: number, timeoutSeconds: number, maxOutputChars: number): Promise<void> {
    const execution = this.state.execution;
    if (!execution || !maySubmitConfirmedStep(this.state, stepIndex)) return;
    this.beginAction("execute-step", "Executing exactly one explicitly confirmed read-only step.");
    try {
      this.state.execution = await this.client.executeStep(execution.execution_id, stepIndex, {
        timeout_seconds: timeoutSeconds,
        max_output_chars: maxOutputChars,
      });
      clearConfirmation(this.state);
      this.finishAction("The selected step finished. Its real result and audit events are shown below.");
    } catch (error) {
      clearConfirmation(this.state);
      this.actionError(error, "The selected step did not complete.");
    }
  }

  private async cancelExecution(): Promise<void> {
    const execution = this.state.execution;
    if (!execution || !mayCancelExecution(this.state)) return;
    this.beginAction("cancel-execution", "Cancelling the pending execution record.");
    try {
      this.state.execution = await this.client.cancelExecution(execution.execution_id);
      clearConfirmation(this.state);
      this.finishAction("Execution cancelled before a step started.");
    } catch (error) {
      this.actionError(error, "The pending execution could not be cancelled.");
    }
  }

  private async createMutationPreview(stepIndex: number): Promise<void> {
    const execution = this.state.execution;
    if (!execution || this.state.pendingAction !== null) return;
    this.beginAction("create-mutation-preview", "Creating an inert mutation preview. No write is occurring.");
    try {
      this.state.mutationPreview = await this.client.createMutationPreview(execution.execution_id, stepIndex);
      this.finishAction("Mutation preview created. Persistent state has not changed.");
    } catch (error) {
      this.actionError(error, "The mutation preview could not be created.");
    }
  }

  private async confirmMutation(stepIndex: number, phrase: string): Promise<void> {
    const execution = this.state.execution;
    const preview = this.state.mutationPreview;
    if (!execution || !preview || this.state.pendingAction !== null) return;
    this.beginAction("confirm-mutation", "Applying exactly the confirmed previewed mutation.");
    try {
      this.state.execution = await this.client.confirmMutation(
        execution.execution_id, stepIndex, preview, phrase,
      );
      this.state.mutationPreview = null;
      this.finishAction("Mutation adapter finished; verification result and audit events are shown below.");
    } catch (error) {
      this.actionError(error, "The mutation was not applied.");
    }
  }

  private async cancelMutationPreview(stepIndex: number): Promise<void> {
    const execution = this.state.execution;
    if (!execution || this.state.pendingAction !== null) return;
    this.beginAction("cancel-mutation-preview", "Cancelling the pending mutation preview.");
    try {
      await this.client.cancelMutationPreview(execution.execution_id, stepIndex);
      this.state.mutationPreview = null;
      this.finishAction("Mutation preview cancelled. No mutation was performed.");
    } catch (error) {
      this.actionError(error, "The mutation preview could not be cancelled.");
    }
  }

  private beginAction(action: PendingAction, message: string): void {
    this.state.pendingAction = action;
    this.state.error = null;
    this.state.statusMessage = message;
    this.renderPanel();
  }

  private finishAction(message: string): void {
    this.state.pendingAction = null;
    this.state.error = null;
    this.state.statusMessage = message;
    this.renderPanel();
  }

  private actionError(error: unknown, fallback: string): void {
    this.state.pendingAction = null;
    this.state.error = this.errorMessage(error, fallback);
    this.state.statusMessage = "The requested action did not complete.";
    this.renderPanel();
  }

  private finishError(generation: number, error: unknown, action: string): void {
    if (generation !== this.state.requestGeneration) return;
    this.state.pendingAction = null;
    this.state.error = this.errorMessage(error, `The ${action} request failed.`);
    this.state.statusMessage = "No review, approval, or execution occurred.";
    this.renderPanel();
  }

  private errorMessage(error: unknown, fallback: string): string {
    if (!(error instanceof CaucoCoreApiError)) return `${fallback} Core returned an invalid response.`;
    return executionErrorMessage(error.kind, error.message);
  }

  private currentReadiness(): PlanReadiness | null {
    return this.state.review?.readiness ?? this.state.plan?.readiness ?? null;
  }

  private generateLabel(): string {
    if (this.state.pendingAction === "planning") return "Generating plan…";
    if ((this.state.review || this.state.execution) && !this.replacementArmed) return "Review New Plan";
    if (this.replacementArmed) return "Generate New Plan";
    return "Generate Plan";
  }

  private actionButton(
    container: HTMLElement,
    text: string,
    action: PendingAction,
    callback: () => void,
  ): HTMLButtonElement {
    const button = container.createEl("button", {
      text: this.state.pendingAction === action ? `${text}…` : text,
      attr: { type: "button" },
    });
    button.disabled = this.state.pendingAction !== null;
    button.addEventListener("click", callback);
    return button;
  }

  private numberControl(
    container: HTMLElement,
    labelText: string,
    value: number,
    minimum: number,
    maximum: number,
    step: number,
  ): HTMLInputElement {
    const label = container.createEl("label", { text: labelText, cls: "cauco-field-label" });
    const input = container.createEl("input", {
      type: "number",
      value: String(value),
      attr: { min: String(minimum), max: String(maximum), step: String(step) },
    });
    label.appendChild(input);
    return input;
  }

}
