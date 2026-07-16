import { App, PluginSettingTab, Setting } from "obsidian";
import type CaucoPlugin from "../main";
import { normalizeCoreUrl } from "./settings";

export class CaucoSettingTab extends PluginSettingTab {
  constructor(app: App, private readonly plugin: CaucoPlugin) {
    super(app, plugin);
  }

  override display(): void {
    const { containerEl } = this;
    containerEl.empty();
    containerEl.createEl("h2", { text: "Cauco settings" });
    containerEl.createEl("p", {
      text: "Configure the local Cauco Core service used by the dashboard.",
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
  }
}
