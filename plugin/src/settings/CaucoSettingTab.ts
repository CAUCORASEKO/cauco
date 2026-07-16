import { App, PluginSettingTab, Setting } from "obsidian";
import type CaucoPlugin from "../main";
import { CaucoCoreClient } from "../services/CaucoCoreClient";
import type { AIModel } from "../types";
import { normalizeCoreUrl } from "./settings";

export class CaucoSettingTab extends PluginSettingTab {
  private models: AIModel[] = [];
  private aiStatus = "Not checked";
  private refreshing = false;

  constructor(app: App, private readonly plugin: CaucoPlugin) {
    super(app, plugin);
  }

  override display(): void {
    const { containerEl } = this;
    containerEl.empty();
    containerEl.createEl("h2", { text: "Cauco settings" });
    containerEl.createEl("p", {
      text: "Configure Cauco Core and select a model installed in local Ollama.",
      cls: "setting-item-description",
    });

    new Setting(containerEl)
      .setName("Local core URL")
      .setDesc("HTTP address of Cauco Core. Localhost is recommended.")
      .addText((text) =>
        text
          .setPlaceholder("http://127.0.0.1:8765")
          .setValue(this.plugin.settings.coreUrl)
          .then((component) => component.inputEl.setAttribute("aria-label", "Local core URL"))
          .onChange(async (value) => {
            this.plugin.settings.coreUrl = normalizeCoreUrl(value);
            await this.plugin.saveSettings();
          }),
      );

    new Setting(containerEl).setName("Ollama connection").setDesc(this.aiStatus);

    new Setting(containerEl)
      .setName("Selected Ollama model")
      .setDesc("The dashboard uses this model. Leave as core default to follow core configuration.")
      .addDropdown((dropdown) => {
        dropdown.addOption("", "Core default");
        for (const model of this.models) dropdown.addOption(model.name, model.name);
        const selected = this.plugin.settings.selectedModel;
        if (selected && !this.models.some((model) => model.name === selected)) {
          dropdown.addOption(selected, `${selected} (not discovered)`);
        }
        dropdown.setValue(selected).onChange(async (value) => {
          this.plugin.settings.selectedModel = value;
          await this.plugin.saveSettings();
        });
        dropdown.selectEl.setAttribute("aria-label", "Selected Ollama model");
      })
      .addButton((button) => {
        button
          .setButtonText(this.refreshing ? "Refreshing…" : "Refresh installed models")
          .setDisabled(this.refreshing)
          .setTooltip("Ask Cauco Core for locally installed Ollama models")
          .onClick(() => void this.refreshModels());
      });
  }

  private async refreshModels(): Promise<void> {
    if (this.refreshing) return;
    this.refreshing = true;
    this.aiStatus = "Checking local Ollama…";
    this.display();
    const client = new CaucoCoreClient(this.plugin.settings.coreUrl);
    try {
      const status = await client.getAIStatus();
      this.models = status.available ? await client.getModels() : [];
      this.aiStatus = status.available
        ? `Connected to ${status.provider}; ${status.modelsCount} model(s) installed.`
        : "Cauco Core is running, but local Ollama is unavailable.";
    } catch (error) {
      this.models = [];
      this.aiStatus = error instanceof Error ? error.message : "Connection check failed.";
    } finally {
      this.refreshing = false;
      this.display();
    }
  }
}
