import { requestUrl } from "obsidian";
import type {
  CaucoStatus,
  ConnectionResult,
  HealthResponse,
  StatusSection,
} from "../types";

const OFFLINE_STATUS: CaucoStatus = {
  runtime: { status: "offline", version: "unavailable" },
  memory: { status: "unavailable", files: 0 },
  agents: { status: "unavailable", registered: 0, active: 0 },
  tools: { status: "unavailable", registered: 0 },
  scheduler: { status: "unavailable", jobs: 0 },
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function parseHealth(value: unknown): HealthResponse {
  if (
    !isRecord(value) ||
    value.status !== "ok" ||
    value.service !== "cauco-core" ||
    typeof value.version !== "string"
  ) {
    throw new Error("The core returned an invalid health response.");
  }
  return { status: "ok", service: "cauco-core", version: value.version };
}

function parseSection(value: unknown, name: string): StatusSection {
  if (!isRecord(value) || typeof value.status !== "string") {
    throw new Error(`The core returned an invalid ${name} status.`);
  }
  const section: StatusSection = { status: value.status };
  for (const [key, item] of Object.entries(value)) {
    if (key !== "status" && (typeof item === "string" || typeof item === "number")) {
      section[key] = item;
    }
  }
  return section;
}

function parseStatus(value: unknown): CaucoStatus {
  if (!isRecord(value)) {
    throw new Error("The core returned an invalid status response.");
  }
  return {
    runtime: parseSection(value.runtime, "runtime"),
    memory: parseSection(value.memory, "memory"),
    agents: parseSection(value.agents, "agents"),
    tools: parseSection(value.tools, "tools"),
    scheduler: parseSection(value.scheduler, "scheduler"),
  };
}

export class CaucoCoreClient {
  constructor(private readonly coreUrl: string) {}

  async checkConnection(): Promise<ConnectionResult> {
    try {
      const healthResponse = await requestUrl({ url: `${this.coreUrl}/health` });
      const health = parseHealth(healthResponse.json as unknown);
      const statusResponse = await requestUrl({ url: `${this.coreUrl}/api/status` });
      return {
        connected: true,
        health,
        status: parseStatus(statusResponse.json as unknown),
      };
    } catch (error) {
      const message = error instanceof Error ? error.message : "Unknown connection error.";
      return { connected: false, status: OFFLINE_STATUS, error: message };
    }
  }
}
