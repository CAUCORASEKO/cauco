export type WakeWordStatus =
  | "disabled"
  | "starting"
  | "listening"
  | "detected"
  | "unavailable"
  | "permission_denied"
  | "error"
  | "stopped";

export interface WakeWordConfiguration {
  readonly phrase: string;
  readonly locale: string;
  readonly sensitivity?: number;
  readonly enabled: true;
}

export interface WakeWordState {
  readonly status: WakeWordStatus;
  readonly message: string;
  readonly microphoneActive: boolean;
  readonly configuration: WakeWordConfiguration | null;
}

export interface WakeWordObserver {
  started(): void;
  detected(): void;
  failed(code: string): void;
}

export interface WakeWordDetector {
  readonly available: boolean;
  start(configuration: WakeWordConfiguration, observer: WakeWordObserver): void;
  stop(): void;
  dispose(): void;
}

export interface WakeWordControl {
  readonly state: WakeWordState;
  enable(configuration: WakeWordConfiguration): void;
  disable(): void;
  dispose(): void;
  subscribe(listener: (state: WakeWordState) => void): () => void;
  onDetected(listener: (configuration: WakeWordConfiguration) => void): () => void;
}

const MESSAGES: Record<WakeWordStatus, string> = {
  disabled: "Wake word is off.",
  starting: "Starting local wake-word listening…",
  listening: "Wake-word microphone is active.",
  detected: "Wake phrase detected. Listening has stopped.",
  unavailable: "Local wake-word detection is unavailable.",
  permission_denied: "Microphone permission was not granted for wake-word listening.",
  error: "Wake-word listening could not continue safely.",
  stopped: "Wake-word listening stopped.",
};

export class WakeWordService implements WakeWordControl {
  private current: WakeWordState;
  private detectedListeners = new Set<(configuration: WakeWordConfiguration) => void>();
  private generation = 0;
  private stateListeners = new Set<(state: WakeWordState) => void>();

  constructor(private readonly detector: WakeWordDetector) {
    this.current = this.createState(detector.available ? "disabled" : "unavailable", null);
  }

  get state(): WakeWordState {
    return this.current;
  }

  enable(configuration: WakeWordConfiguration): void {
    if (["starting", "listening"].includes(this.current.status)) return;
    if (!this.detector.available) {
      this.update("unavailable", configuration);
      return;
    }
    const generation = ++this.generation;
    this.update("starting", configuration);
    try {
      this.detector.start(configuration, {
        started: () => {
          if (generation === this.generation) this.update("listening", configuration);
        },
        detected: () => {
          if (generation !== this.generation) return;
          this.generation += 1;
          this.stopDetector();
          this.update("detected", configuration);
          for (const listener of this.detectedListeners) listener(configuration);
        },
        failed: (code) => {
          if (generation !== this.generation) return;
          this.generation += 1;
          this.stopDetector();
          this.update(
            code === "not-allowed" || code === "permission-denied"
              ? "permission_denied"
              : code === "unavailable"
                ? "unavailable"
                : "error",
            configuration,
          );
        },
      });
    } catch {
      if (generation !== this.generation) return;
      this.generation += 1;
      this.stopDetector();
      this.update("error", configuration);
    }
  }

  disable(): void {
    this.generation += 1;
    this.stopDetector();
    this.update(this.detector.available ? "stopped" : "unavailable", this.current.configuration);
  }

  subscribe(listener: (state: WakeWordState) => void): () => void {
    this.stateListeners.add(listener);
    listener(this.current);
    return () => this.stateListeners.delete(listener);
  }

  onDetected(listener: (configuration: WakeWordConfiguration) => void): () => void {
    this.detectedListeners.add(listener);
    return () => this.detectedListeners.delete(listener);
  }

  dispose(): void {
    this.generation += 1;
    this.stopDetector();
    try {
      this.detector.dispose();
    } catch {
      // Disposal remains fail-closed and never surfaces detector internals.
    }
    this.update("stopped", this.current.configuration);
    this.detectedListeners.clear();
    this.stateListeners.clear();
  }

  private stopDetector(): void {
    try {
      this.detector.stop();
    } catch {
      // A failed stop is not retried in a loop or exposed to the user.
    }
  }

  private update(
    status: WakeWordStatus,
    configuration: WakeWordConfiguration | null,
  ): void {
    this.current = this.createState(status, configuration);
    for (const listener of this.stateListeners) listener(this.current);
  }

  private createState(
    status: WakeWordStatus,
    configuration: WakeWordConfiguration | null,
  ): WakeWordState {
    return Object.freeze({
      status,
      message: MESSAGES[status],
      microphoneActive: status === "starting" || status === "listening",
      configuration,
    });
  }
}
