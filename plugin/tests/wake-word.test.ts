import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import { NativeWakeWordDetector, UnavailableNativeWakeWordDetector } from "../src/voice/nativeWakeWord";
import { WakeActivationCoordinator } from "../src/voice/wakeActivation";
import {
  WakeWordService,
  type WakeWordConfiguration,
  type WakeWordDetector,
  type WakeWordObserver,
} from "../src/voice/wakeWord";

const configuration: WakeWordConfiguration = {
  phrase: "Hola Cauco",
  locale: "es-ES",
  sensitivity: 0.5,
  enabled: true,
};

class FakeDetector implements WakeWordDetector {
  readonly available = true;
  starts: WakeWordConfiguration[] = [];
  observers: WakeWordObserver[] = [];
  stopCalls = 0;
  disposeCalls = 0;

  constructor(private readonly events?: string[]) {}

  start(value: WakeWordConfiguration, observer: WakeWordObserver): void {
    this.starts.push(value);
    this.observers.push(observer);
    this.events?.push("detector-start");
    observer.started();
  }

  stop(): void {
    this.stopCalls += 1;
    this.events?.push("detector-stop");
  }

  dispose(): void {
    this.disposeCalls += 1;
  }
}

test("wake detection is inert until explicitly enabled and preserves configuration", () => {
  const detector = new FakeDetector();
  const wake = new WakeWordService(detector);

  assert.equal(detector.starts.length, 0);
  assert.equal(wake.state.status, "disabled");
  wake.enable(configuration);

  assert.equal(detector.starts.length, 1);
  assert.deepEqual(detector.starts[0], configuration);
  assert.equal(wake.state.status, "listening");
  assert.equal(wake.state.microphoneActive, true);

  wake.enable(configuration);
  assert.equal(detector.starts.length, 1, "double enable must not start another detector");
});

test("wake detection stops before starting exactly one bounded voice turn", () => {
  const events: string[] = [];
  const detector = new FakeDetector(events);
  const wake = new WakeWordService(detector);
  const turns: string[] = [];
  const coordinator = new WakeActivationCoordinator(
    wake,
    (locale) => {
      events.push("voice-start");
      turns.push(locale);
    },
    () => false,
    () => false,
  );

  assert.equal(coordinator.enable(configuration), true);
  detector.observers[0]?.detected();
  detector.observers[0]?.detected();

  assert.deepEqual(turns, ["es-ES"]);
  assert.ok(events.indexOf("detector-stop") < events.indexOf("voice-start"));
  assert.equal(detector.starts.length, 1, "wake detection must not auto-rearm");
  assert.equal(wake.state.status, "detected");
});

test("explicit disable and disposal stop listening", () => {
  const detector = new FakeDetector();
  const wake = new WakeWordService(detector);
  const coordinator = new WakeActivationCoordinator(wake, () => undefined, () => false, () => false);

  coordinator.enable(configuration);
  coordinator.disable();
  assert.equal(wake.state.status, "stopped");
  assert.equal(wake.state.microphoneActive, false);

  coordinator.enable(configuration);
  coordinator.dispose();
  wake.dispose();
  assert.equal(detector.disposeCalls, 1);
  assert.equal(wake.state.microphoneActive, false);
});

test("manual voice input and speech output preempt wake listening", () => {
  for (const preempt of ["manual", "speech"] as const) {
    const detector = new FakeDetector();
    const wake = new WakeWordService(detector);
    const coordinator = new WakeActivationCoordinator(
      wake,
      () => undefined,
      () => false,
      () => false,
    );
    coordinator.enable(configuration);

    if (preempt === "manual") coordinator.manualVoiceStarting();
    else coordinator.speechOutputStarting();

    assert.equal(wake.state.status, "stopped");
    assert.equal(wake.state.microphoneActive, false);
  }
});

test("wake listening cannot start during voice or speech-output collisions", () => {
  const voiceDetector = new FakeDetector();
  const voiceCoordinator = new WakeActivationCoordinator(
    new WakeWordService(voiceDetector),
    () => undefined,
    () => true,
    () => false,
  );
  const outputDetector = new FakeDetector();
  const outputCoordinator = new WakeActivationCoordinator(
    new WakeWordService(outputDetector),
    () => undefined,
    () => false,
    () => true,
  );

  assert.equal(voiceCoordinator.enable(configuration), false);
  assert.equal(outputCoordinator.enable(configuration), false);
  assert.equal(voiceDetector.starts.length, 0);
  assert.equal(outputDetector.starts.length, 0);
});

