import { Plugin } from "obsidian";
import { CAUCO_VIEW_TYPE } from "./constants";
import { CaucoSettingTab } from "./settings/CaucoSettingTab";
import { DEFAULT_SETTINGS, normalizeCoreUrl } from "./settings/settings";
import type { CaucoSettings } from "./types";
import { CaucoDashboardView } from "./views/CaucoDashboardView";

export default class CaucoPlugin extends Plugin {
  override settings: CaucoSettings = DEFAULT_SETTINGS;

  override async onload(): Promise<void> {
    await this.loadSettings();
    this.registerView(CAUCO_VIEW_TYPE, (leaf) => new CaucoDashboardView(leaf, this));
    this.addRibbonIcon("layout-dashboard", "Open Cauco Dashboard", () => {
      void this.activateDashboard();
    });
    this.addCommand({
      id: "open-cauco-dashboard",
      name: "Open Cauco Dashboard",
      callback: () => void this.activateDashboard(),
    });
    this.addSettingTab(new CaucoSettingTab(this.app, this));
  }

  override onunload(): void {
    this.app.workspace.detachLeavesOfType(CAUCO_VIEW_TYPE);
  }

  async saveSettings(): Promise<void> {
    await this.saveData(this.settings);
  }

  private async loadSettings(): Promise<void> {
    const stored = (await this.loadData()) as Partial<CaucoSettings> | null;
    this.settings = {
      ...DEFAULT_SETTINGS,
      ...stored,
      coreUrl: normalizeCoreUrl(stored?.coreUrl ?? DEFAULT_SETTINGS.coreUrl),
      selectedModel:
        typeof stored?.selectedModel === "string" ? stored.selectedModel : DEFAULT_SETTINGS.selectedModel,
    };
  }

  private async activateDashboard(): Promise<void> {
    const workspace = this.app.workspace;
    let leaf = workspace.getLeavesOfType(CAUCO_VIEW_TYPE)[0];
    if (!leaf) {
      leaf = workspace.getLeaf("tab");
      await leaf.setViewState({ type: CAUCO_VIEW_TYPE, active: true });
    }
    await workspace.revealLeaf(leaf);
  }
}
