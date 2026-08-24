import type { SpeechTranscriber, SpeechTranscriptionObserver } from "./types";

interface LocalSpeechRecognitionResult {
  readonly length: number;
  readonly isFinal: boolean;
  readonly [index: number]: { readonly transcript: string };
}

interface LocalSpeechRecognitionEvent {
  readonly results: {
    readonly length: number;
    readonly [index: number]: LocalSpeechRecognitionResult;
  };
}

interface LocalSpeechRecognition {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  maxAlternatives: number;
  processLocally: boolean;
  onstart: (() => void) | null;
  onspeechend: (() => void) | null;
  onresult: ((event: LocalSpeechRecognitionEvent) => void) | null;
  onerror: ((event: { readonly error: string }) => void) | null;
  onend: (() => void) | null;
  start(): void;
  stop(): void;
  abort(): void;
}

type LocalSpeechRecognitionConstructor = new () => LocalSpeechRecognition;

interface SpeechWindow {
  SpeechRecognition?: LocalSpeechRecognitionConstructor;
  webkitSpeechRecognition?: LocalSpeechRecognitionConstructor;
}

export class BrowserLocalSpeechTranscriber implements SpeechTranscriber {
  private recognition?: LocalSpeechRecognition;
  private observer?: SpeechTranscriptionObserver;
  private transcriptReceived = false;

  constructor(private readonly Recognition: LocalSpeechRecognitionConstructor) {}

  get available(): boolean {
    try {
      const probe = new this.Recognition();
      return "processLocally" in probe;
    } catch {
      return false;
    }
  }

  start(locale: string, observer: SpeechTranscriptionObserver): void {
    if (!this.available) {
      observer.failed("unavailable");
      return;
    }
    this.cancel();
    const recognition = new this.Recognition();
    recognition.processLocally = true;
    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;
    recognition.lang = locale;
    this.recognition = recognition;
    this.observer = observer;
    this.transcriptReceived = false;
    recognition.onstart = () => observer.listening();
    recognition.onspeechend = () => observer.processing();
    recognition.onresult = (event) => {
      const text = this.finalTranscript(event);
      if (!text) return;
      this.transcriptReceived = true;
      observer.transcribed(text);
      recognition.stop();
    };
    recognition.onerror = (event) => {
      this.clear();
      observer.failed(event.error);
    };
    recognition.onend = () => {
      const received = this.transcriptReceived;
      this.clear();
      if (!received) observer.failed("no-speech");
    };
    recognition.start();
  }

  stop(): void {
    this.recognition?.stop();
  }

  cancel(): void {
    const recognition = this.recognition;
    this.clear();
    recognition?.abort();
  }

  private finalTranscript(event: LocalSpeechRecognitionEvent): string {
    const parts: string[] = [];
    for (let index = 0; index < event.results.length; index += 1) {
      const result = event.results[index];
      const alternative = result?.[0];
      if (result?.isFinal && alternative?.transcript) parts.push(alternative.transcript);
    }
    return parts.join(" ").trim();
  }

  private clear(): void {
    if (this.recognition) {
      this.recognition.onstart = null;
      this.recognition.onspeechend = null;
      this.recognition.onresult = null;
      this.recognition.onerror = null;
      this.recognition.onend = null;
    }
    this.recognition = undefined;
    this.observer = undefined;
  }
}

export class UnavailableSpeechTranscriber implements SpeechTranscriber {
  readonly available = false;

  start(_locale: string, observer: SpeechTranscriptionObserver): void {
    observer.failed("unavailable");
  }

  stop(): void {}

  cancel(): void {}
}

export function createLocalSpeechTranscriber(
  runtime: SpeechWindow = globalThis as unknown as SpeechWindow,
): SpeechTranscriber {
  const Recognition = runtime.SpeechRecognition ?? runtime.webkitSpeechRecognition;
  if (!Recognition) return new UnavailableSpeechTranscriber();
  const transcriber = new BrowserLocalSpeechTranscriber(Recognition);
  return transcriber.available ? transcriber : new UnavailableSpeechTranscriber();
}
