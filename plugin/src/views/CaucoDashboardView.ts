import { ItemView, WorkspaceLeaf } from "obsidian";
import { CAUCO_VIEW_TYPE } from "../constants";
import type CaucoPlugin from "../main";
import { CaucoCoreClient } from "../services/CaucoCoreClient";
import type { AIModel, CaucoStatus, ConnectionResult, StatusSection } from "../types";
import { CaucoMemoryPanel } from "./CaucoMemoryPanel";
import { CaucoExecutionPanel } from "./CaucoExecutionPanel";
import { CaucoPerceptionPanel } from "./CaucoPerceptionPanel";
import type { CognitiveCycleSnapshot } from "../cognitive/types";
import { GuidedActionModal } from "./GuidedActionModal";
import { ReasoningPlanningApiClient } from "../reasoning/api";
import { CaucoConversationPanel } from "./CaucoConversationPanel";

const SECTION_LABELS: Array<[keyof CaucoStatus, string]> = [
  ["runtime", "Runtime"],
  ["memory", "Memory"],
  ["agents", "Agents"],
  ["tools", "Tools"],
  ["scheduler", "Scheduler"],
];

export class CaucoDashboardView extends ItemView {
  private checking = false;
  private conversationPanel?: CaucoConversationPanel;

  constructor(leaf: WorkspaceLeaf, private readonly plugin: CaucoPlugin) {
    super(leaf);
  }

  override getViewType(): string {
    return CAUCO_VIEW_TYPE;
  }

  override getDisplayText(): string {
    return "Cauco Dashboard";
  }

  override getIcon(): string {
    return "layout-dashboard";
  }

  override async onOpen(): Promise<void> {
    await this.refresh();
  }

  override async onClose(): Promise<void> {
    this.conversationPanel?.dispose();
  }

  private async refresh(): Promise<void> {
    if (this.checking) return;
    this.checking = true;
    this.renderLoading();
    const client = new CaucoCoreClient(this.plugin.settings.coreUrl);
    const result = await client.checkConnection();
    this.checking = false;
    this.render(result);
  }

  private renderLoading(): void {
    const container = this.contentEl;
    container.empty();
    container.addClass("cauco-dashboard");
    container.createEl("p", { text: "Checking local services…", cls: "cauco-empty" });
  }

  private render(result: ConnectionResult): void {
    const container = this.contentEl;
    container.empty();
    container.addClass("cauco-dashboard");

    const header = container.createDiv({ cls: "cauco-header" });
    const heading = header.createDiv();
    heading.createEl("h1", { text: "Cauco" });
    heading.createEl("p", { text: "Local work orchestration status" });
    const button = header.createEl("button", { text: "Check connection", cls: "mod-cta" });
    button.setAttribute("aria-label", "Check connection to Cauco Core and Ollama");
    button.addEventListener("click", () => void this.refresh());

    this.renderConnection(container, result);
    this.renderCognitiveSections(container, result.connected);
    const grid = container.createDiv({ cls: "cauco-grid" });
    for (const [key, label] of SECTION_LABELS) {
      this.renderCard(grid, label, result.status[key]);
    }
    const client = new CaucoCoreClient(this.plugin.settings.coreUrl);
    new CaucoExecutionPanel(client).render(container);
    new CaucoPerceptionPanel(this.plugin.settings.coreUrl, result.connected).render(container);
    this.conversationPanel ??= new CaucoConversationPanel(
      new ReasoningPlanningApiClient(this.plugin.settings.coreUrl),
    );
    this.conversationPanel.render(container, result.connected);
    this.renderChat(container, result);
    new CaucoMemoryPanel(
      client,
      result.memoryFiles ?? [],
      result.memoryError,
    ).render(container);
  }

