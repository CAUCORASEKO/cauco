import type {
  WakeWordConfiguration,
  WakeWordDetector,
  WakeWordObserver,
} from "./wakeWord";

export interface NativeWakeWordApi {
  wakeword(path: "/api/native/wakeword/status" | "/api/native/wakeword/start" | "/api/native/wakeword/stop", body?: Readonly<Record<string, unknown>>): Promise<unknown>;
}

type NativeWakeWordResponse = { available: boolean; state: string; active: boolean; accepted?: boolean };
function parseResponse(value: unknown): NativeWakeWordResponse | undefined {
  if (!value || typeof value !== "object") return undefined;
  const item = value as Record<string, unknown>;
  if (typeof item.available !== "boolean" || typeof item.state !== "string" || typeof item.active !== "boolean") return undefined;
  return item as unknown as NativeWakeWordResponse;
}

export class NativeWakeWordDetector implements WakeWordDetector {
  // Native detection events are intentionally not synthesized here; the host event seam is still pending.
  readonly available = true;
  private generation = 0;
  constructor(private readonly api: NativeWakeWordApi) {}
  start(configuration: WakeWordConfiguration, observer: WakeWordObserver): void {
    const generation = ++this.generation;
    void this.api.wakeword("/api/native/wakeword/status")
      .then((statusValue) => { const status = parseResponse(statusValue); if (!status || !status.available) throw new Error("unavailable"); return this.api.wakeword("/api/native/wakeword/start", { phrase_key: "hola_cauco", locale: configuration.locale }); })
      .then((value) => { const result = parseResponse(value); if (generation !== this.generation) return; if (!result || !result.available || result.accepted !== true || !result.active) observer.failed(result?.state === "permission_denied" ? "permission-denied" : "unavailable"); else observer.started(); })
      .catch(() => { if (generation === this.generation) observer.failed("unavailable"); });
  }
  stop(): void { this.generation += 1; void this.api.wakeword("/api/native/wakeword/stop").catch(() => undefined); }
  dispose(): void { this.stop(); }
}

/**
 * Production wake detection belongs behind a narrow native-host event seam.
 * The current host has no microphone permission, model, or host-to-plugin event channel,
 * so this adapter intentionally performs no capture and exposes no generic audio access.
 */
export class UnavailableNativeWakeWordDetector implements WakeWordDetector {
  readonly available = false;

  start(_configuration: WakeWordConfiguration, observer: WakeWordObserver): void {
    observer.failed("unavailable");
  }

  stop(): void {}

  dispose(): void {}
}

export function createNativeWakeWordDetector(api?: NativeWakeWordApi): WakeWordDetector {
  return api ? new NativeWakeWordDetector(api) : new UnavailableNativeWakeWordDetector();
}
