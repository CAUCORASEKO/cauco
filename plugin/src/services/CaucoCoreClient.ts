import { requestUrl } from "obsidian";
import { ExecutionApiClient } from "../execution/api";
import type { CoreErrorKind } from "../execution/errors";
import type {
  AgentPlanningResponse,
  ExecutionRecord,
  PlanReview,
  StepExecutionControls,
  MutationPreview,
} from "../execution/types";
import type {
  AIChatResponse,
  AIModel,
  AIStatus,
  CaucoStatus,
  ConnectionResult,
  HealthResponse,
  MemoryFileContent,
  MemoryFileMetadata,
  MemorySearchResult,
  MemoryWriteConfirmationResult,
  MemoryWriteOperation,
  MemoryWriteProposal,
  MemoryWriteProposalRecord,
  StatusSection,
} from "../types";
import { parseCognitiveCycle, parseLearningGuidance, parseMemoryCandidates, parseReflection } from "../cognitive/api";
import type { CognitiveCycleSnapshot, LearningGuidanceItem, MemoryCandidate, ReflectionReport } from "../cognitive/types";

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
    typeof value.used_memory !== "boolean" ||
    !Array.isArray(value.memory_sources) ||
    !value.memory_sources.every((item) => typeof item === "string") ||
    value.used_memory !== (value.memory_sources.length > 0) ||
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
    usedMemory: value.used_memory,
    memorySources: value.memory_sources,
    usedTools: value.used_tools,
    usedAgents: value.used_agents,
  };
}

function parseMemoryMetadata(value: unknown): MemoryFileMetadata {
  if (
    !isRecord(value) ||
    typeof value.relative_path !== "string" ||
    typeof value.name !== "string" ||
    typeof value.size !== "number" ||
    !(typeof value.modified_at === "string" || value.modified_at === null) ||
    typeof value.title !== "string"
  ) {
    throw new Error("The core returned invalid memory file metadata.");
  }
  return {
    relativePath: value.relative_path,
    name: value.name,
    size: value.size,
    modifiedAt: value.modified_at,
    title: value.title,
  };
}

function parseMemoryFiles(value: unknown): MemoryFileMetadata[] {
  if (!isRecord(value) || !Array.isArray(value.files) || typeof value.count !== "number") {
    throw new Error("The core returned an invalid memory file list.");
  }
  const files = value.files.map(parseMemoryMetadata);
  if (files.length !== value.count) throw new Error("The memory file count is inconsistent.");
  return files;
}

function parseMemoryFile(value: unknown): MemoryFileContent {
  const metadata = parseMemoryMetadata(value);
  if (!isRecord(value) || typeof value.content !== "string") {
    throw new Error("The core returned invalid memory file content.");
  }
  return { ...metadata, content: value.content };
}

function parseMemorySearch(value: unknown): MemorySearchResult[] {
  if (!isRecord(value) || !Array.isArray(value.results) || typeof value.count !== "number") {
    throw new Error("The core returned an invalid memory search response.");
  }
  const results = value.results.map((item): MemorySearchResult => {
    if (
      !isRecord(item) ||
      typeof item.relative_path !== "string" ||
      typeof item.title !== "string" ||
      typeof item.score !== "number" ||
      !Array.isArray(item.matched_terms) ||
      !item.matched_terms.every((term) => typeof term === "string") ||
      typeof item.excerpt !== "string"
    ) {
      throw new Error("The core returned an invalid memory search result.");
    }
    return {
      relativePath: item.relative_path,
      title: item.title,
      score: item.score,
      matchedTerms: item.matched_terms,
      excerpt: item.excerpt,
    };
  });
  if (results.length !== value.count) throw new Error("The memory result count is inconsistent.");
  return results;
}

const MEMORY_WRITE_OPERATIONS: MemoryWriteOperation[] = [
  "add_task",
  "add_decision",
  "add_relationship_note",
  "add_project_note",
];

function isMemoryWriteOperation(value: unknown): value is MemoryWriteOperation {
  return MEMORY_WRITE_OPERATIONS.some((operation) => operation === value);
}

function parseStringList(value: unknown, name: string): string[] {
  if (!Array.isArray(value) || !value.every((item) => typeof item === "string")) {
    throw new Error(`The core returned invalid ${name}.`);
  }
  return value;
}

