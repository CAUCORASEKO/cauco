import { requestUrl } from "obsidian";
import type {
  AIChatResponse,
  AIModel,
  AIStatus,
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

function parseAIStatus(value: unknown): AIStatus {
  if (
    !isRecord(value) ||
    value.provider !== "ollama" ||
    typeof value.available !== "boolean" ||
    typeof value.base_url !== "string" ||
    typeof value.default_model !== "string" ||
    typeof value.default_model_installed !== "boolean" ||
    typeof value.models_count !== "number"
  ) {
    throw new Error("The core returned an invalid AI status response.");
  }
  return {
    provider: "ollama",
    available: value.available,
    baseUrl: value.base_url,
    defaultModel: value.default_model,
    defaultModelInstalled: value.default_model_installed,
    modelsCount: value.models_count,
  };
}

function parseModel(value: unknown): AIModel {
  if (
    !isRecord(value) ||
    typeof value.name !== "string" ||
    typeof value.size !== "number" ||
    !(typeof value.parameter_size === "string" || value.parameter_size === null) ||
    !(typeof value.quantization_level === "string" || value.quantization_level === null)
  ) {
    throw new Error("The core returned invalid model metadata.");
  }
  return {
    name: value.name,
    size: value.size,
    parameterSize: value.parameter_size,
    quantizationLevel: value.quantization_level,
  };
}

function parseModels(value: unknown): AIModel[] {
  if (!isRecord(value) || value.provider !== "ollama" || !Array.isArray(value.models)) {
    throw new Error("The core returned an invalid model list.");
  }
  return value.models.map(parseModel);
}

function parseChat(value: unknown): AIChatResponse {
  if (
    !isRecord(value) ||
    value.provider !== "ollama" ||
    typeof value.model !== "string" ||
    typeof value.response !== "string" ||
    value.used_memory !== false ||
    !Array.isArray(value.used_tools) ||
    value.used_tools.length !== 0 ||
    !value.used_tools.every((item) => typeof item === "string") ||
    !Array.isArray(value.used_agents) ||
    value.used_agents.length !== 0 ||
    !value.used_agents.every((item) => typeof item === "string")
  ) {
    throw new Error("The core returned an invalid chat response.");
  }
  return {
    provider: "ollama",
    model: value.model,
    response: value.response,
    usedMemory: false,
    usedTools: value.used_tools,
    usedAgents: value.used_agents,
  };
}

export class CaucoCoreClient {
  constructor(private readonly coreUrl: string) {}

  async checkConnection(): Promise<ConnectionResult> {
    try {
      const healthResponse = await requestUrl({ url: `${this.coreUrl}/health` });
      const health = parseHealth(healthResponse.json as unknown);
      const statusResponse = await requestUrl({ url: `${this.coreUrl}/api/status` });
      const result: ConnectionResult = {
        connected: true,
        health,
        status: parseStatus(statusResponse.json as unknown),
      };
      try {
        result.aiStatus = await this.getAIStatus();
        if (result.aiStatus.available) {
          result.models = await this.getModels();
        } else {
          result.models = [];
        }
      } catch (error) {
        result.aiError = this.errorMessage(error);
        result.models = [];
      }
      return result;
    } catch (error) {
      const message = error instanceof Error ? error.message : "Unknown connection error.";
      return { connected: false, status: OFFLINE_STATUS, error: message };
    }
  }

  async getAIStatus(): Promise<AIStatus> {
    const response = await requestUrl({ url: `${this.coreUrl}/api/ai/status` });
    return parseAIStatus(response.json as unknown);
  }

  async getModels(): Promise<AIModel[]> {
    const response = await requestUrl({ url: `${this.coreUrl}/api/ai/models` });
    return parseModels(response.json as unknown);
  }

  async chat(message: string, model?: string): Promise<AIChatResponse> {
    const body: { message: string; model?: string } = { message };
    if (model) body.model = model;
    const response = await requestUrl({
      url: `${this.coreUrl}/api/ai/chat`,
      method: "POST",
      contentType: "application/json",
      body: JSON.stringify(body),
    });
    return parseChat(response.json as unknown);
  }

  private errorMessage(error: unknown): string {
    return error instanceof Error ? error.message : "Unknown local AI error.";
  }
}
