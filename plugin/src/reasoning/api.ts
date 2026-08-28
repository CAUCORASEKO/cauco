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
    private readonly coreUrl: string,
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

  wakeword(path: "/api/native/wakeword/status" | "/api/native/wakeword/start" | "/api/native/wakeword/stop", body: Readonly<Record<string, unknown>> = {}): Promise<unknown> {
    return this.transport(path, body, 3_000);
  }

  subscribeWakewordEvents(onEvent: (event: unknown) => void): () => void {
    const source = new EventSource(`${this.coreUrl}/api/native/wakeword/events`);
    source.addEventListener("wakeword.detected", (event) => { try { onEvent(JSON.parse((event as MessageEvent).data)); } catch { /* fail closed */ } });
    source.onerror = () => source.close();
    return () => source.close();
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
