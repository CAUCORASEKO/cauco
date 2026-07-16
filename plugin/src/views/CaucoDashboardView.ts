import { ItemView, WorkspaceLeaf } from "obsidian";
import { CAUCO_VIEW_TYPE } from "../constants";
import { CaucoCoreClient } from "../services/CaucoCoreClient";
import type { CaucoStatus, ConnectionResult, StatusSection } from "../types";
import type CaucoPlugin from "../main";

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
    container.createEl("p", { text: "Checking local core…", cls: "cauco-empty" });
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
    button.setAttribute("aria-label", "Check connection to Cauco Core");
    button.addEventListener("click", () => void this.refresh());

    const connection = container.createDiv({ cls: "cauco-connection" });
    connection.setAttribute("role", "status");
    const indicator = connection.createSpan({ cls: "cauco-indicator" });
    indicator.addClass(result.connected ? "is-connected" : "is-offline");
    connection.createEl("strong", { text: result.connected ? "Connected" : "Offline" });
    connection.createSpan({
      text: result.connected
        ? `Cauco Core ${result.health?.version ?? ""}`
        : "Start the local core, then check the connection again.",
    });

    if (result.error) {
      const error = container.createEl("p", { text: result.error, cls: "cauco-error" });
      error.setAttribute("role", "alert");
    }

    const grid = container.createDiv({ cls: "cauco-grid" });
    for (const [key, label] of SECTION_LABELS) {
      this.renderCard(grid, label, result.status[key]);
    }
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
}
