import type {
  WakeWordConfiguration,
  WakeWordControl,
  WakeWordState,
} from "./wakeWord";

export class WakeActivationCoordinator {
  private readonly unsubscribeDetected: () => void;
  private activationGeneration = 0;
  private handsFreeEnabled = false;
  private rearmTimer?: ReturnType<typeof setTimeout>;

  constructor(
    private readonly wakeWord: WakeWordControl,
    private readonly startVoiceTurn: (locale: string) => void,
    private readonly voiceBusy: () => boolean,
    private readonly speechOutputBusy: () => boolean,
  ) {
    this.unsubscribeDetected = wakeWord.onDetected((configuration) =>
      this.activate(configuration),
    );
  }

  get state(): WakeWordState {
    return this.wakeWord.state;
  }

  enable(configuration: WakeWordConfiguration): boolean {
    if (this.voiceBusy() || this.speechOutputBusy()) return false;
    this.activationGeneration += 1;
    this.handsFreeEnabled = true;
    this.clearRearm();
    this.wakeWord.enable(configuration);
    return this.wakeWord.state.status !== "unavailable";
  }

  disable(): void {
    this.activationGeneration += 1;
    this.handsFreeEnabled = false;
    this.clearRearm();
    this.wakeWord.disable();
  }

  manualVoiceStarting(): void {
    this.disable();
  }

  speechOutputStarting(): void {
    this.disable();
  }

  subscribe(listener: (state: WakeWordState) => void): () => void {
    return this.wakeWord.subscribe(listener);
  }

  dispose(): void {
    this.activationGeneration += 1;
    this.unsubscribeDetected();
    this.handsFreeEnabled = false;
    this.clearRearm();
    this.wakeWord.disable();
  }

  /** Re-arms only after the voice session has completed TTS. */
  voiceTurnCompleted(configuration: WakeWordConfiguration): void {
    if (!this.handsFreeEnabled || this.voiceBusy() || this.speechOutputBusy()) return;
    const generation = ++this.activationGeneration;
    this.clearRearm();
    this.rearmTimer = setTimeout(() => {
      this.rearmTimer = undefined;
      if (generation !== this.activationGeneration || !this.handsFreeEnabled) return;
      if (this.voiceBusy() || this.speechOutputBusy()) return;
      this.wakeWord.enable(configuration);
    }, 0);
  }

  private activate(configuration: WakeWordConfiguration): void {
    const generation = ++this.activationGeneration;
    if (this.voiceBusy() || this.speechOutputBusy()) {
      this.wakeWord.disable();
      return;
    }
    if (this.wakeWord.state.status !== "detected") return;
    // WakeWordService has synchronously stopped capture before notifying this coordinator.
    if (generation === this.activationGeneration) this.startVoiceTurn(configuration.locale);
  }

  private clearRearm(): void {
    if (this.rearmTimer !== undefined) clearTimeout(this.rearmTimer);
    this.rearmTimer = undefined;
  }
}
