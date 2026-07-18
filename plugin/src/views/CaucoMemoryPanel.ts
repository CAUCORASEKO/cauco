import { CaucoCoreApiError, CaucoCoreClient } from "../services/CaucoCoreClient";
import type {
  MemoryFileMetadata,
  MemorySearchResult,
  MemoryWriteConfirmationResult,
  MemoryWriteOperation,
  MemoryWriteProposal,
} from "../types";

interface MemoryListItem {
  relativePath: string;
  title: string;
  excerpt?: string;
}

type WriteState =
  | { kind: "idle"; instruction: string }
  | { kind: "generating"; instruction: string }
  | {
      kind: "review";
      instruction: string;
      proposal: MemoryWriteProposal;
      expiresAt?: string;
    }
  | {
      kind: "applying";
      instruction: string;
      proposal: MemoryWriteProposal;
      expiresAt?: string;
    }
  | {
      kind: "error";
      instruction: string;
      message: string;
      proposal?: MemoryWriteProposal;
      expiresAt?: string;
      retryApply: boolean;
      regenerate: boolean;
    }
  | { kind: "success"; instruction: ""; result: MemoryWriteConfirmationResult };

const OPERATION_LABELS: Record<MemoryWriteOperation, string> = {
  add_task: "Add task",
  add_decision: "Add decision",
  add_relationship_note: "Add relationship note",
  add_project_note: "Add project note",
};

export class CaucoMemoryPanel {
  private files: MemoryFileMetadata[];
  private writeState: WriteState = { kind: "idle", instruction: "" };

  constructor(
    private readonly client: CaucoCoreClient,
    initialFiles: MemoryFileMetadata[],
    private readonly initialError?: string,
  ) {
    this.files = initialFiles;
  }

  render(container: HTMLElement): void {
    const section = container.createEl("section", { cls: "cauco-memory" });
    const header = section.createDiv({ cls: "cauco-panel-header" });
    header.createEl("h2", { text: "Memory" });
    const count = header.createEl("span", { text: `${this.files.length} Markdown file(s)` });
    const refresh = header.createEl("button", {
      text: "Refresh memory",
      attr: { type: "button", "aria-label": "Refresh Markdown memory files" },
    });

    if (this.initialError) this.renderError(section, this.initialError);

    const controls = section.createDiv({ cls: "cauco-memory-controls" });
    const search = controls.createEl("input", {
      type: "search",
      attr: { placeholder: "Search memory…", "aria-label": "Search memory" },
    });
    search.maxLength = 200;
    const searchButton = controls.createEl("button", {
      text: "Search",
      attr: { type: "button" },
    });
    const content = section.createDiv({ cls: "cauco-memory-content" });
    const list = content.createDiv({ cls: "cauco-memory-list" });
    const preview = content.createDiv({ cls: "cauco-memory-preview" });
    this.renderList(list, preview, this.files);
    this.renderPreviewEmpty(preview);

    refresh.addEventListener("click", () => {
      void this.refresh(refresh, count, list, preview);
    });
    searchButton.addEventListener("click", () => {
      void this.search(search.value, searchButton, count, list, preview);
    });
    search.addEventListener("keydown", (event) => {
      if (event.key === "Enter") void this.search(search.value, searchButton, count, list, preview);
    });

    const writeContainer = section.createDiv({ cls: "cauco-memory-write" });
    this.renderWritePanel(writeContainer);
  }