function parseTimestamp(value: unknown, name: string): string {
  if (typeof value !== "string" || Number.isNaN(Date.parse(value))) {
    throw new Error(`The core returned an invalid ${name}.`);
  }
  return value;
}

function parseTargetFile(value: unknown): string {
  if (
    typeof value !== "string" ||
    !value ||
    value.startsWith("/") ||
    value.startsWith("\\") ||
    /^[A-Za-z]:/.test(value) ||
    value.split(/[\\/]/).includes("..")
  ) {
    throw new Error("The core returned an unsafe memory target.");
  }
  return value;
}

function parseMemoryWriteProposal(value: unknown): MemoryWriteProposal {
  if (
    !isRecord(value) ||
    typeof value.proposal_id !== "string" ||
    !isMemoryWriteOperation(value.operation) ||
    typeof value.target_kind !== "string" ||
    typeof value.target_layer !== "string" ||
    typeof value.target_section !== "string" ||
    typeof value.normalized_content !== "string" ||
    typeof value.markdown_preview !== "string" ||
    typeof value.original_instruction !== "string" ||
    value.requires_confirmation !== true
  ) {
    throw new Error("The core returned an invalid memory write proposal.");
  }
  return {
    proposalId: value.proposal_id,
    operation: value.operation,
    targetFile: parseTargetFile(value.target_file),
    targetKind: value.target_kind,
    targetLayer: value.target_layer,
    targetSection: value.target_section,
    normalizedContent: value.normalized_content,
    markdownPreview: value.markdown_preview,
    originalInstruction: value.original_instruction,
    reasoning: parseStringList(value.reasoning, "proposal reasoning"),
    warnings: parseStringList(value.warnings, "proposal warnings"),
    requiresConfirmation: true,
    createdAt: parseTimestamp(value.created_at, "proposal timestamp"),
  };
}

function parseProposalState(value: unknown): "pending" | "applied" | "expired" {
  if (value !== "pending" && value !== "applied" && value !== "expired") {
    throw new Error("The core returned an invalid proposal state.");
  }
  return value;
}

function parseMemoryWriteProposalRecord(value: unknown): MemoryWriteProposalRecord {
  if (!isRecord(value)) throw new Error("The core returned an invalid proposal record.");
  return {
    proposal: parseMemoryWriteProposal(value.proposal),
    state: parseProposalState(value.state),
    createdAt: parseTimestamp(value.created_at, "record creation timestamp"),
    expiresAt: parseTimestamp(value.expires_at, "proposal expiration timestamp"),
    appliedAt:
      value.applied_at === null ? null : parseTimestamp(value.applied_at, "application timestamp"),
  };
}

function parseMemoryWriteConfirmation(value: unknown): MemoryWriteConfirmationResult {
  if (
    !isRecord(value) ||
    typeof value.proposal_id !== "string" ||
    !isMemoryWriteOperation(value.operation) ||
    typeof value.target_section !== "string" ||
    typeof value.applied_markdown !== "string" ||
    typeof value.memory_refreshed !== "boolean"
  ) {
    throw new Error("The core returned an invalid memory write result.");
  }
  return {
    proposalId: value.proposal_id,
    state: parseProposalState(value.state),
    operation: value.operation,
    targetFile: parseTargetFile(value.target_file),
    targetSection: value.target_section,
    appliedMarkdown: value.applied_markdown,
    memoryRefreshed: value.memory_refreshed,
    appliedAt: parseTimestamp(value.applied_at, "application timestamp"),
    warnings: parseStringList(value.warnings, "application warnings"),
  };
}

export class CaucoCoreApiError extends Error {
  constructor(
    readonly status: number | undefined,
    message: string,
    readonly kind: CoreErrorKind = "server",
  ) {
    super(message);
    this.name = "CaucoCoreApiError";
  }
}

export class CaucoCoreClient {
  private readonly executionApi: ExecutionApiClient;

