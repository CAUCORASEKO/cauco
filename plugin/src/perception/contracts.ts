import type {
  PerceptionCapability,
  PerceptionCollectionResult,
  PerceptionHealth,
  PerceptionModality,
  PerceptionSignal,
  PerceptionSource,
  PerceptionSourceError,
  PerceptionSourceMetadata,
  PerceptionSourceStatus,
} from "./types";

const CAPABILITIES: readonly PerceptionCapability[] = [
  "read",
  "search",
  "refresh",
  "watch",
];

const MODALITIES: readonly PerceptionModality[] = [
  "text",
  "voice",
  "file",
  "email",
  "calendar",
  "repository",
  "application",
  "system_event",
];

const SOURCE_STATUSES: readonly PerceptionSourceStatus[] = [
  "available",
  "degraded",
  "unavailable",
];

function parseRecord(
  value: unknown,
): Record<string, unknown> {
  if (
    typeof value !== "object" ||
    value === null ||
    Array.isArray(value)
  ) {
    throw new Error("Expected an object.");
  }

  return value as Record<string, unknown>;
}

function parseString(
  value: unknown,
  required = true,
): string {
  if (typeof value !== "string") {
    throw new Error("Expected a string.");
  }

  if (required && !value.trim()) {
    throw new Error("Expected a non-blank string.");
  }

  return value;
}

function parseTimestamp(value: unknown): string {
  const timestamp = parseString(value);

  if (Number.isNaN(Date.parse(timestamp))) {
    throw new Error("Expected a valid timestamp.");
  }

  return timestamp;
}

function freeze<T>(value: T): T {
  return Object.freeze(value);
}

function parseEnum<T extends string>(
  value: unknown,
  allowedValues: readonly T[],
): T {
  if (
    typeof value !== "string" ||
    !allowedValues.includes(value as T)
  ) {
    throw new Error("Invalid enum value.");
  }

  return value as T;
}

function parseStringArray(value: unknown): string[] {
  if (
    !Array.isArray(value) ||
    !value.every(
      (item) =>
        typeof item === "string" &&
        item.trim().length > 0,
    )
  ) {
    throw new Error("Expected a non-blank string array.");
  }

  return [...value];
}

function parseMetadata(
  value: unknown,
): Readonly<Record<string, unknown>> {
  const parsed = parseRecord(value);

  return freeze({ ...parsed });
}

function parseSource(value: unknown): PerceptionSource {
  const source = parseRecord(value);
  const metadata = parseRecord(source.metadata);
  const health = parseRecord(source.health);

  const parsedMetadata: PerceptionSourceMetadata = {
    sourceId: parseString(metadata.source_id),
    name: parseString(metadata.name),
    description: parseString(metadata.description, false),
    capabilities: freeze(
      parseStringArray(metadata.capabilities).map(
        (capability) =>
          parseEnum(capability, CAPABILITIES),
      ),
    ),
  };

  const parsedHealth: PerceptionHealth = {
    sourceId: parseString(health.source_id),
    status: parseEnum(
      health.status,
      SOURCE_STATUSES,
    ),
    checkedAt: parseTimestamp(health.checked_at),
    message:
      health.message === null
        ? null
        : parseString(health.message, false),
  };

  return freeze({
    metadata: freeze(parsedMetadata),
    health: freeze(parsedHealth),
  });
}

export function parsePerceptionSourceList(
  value: unknown,
): PerceptionSource[] {
  try {
    const response = parseRecord(value);

    if (
      !Array.isArray(response.sources) ||
      typeof response.count !== "number" ||
      !Number.isInteger(response.count) ||
      response.count < 0
    ) {
      throw new Error("Invalid source list.");
    }

    const sources = response.sources.map(parseSource);

    if (sources.length !== response.count) {
      throw new Error("Source count mismatch.");
    }

    return freeze(sources);
  } catch {
    throw new Error(
      "The core returned an invalid perception source list.",
    );
  }
}

function parseSignal(value: unknown): PerceptionSignal {
  const signal = parseRecord(value);
  const confidence = signal.confidence;

  if (
    typeof confidence !== "number" ||
    !Number.isFinite(confidence) ||
    confidence < 0 ||
    confidence > 1
  ) {
    throw new Error("Invalid signal confidence.");
  }

  return freeze({
    signalId: parseString(signal.signal_id),
    sourceId: parseString(signal.source_id),
    modality: parseEnum(
      signal.modality,
      MODALITIES,
    ),
    observedAt: parseTimestamp(signal.observed_at),
    content: parseString(signal.content, false),
    title:
      signal.title === undefined || signal.title === null
        ? null
        : parseString(signal.title, false),
    reference:
      signal.reference === undefined ||
      signal.reference === null
        ? null
        : parseString(signal.reference, false),
    confidence,
    metadata: parseMetadata(signal.metadata),
  });
}

function parseSourceError(
  value: unknown,
): PerceptionSourceError {
  const error = parseRecord(value);

  return freeze({
    sourceId: parseString(error.source_id),
    errorType: parseString(error.error_type),
    message: parseString(error.message),
  });
}

export function parsePerceptionCollectionResult(
  value: unknown,
): PerceptionCollectionResult {
  try {
    const response = parseRecord(value);

    const requestedSourceIds = parseStringArray(
      response.requested_source_ids,
    );

    const successfulSourceIds = parseStringArray(
      response.successful_source_ids,
    );

    if (!Array.isArray(response.signals)) {
      throw new Error("Invalid signals.");
    }

    if (!Array.isArray(response.errors)) {
      throw new Error("Invalid source errors.");
    }

    const signals = response.signals.map(parseSignal);
    const errors = response.errors.map(parseSourceError);

    const successfulSourcesWereRequested =
      successfulSourceIds.every((sourceId) =>
        requestedSourceIds.includes(sourceId),
      );

    const signalSourcesWereRequested = signals.every(
      (signal) =>
        requestedSourceIds.includes(signal.sourceId),
    );

    if (
      !successfulSourcesWereRequested ||
      !signalSourcesWereRequested
    ) {
      throw new Error(
        "Collection references an unrequested source.",
      );
    }

    return freeze({
      requestedSourceIds: freeze([
        ...requestedSourceIds,
      ]),
      successfulSourceIds: freeze([
        ...successfulSourceIds,
      ]),
      signals: freeze([...signals]),
      errors: freeze([...errors]),
      collectedAt: parseTimestamp(
        response.collected_at,
      ),
    });
  } catch {
    throw new Error(
      "The core returned an invalid perception collection result.",
    );
  }
}