  private renderWritePanel(container: HTMLElement): void {
    container.empty();
    container.createEl("h3", { text: "Write to Memory" });
    container.createEl("p", {
      text: "Cauco will only apply the preview after your confirmation. The server chooses the approved memory file.",
      cls: "cauco-trust-note",
    });

    if (this.writeState.kind === "success") {
      const status = container.createEl("p", {
        text: this.writeStatus(),
        cls: "cauco-write-status",
      });
      status.setAttribute("aria-live", "polite");
      status.setAttribute("aria-atomic", "true");
      this.renderWriteResult(container, this.writeState.result);
      return;
    }

    const hasProposal =
      this.writeState.kind === "review" ||
      this.writeState.kind === "applying" ||
      (this.writeState.kind === "error" && this.writeState.proposal !== undefined);

    const label = container.createEl("label", {
      text: "Memory instruction",
      cls: "cauco-field-label",
      attr: { for: "cauco-memory-instruction" },
    });
    const textarea = container.createEl("textarea", {
      cls: "cauco-memory-instruction",
      attr: {
        id: "cauco-memory-instruction",
        placeholder: "Describe what Cauco should remember...",
        maxlength: "4000",
        rows: "5",
      },
    });
    label.insertAdjacentElement("afterend", textarea);
    textarea.value = this.writeState.instruction;
    textarea.disabled = this.writeState.kind === "generating" || hasProposal;

    container.createEl("small", {
      text: "Example: Remember that tomorrow I must review Phase 4. Submit with Cmd+Enter or Ctrl+Enter.",
      cls: "cauco-write-example",
    });
    const inputActions = container.createDiv({ cls: "cauco-write-actions" });
    const generate = inputActions.createEl("button", {
      text: this.writeState.kind === "generating" ? "Generating proposal…" : "Generate Proposal",
      cls: "mod-cta",
      attr: { type: "button" },
    });
    generate.disabled =
      !this.writeState.instruction.trim() ||
      this.writeState.kind === "generating" ||
      hasProposal;

    const status = container.createEl("p", { cls: "cauco-write-status" });
    status.setAttribute("aria-live", "polite");
    status.setAttribute("aria-atomic", "true");
    status.setText(this.writeStatus());

    textarea.addEventListener("input", () => {
      this.writeState.instruction = textarea.value;
      generate.disabled = !textarea.value.trim();
    });
    const submit = (): void => {
      const instruction = textarea.value.trim();
      if (instruction && !generate.disabled) void this.generateProposal(instruction, container);
    };
    generate.addEventListener("click", submit);
    textarea.addEventListener("keydown", (event) => {
      if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
        event.preventDefault();
        submit();
      }
    });

