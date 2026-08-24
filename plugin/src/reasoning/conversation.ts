import type { ConversationEntry, ReasoningPlanningResponse } from "./types";

export interface ConversationResponseView {
  readonly planningStatus: string;
  readonly selectedAgent: string;
  readonly routingMatch: string;
  readonly safety: readonly [string, boolean][];
}

export function responseView(response: ReasoningPlanningResponse): ConversationResponseView {
  const routing = response.planning.routing;
  const selected = routing.selectedAgent;
  const match = routing.match;
  return Object.freeze({
    planningStatus: response.planning.status,
    selectedAgent: selected ? `${selected.name} (${selected.id})` : "No agent selected",
    routingMatch: match
      ? `${match.agentId}: ${match.matched ? "matched" : "not matched"} · score ${match.score}`
      : "No routing match",
    safety: Object.freeze<readonly [string, boolean][]>([
      ["proposal_only", response.planning.proposalOnly],
      ["execution_performed", response.planning.executionPerformed],
      ["review_approved", response.planning.reviewApproved],
      ["runtime_started", response.planning.runtimeStarted],
    ]),
  });
}

export class ConversationHistory {
  private readonly items: ConversationEntry[] = [];

  add(entry: ConversationEntry): void {
    this.items.push(Object.freeze(entry));
  }

  entries(): readonly ConversationEntry[] {
    return Object.freeze([...this.items]);
  }
}
