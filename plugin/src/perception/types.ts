export type PerceptionCapability = "read" | "search" | "refresh" | "watch";

export type PerceptionModality =
  | "text"
  | "voice"
  | "file"
  | "email"
  | "calendar"
  | "repository"
  | "application"
  | "system_event";

export type PerceptionSourceStatus = "available" | "degraded" | "unavailable";

export interface PerceptionSourceMetadata {
  sourceId: string;
  name: string;
  description: string;
  capabilities: PerceptionCapability[];
}

export interface PerceptionHealth {
  sourceId: string;
  status: PerceptionSourceStatus;
  checkedAt: string;
  message: string | null;
}

export interface PerceptionSource {
  metadata: PerceptionSourceMetadata;
  health: PerceptionHealth;
}

export interface PerceptionSignal {
  signalId: string;
  sourceId: string;
  modality: PerceptionModality;
  observedAt: string;
  content: string;
  title: string | null;
  reference: string | null;
  confidence: number;
  metadata: Readonly<Record<string, unknown>>;
}

export interface PerceptionSourceError {
  sourceId: string;
  errorType: string;
  message: string;
}

export interface PerceptionCollectionResult {
  requestedSourceIds: string[];
  successfulSourceIds: string[];
  signals: PerceptionSignal[];
  errors: PerceptionSourceError[];
  collectedAt: string;
}

export interface PerceptionCollectRequest {
  sourceIds?: string[];
  query?: string;
  since?: string;
  limit?: number;
  metadata?: Record<string, unknown>;
  requiredCapability?: PerceptionCapability;
}
