export interface ReasoningPlanRequest {
  readonly instruction: string;
  readonly useReasoning?: boolean;
  readonly intent?: string;
  readonly preferredAgentId?: string;
}

export interface ReasoningAgentMatch {
  readonly agentId: string;
  readonly matched: boolean;
  readonly score: number;
  readonly matchedSignals: readonly string[];
  readonly reasoning: readonly string[];
  readonly priority: number;
}

export interface ReasoningPlanStep {
  readonly order: number;
  readonly title: string;
  readonly description: string;
  readonly proposedAction: string;
  readonly requiresConfirmation: boolean;
  readonly executionAvailable: boolean;
  readonly warnings: readonly string[];
}

export interface ReasoningAgentPlan {
  readonly agentId: string;
  readonly agentName: string;
  readonly status: string;
  readonly objective: string;
  readonly steps: readonly ReasoningPlanStep[];
  readonly openQuestions: readonly string[];
  readonly warnings: readonly string[];
  readonly requiresConfirmation: boolean;
  readonly executionPerformed: boolean;
}

export interface ReasoningPlanningResponse {
  readonly reasoningRequested: boolean;
  readonly reasoningInvoked: boolean;
  readonly proposalProduced: boolean;
  readonly proposalValidated: boolean;
  readonly planningContextEnriched: boolean;
  readonly provider: string | null;
  readonly model: string | null;
  readonly explanation: string;
  readonly planning: {
    readonly status: string;
    readonly routing: {
      readonly selectedAgent: { readonly id: string; readonly name: string } | null;
      readonly match: ReasoningAgentMatch | null;
      readonly matches: readonly ReasoningAgentMatch[];
      readonly preferredAgentRejected: boolean;
    };
    readonly plan: ReasoningAgentPlan | null;
    readonly proposalOnly: boolean;
    readonly executionPerformed: boolean;
    readonly reviewApproved: boolean;
    readonly runtimeStarted: boolean;
  };
  readonly raw: Readonly<Record<string, unknown>>;
}

export interface ConversationEntry {
  readonly instruction: string;
  readonly useReasoning: boolean;
  readonly response?: ReasoningPlanningResponse;
  readonly error?: string;
}
