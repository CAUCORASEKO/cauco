import { Modal, Setting } from "obsidian";

export interface GuidedActionModalOptions {
  title: string;
  explanation: string;
  details?: string[];
  preview?: string;
  confirmLabel: string;
  destructive?: boolean;
  onConfirm?: () => void;
  onCancel?: () => void;
}

export class GuidedActionModal extends Modal {
  private settled = false;

  constructor(
    app: ConstructorParameters<typeof Modal>[0],
    private readonly options: GuidedActionModalOptions,
  ) {
    super(app);
  }

  override onOpen(): void {
    const { contentEl } = this;
    contentEl.empty();
    contentEl.createEl("h2", { text: this.options.title });
    contentEl.createEl("p", { text: this.options.explanation });
    for (const detail of this.options.details ?? []) contentEl.createEl("p", { text: detail });
    if (this.options.preview !== undefined) {
      contentEl.createEl("h3", { text: "Exact Markdown preview" });
      contentEl.createEl("pre", { text: this.options.preview, cls: "cauco-guided-preview" });
    }
    new Setting(contentEl)
      .addButton((button) => button.setButtonText("Cancel").onClick(() => this.close()))
      .addButton((button) => {
        button.setButtonText(this.options.confirmLabel);
        if (this.options.destructive) button.setWarning();
        button.onClick(() => {
          this.settled = true;
          this.close();
          this.options.onConfirm?.();
        });
      });
  }

  override onClose(): void {
    this.contentEl.empty();
    if (!this.settled) this.options.onCancel?.();
  }
}