    if (this.writeState.kind === "error") {
      this.renderError(container, this.writeState.message);
    }
    if (
      this.writeState.kind === "review" ||
      this.writeState.kind === "applying" ||
      (this.writeState.kind === "error" && this.writeState.proposal)
    ) {
      this.renderProposalReview(container, this.writeState);
    }
  }

  private writeStatus(): string {
    switch (this.writeState.kind) {
      case "generating":
        return "Generating a review-only proposal. No memory has been changed.";
      case "review":
        return "Proposal ready for review. No memory has been changed yet.";
      case "applying":
        return "Applying the confirmed proposal…";
      case "success":
        return "The confirmed memory change was applied.";
      case "error":
        return "The memory write request did not complete.";
      default:
        return "No memory has been changed.";
    }
  }

  private async generateProposal(instruction: string, container: HTMLElement): Promise<void> {
    if (this.writeState.kind === "generating" || this.writeState.kind === "applying") return;
    this.writeState = { kind: "generating", instruction };
    this.renderWritePanel(container);
    try {
      const proposal = await this.client.createMemoryWriteProposal({ instruction });
      let expiresAt: string | undefined;
      try {
        const record = await this.client.getMemoryWriteProposal(proposal.proposalId);
        if (record.proposal.proposalId === proposal.proposalId) expiresAt = record.expiresAt;
      } catch {
        // Exact expiration is useful but optional; the returned proposal remains reviewable.
      }
      this.writeState = { kind: "review", instruction, proposal, expiresAt };
    } catch (error) {
      this.writeState = {
        kind: "error",
        instruction,
        message: this.writeErrorMessage(error, "generate"),
        retryApply: false,
        regenerate: false,
      };
    }
    this.renderWritePanel(container);
  }

  private renderProposalReview(
    container: HTMLElement,
    state: Extract<WriteState, { kind: "review" | "applying" | "error" }>,
  ): void {
    const proposal = state.proposal;
    if (!proposal) return;
    const card = container.createDiv({ cls: "cauco-proposal-review" });
    card.createEl("h4", { text: "Proposal Review" });
    card.createEl("p", {
      text: "This change has not been applied yet.",
      cls: "cauco-pending-note",
    });
    const details = card.createEl("dl", { cls: "cauco-proposal-details" });
    this.addDetail(details, "Operation", OPERATION_LABELS[proposal.operation]);
    this.addDetail(details, "Target file", proposal.targetFile);
    this.addDetail(details, "Target section", proposal.targetSection);
    this.addDetail(details, "Memory type", `${proposal.targetKind} · ${proposal.targetLayer}`);
    this.addDetail(details, "Confirmation required", proposal.requiresConfirmation ? "Yes" : "No");
    this.addDetail(details, "Created", this.formatTimestamp(proposal.createdAt));
    if (state.expiresAt) this.addDetail(details, "Expires", this.formatTimestamp(state.expiresAt));

    card.createEl("h5", { text: "Normalized content" });
    card.createEl("p", { text: proposal.normalizedContent, cls: "cauco-normalized-content" });
    card.createEl("h5", { text: "Markdown preview" });
    card.createEl("pre", { text: proposal.markdownPreview, cls: "cauco-proposal-markdown" });
    card.createEl("h5", { text: "Reasoning" });
    const reasoning = card.createEl("ul");
    for (const reason of proposal.reasoning) reasoning.createEl("li", { text: reason });
    this.renderWarnings(card, proposal.warnings, "Proposal warnings");

    const actions = card.createDiv({ cls: "cauco-write-actions" });
    if (state.kind === "error" && state.regenerate) {
      const regenerate = actions.createEl("button", {
        text: "Generate New Proposal",
        cls: "mod-cta",
        attr: { type: "button" },
      });
      regenerate.addEventListener("click", () => {
        void this.generateProposal(state.instruction, container);
      });
    } else {
      const apply = actions.createEl("button", {
        text:
          state.kind === "applying"
            ? "Applying…"
            : state.kind === "error"
              ? "Try Apply Again"
              : "Apply Change",
        cls: "mod-cta",
        attr: { type: "button" },
      });
      apply.disabled = state.kind === "applying" || (state.kind === "error" && !state.retryApply);
      apply.addEventListener("click", () => void this.applyProposal(container));
    }
    const cancel = actions.createEl("button", { text: "Cancel", attr: { type: "button" } });
    cancel.disabled = state.kind === "applying";
    cancel.addEventListener("click", () => {
      this.writeState = { kind: "idle", instruction: state.instruction };
      this.renderWritePanel(container);
    });
  }

  private async applyProposal(container: HTMLElement): Promise<void> {
    if (this.writeState.kind !== "review" && this.writeState.kind !== "error") return;
    if (this.writeState.kind === "error" && !this.writeState.retryApply) return;
    const { instruction, proposal, expiresAt } = this.writeState;
    if (!proposal) return;
    this.writeState = { kind: "applying", instruction, proposal, expiresAt };
    this.renderWritePanel(container);
    try {
      const result = await this.client.confirmMemoryWriteProposal(proposal.proposalId, {
        confirm: true,
      });
      if (result.proposalId !== proposal.proposalId) {
        throw new Error("The core returned a result for a different proposal.");
      }
      this.writeState = { kind: "success", instruction: "", result };
    } catch (error) {
      const status = error instanceof CaucoCoreApiError ? error.status : undefined;
      this.writeState = {
        kind: "error",
        instruction,
        proposal,
        expiresAt,
        message: this.writeErrorMessage(error, "apply"),
        retryApply: status === undefined || status >= 500,
        regenerate: status === 400 || status === 404 || status === 409 || status === 410 || status === 422,
      };
    }
    this.renderWritePanel(container);
  }

  private renderWriteResult(container: HTMLElement, result: MemoryWriteConfirmationResult): void {
    const card = container.createDiv({ cls: "cauco-write-result" });
    card.createEl("h4", { text: "Memory Change Applied" });
    const details = card.createEl("dl", { cls: "cauco-proposal-details" });
    this.addDetail(details, "State", result.state);
    this.addDetail(details, "Operation", OPERATION_LABELS[result.operation]);
    this.addDetail(details, "Target file", result.targetFile);
    this.addDetail(details, "Target section", result.targetSection);
    this.addDetail(details, "Memory refreshed", result.memoryRefreshed ? "Yes" : "No");
    this.addDetail(details, "Applied", this.formatTimestamp(result.appliedAt));
    card.createEl("h5", { text: "Applied Markdown" });
    card.createEl("pre", { text: result.appliedMarkdown, cls: "cauco-proposal-markdown" });
    this.renderWarnings(card, result.warnings, "Result warnings");
    card.createEl("p", {
      text: "The instruction was cleared after the successful write.",
      cls: "cauco-trust-note",
    });
    const another = card.createEl("button", {
      text: "Write Another Memory",
      attr: { type: "button" },
    });
    another.addEventListener("click", () => {
      this.writeState = { kind: "idle", instruction: "" };
      this.renderWritePanel(container);
    });
  }

  private addDetail(container: HTMLElement, term: string, description: string): void {
    container.createEl("dt", { text: term });
    container.createEl("dd", { text: description });
  }

  private renderWarnings(container: HTMLElement, warnings: string[], label: string): void {
    if (warnings.length === 0) return;
    const warning = container.createDiv({ cls: "cauco-write-warnings" });
    warning.createEl("strong", { text: label });
    const list = warning.createEl("ul");
    for (const message of warnings) list.createEl("li", { text: message });
  }

  private writeErrorMessage(error: unknown, phase: "generate" | "apply"): string {
    if (!(error instanceof CaucoCoreApiError)) {
      return phase === "apply"
        ? "The local memory service returned an invalid result. The write status could not be verified; review memory before trying again."
        : "The local memory service returned an invalid response. No memory was changed.";
    }
    if (error.status === 404 && phase === "apply") {
      return "This proposal is no longer available. The Cauco Core may have restarted. Generate a new proposal.";
    }
    if (error.status === 410) {
      return "This proposal has expired. Generate a new proposal before applying the change.";
    }
    if (error.status === 409) return `The proposal could not be applied: ${error.message}`;
    if (error.status === 400) return `The confirmation was rejected: ${error.message}`;
    if (error.status === 422) return `The proposal is invalid or unsafe: ${error.message}`;
    return phase === "apply"
      ? "Could not verify the result from the local Cauco Core. The proposal was preserved; review memory before trying again."
      : "Could not complete the request with the local Cauco Core. No memory was changed.";
  }

  private formatTimestamp(value: string): string {
    return new Date(value).toLocaleString();
  }

  private async refresh(
    button: HTMLButtonElement,
    count: HTMLElement,
    list: HTMLElement,
    preview: HTMLElement,
  ): Promise<void> {
    button.disabled = true;
    button.setText("Refreshing…");
    try {
      this.files = await this.client.getMemoryFiles();
      count.setText(`${this.files.length} Markdown file(s)`);
      this.renderList(list, preview, this.files);
      this.renderPreviewEmpty(preview);
    } catch (error) {
      preview.empty();
      this.renderError(preview, this.errorMessage(error));
    } finally {
      button.disabled = false;
      button.setText("Refresh memory");
    }
  }

  private async search(
    rawQuery: string,
    button: HTMLButtonElement,
    count: HTMLElement,
    list: HTMLElement,
    preview: HTMLElement,
  ): Promise<void> {
    const query = rawQuery.trim();
    if (!query) {
      count.setText(`${this.files.length} Markdown file(s)`);
      this.renderList(list, preview, this.files);
      return;
    }
    button.disabled = true;
    button.setText("Searching…");
    try {
      const results = await this.client.searchMemory(query);
      count.setText(`${results.length} matching file(s)`);
      this.renderList(list, preview, results);
    } catch (error) {
      list.empty();
      this.renderError(list, this.errorMessage(error));
    } finally {
      button.disabled = false;
      button.setText("Search");
    }
  }

  private renderList(
    container: HTMLElement,
    preview: HTMLElement,
    items: Array<MemoryFileMetadata | MemorySearchResult>,
  ): void {
    container.empty();
    if (items.length === 0) {
      container.createEl("p", { text: "No matching Markdown memory files.", cls: "cauco-empty" });
      return;
    }
    for (const item of items) {
      const entry: MemoryListItem = {
        relativePath: item.relativePath,
        title: item.title,
        excerpt: "excerpt" in item ? item.excerpt : undefined,
      };
      const button = container.createEl("button", {
        cls: "cauco-memory-item",
        attr: { type: "button" },
      });
      button.createEl("strong", { text: entry.title });
      button.createEl("span", { text: entry.relativePath });
      if (entry.excerpt) button.createEl("small", { text: entry.excerpt });
      button.addEventListener("click", () => void this.preview(entry.relativePath, preview));
    }
  }

  private async preview(relativePath: string, container: HTMLElement): Promise<void> {
    container.empty();
    container.createEl("p", { text: "Loading preview…", cls: "cauco-empty" });
    try {
      const memoryFile = await this.client.getMemoryFile(relativePath);
      container.empty();
      container.createEl("h3", { text: memoryFile.title });
      container.createEl("small", {
        text: `${memoryFile.relativePath} · ${memoryFile.size} bytes · read-only`,
        cls: "cauco-response-meta",
      });
      container.createEl("pre", { text: memoryFile.content });
    } catch (error) {
      container.empty();
      this.renderError(container, this.errorMessage(error));
    }
  }

  private renderPreviewEmpty(container: HTMLElement): void {
    container.empty();
    container.createEl("p", {
      text: "Select a memory file to preview it. Direct editing is not available.",
      cls: "cauco-empty",
    });
  }

  private renderError(container: HTMLElement, message: string): void {
    const error = container.createEl("p", { text: message, cls: "cauco-error" });
    error.setAttribute("role", "alert");
  }

  private errorMessage(error: unknown): string {
    return error instanceof Error ? error.message : "The memory request failed.";
  }
}
