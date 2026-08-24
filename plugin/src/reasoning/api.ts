import { requestUrl } from "obsidian";
import { parseReasoningPlanningResponse } from "./contracts";
import type { ReasoningPlanRequest, ReasoningPlanningResponse } from "./types";

export type ReasoningTransport = (
  path: string,
  body: Readonly<Record<string, unknown>>,
  timeoutMs: number,
) => Promise<unknown>;

export class ReasoningPlanningApiClient {
  constructor(
    coreUrl: string,
    private readonly transport: ReasoningTransport = createTransport(coreUrl),
    private readonly timeoutMs = 30_000,
  ) {}

  async plan(request: ReasoningPlanRequest): Promise<ReasoningPlanningResponse> {
    const body: Record<string, unknown> = {
      instruction: request.instruction,
      use_reasoning: request.useReasoning ?? false,
    };
    if (request.intent) body.intent = request.intent;
    if (request.preferredAgentId) body.preferred_agent_id = request.preferredAgentId;
    try {
      return parseReasoningPlanningResponse(
        await this.transport("/api/reasoning/plan", body, this.timeoutMs),
      );
    } catch (error) {
      if (error instanceof ReasoningPlanningApiError) throw error;
      throw new ReasoningPlanningApiError(
        "Advisory planning is unavailable. No action was taken.",
      );
    }
  }
}

function createTransport(coreUrl: string): ReasoningTransport {
  const baseUrl = coreUrl.replace(/\/+$/, "");
  return async (path, body, timeoutMs) => {
    let timeout: ReturnType<typeof setTimeout> | undefined;
    try {
      const response = await Promise.race([
        requestUrl({
          url: `${baseUrl}${path}`,
          method: "POST",
          contentType: "application/json",
          body: JSON.stringify(body),
          throw: false,
        }),
        new Promise<never>((_, reject) => {
          timeout = setTimeout(() => reject(new Error("timeout")), timeoutMs);
        }),
      ]);
      if (response.status >= 400) {
        throw new ReasoningPlanningApiError(
          response.status >= 500
            ? "Cauco Core could not complete advisory planning. No action was taken."
            : "Cauco Core did not accept this advisory planning request. No action was taken.",
        );
      }
      return response.json as unknown;
    } catch (error) {
      if (error instanceof ReasoningPlanningApiError) throw error;
      throw new ReasoningPlanningApiError(
        "Could not reach Cauco Core for advisory planning. No action was taken.",
      );
    } finally {
      if (timeout !== undefined) clearTimeout(timeout);
    }
  };
}

export class ReasoningPlanningApiError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "ReasoningPlanningApiError";
  }
}
