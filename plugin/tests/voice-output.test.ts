import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import type { ReasoningPlanningResponse } from "../src/reasoning/types";
import { BrowserLocalSpeechSynthesizer } from "../src/voice/browserTts";
import { SpeechOutputController } from "../src/voice/outputController";
import { SpeechOutputService, spokenPlanningResponse } from "../src/voice/speechOutput";
import type { SpeechSynthesizer, SpeechSynthesisRequest } from "../src/voice/types";

class FakeSynthesizer implements SpeechSynthesizer {
  speakCalls: SpeechSynthesisRequest[] = [];
  stopCalls = 0;
  rejectWith?: Error;

  constructor(readonly available = true) {}

  speak(request: SpeechSynthesisRequest): Promise<void> {
    this.speakCalls.push(request);
    return this.rejectWith ? Promise.reject(this.rejectWith) : Promise.resolve();
  }

  stop(): void {
    this.stopCalls += 1;
  }
}

function response(): ReasoningPlanningResponse {
  return {
    reasoningRequested: true,
    reasoningInvoked: true,
    proposalProduced: true,
    proposalValidated: true,
    planningContextEnriched: true,
    provider: "secret-provider-debug",
    model: "secret-model-debug",
    explanation: "Cauco prepared a safe advisory plan.",
    planning: {
      status: "planned",
      routing: {
        selectedAgent: { id: "private-agent-id", name: "Project Agent" },
        match: {
          agentId: "private-agent-id",
          matched: true,
          score: 99,
          matchedSignals: ["internal signal"],
          reasoning: ["internal routing reason"],
          priority: 10,
        },
        matches: [],
        preferredAgentRejected: false,
      },
      plan: {
        agentId: "private-agent-id",
        agentName: "Project Agent",
        status: "proposal_only",
        objective: "Prepare the next project milestone",
        steps: [
          {
            order: 1,
            title: "Review scope",
            description: "Inspect the agreed project scope.",
            proposedAction: "internal proposed action",
            requiresConfirmation: false,
            executionAvailable: false,
            warnings: [],
          },
        ],
        openQuestions: [],
        warnings: [],
        requiresConfirmation: true,
        executionPerformed: false,
      },
      proposalOnly: true,
      executionPerformed: false,
      reviewApproved: false,
      runtimeStarted: false,
    },
    raw: { debug_secret: "raw-debug-secret", stack: "private stack trace" },
  };
}

test("TTS is inert until explicit speak and forwards locale", () => {
  const synthesizer = new FakeSynthesizer();
  const output = new SpeechOutputService(synthesizer);
  const controller = new SpeechOutputController(output, () => false);

  assert.equal(synthesizer.speakCalls.length, 0);
  assert.equal(controller.speak({ text: "Hola", locale: "es-ES" }), true);
  assert.deepEqual(synthesizer.speakCalls, [{ text: "Hola", locale: "es-ES" }]);
});

test("Stop cancels synthesis and a second utterance safely replaces the first", () => {
  const synthesizer = new FakeSynthesizer();
  const controller = new SpeechOutputController(
    new SpeechOutputService(synthesizer),
    () => false,
  );

  controller.speak({ text: "First", locale: "en-US" });
  const afterFirst = synthesizer.stopCalls;
  controller.speak({ text: "Second", locale: "fi-FI" });
  assert.equal(synthesizer.stopCalls, afterFirst + 1);
  assert.equal(synthesizer.speakCalls.at(-1)?.text, "Second");

  controller.stop();
  assert.equal(synthesizer.stopCalls, afterFirst + 2);
});

test("spoken formatter includes conversational plan text and excludes diagnostics", () => {
  const text = spokenPlanningResponse(response());

  assert.match(text, /safe advisory plan/);
  assert.match(text, /Project Agent/);
  assert.match(text, /Prepare the next project milestone/);
  assert.match(text, /Review scope/);
  assert.match(text, /Inspect the agreed project scope/);
  for (const excluded of [
    "raw-debug-secret",
    "private stack trace",
    "secret-provider-debug",
    "secret-model-debug",
    "private-agent-id",
    "internal signal",
    "internal routing reason",
    "proposal_only",
    "runtimeStarted",
  ]) {
    assert.equal(text.includes(excluded), false);
  }
});