  private renderCognitiveSections(container: HTMLElement, connected: boolean): void {
    const section = container.createEl("section", { cls: "cauco-cognitive-dashboard" });
    section.createEl("h2", { text: "Cognitive state" });
    const tabs = section.createDiv({ cls: "cauco-dashboard-tabs" });
    const panels = new Map<string, HTMLElement>();
    for (const label of ["Overview", "Cognitive Cycle", "Learning", "Reflection", "Memory Candidates"]) {
      const button = tabs.createEl("button", { text: label, cls: "cauco-dashboard-tab" });
      const panel = section.createDiv({ cls: "cauco-dashboard-panel" });
      panel.createEl("h3", { text: label });
      panel.createEl("p", { text: connected ? "Loading…" : "Cauco Core is unavailable.", cls: "cauco-empty" });
      panels.set(label, panel);
      button.addEventListener("click", () => { for (const [name, item] of panels) item.toggleAttribute("hidden", name !== label); });
      panel.toggleAttribute("hidden", label !== "Overview");
    }
    this.renderOverview(panels.get("Overview")!, connected);
    if (connected) void this.loadCognitiveSections(panels);
  }

  private renderOverview(panel: HTMLElement, connected: boolean): void {
    panel.empty();
    panel.createEl("p", { text: connected ? "Core is reachable. Memory and runtime details are shown above." : "Start Cauco Core and use Check connection to retry.", cls: connected ? undefined : "cauco-empty" });
  }

  private async loadCognitiveSections(panels: Map<string, HTMLElement>): Promise<void> {
    const client = new CaucoCoreClient(this.plugin.settings.coreUrl);
    await Promise.all([
      this.loadLearning(panels.get("Learning")!, client),
      this.loadReflection(panels.get("Reflection")!, client),
      this.loadCandidates(panels.get("Memory Candidates")!, client),
      this.loadCycle(panels.get("Cognitive Cycle")!, client),
    ]);
  }

  private renderSafeError(panel: HTMLElement, error: unknown): void {
    panel.empty();
    panel.createEl("p", { text: error instanceof Error ? error.message : "Could not load this section.", cls: "cauco-error" });
  }

  private async loadCycle(panel: HTMLElement, client: CaucoCoreClient): Promise<void> {
    panel.empty();
    const input = panel.createEl("input", { type: "text", placeholder: "Enter review_id", cls: "cauco-cycle-input" });
    const button = panel.createEl("button", { text: "Load cycle", cls: "mod-cta" });
    const output = panel.createDiv({ cls: "cauco-dashboard-output" });
    output.createEl("p", { text: "Enter a review_id to observe its cycle.", cls: "cauco-empty" });
    const load = async () => { const reviewId = input.value.trim(); if (!reviewId) return; output.empty(); output.createEl("p", { text: "Loading…", cls: "cauco-empty" }); try { this.renderCycle(output, await client.getCognitiveCycle(reviewId)); } catch (error) { this.renderSafeError(output, error); } };
    button.addEventListener("click", () => void load());
    input.addEventListener("keydown", (event) => { if (event.key === "Enter") void load(); });
  }

  private renderCycle(container: HTMLElement, value: CognitiveCycleSnapshot): void {
    container.empty();
    this.renderDefinitionList(container, [["Stage", value.currentStage], ["Overall status", value.overallStatus], ["Blocked", String(value.blocked)], ["Terminal", String(value.terminal)], ["Awaiting human action", String(value.awaitingHumanAction)], ["Next permitted action", value.nextPermittedAction ?? "None"]]);
    this.renderObjectList(container, "Related records", value.relatedRecordIds); this.renderObjectList(container, "Candidate counts", value.candidateCounts); this.renderObjectList(container, "Proposal counts", value.proposalCounts); this.renderMessages(container, "Warnings", value.warnings); this.renderMessages(container, "Limitations", value.limitations);
    this.renderGuidedAction(container, value);
  }

