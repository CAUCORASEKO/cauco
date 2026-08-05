export interface CognitiveCycleSnapshot {
  reviewId: string;
  currentStage: string;
  overallStatus: string;
  blocked: boolean;
  terminal: boolean;
  awaitingHumanAction: boolean;
  nextPermittedAction: string | null;
  safeEndpoint: string | null;
  relatedRecordIds: Record<string, unknown>;
  candidateCounts: Record<string, number>;
  proposalCounts: Record<string, number>;
  warnings: string[];
  limitations: string[];
  method: string;
}

export interface LearningGuidanceItem {
  candidateId: string;
  experienceId: string;
  proposalId: string;
  category: string;
  lesson: string;
  confidence: number;
  reasonSelected: string;
  toolId: string | null;
  operationId: string | null;
  stepIndex: number | null;
}

export interface ReflectionReport {
  summary: Record<string, number>;
  patterns: Array<{ category: string; lesson: string; count: number }>;
  method: string;
  limitations: string[];
}

export interface MemoryCandidate {
  candidateId: string;
  experienceId: string;
  verificationId: string;
  executionId: string;
  reviewId: string;
  lesson: { category: string; observation: string; lesson: string; confidence: number };
  target: string;
  status: "pending_review" | "approved" | "rejected" | "expired";
  disposition: string | null;
  rationale: string;
}
