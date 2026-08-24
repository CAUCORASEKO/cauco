import assert from "node:assert/strict";
import test from "node:test";
import { ReasoningPlanningApiClient } from "../src/reasoning/api";
import { BrowserLocalSpeechTranscriber } from "../src/voice/browserSpeech";
import { VoiceInputController } from "../src/voice/inputController";
import { SpeechTranscriptionService } from "../src/voice/service";
import type { SpeechTranscriber, SpeechTranscriptionObserver } from "../src/voice/types";

class FakeTranscriber implements SpeechTranscriber {
  startCalls = 0;
  stopCalls = 0;
  cancelCalls = 0;
  locale?: string;
  observer?: SpeechTranscriptionObserver;

  constructor(readonly available = true) {}

  start(locale: string, observer: SpeechTranscriptionObserver): void {
    this.startCalls += 1;
    this.locale = locale;
    this.observer = observer;
  }

  stop(): void {
    this.stopCalls += 1;
  }

  cancel(): void {
    this.cancelCalls += 1;
  }
}

function controller(transcriber: FakeTranscriber, initial = "") {
  const service = new SpeechTranscriptionService(transcriber);
  let input = initial;
  const states: string[] = [];
  const value = new VoiceInputController(
    service,
    () => input,
    (next) => {
      input = next;
    },
    (state) => states.push(state.status),
  );
  return { service, value, states, getInput: () => input, setInput: (next: string) => (input = next) };
}

test("microphone remains inactive until an explicit start action", () => {
  const transcriber = new FakeTranscriber();
  const voice = controller(transcriber);

  assert.equal(transcriber.startCalls, 0);
  assert.deepEqual(voice.states, ["idle"]);

  voice.value.start("fi-FI");
  assert.equal(transcriber.startCalls, 1);
  assert.equal(transcriber.locale, "fi-FI");
  assert.equal(voice.value.state.status, "requesting-permission");
});

test("stop and cancel are explicit and never submit conversation requests", () => {
  const transcriber = new FakeTranscriber();
  const voice = controller(transcriber);
  let advisorySubmissions = 0;

  voice.value.start("es-ES");
  transcriber.observer?.listening();
  voice.value.stop();
  assert.equal(transcriber.stopCalls, 1);
  assert.equal(voice.value.state.status, "processing");

  voice.value.cancel();
  assert.equal(transcriber.cancelCalls, 1);
  assert.equal(voice.value.state.status, "idle");
  assert.equal(advisorySubmissions, 0);
});

test("successful transcription populates and preserves editable input without auto-submit", () => {
  const transcriber = new FakeTranscriber();
  const voice = controller(transcriber, "Existing request.");
  let advisorySubmissions = 0;

  voice.value.start("en-GB");
  transcriber.observer?.transcribed("Add the next step");

  assert.equal(voice.getInput(), "Existing request. Add the next step");
  assert.equal(voice.value.state.status, "completed");
  assert.equal(advisorySubmissions, 0);

  voice.setInput("Edited transcription before planning");
  assert.equal(voice.getInput(), "Edited transcription before planning");
});

test("edited transcription can use the unchanged advisory request path", async () => {
  const requests: Readonly<Record<string, unknown>>[] = [];
  const client = new ReasoningPlanningApiClient("http://localhost", async (_path, body) => {
    requests.push(body);
    throw new Error("response shape is irrelevant after request capture");
  });

  await assert.rejects(
    client.plan({ instruction: "Edited transcription", useReasoning: false }),
  );

  assert.equal(requests[0]?.instruction, "Edited transcription");
  assert.equal(requests[0]?.use_reasoning, false);
  assert.equal("allow_execution" in (requests[0] ?? {}), false);
});

test("unavailable speech leaves typed advisory conversation functional", async () => {
  const transcriber = new FakeTranscriber(false);
  const voice = controller(transcriber, "Typed request remains");
  let requestedInstruction = "";
  const client = new ReasoningPlanningApiClient("http://localhost", async (_path, body) => {
    requestedInstruction = String(body.instruction);
    throw new Error("stop after capture");
  });

  voice.value.start("sv-SE");
  await assert.rejects(client.plan({ instruction: voice.getInput() }));

  assert.equal(transcriber.startCalls, 0);
  assert.equal(voice.value.state.status, "unavailable");
  assert.equal(requestedInstruction, "Typed request remains");
});

test("permission denial and runtime failures expose only bounded safe messages", () => {
  const denied = new FakeTranscriber();
  const deniedVoice = controller(denied, "Preserve me");
  deniedVoice.value.start("en-US");
  denied.observer?.failed("not-allowed");
  assert.equal(deniedVoice.value.state.status, "permission-denied");
  assert.match(deniedVoice.value.state.message, /permission was not granted/i);
  assert.equal(deniedVoice.getInput(), "Preserve me");

  const failing: SpeechTranscriber = {
    available: true,
    start: () => {
      throw new Error("secret-api-key-/Users/private/audio");
    },
    stop: () => undefined,
    cancel: () => undefined,
  };
  const service = new SpeechTranscriptionService(failing);
  service.start("en-US");
  assert.equal(service.state.status, "error");
  assert.equal(service.state.message.includes("secret-api-key"), false);
  assert.equal(service.state.message.includes("/Users/private"), false);
});

test("browser adapter requires local processing and forwards locale", () => {
  class FakeRecognition {
    static instances: FakeRecognition[] = [];
    continuous = true;
    interimResults = true;
    lang = "";
    maxAlternatives = 0;
    processLocally = false;
    onstart: (() => void) | null = null;
    onspeechend: (() => void) | null = null;
    onresult = null;
    onerror = null;
    onend = null;
    starts = 0;
    stops = 0;
    aborts = 0;

    constructor() {
      FakeRecognition.instances.push(this);
    }

    start(): void {
      this.starts += 1;
    }

    stop(): void {
      this.stops += 1;
    }

    abort(): void {
      this.aborts += 1;
    }
  }

  const adapter = new BrowserLocalSpeechTranscriber(FakeRecognition);
  const observer: SpeechTranscriptionObserver = {
    listening: () => undefined,
    processing: () => undefined,
    transcribed: () => undefined,
    failed: () => undefined,
  };
  adapter.start("es-MX", observer);
  const active = FakeRecognition.instances.at(-1);

  assert.equal(active?.processLocally, true);
  assert.equal(active?.continuous, false);
  assert.equal(active?.lang, "es-MX");
  assert.equal(active?.starts, 1);
});

test("voice panel source has no execution, persistence, TTS, or automatic activation path", async () => {
  const { readFile } = await import("node:fs/promises");
  const source = await readFile("src/views/CaucoConversationPanel.ts", "utf8");
  const voice = await readFile("src/voice/browserSpeech.ts", "utf8");

  assert.match(source, /microphone\.addEventListener\("click"/);
  assert.doesNotMatch(source, /\.start\([^)]*\)[^}]*render\(/);
  for (const forbidden of [
    "/api/executions",
    "allow_execution",
    "createExecution",
    "approvePlanReview",
    "speechSynthesis",
    "MediaRecorder",
    "writeFile",
    "localStorage",
  ]) {
    assert.equal(`${source}\n${voice}`.includes(forbidden), false);
  }
});
