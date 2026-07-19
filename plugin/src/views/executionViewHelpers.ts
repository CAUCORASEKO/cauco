import { safeDisplayText } from "../execution/contracts";
import type { ToolReadiness } from "../execution/types";

export function addDetail(container: HTMLElement, term: string, value: string): void {
  container.createEl("dt", { text: term });
  container.createEl("dd", { text: safeDisplayText(value, 1000) });
}

export function addBadge(container: HTMLElement, text: string): void {
  container.createEl("span", {
    text,
    cls: `cauco-status-badge is-${text.toLowerCase().replaceAll(" ", "-")}`,
  });
}

export function renderWarnings(container: HTMLElement, warnings: readonly string[]): void {
  if (warnings.length === 0) return;
  const list = container.createEl("ul", { cls: "cauco-warning-list" });
  for (const warning of warnings) list.createEl("li", { text: safeDisplayText(warning, 500) });
}

export function renderSafeError(container: HTMLElement, message: string): void {
  const error = container.createEl("p", {
    text: safeDisplayText(message, 500),
    cls: "cauco-error",
  });
  error.setAttribute("role", "alert");
}

export function readinessBlockingReason(readiness: ToolReadiness): string {
  if (!readiness.registered) return "Tool metadata is not registered.";
  if (!readiness.operation_exists) return "The requested operation is not declared.";
  if (!readiness.enabled) return "The operation is disabled.";
  if (!readiness.runtime_execution_allowed) return "Runtime policy blocks this operation.";
  if (!readiness.adapter_available) return "No runtime adapter is available.";
  return "Core does not currently consider this step executable.";
}

export function shortId(value: string): string {
  return value.length <= 18 ? value : `${value.slice(0, 10)}…${value.slice(-6)}`;
}

export function statusLabel(value: string): string {
  return value.replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export function formatTimestamp(value: string): string {
  return new Date(value).toLocaleString();
}
