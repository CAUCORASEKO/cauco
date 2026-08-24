import type {
  ReasoningAgentMatch,
  ReasoningAgentPlan,
  ReasoningPlanStep,
  ReasoningPlanningResponse,
} from "./types";

function invalid(): never {
  throw new Error("Cauco Core returned an invalid advisory planning response.");
}

function record(value: unknown): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) invalid();
  return value as Record<string, unknown>;
}

function string(value: unknown): string {
  if (typeof value !== "string") invalid();
  return value;
}

function nullableString(value: unknown): string | null {
  if (value !== null && typeof value !== "string") invalid();
  return value as string | null;
}

function boolean(value: unknown): boolean {
  if (typeof value !== "boolean") invalid();
  return value;
}

function number(value: unknown): number {
  if (typeof value !== "number" || !Number.isFinite(value)) invalid();
  return value;
}

function strings(value: unknown): readonly string[] {
  if (!Array.isArray(value) || !value.every((item) => typeof item === "string")) invalid();
  return Object.freeze([...value]);
}

function match(value: unknown): ReasoningAgentMatch {
  const item = record(value);
  return Object.freeze({
    agentId: string(item.agent_id),
    matched: boolean(item.matched),
    score: number(item.score),
    matchedSignals: strings(item.matched_signals),
    reasoning: strings(item.reasoning),
    priority: number(item.priority),
  });
}

function step(value: unknown): ReasoningPlanStep {
  const item = record(value);
  return Object.freeze({
    order: number(item.order),
    title: string(item.title),
    description: string(item.description),
    proposedAction: string(item.proposed_action),
    requiresConfirmation: boolean(item.requires_confirmation),
    executionAvailable: boolean(item.execution_available),
    warnings: strings(item.warnings),
  });
}

function plan(value: unknown): ReasoningAgentPlan | null {
  if (value === null) return null;
  const item = record(value);
  if (!Array.isArray(item.steps)) invalid();
  return Object.freeze({
    agentId: string(item.agent_id),
    agentName: string(item.agent_name),
    status: string(item.status),
    objective: string(item.objective),
    steps: Object.freeze(item.steps.map(step)),
    openQuestions: strings(item.open_questions),
    warnings: strings(item.warnings),
    requiresConfirmation: boolean(item.requires_confirmation),
    executionPerformed: boolean(item.execution_performed),
  });
}

export function parseReasoningPlanningResponse(value: unknown): ReasoningPlanningResponse {
  const root = record(value);
  const planning = record(root.planning);
  const routing = record(planning.routing);
  const selected = routing.selected_agent === null ? null : record(routing.selected_agent);
  if (!Array.isArray(routing.matches)) invalid();

  return Object.freeze({
    reasoningRequested: boolean(root.reasoning_requested),
    reasoningInvoked: boolean(root.reasoning_invoked),
    proposalProduced: boolean(root.proposal_produced),
    proposalValidated: boolean(root.proposal_validated),
    planningContextEnriched: boolean(root.planning_context_enriched),
    provider: nullableString(root.provider),
    model: nullableString(root.model),
    explanation: string(root.explanation),
    planning: Object.freeze({
      status: string(planning.status),
      routing: Object.freeze({
        selectedAgent:
          selected === null
            ? null
            : Object.freeze({ id: string(selected.id), name: string(selected.name) }),
        match: routing.match === null ? null : match(routing.match),
        matches: Object.freeze(routing.matches.map(match)),
        preferredAgentRejected: boolean(routing.preferred_agent_rejected),
      }),
      plan: plan(planning.plan),
      proposalOnly: boolean(planning.proposal_only),
      executionPerformed: boolean(planning.execution_performed),
      reviewApproved: boolean(planning.review_approved),
      runtimeStarted: boolean(planning.runtime_started),
    }),
    raw: Object.freeze({ ...root }),
  });
}