  private renderGuidedAction(container: HTMLElement, snapshot: CognitiveCycleSnapshot): void {
    const section = container.createDiv({ cls: "cauco-guided-action" });
    section.createEl("h4", { text: "Guided Action" });
    const actions = this.guidedActions(snapshot);
    if (!actions.length) { section.createEl("p", { text: "No guided action is available for this state.", cls: "cauco-empty" }); return; }
    const primary = actions[0]!;
    section.createEl("p", { text: primary.reason });
    const ids = primary.kind === "create-execution" || primary.kind === "approve-plan" || primary.kind === "reject-plan" ? [snapshot.reviewId] : primary.kind === "create-verification" ? this.scalarIds(snapshot, "execution_id") : primary.kind === "consolidate-experience" ? this.scalarIds(snapshot, "verification_id") : primary.kind === "confirm-memory-write" ? this.arrayIds(snapshot, "proposal_ids") : this.arrayIds(snapshot, "candidate_ids");
    if (ids.length !== 1) { section.createEl("p", { text: "Action unavailable: the required record ID is missing or ambiguous.", cls: "cauco-error" }); return; }
    section.createEl("p", { text: `Affected record: ${ids[0]}` });
    const reason = section.createEl("input", { type: "text", placeholder: "Rejection reason (only required for reject plan)" }); reason.hidden = !actions.some((item) => item.kind === "reject-plan");
    const disposition = section.createEl("select"); disposition.hidden = !actions.some((item) => item.kind === "reject-candidate"); disposition.createEl("option", { text: "Retain as experience only", value: "retain_as_experience_only" }); disposition.createEl("option", { text: "Discard", value: "discard" });
    for (const item of actions) { const button = section.createEl("button", { text: item.label, cls: item.kind.startsWith("reject") ? undefined : "mod-cta" }); if (item.kind === "reject-plan") { button.disabled = true; reason.addEventListener("input", () => { button.disabled = reason.value.trim().length === 0; }); } button.addEventListener("click", () => void this.performGuidedAction(snapshot, item.kind, ids[0]!, item.kind === "reject-candidate" ? disposition.value : reason.value.trim(), button, section)); }
  }

  private guidedActions(snapshot: CognitiveCycleSnapshot): Array<{ kind: string; label: string; reason: string }> {
    if (snapshot.currentStage === "awaiting_plan_approval") return [{ kind: "approve-plan", label: "Approve plan", reason: "The plan is pending explicit human approval." }, { kind: "reject-plan", label: "Reject plan", reason: "Rejecting stops this reviewed plan." }];
    if (snapshot.currentStage === "awaiting_memory_candidate_review") return [{ kind: "approve-candidate", label: "Approve candidate", reason: "A pending learning candidate requires human review." }, { kind: "reject-candidate", label: "Reject candidate", reason: "Choose whether to retain the lesson only as experience or discard it." }];
    const actions: Record<string, { kind: string; label: string; reason: string }> = { ready_for_execution: { kind: "create-execution", label: "Create execution", reason: "The approved plan is ready for a separate execution record." }, awaiting_verification: { kind: "create-verification", label: "Create verification", reason: "The terminal execution awaits explicit outcome verification." }, awaiting_experience_consolidation: { kind: "consolidate-experience", label: "Consolidate experience", reason: "The verified outcome awaits experience consolidation." }, awaiting_candidate_promotion: { kind: "promote-candidate", label: "Promote candidate", reason: "The approved learning candidate is eligible for promotion." }, awaiting_memory_write_confirmation: { kind: "confirm-memory-write", label: "Confirm memory write", reason: "An existing pending proposal requires explicit confirmation." } };
    const action = actions[snapshot.currentStage];
    return action ? [action] : [];
  }

  private scalarIds(snapshot: CognitiveCycleSnapshot, key: string): string[] { return typeof snapshot.relatedRecordIds[key] === "string" ? [snapshot.relatedRecordIds[key] as string] : []; }
  private arrayIds(snapshot: CognitiveCycleSnapshot, key: string): string[] { const value = snapshot.relatedRecordIds[key]; return Array.isArray(value) && value.every((item) => typeof item === "string") ? value as string[] : []; }

