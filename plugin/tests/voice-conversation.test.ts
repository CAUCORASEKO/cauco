import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import {
  VoiceConversationSession,
  type VoiceTurnResult,
} from "../src/voice/conversationSession";
import { SpeechTranscriptionService } from "../src/voice/service";
import type {
  SpeechOutput,
  SpeechSynthesisRequest,
  SpeechSynthesisState,
  SpeechTranscriber,
  SpeechTranscription,
  SpeechTranscriptionObserver,
  SpeechTranscriptionState,
} from "../src/voice/types";

class FakeSpeech implements SpeechTranscription {
  startCalls: string[] = [];
  stopCalls = 0;
  cancelCalls = 0;
  private stateListeners = new Set<(state: SpeechTranscriptionState) => void>();
  private transcriptListeners = new Set<(text: string) => void>();

  constructor(
    public state: SpeechTranscriptionState = { status: "idle", message: "ready" },
  ) {}

  start(locale: string): void {
    this.startCalls.push(locale);
    this.emitState("requesting-permission");
  }

  stop(): void {
    this.stopCalls += 1;
    this.emitState("processing");
  }

  cancel(): void {
    this.cancelCalls += 1;
    this.emitState("idle");
  }

  subscribe(listener: (state: SpeechTranscriptionState) => void): () => void {
    this.stateListeners.add(listener);
    listener(this.state);
    return () => this.stateListeners.delete(listener);
  }

  subscribeToTranscript(listener: (text: string) => void): () => void {
    this.transcriptListeners.add(listener);
    return () => this.transcriptListeners.delete(listener);
  }

  emitState(status: SpeechTranscriptionState["status"], message = "runtime detail"): void {
    this.state = { status, message };
    for (const listener of this.stateListeners) listener(this.state);
  }

  emitTranscript(text: string): void {
    for (const listener of this.transcriptListeners) listener(text);
  }
}

class FakeOutput implements SpeechOutput {
  state: SpeechSynthesisState;
  speakCalls: SpeechSynthesisRequest[] = [];
  stopCalls = 0;
  pending: Array<() => void> = [];
  private listeners = new Set<(state: SpeechSynthesisState) => void>();

  constructor(available = true) {
    this.state = {
      status: available ? "idle" : "unavailable",
      message: available ? "ready" : "unavailable",
    };
  }

  speak(request: SpeechSynthesisRequest): Promise<void> {
    this.speakCalls.push(request);
    if (this.state.status === "unavailable") return Promise.resolve();
    this.emit("speaking");
    return new Promise((resolve) => this.pending.push(resolve));
  }

  stop(): void {
    this.stopCalls += 1;
    this.emit(this.state.status === "unavailable" ? "unavailable" : "idle");
  }

  subscribe(listener: (state: SpeechSynthesisState) => void): () => void {
    this.listeners.add(listener);
    listener(this.state);
    return () => this.listeners.delete(listener);
  }

  finish(index = 0): void {
    this.pending[index]?.();
    this.emit("idle");
  }

  fail(): void {
    this.emit("error", "secret-provider-runtime");
    this.pending.shift()?.();
  }

  private emit(status: SpeechSynthesisState["status"], message = status): void {
    this.state = { status, message };
    for (const listener of this.listeners) listener(this.state);
  }
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((yes, no) => {
    resolve = yes;
    reject = no;
  });
  return { promise, resolve, reject };
}

async function flush(): Promise<void> {
  await Promise.resolve();
  await Promise.resolve();
}

test("voice conversation is inert until explicit Start and ignores double Start", () => {
  const speech = new FakeSpeech();
  const output = new FakeOutput();
  const session = new VoiceConversationSession(
    speech,
    output,
    async () => ({ spokenText: "response" }),
    () => undefined,
  );

  assert.equal(speech.startCalls.length, 0);
  assert.equal(session.state.status, "waiting_for_user_start");

  session.start("fi-FI");
  session.start("es-ES");
  assert.deepEqual(speech.startCalls, ["fi-FI"]);
  assert.equal(session.state.status, "requesting_permission");
});

