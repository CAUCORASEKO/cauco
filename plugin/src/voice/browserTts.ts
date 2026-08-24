import type { SpeechSynthesizer, SpeechSynthesisRequest } from "./types";

interface LocalVoice {
  readonly default: boolean;
  readonly lang: string;
  readonly localService: boolean;
  readonly name: string;
  readonly voiceURI: string;
}

interface LocalUtterance {
  lang: string;
  voice: LocalVoice | null;
  onend: (() => void) | null;
  onerror: (() => void) | null;
}

interface LocalUtteranceConstructor {
  new (text: string): LocalUtterance;
}

interface LocalSpeechSynthesis {
  cancel(): void;
  getVoices(): LocalVoice[];
  speak(utterance: LocalUtterance): void;
}

interface SpeechSynthesisRuntime {
  speechSynthesis?: LocalSpeechSynthesis;
  SpeechSynthesisUtterance?: LocalUtteranceConstructor;
}

export class BrowserLocalSpeechSynthesizer implements SpeechSynthesizer {
  private finishCurrent?: () => void;

  constructor(
    private readonly synthesis: LocalSpeechSynthesis,
    private readonly Utterance: LocalUtteranceConstructor,
  ) {}

  get available(): boolean {
    return this.localVoices().length > 0;
  }

  speak(request: SpeechSynthesisRequest): Promise<void> {
    this.stop();
    const voice = this.selectVoice(request.locale);
    if (!voice) return Promise.reject(new Error("local-voice-unavailable"));
    return new Promise((resolve, reject) => {
      const utterance = new this.Utterance(request.text);
      utterance.lang = request.locale;
      utterance.voice = voice;
      const finish = (failed: boolean): void => {
        if (this.finishCurrent !== cancel) return;
        this.finishCurrent = undefined;
        utterance.onend = null;
        utterance.onerror = null;
        if (failed) reject(new Error("local-synthesis-failed"));
        else resolve();
      };
      const cancel = (): void => finish(false);
      this.finishCurrent = cancel;
      utterance.onend = () => finish(false);
      utterance.onerror = () => finish(true);
      this.synthesis.speak(utterance);
    });
  }

  stop(): void {
    this.synthesis.cancel();
    this.finishCurrent?.();
  }

  private selectVoice(locale: string): LocalVoice | undefined {
    const normalized = locale.toLowerCase();
    const language = normalized.split("-")[0];
    const voices = this.localVoices();
    return (
      voices.find((voice) => voice.lang.toLowerCase() === normalized) ??
      voices.find((voice) => voice.lang.toLowerCase().split("-")[0] === language) ??
      voices.find((voice) => voice.default) ??
      voices[0]
    );
  }

  private localVoices(): LocalVoice[] {
    return this.synthesis
      .getVoices()
      .filter((voice) => voice.localService)
      .sort((left, right) =>
        `${left.lang}\u0000${left.name}\u0000${left.voiceURI}`.localeCompare(
          `${right.lang}\u0000${right.name}\u0000${right.voiceURI}`,
        ),
      );
  }
}

export class UnavailableSpeechSynthesizer implements SpeechSynthesizer {
  readonly available = false;

  speak(_request: SpeechSynthesisRequest): Promise<void> {
    return Promise.reject(new Error("local-synthesis-unavailable"));
  }

  stop(): void {}
}

export function createLocalSpeechSynthesizer(
  runtime: SpeechSynthesisRuntime = globalThis as unknown as SpeechSynthesisRuntime,
): SpeechSynthesizer {
  if (!runtime.speechSynthesis || !runtime.SpeechSynthesisUtterance) {
    return new UnavailableSpeechSynthesizer();
  }
  return new BrowserLocalSpeechSynthesizer(
    runtime.speechSynthesis,
    runtime.SpeechSynthesisUtterance,
  );
}