  private async performGuidedAction(snapshot: CognitiveCycleSnapshot, kind: string, id: string, reason: string, button: HTMLButtonElement, section: HTMLElement): Promise<void> {
    button.disabled = true; button.setText("Checking latest state…");
    try { const client = new CaucoCoreClient(this.plugin.settings.coreUrl); const latest = await client.getCognitiveCycle(snapshot.reviewId); if (latest.currentStage !== snapshot.currentStage || latest.nextPermittedAction !== snapshot.nextPermittedAction) throw new Error("This cycle changed. Refresh the cycle before trying again."); let preview: string | undefined; const details: string[] = [`Affected record: ${id}`]; if (kind === "reject-candidate") details.push(`Disposition: ${reason}`); if (kind === "confirm-memory-write") { const proposal = await client.getMemoryWriteProposal(id); if (proposal.state !== "pending") throw new Error("This memory proposal is no longer pending."); preview = proposal.proposal.markdownPreview; details.push(`Source proposal: ${id}`, `Target: ${proposal.proposal.targetFile}`, `Section: ${proposal.proposal.targetSection}`, `Provenance: ${proposal.proposal.source_type ?? "unknown"}:${proposal.proposal.source_id ?? "unknown"}`); details.push(...proposal.proposal.warnings.map((warning) => `Warning: ${warning}`)); } const confirmed = await this.confirmGuidedAction(kind, details, preview); if (!confirmed) { button.disabled = false; button.setText("Confirm action"); return; } button.setText("Applying…"); if (kind === "approve-plan") await client.approvePlanReview(id); else if (kind === "reject-plan") await client.rejectPlanReview(id, reason); else if (kind === "create-execution") await client.createExecution(id); else if (kind === "create-verification") await client.createVerification(id); else if (kind === "consolidate-experience") await client.consolidateExperience(id); else if (kind === "approve-candidate") await client.approveCandidate(id); else if (kind === "reject-candidate") await client.rejectCandidate(id, reason as "retain_as_experience_only" | "discard"); else if (kind === "promote-candidate") await client.promoteCandidate(id); else if (kind === "confirm-memory-write") await client.confirmMemoryWriteProposal(id, { confirm: true }); section.empty(); section.createEl("p", { text: "Action completed. Refreshing…", cls: "cauco-success" }); await this.refresh(); } catch (error) { section.createEl("p", { text: error instanceof Error ? error.message : "The guided action could not be completed.", cls: "cauco-error" }); button.disabled = false; }
  }

  private confirmGuidedAction(kind: string, details: string[], preview?: string): Promise<boolean> {
    return new Promise((resolve) => {
      const modal = new GuidedActionModal(this.plugin.app, { title: `${kind.replaceAll("-", " ")} confirmation`, explanation: "This is one explicit lifecycle request. It will not approve, execute, or confirm any later stage automatically.", details, preview, confirmLabel: "Confirm action", destructive: kind.includes("reject"), onConfirm: () => resolve(true), onCancel: () => resolve(false) });
      modal.open();
    });
  }

  private async loadLearning(panel: HTMLElement, client: CaucoCoreClient): Promise<void> { panel.empty(); const input = panel.createEl("input", { type: "text", placeholder: "Instruction used only to query guidance" }); const button = panel.createEl("button", { text: "Query guidance" }); const out = panel.createDiv(); const load = async () => { if (!input.value.trim()) return; out.empty(); out.createEl("p", { text: "Loading…", cls: "cauco-empty" }); try { const items = await client.getLearningGuidance(input.value.trim()); out.empty(); if (!items.length) { out.createEl("p", { text: "No applied guidance matched.", cls: "cauco-empty" }); return; } for (const item of items) { const card = out.createDiv({ cls: "cauco-data-card" }); card.createEl("strong", { text: item.lesson }); card.createEl("p", { text: `${item.category} · confidence ${item.confidence} · ${item.reasonSelected}` }); card.createEl("small", { text: `candidate ${item.candidateId} · experience ${item.experienceId} · proposal ${item.proposalId}` }); } } catch (error) { this.renderSafeError(out, error); } }; button.addEventListener("click", () => void load()); }

  private async loadReflection(panel: HTMLElement, client: CaucoCoreClient): Promise<void> { try { const value = await client.getReflection(); panel.empty(); this.renderObjectList(panel, "Summary", value.summary); for (const pattern of value.patterns) panel.createEl("p", { text: `${pattern.category} · ${pattern.count}× · ${pattern.lesson}` }); this.renderMessages(panel, "Limitations", value.limitations); panel.createEl("small", { text: `Method: ${value.method}` }); } catch (error) { this.renderSafeError(panel, error); } }

