import type {
  SpeechOutput,
  SpeechSynthesisState,
  SpeechTranscription,
  SpeechTranscriptionState,
} from "./types";

export type VoiceConversationStatus =
  | "idle"
  | "waiting_for_user_start"
  | "requesting_permission"
  | "listening"
  | "transcribing"
  | "ready_to_submit"
  | "planning"
  | "speaking"
  | "turn_complete"
  | "stopped"
  | "unavailable"
  | "error";

export interface VoiceConversationState {
  readonly status: VoiceConversationStatus;
  readonly message: string;
  readonly transcript: string;
}

export interface VoiceTurnResult {
  readonly spokenText: string;
}

export type VoiceTurnSubmitter = (instruction: string) => Promise<VoiceTurnResult>;

const MESSAGES: Record<VoiceConversationStatus, string> = {
  idle: "Voice conversation is idle.",
  waiting_for_user_start: "Ready for an explicit voice turn.",
  requesting_permission: "Requesting microphone permission…",
  listening: "Listening for this turn…",
  transcribing: "Transcribing this turn…",
  ready_to_submit: "Transcript ready for advisory planning.",
  planning: "Preparing an advisory response…",
  speaking: "Speaking Cauco's advisory response…",
  turn_complete: "Voice turn complete. Start the next turn when ready.",
  stopped: "Voice conversation stopped.",
  unavailable: "Voice conversation is unavailable. Typed conversation still works.",
  error: "This voice turn could not be completed safely.",
};

export class VoiceConversationSession {
  private current: VoiceConversationState;
  private generation = 0;
  private listeners = new Set<(state: VoiceConversationState) => void>();
  private locale = "";
  private turnActive = false;
  private readonly unsubscribeSpeech: () => void;
  private readonly unsubscribeTranscript: () => void;
  private readonly unsubscribeOutput: () => void;

  constructor(
    private readonly speech: SpeechTranscription,
    private readonly output: SpeechOutput,
    private readonly submit: VoiceTurnSubmitter,
    private readonly showTranscript: (text: string) => void,
  ) {
    this.current = this.createState(
      speech.state.status === "unavailable" ? "unavailable" : "waiting_for_user_start",
      "",
    );
    this.unsubscribeSpeech = speech.subscribe((state) => this.speechChanged(state));
    this.unsubscribeTranscript = speech.subscribeToTranscript((text) =>
      this.transcriptCompleted(text),
    );
    this.unsubscribeOutput = output.subscribe((state) => this.outputChanged(state));
  }

  get state(): VoiceConversationState {
    return this.current;
  }

  start(locale: string): void {
    if (this.turnActive || this.current.status === "planning" || this.current.status === "speaking") {
      return;
    }
    if (this.speech.state.status === "unavailable") {
      this.update("unavailable", "");
      return;
    }
    this.beginTurn(locale);
  }

  next(locale: string): void {
    if (this.current.status !== "turn_complete") return;
    this.beginTurn(locale);
  }

  stopListening(): void {
    if (!this.turnActive) return;
    if (["requesting_permission", "listening"].includes(this.current.status)) {
      this.update("transcribing", this.current.transcript);
      this.speech.stop();
    }
  }

  stopSpeaking(): void {
    if (this.current.status !== "speaking") return;
    this.generation += 1;
    this.turnActive = false;
    this.output.stop();
    this.update("turn_complete", this.current.transcript);
  }

  stop(): void {
    this.generation += 1;
    this.turnActive = false;
    this.speech.cancel();
    this.output.stop();
    this.update("stopped", this.current.transcript);
  }

  subscribe(listener: (state: VoiceConversationState) => void): () => void {
    this.listeners.add(listener);
    listener(this.current);
    return () => this.listeners.delete(listener);
  }

  dispose(): void {
    this.stop();
    this.unsubscribeSpeech();
    this.unsubscribeTranscript();
    this.unsubscribeOutput();
    this.listeners.clear();
  }

  private beginTurn(locale: string): void {
    this.generation += 1;
    this.turnActive = true;
    this.locale = locale;
    this.output.stop();
    this.update("requesting_permission", "");
    this.speech.start(locale);
  }

  private speechChanged(state: SpeechTranscriptionState): void {
    if (!this.turnActive) return;
    if (state.status === "requesting-permission") {
      this.update("requesting_permission", this.current.transcript);
    } else if (state.status === "listening") {
      this.update("listening", this.current.transcript);
    } else if (state.status === "processing") {
      this.update("transcribing", this.current.transcript);
    } else if (state.status === "unavailable") {
      this.turnActive = false;
      this.update("unavailable", this.current.transcript);
    } else if (state.status === "permission-denied" || state.status === "error") {
      this.generation += 1;
      this.turnActive = false;
      this.speech.cancel();
      this.update("error", this.current.transcript);
    }
  }

  private transcriptCompleted(text: string): void {
    if (
      !this.turnActive ||
      !["requesting_permission", "listening", "transcribing"].includes(this.current.status)
    ) {
      return;
    }
    const transcript = text.trim().slice(0, 4000);
    if (!transcript) return;
    const generation = this.generation;
    this.showTranscript(transcript);
    this.update("ready_to_submit", transcript);
    void this.planTurn(generation, transcript);
  }

  private async planTurn(generation: number, transcript: string): Promise<void> {
    this.update("planning", transcript);
    try {
      const result = await this.submit(transcript);
      if (!this.isCurrent(generation)) return;
      await this.output.speak({ text: result.spokenText, locale: this.locale });
      if (!this.isCurrent(generation)) return;
      this.turnActive = false;
      this.update("turn_complete", transcript);
    } catch {
      if (!this.isCurrent(generation)) return;
      this.turnActive = false;
      this.output.stop();
      this.update("error", transcript);
    }
  }

  private outputChanged(state: SpeechSynthesisState): void {
    if (!this.turnActive) return;
    if (state.status === "speaking") this.update("speaking", this.current.transcript);
  }

  private isCurrent(generation: number): boolean {
    return this.turnActive && generation === this.generation;
  }

  private update(status: VoiceConversationStatus, transcript: string): void {
    this.current = this.createState(status, transcript);
    for (const listener of this.listeners) listener(this.current);
  }

  private createState(status: VoiceConversationStatus, transcript: string): VoiceConversationState {
    return Object.freeze({ status, message: MESSAGES[status], transcript });
  }
}
