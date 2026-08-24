import type { ReasoningPlanningApiClient } from "../reasoning/api";
import { ConversationHistory, responseView } from "../reasoning/conversation";
import type { ConversationEntry, ReasoningPlanningResponse } from "../reasoning/types";

export class CaucoConversationPanel {
  private readonly history = new ConversationHistory();
  private submitting = false;
  private historyElement?: HTMLElement;

  constructor(private readonly client: ReasoningPlanningApiClient) {}

  render(container: HTMLElement, connected: boolean): void {
    const section = container.createEl("section", { cls: "cauco-conversation" });
    const header = section.createDiv({ cls: "cauco-panel-header" });
    header.createEl("h2", { text: "Cauco Conversation" });
    header.createEl("span", { text: "Advisory planning only" });
    section.createEl("p", {
      text: "Explore routing and proposed plans. This panel cannot approve, execute, or mutate anything.",
      cls: "cauco-trust-note",
    });

    this.historyElement = section.createDiv({ cls: "cauco-conversation-history" });
    this.renderHistory();

    const label = section.createEl("label", { text: "Instruction", cls: "cauco-field-label" });
    const input = section.createEl("textarea", {
      cls: "cauco-conversation-input",
      attr: { placeholder: "Describe what you want Cauco to plan…", rows: "4" },
    });
    label.htmlFor = "cauco-conversation-input";
    input.id = "cauco-conversation-input";
    input.maxLength = 4000;
    input.disabled = !connected;

    const actions = section.createDiv({ cls: "cauco-conversation-actions" });
    const toggleLabel = actions.createEl("label", { cls: "cauco-reasoning-toggle" });
    const useReasoning = toggleLabel.createEl("input", { type: "checkbox" });
    useReasoning.checked = false;
    useReasoning.disabled = !connected;
    toggleLabel.appendText("Use reasoning");
    const submit = actions.createEl("button", { text: "Plan", cls: "mod-cta" });
    submit.disabled = !connected;
    submit.addEventListener("click", () => {
      void this.submit(input, useReasoning, submit);
    });
  }

  entries(): readonly ConversationEntry[] {
    return this.history.entries();
  }

  private async submit(
    input: HTMLTextAreaElement,
    useReasoning: HTMLInputElement,
    button: HTMLButtonElement,
  ): Promise<void> {
    const instruction = input.value.trim();
    if (!instruction || this.submitting) return;
    this.submitting = true;
    input.disabled = true;
    useReasoning.disabled = true;
    button.disabled = true;
    button.setText("Planning…");
    try {
      const response = await this.client.plan({
        instruction,
        useReasoning: useReasoning.checked,
      });
      this.history.add({ instruction, useReasoning: useReasoning.checked, response });
      input.value = "";
    } catch (error) {
      this.history.add({
        instruction,
        useReasoning: useReasoning.checked,
        error:
          error instanceof Error
            ? error.message
            : "Advisory planning is unavailable. No action was taken.",
      });
    } finally {
      this.submitting = false;
      input.disabled = false;
      useReasoning.disabled = false;
      button.disabled = false;
      button.setText("Plan");
      this.renderHistory();
    }
  }

  private renderHistory(): void {
    if (!this.historyElement) return;
    this.historyElement.empty();
    const entries = this.history.entries();
    if (entries.length === 0) {
      this.historyElement.createEl("p", {
        text: "Conversation results remain here until this dashboard session closes.",
        cls: "cauco-empty",
      });
      return;
    }
    for (const entry of entries) this.renderEntry(this.historyElement, entry);
  }

  private renderEntry(container: HTMLElement, entry: ConversationEntry): void {
    const user = container.createDiv({ cls: "cauco-conversation-message is-user" });
    user.createEl("strong", { text: "You" });
    user.createEl("p", { text: entry.instruction });
    if (entry.error) {
      const response = container.createDiv({ cls: "cauco-conversation-message is-cauco" });
      response.createEl("strong", { text: "Cauco" });
      const message = response.createEl("p", { text: entry.error, cls: "cauco-error" });
      message.setAttribute("role", "alert");
      return;
    }
    if (entry.response) this.renderResponse(container, entry.response);
  }

  private renderResponse(container: HTMLElement, response: ReasoningPlanningResponse): void {
    const view = responseView(response);
    const card = container.createDiv({ cls: "cauco-conversation-message is-cauco" });
    card.createEl("strong", { text: "Cauco" });
    card.createEl("p", { text: response.explanation });
    const summary = card.createEl("dl", { cls: "cauco-control-details" });
    const rows: Array<[string, string]> = [
      ["Planning status", view.planningStatus],
      ["Selected agent", view.selectedAgent],
      ["Routing match", view.routingMatch],
      ["Reasoning requested", String(response.reasoningRequested)],
      ["Reasoning invoked", String(response.reasoningInvoked)],
      ["Proposal produced", String(response.proposalProduced)],
      ["Proposal validated", String(response.proposalValidated)],
      ["Planning context enriched", String(response.planningContextEnriched)],
      ["Provider", response.provider ?? "None"],
      ["Model", response.model ?? "None"],
    ];
    for (const [name, value] of rows) {
      summary.createEl("dt", { text: name });
      summary.createEl("dd", { text: value });
    }

    const safety = card.createDiv({ cls: "cauco-conversation-safety" });
    safety.createEl("h4", { text: "Safety state" });
    for (const [name, value] of view.safety) {
      const safe = name === "proposal_only" ? value : !value;
      const flag = safety.createEl("span", {
        text: `${name}: ${String(value)}`,
        cls: `cauco-safety-flag ${safe ? "is-safe" : "is-unsafe"}`,
      });
      flag.setAttribute("data-safety-flag", name);
    }

    if (response.planning.plan) {
      const plan = response.planning.plan;
      const planSection = card.createDiv({ cls: "cauco-conversation-plan" });
      planSection.createEl("h4", { text: plan.objective });
      planSection.createEl("small", { text: `${plan.agentName} · ${plan.status}` });
      const steps = planSection.createEl("ol");
      for (const step of plan.steps) {
        const item = steps.createEl("li");
        item.createEl("strong", { text: step.title });
        item.createEl("p", { text: step.description });
      }
    }

    const details = card.createEl("details", { cls: "cauco-conversation-details" });
    details.createEl("summary", { text: "Details / Debug" });
    details.createEl("pre", { text: JSON.stringify(response.raw, null, 2) });
  }
}
