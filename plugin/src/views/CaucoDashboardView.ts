import { ItemView, WorkspaceLeaf } from "obsidian";
import { CAUCO_VIEW_TYPE } from "../constants";
import type CaucoPlugin from "../main";
import { CaucoCoreClient } from "../services/CaucoCoreClient";
import type { AIModel, CaucoStatus, ConnectionResult, StatusSection } from "../types";
import { CaucoMemoryPanel } from "./CaucoMemoryPanel";
import { CaucoExecutionPanel } from "./CaucoExecutionPanel";

const SECTION_LABELS: Array<[keyof CaucoStatus, string]> = [
  ["runtime", "Runtime"],
  ["memory", "Memory"],
  ["agents", "Agents"],
  ["tools", "Tools"],
  ["scheduler", "Scheduler"],
];

export class CaucoDashboardView extends ItemView {
  private checking = false;

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
    const grid = container.createDiv({ cls: "cauco-grid" });
    for (const [key, label] of SECTION_LABELS) {
      this.renderCard(grid, label, result.status[key]);
    }
    const client = new CaucoCoreClient(this.plugin.settings.coreUrl);
    new CaucoExecutionPanel(client).render(container);
    this.renderChat(container, result);
    new CaucoMemoryPanel(
      client,
      result.memoryFiles ?? [],
      result.memoryError,
    ).render(container);
  }

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
