import type {
  CognitiveCycleSnapshot,
  LearningGuidanceItem,
  MemoryCandidate,
  ReflectionReport,
} from "./types";

function record(value: unknown, name: string): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    throw new Error(`Invalid ${name} response.`);
  }
  return value as Record<string, unknown>;
}

function string(value: unknown, name: string): string {
  if (typeof value !== "string") throw new Error(`Invalid ${name}.`);
  return value;
}

function strings(value: unknown, name: string): string[] {
  if (!Array.isArray(value) || !value.every((item) => typeof item === "string")) {
    throw new Error(`Invalid ${name}.`);
  }
  return value;
}

function bool(value: unknown, name: string): boolean {
  if (typeof value !== "boolean") throw new Error(`Invalid ${name}.`);
  return value;
}

function counts(value: unknown, name: string): Record<string, number> {
  const result = record(value, name);
  for (const item of Object.values(result)) if (typeof item !== "number") throw new Error(`Invalid ${name}.`);
  return result as Record<string, number>;
}

export function parseCognitiveCycle(value: unknown): CognitiveCycleSnapshot {
  const item = record(value, "cognitive-cycle");
  return {
    reviewId: string(item.review_id, "review ID"), currentStage: string(item.current_stage, "stage"),
    overallStatus: string(item.overall_cycle_status, "cycle status"), blocked: bool(item.blocked, "blocked state"),
    terminal: bool(item.terminal, "terminal state"), awaitingHumanAction: bool(item.awaiting_human_action, "human-action state"),
    nextPermittedAction: item.next_permitted_action === null ? null : string(item.next_permitted_action, "next action"),
    safeEndpoint: item.safe_endpoint === null ? null : string(item.safe_endpoint, "safe endpoint"),
    relatedRecordIds: record(item.related_record_ids, "related record IDs"), candidateCounts: counts(item.candidate_counts, "candidate counts"),
    proposalCounts: counts(item.proposal_counts, "proposal counts"), warnings: strings(item.warnings, "cycle warnings"),
    limitations: strings(item.limitations, "cycle limitations"), method: string(item.method, "cycle method"),
  };
}

export function parseLearningGuidance(value: unknown): LearningGuidanceItem[] {
  const root = record(value, "learning guidance");
  if (!Array.isArray(root.guidance)) throw new Error("Invalid learning guidance items.");
  return root.guidance.map((raw) => {
    const item = record(raw, "learning guidance item");
    if (typeof item.confidence !== "number") throw new Error("Invalid guidance confidence.");
    return { candidateId: string(item.candidate_id, "candidate provenance"), experienceId: string(item.experience_id, "experience provenance"), proposalId: string(item.proposal_id, "proposal provenance"), category: string(item.category, "guidance category"), lesson: string(item.lesson, "lesson"), confidence: item.confidence, reasonSelected: string(item.reason_selected, "selection reason"), toolId: item.tool_id === null ? null : string(item.tool_id, "tool"), operationId: item.operation_id === null ? null : string(item.operation_id, "operation"), stepIndex: item.step_index === null ? null : Number(item.step_index) };
  });
}

export function parseReflection(value: unknown): ReflectionReport {
  const root = record(value, "reflection");
  const summary = counts(root.summary, "reflection summary");
  if (!Array.isArray(root.patterns)) throw new Error("Invalid reflection patterns.");
  const patterns = root.patterns.map((raw) => { const item = record(raw, "reflection pattern"); if (typeof item.count !== "number") throw new Error("Invalid reflection pattern count."); return { category: string(item.category, "pattern category"), lesson: string(item.lesson, "pattern lesson"), count: item.count }; });
  return { summary, patterns, method: string(root.method, "reflection method"), limitations: strings(root.limitations, "reflection limitations") };
}

export function parseMemoryCandidates(value: unknown): MemoryCandidate[] {
  const root = record(value, "memory candidates");
  if (!Array.isArray(root.candidates)) throw new Error("Invalid memory candidates.");
  return root.candidates.map((raw) => { const item = record(raw, "memory candidate"); const lesson = record(item.lesson, "candidate lesson"); const status = item.status; if (status !== "pending_review" && status !== "approved" && status !== "rejected" && status !== "expired") throw new Error("Invalid candidate status."); if (typeof lesson.confidence !== "number") throw new Error("Invalid candidate confidence."); return { candidateId: string(item.candidate_id, "candidate ID"), experienceId: string(item.experience_id, "experience ID"), verificationId: string(item.verification_id, "verification ID"), executionId: string(item.execution_id, "execution ID"), reviewId: string(item.review_id, "review ID"), lesson: { category: string(lesson.category, "candidate category"), observation: string(lesson.observation, "observation"), lesson: string(lesson.lesson, "candidate lesson"), confidence: lesson.confidence }, target: string(item.target, "candidate target"), status, disposition: item.disposition === null ? null : string(item.disposition, "candidate disposition"), rationale: string(item.rationale, "candidate rationale") }; });
}

export function parseMemoryCandidateRecord(value: unknown): MemoryCandidate {
  const root = record(value, "memory candidate");
  return parseMemoryCandidates({ candidates: [root] })[0]!;
}
