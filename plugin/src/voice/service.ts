import type {
  SpeechTranscriber,
  SpeechTranscription,
  SpeechTranscriptionState,
} from "./types";

const MESSAGES: Record<SpeechTranscriptionState["status"], string> = {
  idle: "Microphone ready.",
  "requesting-permission": "Requesting microphone permission…",
  listening: "Listening…",
  processing: "Transcribing…",
  completed: "Transcription added. Review or edit it before planning.",
  unavailable: "Local speech transcription is unavailable. You can continue typing.",
  "permission-denied":
    "Microphone permission was not granted. You can continue typing or update app permissions.",
  error: "Speech transcription could not be completed. Your existing text was preserved.",
};

export class SpeechTranscriptionService implements SpeechTranscription {
  private stateListeners = new Set<(state: SpeechTranscriptionState) => void>();
  private transcriptListeners = new Set<(text: string) => void>();
  private current: SpeechTranscriptionState;
  private generation = 0;

  constructor(private readonly transcriber: SpeechTranscriber) {
    this.current = this.createState(transcriber.available ? "idle" : "unavailable");
  }

  get state(): SpeechTranscriptionState {
    return this.current;
  }

  start(locale: string): void {
    if (!this.transcriber.available) {
      this.update("unavailable");
      return;
    }
    const generation = ++this.generation;
    this.update("requesting-permission");
    try {
      this.transcriber.start(locale, {
        listening: () => this.updateIfCurrent(generation, "listening"),
        processing: () => this.updateIfCurrent(generation, "processing"),
        transcribed: (text) => {
          if (generation !== this.generation) return;
          const bounded = text.trim().slice(0, 4000);
          if (!bounded) {
            this.update("error");
            return;
          }
          for (const listener of this.transcriptListeners) listener(bounded);
          this.update("completed");
        },
        failed: (code) => {
          if (generation !== this.generation) return;
          this.update(
            code === "not-allowed" || code === "service-not-allowed"
              ? "permission-denied"
              : code === "unavailable" || code === "language-not-supported"
                ? "unavailable"
                : "error",
          );
        },
      });
    } catch {
      this.update("error");
    }
  }

  stop(): void {
    if (!this.isActive()) return;
    this.update("processing");
    try {
      this.transcriber.stop();
    } catch {
      this.update("error");
    }
  }

  cancel(): void {
    if (!this.isActive()) return;
    this.generation += 1;
    try {
      this.transcriber.cancel();
    } catch {
      // Cancellation remains fail-closed and returns the UI to an editable state.
    }
    this.update("idle");
  }

  subscribe(listener: (state: SpeechTranscriptionState) => void): () => void {
    this.stateListeners.add(listener);
    listener(this.current);
    return () => this.stateListeners.delete(listener);
  }

  subscribeToTranscript(listener: (text: string) => void): () => void {
    this.transcriptListeners.add(listener);
    return () => this.transcriptListeners.delete(listener);
  }

  private isActive(): boolean {
    return ["requesting-permission", "listening", "processing"].includes(
      this.current.status,
    );
  }

  private update(status: SpeechTranscriptionState["status"]): void {
    this.current = this.createState(status);
    for (const listener of this.stateListeners) listener(this.current);
  }

  private updateIfCurrent(
    generation: number,
    status: SpeechTranscriptionState["status"],
  ): void {
    if (generation === this.generation) this.update(status);
  }

  private createState(status: SpeechTranscriptionState["status"]): SpeechTranscriptionState {
    return Object.freeze({ status, message: MESSAGES[status] });
  }
}
