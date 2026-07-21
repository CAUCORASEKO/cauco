import { PerceptionApiClient } from "../perception/api";
import type {
  PerceptionCollectionResult,
  PerceptionSignal,
  PerceptionSource,
  PerceptionSourceError,
} from "../perception/types";

type PerceptionAction = "sources" | "recent" | "search";

export class CaucoPerceptionPanel {
  private readonly api: PerceptionApiClient;

  private sources: PerceptionSource[] = [];
  private result: PerceptionCollectionResult | null = null;
  private busyAction: PerceptionAction | null = null;
  private requestError: string | null = null;
  private lastOperationWasSearch = false;

  constructor(
    coreUrl: string,
    private readonly connected: boolean,
  ) {
    this.api = new PerceptionApiClient(coreUrl);
  }

  render(container: HTMLElement): void {
    const section = container.createEl("section", {
      cls: "cauco-perception",
    });

    const header = section.createDiv({
      cls: "cauco-panel-header",
    });

    header.createEl("h2", {
      text: "Perception",
    });

    const refreshButton = header.createEl("button", {
      text: "Refresh sources",
      attr: {
        type: "button",
      },
    });

    const summary = section.createEl("p", {
      cls: "cauco-perception-summary",
    });

    const requestErrorArea = section.createDiv({
      cls: "cauco-perception-request-error",
    });
    requestErrorArea.setAttribute("aria-live", "assertive");

    const sourceArea = section.createDiv({
      cls: "cauco-perception-sources",
    });

    const controls = section.createDiv({
      cls: "cauco-perception-controls",
    });

    const searchInput = controls.createEl("input", {
      type: "search",
      attr: {
        placeholder: "Search perception…",
        "aria-label": "Search perception",
        maxlength: "500",
      },
    });

    const searchButton = controls.createEl("button", {
      text: "Search",
      attr: {
        type: "button",
      },
    });

    const collectButton = controls.createEl("button", {
      text: "Collect recent",
      attr: {
        type: "button",
      },
    });

    const statusArea = section.createEl("p", {
      cls: "cauco-perception-status",
    });
    statusArea.setAttribute("aria-live", "polite");

    const signalsArea = section.createDiv({
      cls: "cauco-perception-signals",
    });

    const errorsArea = section.createDiv({
      cls: "cauco-perception-errors",
    });

    const render = (): void => {
      this.renderSummary(summary);
      this.renderRequestError(requestErrorArea);
      this.renderSources(sourceArea);
      this.renderSignals(signalsArea);
      this.renderCollectionErrors(errorsArea);
      this.renderStatus(statusArea);
      this.updateControls(
        refreshButton,
        searchButton,
        collectButton,
        searchInput,
      );
    };

    const run = async (
      action: PerceptionAction,
      query?: string,
    ): Promise<void> => {
      if (!this.connected || this.busyAction !== null) {
        return;
      }

      this.busyAction = action;
      this.requestError = null;
      render();

      try {
        if (action === "sources") {
          this.sources = await this.api.getSources();
        } else {
          this.lastOperationWasSearch = action === "search";
          this.result = await this.api.collect(
            action === "search"
              ? {
                  query,
                  limit: 20,
                }
              : {
                  limit: 20,
                },
          );
        }
      } catch (error) {
        this.requestError =
          error instanceof Error
            ? error.message
            : "The perception request failed.";
      } finally {
        this.busyAction = null;
        render();
      }
    };

    const runSearch = (): void => {
      const query = searchInput.value.trim();

      if (!query) {
        this.requestError = "Enter a search query before searching.";
        render();
        return;
      }

      void run("search", query);
    };

    refreshButton.addEventListener("click", () => {
      void run("sources");
    });

    collectButton.addEventListener("click", () => {
      void run("recent");
    });

    searchButton.addEventListener("click", runSearch);

    searchInput.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        runSearch();
      }
    });

    render();

    if (this.connected) {
      void run("sources").then(() => {
        if (this.connected && this.requestError === null) {
          return run("recent");
        }

        return undefined;
      });
    }
  }

  private renderSummary(container: HTMLElement): void {
    if (!this.connected) {
      container.setText("Perception unavailable · Last collection: Never");
      return;
    }

    const sourceCount = this.sources.length;
    const signalCount = this.result?.signals.length ?? 0;
    const collectedAt = this.result
      ? new Date(this.result.collectedAt).toLocaleString()
      : "Never";

    container.setText(
      `${sourceCount} ${sourceCount === 1 ? "source" : "sources"} · ` +
        `${signalCount} ${signalCount === 1 ? "signal" : "signals"} · ` +
        `Last collection: ${collectedAt}`,
    );
  }

  private renderRequestError(container: HTMLElement): void {
    container.empty();

    if (!this.requestError) {
      return;
    }

    container.createEl("p", {
      text: this.requestError,
      cls: "cauco-error",
      attr: {
        role: "alert",
      },
    });
  }

  private renderSources(container: HTMLElement): void {
    container.empty();

    container.createEl("h3", {
      text: "Sources",
    });

    if (!this.connected) {
      container.createEl("p", {
        text: "Perception unavailable.",
        cls: "cauco-empty",
      });
      return;
    }

    if (this.sources.length === 0) {
      container.createEl("p", {
        text:
          this.busyAction === "sources"
            ? "Loading perception sources…"
            : "No sources registered.",
        cls: "cauco-empty",
      });
      return;
    }

    for (const source of this.sources) {
      const item = container.createDiv({
        cls: "cauco-perception-source",
      });

      const itemHeader = item.createDiv({
        cls: "cauco-perception-source-header",
      });

      itemHeader.createEl("strong", {
        text: source.metadata.name,
      });

      const statusBadge = itemHeader.createSpan({
        text: source.health.status,
        cls: `cauco-perception-badge is-${source.health.status}`,
      });

      statusBadge.setAttribute(
        "aria-label",
        `Status: ${source.health.status}`,
      );

      item.createEl("small", {
        text: source.metadata.sourceId,
        cls: "cauco-perception-source-id",
      });

      if (source.metadata.description) {
        item.createEl("p", {
          text: source.metadata.description,
        });
      }

      const capabilities = item.createDiv({
        cls: "cauco-perception-capabilities",
      });

      for (const capability of source.metadata.capabilities) {
        capabilities.createSpan({
          text: capability,
          cls: "cauco-perception-capability",
        });
      }

      item.createEl("small", {
        text: `Checked ${new Date(
          source.health.checkedAt,
        ).toLocaleString()}`,
      });

      if (source.health.message) {
        item.createEl("p", {
          text: source.health.message,
          cls: "cauco-perception-health-message",
        });
      }
    }
  }

  private renderSignals(container: HTMLElement): void {
    container.empty();

    container.createEl("h3", {
      text: this.lastOperationWasSearch
        ? "Search results"
        : "Recent signals",
    });

    const signals = this.result?.signals ?? [];

    if (signals.length === 0) {
      container.createEl("p", {
        text: this.lastOperationWasSearch
          ? "No matches found."
          : "No signals collected.",
        cls: "cauco-empty",
      });
      return;
    }

    const ordered = [...signals].sort(
      (left, right) =>
        Date.parse(right.observedAt) - Date.parse(left.observedAt),
    );

    for (const signal of ordered) {
      this.renderSignal(container, signal);
    }
  }

  private renderSignal(
    container: HTMLElement,
    signal: PerceptionSignal,
  ): void {
    const item = container.createDiv({
      cls: "cauco-perception-signal",
    });

    const header = item.createDiv({
      cls: "cauco-perception-signal-header",
    });

    header.createEl("strong", {
      text: signal.title || "Untitled signal",
    });

    header.createSpan({
      text: signal.modality,
      cls: "cauco-perception-badge",
    });

    item.createEl("small", {
      text:
        `${signal.sourceId} · ` +
        `${new Date(signal.observedAt).toLocaleString()} · ` +
        `confidence ${Math.round(signal.confidence * 100)}%`,
    });

    if (signal.reference) {
      item.createEl("small", {
        text: `Reference: ${signal.reference}`,
        cls: "cauco-perception-reference",
      });
    }

    item.createEl("p", {
      text: signal.content || "No signal content.",
      cls: "cauco-perception-content",
    });
  }

  private renderCollectionErrors(container: HTMLElement): void {
    container.empty();

    container.createEl("h3", {
      text: "Collection errors",
    });

    const errors = this.result?.errors ?? [];

    if (errors.length === 0) {
      container.createEl("p", {
        text: "No collection errors.",
        cls: "cauco-empty",
      });
      return;
    }

    for (const error of errors) {
      this.renderCollectionError(container, error);
    }
  }

  private renderCollectionError(
    container: HTMLElement,
    error: PerceptionSourceError,
  ): void {
    const item = container.createDiv({
      cls: "cauco-perception-error",
    });

    item.createEl("strong", {
      text: error.sourceId,
    });

    item.createEl("small", {
      text: error.errorType,
    });

    item.createEl("p", {
      text: error.message,
    });
  }

  private renderStatus(container: HTMLElement): void {
    const messages: Record<PerceptionAction, string> = {
      sources: "Refreshing perception sources…",
      recent: "Collecting recent perception signals…",
      search: "Searching perception…",
    };

    container.setText(
      this.busyAction === null ? "" : messages[this.busyAction],
    );
  }

  private updateControls(
    refreshButton: HTMLButtonElement,
    searchButton: HTMLButtonElement,
    collectButton: HTMLButtonElement,
    searchInput: HTMLInputElement,
  ): void {
    const unavailable = !this.connected;
    const busy = this.busyAction !== null;

    refreshButton.disabled = unavailable || busy;
    searchButton.disabled = unavailable || busy;
    collectButton.disabled = unavailable || busy;
    searchInput.disabled = unavailable || busy;

    refreshButton.setText(
      this.busyAction === "sources"
        ? "Refreshing…"
        : "Refresh sources",
    );

    searchButton.setText(
      this.busyAction === "search" ? "Searching…" : "Search",
    );

    collectButton.setText(
      this.busyAction === "recent"
        ? "Collecting…"
        : "Collect recent",
    );
  }
}