  private async loadCandidates(panel: HTMLElement, client: CaucoCoreClient): Promise<void> { try { const values = await client.getMemoryCandidates(); panel.empty(); if (!values.length) { panel.createEl("p", { text: "No memory candidates found.", cls: "cauco-empty" }); return; } for (const item of values) { const card = panel.createDiv({ cls: "cauco-data-card" }); card.createEl("strong", { text: `${item.status}: ${item.lesson.lesson}` }); card.createEl("p", { text: `${item.lesson.category} · confidence ${item.lesson.confidence} · ${item.disposition ?? "no disposition"}` }); card.createEl("small", { text: `candidate ${item.candidateId} · review ${item.reviewId} · experience ${item.experienceId}` }); card.createEl("p", { text: item.rationale }); } } catch (error) { this.renderSafeError(panel, error); } }

  private renderDefinitionList(container: HTMLElement, values: Array<[string, string]>): void { const dl = container.createEl("dl", { cls: "cauco-control-details" }); for (const [key, value] of values) { dl.createEl("dt", { text: key }); dl.createEl("dd", { text: value }); } }
  private renderObjectList(container: HTMLElement, title: string, values: Record<string, unknown>): void { container.createEl("h4", { text: title }); for (const key of Object.keys(values).sort()) container.createEl("p", { text: `${key}: ${String(values[key])}` }); }
  private renderMessages(container: HTMLElement, title: string, values: string[]): void { if (!values.length) return; container.createEl("h4", { text: title }); const list = container.createEl("ul"); for (const value of values) list.createEl("li", { text: value }); }

  private renderConnection(container: HTMLElement, result: ConnectionResult): void {
    const connection = container.createDiv({ cls: "cauco-connection" });
    connection.setAttribute("role", "status");
    const indicator = connection.createSpan({ cls: "cauco-indicator" });
    indicator.addClass(result.connected ? "is-connected" : "is-offline");
    connection.createEl("strong", { text: result.connected ? "Core connected" : "Core offline" });
    connection.createSpan({
      text: result.connected
        ? `Cauco Core ${result.health?.version ?? ""}`
        : "Start the local core, then check the connection again.",
    });
    if (result.error) this.renderError(container, result.error);
  }

  private renderChat(container: HTMLElement, result: ConnectionResult): void {
    const section = container.createEl("section", { cls: "cauco-chat" });
    section.createEl("h2", { text: "Local chat" });

    const models = result.models ?? [];
    const selectedModel = this.resolveSelectedModel(models, result);
    const modelInstalled = models.some((model) => model.name === selectedModel);
    const available = result.connected && result.aiStatus?.available === true && modelInstalled;

    const provider = section.createDiv({ cls: "cauco-chat-provider" });
    const aiIndicator = provider.createSpan({ cls: "cauco-indicator" });
    aiIndicator.addClass(result.aiStatus?.available ? "is-connected" : "is-offline");
    provider.createEl("strong", {
      text: result.aiStatus?.available ? "Ollama available" : "Ollama unavailable",
    });
    provider.createSpan({ text: selectedModel ? `Model: ${selectedModel}` : "No installed model" });

    if (result.aiError) this.renderError(section, result.aiError);
    if (result.aiStatus?.available && !modelInstalled) {
      this.renderError(section, "Select an installed Ollama model in Cauco settings.");
    }

    const modelLabel = section.createEl("label", { text: "Model", cls: "cauco-field-label" });
    const selector = section.createEl("select", { cls: "dropdown" });
    modelLabel.htmlFor = "cauco-chat-model";
    selector.id = "cauco-chat-model";
    if (models.length === 0) {
      selector.createEl("option", { text: "No models available", value: "" });
    } else {
      for (const model of models) {
        selector.createEl("option", { text: model.name, value: model.name });
      }
      selector.value = selectedModel;
    }
    selector.disabled = !result.aiStatus?.available || models.length === 0;
    const inputLabel = section.createEl("label", {
      text: "Message",
      cls: "cauco-field-label",
    });
    const input = section.createEl("textarea", {
      cls: "cauco-chat-input",
      attr: { placeholder: "Ask Cauco using the selected local model…", rows: "4" },
    });
    inputLabel.htmlFor = "cauco-chat-input";
    input.id = "cauco-chat-input";
    input.disabled = !available;
    input.maxLength = 8000;

    const actions = section.createDiv({ cls: "cauco-chat-actions" });
    const memoryLabel = actions.createEl("label", { cls: "cauco-memory-toggle" });
    const useMemory = memoryLabel.createEl("input", { type: "checkbox" });
    useMemory.checked = true;
    memoryLabel.appendText("Use memory");
    const send = actions.createEl("button", { text: "Send", cls: "mod-cta" });
    send.disabled = !available;
    const responseArea = section.createDiv({ cls: "cauco-chat-response" });
    responseArea.setAttribute("aria-live", "polite");
    responseArea.createEl("p", {
      text: available
        ? "Memory retrieval is read-only and can be disabled for each request."
        : "Start Ollama and install or select a model to enable chat.",
      cls: "cauco-empty",
    });

    selector.addEventListener("change", () => {
      this.plugin.settings.selectedModel = selector.value;
      void this.plugin.saveSettings();
      const enabled = result.aiStatus?.available === true && selector.value.length > 0;
      input.disabled = !enabled;
      send.disabled = !enabled;
      provider.lastElementChild?.setText(`Model: ${selector.value}`);
    });

    send.addEventListener("click", () => {
      void this.sendMessage(input, selector, useMemory, send, responseArea);
    });
  }