  constructor(private readonly coreUrl: string) {
    this.executionApi = new ExecutionApiClient((path, method, body, timeoutMs) =>
      this.coreJsonRequest(path, method, body, timeoutMs),
    );
  }

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
      try {
        result.memoryFiles = await this.getMemoryFiles();
      } catch (error) {
        result.memoryError = this.errorMessage(error);
        result.memoryFiles = [];
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

  async chat(message: string, model?: string, useMemory = true): Promise<AIChatResponse> {
    const body: { message: string; model?: string; use_memory: boolean } = {
      message,
      use_memory: useMemory,
    };
    if (model) body.model = model;
    const response = await requestUrl({
      url: `${this.coreUrl}/api/ai/chat`,
      method: "POST",
      contentType: "application/json",
      body: JSON.stringify(body),
    });
    return parseChat(response.json as unknown);
  }

  async getMemoryFiles(): Promise<MemoryFileMetadata[]> {
    const response = await requestUrl({ url: `${this.coreUrl}/api/memory/files` });
    return parseMemoryFiles(response.json as unknown);
  }

  async getCognitiveCycle(reviewId: string): Promise<CognitiveCycleSnapshot> {
    const value = await this.coreJsonRequest(`/api/cognitive-cycles/reviews/${encodeURIComponent(reviewId)}`, "GET", undefined, 10000);
    return parseCognitiveCycle(value);
  }

  async getLearningGuidance(instruction: string): Promise<LearningGuidanceItem[]> {
    const value = await this.coreJsonRequest(`/api/learning-guidance?instruction=${encodeURIComponent(instruction)}&limit=3`, "GET", undefined, 10000);
    return parseLearningGuidance(value);
  }

  async getReflection(): Promise<ReflectionReport> {
    const value = await this.coreJsonRequest("/api/reflection", "GET", undefined, 10000);
    return parseReflection(value);
  }

  async getMemoryCandidates(): Promise<MemoryCandidate[]> {
    const value = await this.coreJsonRequest("/api/memory-candidates?limit=100", "GET", undefined, 10000);
    return parseMemoryCandidates(value);
  }

  async getMemoryFile(relativePath: string): Promise<MemoryFileContent> {
    const path = encodeURIComponent(relativePath);
    const response = await requestUrl({ url: `${this.coreUrl}/api/memory/file?path=${path}` });
    return parseMemoryFile(response.json as unknown);
  }

  async searchMemory(query: string, limit = 10): Promise<MemorySearchResult[]> {
    const q = encodeURIComponent(query);
    const response = await requestUrl({
      url: `${this.coreUrl}/api/memory/search?q=${q}&limit=${limit}`,
    });
    return parseMemorySearch(response.json as unknown);
  }

  async createMemoryWriteProposal(request: {
    instruction: string;
  }): Promise<MemoryWriteProposal> {
    const value = await this.memoryWriteRequest("/api/memory/write-proposals", "POST", request);
    return parseMemoryWriteProposal(value);
  }

  async getMemoryWriteProposal(proposalId: string): Promise<MemoryWriteProposalRecord> {
    const id = encodeURIComponent(proposalId);
    const value = await this.memoryWriteRequest(`/api/memory/write-proposals/${id}`, "GET");
    return parseMemoryWriteProposalRecord(value);
  }

  async confirmMemoryWriteProposal(
    proposalId: string,
    request: { confirm: true },
  ): Promise<MemoryWriteConfirmationResult> {
    const id = encodeURIComponent(proposalId);
    const value = await this.memoryWriteRequest(
      `/api/memory/write-proposals/${id}/confirm`,
      "POST",
      request,
    );
    return parseMemoryWriteConfirmation(value);
  }

  async generatePlan(instruction: string): Promise<AgentPlanningResponse> {
    return this.executionApi.generatePlan(instruction);
  }

  async createPlanReview(instruction: string): Promise<PlanReview> {
    return this.executionApi.createReview(instruction);
  }

  async getPlanReview(reviewId: string): Promise<PlanReview> {
    return this.executionApi.getReview(reviewId);
  }

  async approvePlanReview(reviewId: string): Promise<PlanReview> {
    return this.executionApi.approveReview(reviewId);
  }

  async rejectPlanReview(reviewId: string, reason: string): Promise<PlanReview> {
    return this.executionApi.rejectReview(reviewId, reason);
  }

  async cancelPlanReview(reviewId: string): Promise<PlanReview> {
    return this.executionApi.cancelReview(reviewId);
  }

  async createExecution(reviewId: string): Promise<ExecutionRecord> {
    return this.executionApi.createExecution(reviewId);
  }

  async getExecution(executionId: string): Promise<ExecutionRecord> {
    return this.executionApi.getExecution(executionId);
  }

  async executeStep(
    executionId: string,
    stepIndex: number,
    controls: StepExecutionControls,
  ): Promise<ExecutionRecord> {
    return this.executionApi.executeStep(executionId, stepIndex, controls);
  }

  async cancelExecution(executionId: string): Promise<ExecutionRecord> {
    return this.executionApi.cancelExecution(executionId);
  }

  async createMutationPreview(executionId: string, stepIndex: number): Promise<MutationPreview> {
    return this.executionApi.createMutationPreview(executionId, stepIndex);
  }

  async confirmMutation(
    executionId: string,
    stepIndex: number,
    preview: MutationPreview,
    phrase: string,
  ): Promise<ExecutionRecord> {
    return this.executionApi.confirmMutation(executionId, stepIndex, preview, phrase);
  }

  async cancelMutationPreview(executionId: string, stepIndex: number): Promise<MutationPreview> {
    return this.executionApi.cancelMutationPreview(executionId, stepIndex);
  }

  private async coreJsonRequest(
    path: string,
    method: "GET" | "POST",
    body: Readonly<Record<string, unknown>> | undefined,
    timeoutMs: number,
  ): Promise<unknown> {
    let timeout: ReturnType<typeof setTimeout> | undefined;
    try {
      const response = await Promise.race([
        requestUrl({
          url: `${this.coreUrl}${path}`,
          method,
          contentType: "application/json",
          body: body === undefined ? undefined : JSON.stringify(body),
          throw: false,
        }),
        new Promise<never>((_, reject) => {
          timeout = setTimeout(
            () => reject(new CaucoCoreApiError(undefined, "The Cauco Core request timed out.", "timeout")),
            timeoutMs,
          );
        }),
      ]);
      if (response.status >= 400) {
        const payload = response.json as unknown;
        const detail = isRecord(payload) && typeof payload.detail === "string" ? payload.detail : "";
        throw new CaucoCoreApiError(
          response.status,
          sanitizeCoreMessage(detail || "The Cauco Core request failed."),
          errorKind(response.status),
        );
      }
      return response.json as unknown;
    } catch (error) {
      if (error instanceof CaucoCoreApiError) throw error;
      throw new CaucoCoreApiError(undefined, "Could not reach the local Cauco Core.", "network");
    } finally {
      if (timeout !== undefined) clearTimeout(timeout);
    }
  }

  private async memoryWriteRequest(
    path: string,
    method: "GET" | "POST",
    body?: { instruction: string } | { confirm: true },
  ): Promise<unknown> {
    try {
      const response = await requestUrl({
        url: `${this.coreUrl}${path}`,
        method,
        contentType: "application/json",
        body: body ? JSON.stringify(body) : undefined,
        throw: false,
      });
      if (response.status >= 400) {
        const payload = response.json as unknown;
        const detail = isRecord(payload) && typeof payload.detail === "string" ? payload.detail : "";
        throw new CaucoCoreApiError(response.status, detail || "The memory request failed.");
      }
      return response.json as unknown;
    } catch (error) {
      if (error instanceof CaucoCoreApiError) throw error;
      throw new CaucoCoreApiError(undefined, "Could not reach the local Cauco Core.");
    }
  }

  private errorMessage(error: unknown): string {
    return error instanceof Error ? error.message : "Unknown local AI error.";
  }
}

function errorKind(
  status: number,
): "validation" | "conflict" | "forbidden" | "not-found" | "server" {
  if (status === 403) return "forbidden";
  if (status === 404) return "not-found";
  if (status === 409) return "conflict";
  if (status === 400 || status === 422) return "validation";
  return "server";
}

function sanitizeCoreMessage(value: string): string {
  return value
    .replace(/(?:\/Users|\/home|\/private|\/var\/folders)\/[\w.@%+~/-]+/g, "[local path redacted]")
    .replace(/[A-Za-z]:\\[^\s"']+/g, "[local path redacted]")
    .slice(0, 500);
}
