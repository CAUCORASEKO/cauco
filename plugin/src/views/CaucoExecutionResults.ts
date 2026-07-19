import { isRecord, safeDisplayText } from "../execution/contracts";
import type { AuditEvent, JsonValue, ToolResult } from "../execution/types";
import {
  addDetail,
  formatTimestamp,
  renderSafeError,
  statusLabel,
} from "./executionViewHelpers";

export function renderToolResult(card: HTMLElement, result: ToolResult): void {
  const details = card.createEl("details", { cls: "cauco-result-panel" });
  details.createEl("summary", {
    text: `${result.success ? "Successful" : "Failed"} real result · ${result.duration_ms} ms${result.truncated ? " · truncated" : ""}`,
  });
  if (result.tool_id === "git" && result.operation_id === "status") {
    renderGitResult(details, result);
  } else if (result.tool_id === "filesystem" && result.operation_id === "list_directory") {
    renderDirectoryResult(details, result);
  } else if (result.tool_id === "filesystem" && result.operation_id === "read_file") {
    details.createEl("p", {
      text: `Workspace file: ${structuredString(result.structured_data.path) ?? "approved relative path"}`,
      cls: "cauco-trust-note",
    });
  }
  if (result.error_message) renderSafeError(details, result.error_message);
  details.createEl("pre", {
    text: safeDisplayText(result.output),
    cls: "cauco-result-output",
  });
}

export function renderAuditTrail(section: HTMLElement, events: readonly AuditEvent[]): void {
  const details = section.createEl("details", { cls: "cauco-audit-panel" });
  details.createEl("summary", { text: `7. Audit trail (${events.length})` });
  const ordered = [...events].sort((a, b) => a.timestamp.localeCompare(b.timestamp));
  for (const event of ordered) {
    const item = details.createEl("article", { cls: "cauco-audit-event" });
    item.createEl("strong", { text: `${statusLabel(event.event_type)} · ${event.outcome}` });
    item.createEl("small", {
      text: `${formatTimestamp(event.timestamp)}${event.step_index === null ? "" : ` · step ${event.step_index}`}`,
      cls: "cauco-response-meta",
    });
    item.createEl("p", { text: safeDisplayText(event.safe_message, 500) });
    const metadata = Object.entries(event.metadata).slice(0, 10);
    if (metadata.length > 0) {
      item.createEl("small", {
        text: metadata
          .map(([key, value]) => `${key}: ${safeDisplayText(String(value), 100)}`)
          .join(" · "),
        cls: "cauco-response-meta",
      });
    }
  }
}

function renderGitResult(container: HTMLElement, result: ToolResult): void {
  const data = result.structured_data;
  const summary = container.createEl("dl", { cls: "cauco-control-details" });
  addDetail(summary, "Working tree", data.clean === true ? "Clean" : "Changes present");
  addDetail(summary, "Branch", structuredString(data.branch) ?? "Unavailable");
  if (Array.isArray(data.changed_entries)) {
    const list = container.createEl("ul", { cls: "cauco-result-list" });
    for (const entry of data.changed_entries.slice(0, 200)) {
      if (isRecord(entry)) {
        list.createEl("li", {
          text: `${typeof entry.status === "string" ? entry.status : ""} ${typeof entry.path === "string" ? safeDisplayText(entry.path, 500) : ""}`.trim(),
        });
      }
    }
  }
}

function renderDirectoryResult(container: HTMLElement, result: ToolResult): void {
  const data = result.structured_data;
  container.createEl("p", {
    text: `Relative directory: ${structuredString(data.path) ?? "."}`,
    cls: "cauco-trust-note",
  });
  if (!Array.isArray(data.entries)) return;
  const list = container.createEl("ul", { cls: "cauco-result-list" });
  for (const entry of data.entries.slice(0, 1000)) {
    if (!isRecord(entry)) continue;
    const path = typeof entry.path === "string" ? safeDisplayText(entry.path, 500) : "Unknown entry";
    const type = typeof entry.type === "string" ? entry.type : "unknown";
    const size = typeof entry.size === "number" ? ` · ${entry.size} bytes` : "";
    list.createEl("li", { text: `${path} · ${type}${size}` });
  }
}

function structuredString(value: JsonValue | undefined): string | null {
  return typeof value === "string" ? safeDisplayText(value, 500) : null;
}
