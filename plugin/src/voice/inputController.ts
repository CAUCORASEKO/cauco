import type {
  SpeechTranscription,
  SpeechTranscriptionState,
} from "./types";

export class VoiceInputController {
  private readonly unsubscribeState: () => void;
  private readonly unsubscribeTranscript: () => void;

  constructor(
    private readonly speech: SpeechTranscription,
    private readonly readInput: () => string,
    private readonly writeInput: (value: string) => void,
    stateChanged: (state: SpeechTranscriptionState) => void,
  ) {
    this.unsubscribeState = speech.subscribe(stateChanged);
    this.unsubscribeTranscript = speech.subscribeToTranscript((transcript) => {
      const existing = this.readInput().trim();
      this.writeInput(existing ? `${existing} ${transcript}` : transcript);
    });
  }

  get state(): SpeechTranscriptionState {
    return this.speech.state;
  }

  start(locale: string): void {
    this.speech.start(locale);
  }

  stop(): void {
    this.speech.stop();
  }

  cancel(): void {
    this.speech.cancel();
  }

  dispose(): void {
    this.cancel();
    this.unsubscribeState();
    this.unsubscribeTranscript();
  }
}
