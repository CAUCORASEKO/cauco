export type SpeechTranscriptionStatus =
  | "idle"
  | "requesting-permission"
  | "listening"
  | "processing"
  | "completed"
  | "unavailable"
  | "permission-denied"
  | "error";

export interface SpeechTranscriptionState {
  readonly status: SpeechTranscriptionStatus;
  readonly message: string;
}

export interface SpeechTranscriptionObserver {
  listening(): void;
  processing(): void;
  transcribed(text: string): void;
  failed(code: string): void;
}

export interface SpeechTranscriber {
  readonly available: boolean;
  start(locale: string, observer: SpeechTranscriptionObserver): void;
  stop(): void;
  cancel(): void;
}

export interface SpeechTranscription {
  readonly state: SpeechTranscriptionState;
  start(locale: string): void;
  stop(): void;
  cancel(): void;
  subscribe(listener: (state: SpeechTranscriptionState) => void): () => void;
  subscribeToTranscript(listener: (text: string) => void): () => void;
}
