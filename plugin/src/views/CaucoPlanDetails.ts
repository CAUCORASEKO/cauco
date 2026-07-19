import { safeDisplayText } from "../execution/contracts";
import type { AgentContext, AgentPlan, PlanReadiness } from "../execution/types";
import {
  addBadge,
  addDetail,
  readinessBlockingReason,
  renderWarnings,
  shortId,
} from "./executionViewHelpers";

export function renderPlanSteps(
  section: HTMLElement,
  plan: AgentPlan,
  readiness: PlanReadiness | null,
): void {
  const cards = section.createDiv({ cls: "cauco-step-list" });
  plan.steps.forEach((step, index) => {
    const item = readiness?.references[index] ?? null;
    const card = cards.createEl("article", { cls: "cauco-step-card" });
    const title = card.createDiv({ cls: "cauco-step-heading" });
    title.createEl("h4", { text: `${step.order}. ${step.title}` });
    addBadge(title, item?.executable_now ? "Ready" : item ? "Blocked" : "Not reviewed");
    card.createEl("p", { text: step.description });
    const details = card.createEl("dl", { cls: "cauco-control-details" });
    addDetail(details, "Tool", `${step.tool_reference.tool_id}.${step.tool_reference.operation_id}`);
    addDetail(details, "Target", step.tool_reference.target ?? "Configured workspace");
    addDetail(
      details,
      "Confirmation",
      item?.confirmation_required ? "Required" : "Step click required",
    );
    addDetail(details, "Runtime allowed", item?.runtime_execution_allowed ? "Yes" : "No");
    addDetail(details, "Adapter available", item?.adapter_available ? "Yes" : "No");
    addDetail(details, "Executable now", item?.executable_now ? "Yes" : "No");
    if (item && !item.executable_now) {
      card.createEl("p", { text: readinessBlockingReason(item), cls: "cauco-blocked-note" });
    }
    renderWarnings(card, step.warnings);
  });
}

export function renderPlanContext(root: HTMLElement, context: AgentContext): void {
  const details = root.createEl("details", {
    cls: "cauco-control-section cauco-context-panel",
  });
  details.createEl("summary", {
    text: `3. Context and provenance (${context.memory_references.length})`,
  });
  details.createEl("p", { text: context.context_summary, cls: "cauco-trust-note" });
  if (context.memory_references.length === 0) {
    details.createEl("p", {
      text: "No grounded memory context was selected.",
      cls: "cauco-empty",
    });
  }
  for (const reference of context.memory_references) {
    const item = details.createEl("article", { cls: "cauco-context-item" });
    item.createEl("h4", { text: reference.title || reference.name });
    item.createEl("small", {
      text: `${reference.kind} · ${reference.layer} · ${reference.relative_path}`,
      cls: "cauco-response-meta",
    });
    item.createEl("p", { text: reference.reason_selected });
    item.createEl("pre", {
      text: safeDisplayText(reference.excerpt, 4000),
      cls: "cauco-result-output",
    });
    item.createEl("small", {
      text: `Provenance: ${shortId(reference.memory_id)}${reference.excerpt_truncated ? " · excerpt truncated" : ""}`,
      cls: "cauco-response-meta",
    });
  }
}