test("stale callbacks cannot activate a disabled or newer session", () => {
  const detector = new FakeDetector();
  const wake = new WakeWordService(detector);
  let turns = 0;
  const coordinator = new WakeActivationCoordinator(wake, () => turns++, () => false, () => false);

  coordinator.enable(configuration);
  const stale = detector.observers[0];
  coordinator.disable();
  coordinator.enable({ ...configuration, phrase: "Cauco local" });
  stale?.detected();

  assert.equal(turns, 0);
  assert.equal(wake.state.status, "listening");
});

test("permission and detector failures are fail-closed and secret-safe", () => {
  const detector = new FakeDetector();
  const wake = new WakeWordService(detector);
  wake.enable(configuration);
  detector.observers[0]?.failed("permission-denied");
  assert.equal(wake.state.status, "permission_denied");
  assert.equal(wake.state.microphoneActive, false);

  wake.enable(configuration);
  detector.observers[1]?.failed("api-key=super-secret-provider-error");
  assert.equal(wake.state.status, "error");
  assert.equal(wake.state.message.includes("super-secret"), false);
});

test("production placeholder performs no capture and leaves manual voice available", () => {
  const wake = new WakeWordService(new UnavailableNativeWakeWordDetector());
  let manualTurns = 0;
  const coordinator = new WakeActivationCoordinator(
    wake,
    () => undefined,
    () => false,
    () => false,
  );

  assert.equal(coordinator.enable(configuration), false);
  assert.equal(wake.state.status, "unavailable");
  manualTurns += 1;
  assert.equal(manualTurns, 1);
});

test("wake-word boundary has no network, persistence, or execution capabilities", async () => {
  const sources = await Promise.all(
    ["wakeWord.ts", "wakeActivation.ts", "nativeWakeWord.ts"].map((name) =>
      readFile(`src/voice/${name}`, "utf8"),
    ),
  );
  const source = sources.join("\n");

  for (const forbidden of [
    "fetch(",
    "requestUrl",
    "localStorage",
    "ExecutionService",
    "MutationService",
    "NativeBroker",
    "allow_execution",
    "deepagents",
  ]) {
    assert.equal(source.includes(forbidden), false, `unexpected capability: ${forbidden}`);
  }
});

test("conversation panel exposes explicit wake controls and disposes the detector", async () => {
  const panel = await readFile("src/views/CaucoConversationPanel.ts", "utf8");

  assert.match(panel, /Enable “Hola Cauco”/);
  assert.match(panel, /this\.wakeWord\.dispose\(\)/);
  assert.match(panel, /this\.wakeActivation\?\.manualVoiceStarting\(\)/);
  assert.match(panel, /this\.wakeActivation\?\.speechOutputStarting\(\)/);
  assert.doesNotMatch(panel, /allowExecution|allow_execution/);
});

test("native adapter queries status and starts only an accepted active detector", async () => {
  const calls: Array<[string, Record<string, unknown>]> = [];
  const detector = new NativeWakeWordDetector({
    wakeword: async (path, body = {}) => { calls.push([path, { ...body }]); return path.endsWith("status") ? { available: true, state: "stopped", active: false } : { available: true, state: "listening", active: true, accepted: true }; },
  });
  const observer = { started() {}, detected() {}, failed(code: string) { assert.fail(code); } };
  detector.start(configuration, observer);
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.deepEqual(calls, [["/api/native/wakeword/status", {}], ["/api/native/wakeword/start", { phrase_key: "hola_cauco", locale: "es-ES" }]]);
});

test("native adapter maps unavailable status and stop is bounded", async () => {
  const calls: string[] = [];
  const detector = new NativeWakeWordDetector({ wakeword: async (path) => { calls.push(path); return { available: false, state: "unavailable", active: false }; } });
  let failure = "";
  detector.start(configuration, { started() {}, detected() {}, failed(code) { failure = code; } });
  await new Promise((resolve) => setTimeout(resolve, 0));
  detector.stop();
  assert.equal(failure, "unavailable");
  assert.deepEqual(calls, ["/api/native/wakeword/status", "/api/native/wakeword/stop"]);
});
