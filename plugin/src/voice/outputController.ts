import type {
  SpeechOutput,
  SpeechSynthesisRequest,
  SpeechSynthesisState,
} from "./types";

export class SpeechOutputController {
  constructor(
    private readonly output: SpeechOutput,
    private readonly microphoneActive: () => boolean,
  ) {}

  get state(): SpeechSynthesisState {
    return this.output.state;
  }

  speak(request: SpeechSynthesisRequest): boolean {
    if (this.microphoneActive()) return false;
    void this.output.speak(request);
    return true;
  }

  stop(): void {
    this.output.stop();
  }

  subscribe(listener: (state: SpeechSynthesisState) => void): () => void {
    return this.output.subscribe(listener);
  }

  dispose(): void {
    this.stop();
  }
}
