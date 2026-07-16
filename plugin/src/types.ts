export interface CaucoSettings {
  coreUrl: string;
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
}
