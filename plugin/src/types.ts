export interface CaucoSettings {
  coreUrl: string;
  selectedModel: string;
}

export interface HealthResponse {
  status: "ok";
  service: "cauco-core";
  version: string;
}

export interface StatusSection {
  status: string;
  [key: string]: string | number;
}

export interface CaucoStatus {
  runtime: StatusSection;
  memory: StatusSection;
  agents: StatusSection;
  tools: StatusSection;
  scheduler: StatusSection;
}

export interface ConnectionResult {
  connected: boolean;
  health?: HealthResponse;
  status: CaucoStatus;
  error?: string;
  aiStatus?: AIStatus;
  models?: AIModel[];
  aiError?: string;
  memoryFiles?: MemoryFileMetadata[];
  memoryError?: string;
}

export interface AIStatus {
  provider: "ollama";
  available: boolean;
  baseUrl: string;
  defaultModel: string;
  defaultModelInstalled: boolean;
  modelsCount: number;
}

export interface AIModel {
  name: string;
  size: number;
  parameterSize: string | null;
  quantizationLevel: string | null;
}

export interface AIChatResponse {
  provider: "ollama";
  model: string;
  response: string;
  usedMemory: boolean;
  memorySources: string[];
  usedTools: string[];
  usedAgents: string[];
}

export interface MemoryFileMetadata {
  relativePath: string;
  name: string;
  size: number;
  modifiedAt: string | null;
  title: string;
}

export interface MemoryFileContent extends MemoryFileMetadata {
  content: string;
}

export interface MemorySearchResult {
  relativePath: string;
  title: string;
  score: number;
  matchedTerms: string[];
  excerpt: string;
}

export type MemoryWriteOperation =
  | "add_task"
  | "add_decision"
  | "add_relationship_note"
  | "add_project_note";

export type MemoryWriteProposalState = "pending" | "applied" | "expired";

export interface MemoryWriteProposal {
  proposalId: string;
  operation: MemoryWriteOperation;
  targetFile: string;
  targetKind: string;
  targetLayer: string;
  targetSection: string;
  normalizedContent: string;
  markdownPreview: string;
  originalInstruction: string;
  reasoning: string[];
  warnings: string[];
  requiresConfirmation: boolean;
  createdAt: string;
  sourceType?: string | null;
  sourceId?: string | null;
  source_type?: string | null;
  source_id?: string | null;
}

export interface MemoryWriteProposalRecord {
  proposal: MemoryWriteProposal;
  state: MemoryWriteProposalState;
  createdAt: string;
  expiresAt: string;
  appliedAt: string | null;
}

export interface MemoryWriteConfirmationResult {
  proposalId: string;
  state: MemoryWriteProposalState;
  operation: MemoryWriteOperation;
  targetFile: string;
  targetSection: string;
  appliedMarkdown: string;
  memoryRefreshed: boolean;
  appliedAt: string;
  warnings: string[];
}