test("unavailable and failing synthesis remain safe without affecting text", async () => {
  const unavailable = new FakeSynthesizer(false);
  const unavailableOutput = new SpeechOutputService(unavailable);
  await unavailableOutput.speak({ text: "Written response", locale: "sv-SE" });
  assert.equal(unavailableOutput.state.status, "unavailable");
  assert.equal(unavailable.speakCalls.length, 0);

  const failing = new FakeSynthesizer();
  failing.rejectWith = new Error("secret-api-key /Users/private/voice");
  const failingOutput = new SpeechOutputService(failing);
  await failingOutput.speak({ text: "Still visible", locale: "en-GB" });
  assert.equal(failingOutput.state.status, "error");
  assert.equal(failingOutput.state.message.includes("secret-api-key"), false);
  assert.equal(failingOutput.state.message.includes("/Users/private"), false);
});

test("disposing output stops active speech", () => {
  const synthesizer = new FakeSynthesizer();
  const controller = new SpeechOutputController(
    new SpeechOutputService(synthesizer),
    () => false,
  );
  controller.speak({ text: "Speaking", locale: "en-US" });
  const beforeDispose = synthesizer.stopCalls;

  controller.dispose();

  assert.equal(synthesizer.stopCalls, beforeDispose + 1);
});

test("TTS is blocked while STT is active to prevent feedback", () => {
  const synthesizer = new FakeSynthesizer();
  const controller = new SpeechOutputController(
    new SpeechOutputService(synthesizer),
    () => true,
  );

  assert.equal(controller.speak({ text: "Do not play", locale: "en-US" }), false);
  assert.equal(synthesizer.speakCalls.length, 0);
});

test("browser synthesis selects only a deterministic matching local voice", () => {
  const spoken: FakeUtterance[] = [];
  class FakeUtterance {
    lang = "";
    voice: FakeVoice | null = null;
    onend: (() => void) | null = null;
    onerror: (() => void) | null = null;

    constructor(readonly text: string) {}
  }
  interface FakeVoice {
    default: boolean;
    lang: string;
    localService: boolean;
    name: string;
    voiceURI: string;
  }
  const voices: FakeVoice[] = [
    { default: true, lang: "en-US", localService: true, name: "Local English", voiceURI: "en" },
    { default: false, lang: "es-ES", localService: false, name: "Remote Spanish", voiceURI: "remote" },
    { default: false, lang: "es-MX", localService: true, name: "Local Spanish", voiceURI: "es" },
  ];
  const synthesis = {
    cancel: () => undefined,
    getVoices: () => voices,
    speak: (utterance: FakeUtterance) => spoken.push(utterance),
  };
  const adapter = new BrowserLocalSpeechSynthesizer(synthesis, FakeUtterance);

  void adapter.speak({ text: "Hola", locale: "es-MX" });

  assert.equal(spoken[0]?.voice?.name, "Local Spanish");
  assert.equal(spoken[0]?.voice?.localService, true);
  assert.equal(spoken[0]?.lang, "es-MX");
});

test("panel voice output has no autoplay, cloud, execution, or debug synthesis path", async () => {
  const panel = await readFile("src/views/CaucoConversationPanel.ts", "utf8");
  const formatter = await readFile("src/voice/speechOutput.ts", "utf8");
  const browser = await readFile("src/voice/browserTts.ts", "utf8");
  const dashboard = await readFile("src/views/CaucoDashboardView.ts", "utf8");

  assert.match(panel, /speak\.addEventListener\("click"/);
  assert.match(dashboard, /conversationPanel\?\.dispose\(\)/);
  assert.doesNotMatch(formatter, /response\.raw|response\.provider|response\.model/);
  for (const forbidden of [
    "fetch(",
    "requestUrl",
    "openai",
    "elevenlabs",
    "gemini",
    "edge_tts",
    "/api/executions",
    "allow_execution",
    "createexecution",
    "approveplanreview",
    "confirmmutation",
  ]) {
    assert.equal(`${panel}\n${formatter}\n${browser}`.toLowerCase().includes(forbidden), false);
  }
});