  private async sendMessage(
    input: HTMLTextAreaElement,
    selector: HTMLSelectElement,
    useMemory: HTMLInputElement,
    button: HTMLButtonElement,
    responseArea: HTMLElement,
  ): Promise<void> {
    const message = input.value.trim();
    if (!message) {
      responseArea.empty();
      this.renderError(responseArea, "Enter a message before sending.");
      return;
    }
    input.disabled = true;
    selector.disabled = true;
    useMemory.disabled = true;
    button.disabled = true;
    button.setText("Sending…");
    responseArea.empty();
    responseArea.createEl("p", { text: "Waiting for local Ollama…", cls: "cauco-empty" });
    try {
      const response = await new CaucoCoreClient(this.plugin.settings.coreUrl).chat(
        message,
        selector.value || undefined,
        useMemory.checked,
      );
      responseArea.empty();
      responseArea.createEl("p", { text: response.response });
      responseArea.createEl("small", {
        text: `${response.provider} · ${response.model} · no tools or agents used`,
        cls: "cauco-response-meta",
      });
      if (response.usedMemory) {
        const sources = responseArea.createDiv({ cls: "cauco-memory-sources" });
        sources.createEl("strong", { text: "Memory sources" });
        const list = sources.createEl("ul");
        for (const source of response.memorySources) list.createEl("li", { text: source });
      } else {
        responseArea.createEl("small", {
          text: "No memory was used for this response.",
          cls: "cauco-response-meta",
        });
      }
    } catch (error) {
      responseArea.empty();
      this.renderError(
        responseArea,
        error instanceof Error ? error.message : "The local chat request failed.",
      );
    } finally {
      input.disabled = false;
      selector.disabled = false;
      useMemory.disabled = false;
      button.disabled = false;
      button.setText("Send");
    }
  }

  private resolveSelectedModel(models: AIModel[], result: ConnectionResult): string {
    const configured = this.plugin.settings.selectedModel;
    if (configured && models.some((model) => model.name === configured)) return configured;
    return result.aiStatus?.defaultModel ?? "";
  }

  private renderCard(container: HTMLElement, label: string, section: StatusSection): void {
    const card = container.createEl("section", { cls: "cauco-card" });
    card.createEl("h2", { text: label });
    card.createEl("p", { text: section.status, cls: "cauco-card-status" });
    const details = Object.entries(section).filter(([key]) => key !== "status");
    if (details.length === 0) {
      card.createEl("p", { text: "No details available.", cls: "cauco-empty" });
      return;
    }
    const list = card.createEl("dl");
    for (const [key, value] of details) {
      list.createEl("dt", { text: key.replaceAll("_", " ") });
      list.createEl("dd", { text: String(value) });
    }
  }

  private renderError(container: HTMLElement, message: string): void {
    const error = container.createEl("p", { text: message, cls: "cauco-error" });
    error.setAttribute("role", "alert");
  }
}
