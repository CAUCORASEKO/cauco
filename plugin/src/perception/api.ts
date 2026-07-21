import { requestUrl } from "obsidian";

import {
  parsePerceptionCollectionResult,
  parsePerceptionSourceList,
} from "./contracts";
import type {
  PerceptionCollectRequest,
  PerceptionCollectionResult,
  PerceptionSource,
} from "./types";

type PerceptionHttpMethod = "GET" | "POST";

export interface PerceptionTransportResponse {
  status: number;
  json?: unknown;
  text?: string;
}

export type PerceptionTransport = (
  path: string,
  method: PerceptionHttpMethod,
  body?: Readonly<Record<string, unknown>>,
) => Promise<PerceptionTransportResponse>;

export class PerceptionApiClient {
  private readonly baseUrl: string;
  private readonly transport: PerceptionTransport;

  constructor(
    coreUrl: string,
    transport?: PerceptionTransport,
  ) {
    this.baseUrl = coreUrl.replace(/\/+$/, "");

    this.transport =
      transport ??
      (async (
        path,
        method,
        body,
      ): Promise<PerceptionTransportResponse> => {
        const response = await requestUrl({
          url: `${this.baseUrl}${path}`,
          method,
          body:
            body === undefined
              ? undefined
              : JSON.stringify(body),
          headers: {
            "Content-Type": "application/json",
          },
          throw: false,
        });

        return {
          status: response.status,
          json: response.json,
          text: response.text,
        };
      });
  }

  async getSources(): Promise<PerceptionSource[]> {
    const response = await this.safeTransport(
      "/api/perception/sources",
      "GET",
    );

    this.checkResponse(response);

    return parsePerceptionSourceList(response.json);
  }

  async collect(
    request: PerceptionCollectRequest = {},
  ): Promise<PerceptionCollectionResult> {
    if (
      request.query !== undefined &&
      !request.query.trim()
    ) {
      throw new Error(
        "Enter a search query before searching.",
      );
    }

    const body: Record<string, unknown> = {};

    if (request.sourceIds !== undefined) {
      body.source_ids = request.sourceIds;
    }

    if (request.query !== undefined) {
      body.query = request.query.trim();
    }

    if (request.since !== undefined) {
      body.since = request.since;
    }

    if (request.limit !== undefined) {
      body.limit = request.limit;
    }

    if (request.metadata !== undefined) {
      body.metadata = request.metadata;
    }

    if (request.requiredCapability !== undefined) {
      body.required_capability =
        request.requiredCapability;
    }

    const response = await this.safeTransport(
      "/api/perception/collect",
      "POST",
      body,
    );

    this.checkResponse(response);

    return parsePerceptionCollectionResult(response.json);
  }

  private async safeTransport(
    path: string,
    method: PerceptionHttpMethod,
    body?: Readonly<Record<string, unknown>>,
  ): Promise<PerceptionTransportResponse> {
    try {
      return await this.transport(path, method, body);
    } catch {
      throw new Error(
        "Unable to reach the local core for perception.",
      );
    }
  }

  private checkResponse(
    response: PerceptionTransportResponse,
  ): void {
    if (
      response.status >= 200 &&
      response.status < 300
    ) {
      return;
    }

    const detail = this.extractDetail(response.json);

    throw new Error(
      detail
        ? `Perception request failed: ${detail}`
        : "The local core perception request failed.",
    );
  }

  private extractDetail(value: unknown): string | null {
    if (
      typeof value !== "object" ||
      value === null ||
      Array.isArray(value)
    ) {
      return null;
    }

    const detail = (
      value as Record<string, unknown>
    ).detail;

    return typeof detail === "string" &&
      detail.trim().length > 0
      ? detail
      : null;
  }
}