test("normal microphone transcript never auto-submits outside voice-conversation mode", () => {
  const speech = new FakeSpeech();
  let submissions = 0;
  new VoiceConversationSession(
    speech,
    new FakeOutput(),
    async () => {
      submissions += 1;
      return { spokenText: "response" };
    },
    () => undefined,
  );

  speech.emitTranscript("Normal microphone text");

  assert.equal(submissions, 0);
});

test("completed voice transcript enters shared history and submits exactly once", async () => {
  const speech = new FakeSpeech();
  const output = new FakeOutput();
  const history: string[] = [];
  const visible: string[] = [];
  const planning = deferred<VoiceTurnResult>();
  const session = new VoiceConversationSession(
    speech,
    output,
    async (instruction) => {
      history.push(instruction);
      return planning.promise;
    },
    (text) => visible.push(text),
  );

  session.start("es-ES");
  speech.emitState("listening");
  speech.emitTranscript("Planifica el siguiente paso");
  speech.emitTranscript("Duplicate completion");

  assert.deepEqual(visible, ["Planifica el siguiente paso"]);
  assert.deepEqual(history, ["Planifica el siguiente paso"]);
  assert.equal(output.speakCalls.length, 0);

  planning.resolve({ spokenText: "Plan advisory response" });
  await flush();
  assert.equal(output.speakCalls.length, 1);
  assert.equal(output.speakCalls[0]?.locale, "es-ES");
});

test("successful turn speaks after planning and waits for explicit Next turn", async () => {
  const speech = new FakeSpeech();
  const output = new FakeOutput();
  const session = new VoiceConversationSession(
    speech,
    output,
    async () => ({ spokenText: "Concise response" }),
    () => undefined,
  );

  session.start("en-GB");
  speech.emitTranscript("First turn");
  await flush();
  assert.equal(session.state.status, "speaking");
  assert.equal(speech.startCalls.length, 1);

  output.finish();
  await flush();
  assert.equal(session.state.status, "turn_complete");
  assert.equal(speech.startCalls.length, 1);

  session.next("en-GB");
  session.next("en-GB");
  assert.equal(speech.startCalls.length, 2);
  assert.equal(session.state.status, "requesting_permission");
});

test("Stop listening, speaking, and planning remain bounded", async () => {
  const speech = new FakeSpeech();
  const output = new FakeOutput();
  const planning = deferred<VoiceTurnResult>();
  const session = new VoiceConversationSession(
    speech,
    output,
    async () => planning.promise,
    () => undefined,
  );

  session.start("en-US");
  speech.emitState("listening");
  session.stopListening();
  assert.equal(speech.stopCalls, 1);
  assert.equal(session.state.status, "transcribing");

  speech.emitTranscript("Pending plan");
  session.stop();
  assert.equal(session.state.status, "stopped");
  planning.resolve({ spokenText: "Must not speak" });
  await flush();
  assert.equal(output.speakCalls.length, 0);

  session.start("en-US");
  speech.emitTranscript("Speaking turn");
  await flush();
  assert.equal(session.state.status, "speaking");
  const beforeStop = output.stopCalls;
  session.stopSpeaking();
  assert.equal(output.stopCalls, beforeStop + 1);
  assert.equal(session.state.status, "turn_complete");
});

test("stale STT completion after cancellation cannot submit a later turn", async () => {
  class RecordingTranscriber implements SpeechTranscriber {
    readonly available = true;
    observers: SpeechTranscriptionObserver[] = [];
    start(_locale: string, observer: SpeechTranscriptionObserver): void {
      this.observers.push(observer);
    }
    stop(): void {}
    cancel(): void {}
  }
  const transcriber = new RecordingTranscriber();
  const speech = new SpeechTranscriptionService(transcriber);
  let submissions = 0;
  const session = new VoiceConversationSession(
    speech,
    new FakeOutput(false),
    async () => {
      submissions += 1;
      return { spokenText: "response" };
    },
    () => undefined,
  );

  session.start("en-US");
  session.stop();
  session.start("fi-FI");
  transcriber.observers[0]?.transcribed("stale transcript");
  assert.equal(submissions, 0);
  transcriber.observers[1]?.transcribed("current transcript");
  await flush();
  assert.equal(submissions, 1);
});

