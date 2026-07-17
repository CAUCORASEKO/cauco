import { CaucoCoreClient } from "../services/CaucoCoreClient";
import type { MemoryFileMetadata, MemorySearchResult } from "../types";

interface MemoryListItem {
  relativePath: string;
  title: string;
  excerpt?: string;
}

export class CaucoMemoryPanel {
  private files: MemoryFileMetadata[];

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
    const refresh = header.createEl("button", { text: "Refresh memory" });
    refresh.setAttribute("aria-label", "Refresh Markdown memory files");

    if (this.initialError) this.renderError(section, this.initialError);

    const controls = section.createDiv({ cls: "cauco-memory-controls" });
    const search = controls.createEl("input", {
      type: "search",
      attr: { placeholder: "Search memory…", "aria-label": "Search memory" },
    });
    search.maxLength = 200;
    const searchButton = controls.createEl("button", { text: "Search" });
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
      const button = container.createEl("button", { cls: "cauco-memory-item" });
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
      text: "Select a memory file to preview it. Editing is not available.",
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
