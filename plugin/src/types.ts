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
  usedMemory: false;
  usedTools: string[];
  usedAgents: string[];
}