test("stale TTS completion cannot advance a newer turn", async () => {
  const speech = new FakeSpeech();
  const output = new FakeOutput();
  const session = new VoiceConversationSession(
    speech,
    output,
    async (instruction) => ({ spokenText: instruction }),
    () => undefined,
  );

  session.start("en-US");
  speech.emitTranscript("first");
  await flush();
  session.stopSpeaking();
  session.next("en-US");
  speech.emitTranscript("second");
  await flush();
  assert.equal(session.state.status, "speaking");

  output.finish(0);
  await flush();
  assert.equal(session.state.status, "speaking");
});

test("unavailable STT and TTS failures preserve a safe bounded turn", async () => {
  const unavailableSpeech = new FakeSpeech({ status: "unavailable", message: "secret" });
  let submissions = 0;
  const unavailable = new VoiceConversationSession(
    unavailableSpeech,
    new FakeOutput(),
    async () => {
      submissions += 1;
      return { spokenText: "response" };
    },
    () => undefined,
  );
  unavailable.start("sv-SE");
  assert.equal(unavailable.state.status, "unavailable");
  assert.equal(unavailableSpeech.startCalls.length, 0);
  assert.equal(submissions, 0);

  const speech = new FakeSpeech();
  const output = new FakeOutput(false);
  const rendered: string[] = [];
  const session = new VoiceConversationSession(
    speech,
    output,
    async (instruction) => {
      rendered.push(instruction);
      return { spokenText: "response" };
    },
    () => undefined,
  );
  session.start("sv-SE");
  speech.emitTranscript("Visible advisory request");
  await flush();
  assert.deepEqual(rendered, ["Visible advisory request"]);
  assert.equal(session.state.status, "turn_complete");
});

test("permission and planning failures expose no exception secrets", async () => {
  const speech = new FakeSpeech();
  const session = new VoiceConversationSession(
    speech,
    new FakeOutput(),
    async () => {
      throw new Error("secret-provider-key /Users/private/core");
    },
    () => undefined,
  );
  session.start("en-US");
  speech.emitState("permission-denied", "secret microphone internals");
  assert.equal(session.state.status, "error");
  assert.equal(session.state.message.includes("secret"), false);

  session.start("en-US");
  speech.emitTranscript("Fail planning safely");
  await flush();
  assert.equal(session.state.status, "error");
  assert.equal(session.state.message.includes("secret-provider-key"), false);
  assert.equal(session.state.message.includes("/Users/private"), false);
});

test("dispose cancels all voice activity and source remains advisory-only", async () => {
  const speech = new FakeSpeech();
  const output = new FakeOutput();
  const session = new VoiceConversationSession(
    speech,
    output,
    async () => ({ spokenText: "response" }),
    () => undefined,
  );
  session.start("fi-FI");
  const speechStops = speech.cancelCalls;
  const outputStops = output.stopCalls;
  session.dispose();
  assert.equal(speech.cancelCalls, speechStops + 1);
  assert.equal(output.stopCalls, outputStops + 1);
  assert.equal(session.state.status, "stopped");

  const coordinator = await readFile("src/voice/conversationSession.ts", "utf8");
  const panel = await readFile("src/views/CaucoConversationPanel.ts", "utf8");
  assert.match(panel, /submitInstruction\(instruction, useReasoning\.checked\)/);
  for (const forbidden of [
    "/api/executions",
    "allow_execution",
    "createexecution",
    "approveplanreview",
    "confirmmutation",
    "runtime",
    "nativebroker",
    "deepagents",
    "localstorage",
  ]) {
    assert.equal(`${coordinator}\n${panel}`.toLowerCase().includes(forbidden), false);
  }
});
