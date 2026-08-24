import type { ReasoningPlanningApiClient } from "../reasoning/api";
import { ConversationHistory, responseView } from "../reasoning/conversation";
import type { ConversationEntry, ReasoningPlanningResponse } from "../reasoning/types";
import { createLocalSpeechTranscriber } from "../voice/browserSpeech";
import { createLocalSpeechSynthesizer } from "../voice/browserTts";
import { VoiceInputController } from "../voice/inputController";
import { SpeechOutputController } from "../voice/outputController";
import { SpeechTranscriptionService } from "../voice/service";
import { SpeechOutputService, spokenPlanningResponse } from "../voice/speechOutput";
import type {
  SpeechOutput,
  SpeechSynthesisState,
  SpeechTranscription,
  SpeechTranscriptionState,
} from "../voice/types";

export class CaucoConversationPanel {
  private readonly history = new ConversationHistory();
  private submitting = false;
  private historyElement?: HTMLElement;
  private outputButton?: HTMLButtonElement;
  private outputController: SpeechOutputController;
  private outputStatus?: HTMLElement;
  private readonly unsubscribeOutput: () => void;
  private voiceController?: VoiceInputController;

  constructor(
    private readonly client: ReasoningPlanningApiClient,
    private readonly speech: SpeechTranscription = new SpeechTranscriptionService(
      createLocalSpeechTranscriber(),
    ),
    output: SpeechOutput = new SpeechOutputService(createLocalSpeechSynthesizer()),
  ) {
    this.outputController = new SpeechOutputController(output, () => this.microphoneActive());
    this.unsubscribeOutput = this.outputController.subscribe((state) =>
      this.renderOutputState(state),
    );
  }

  render(container: HTMLElement, connected: boolean): void {
    this.voiceController?.dispose();
    this.outputController.stop();
    this.outputButton = undefined;
    this.outputStatus = undefined;
    const section = container.createEl("section", { cls: "cauco-conversation" });
    const header = section.createDiv({ cls: "cauco-panel-header" });
    header.createEl("h2", { text: "Cauco Conversation" });
    header.createEl("span", { text: "Advisory planning only" });
    section.createEl("p", {
      text: "Explore routing and proposed plans. This panel cannot approve, execute, or mutate anything.",
      cls: "cauco-trust-note",
    });

    this.historyElement = section.createDiv({ cls: "cauco-conversation-history" });
    this.renderHistory();

    const label = section.createEl("label", { text: "Instruction", cls: "cauco-field-label" });
    const input = section.createEl("textarea", {
      cls: "cauco-conversation-input",
      attr: { placeholder: "Describe what you want Cauco to plan…", rows: "4" },
    });
    label.htmlFor = "cauco-conversation-input";
    input.id = "cauco-conversation-input";
    input.maxLength = 4000;
    input.disabled = !connected;

    const voice = section.createDiv({ cls: "cauco-conversation-voice" });
    const microphone = voice.createEl("button", { text: "Use microphone" });
    microphone.setAttribute("aria-label", "Start local speech transcription");
    microphone.title = "Start local speech transcription";
    const cancelMicrophone = voice.createEl("button", { text: "Cancel" });
    cancelMicrophone.setAttribute("aria-label", "Cancel speech transcription");
    cancelMicrophone.title = "Cancel speech transcription without submitting";
    const voiceStatus = voice.createEl("span", { cls: "cauco-voice-status" });
    voiceStatus.setAttribute("role", "status");
    const renderVoiceState = (state: SpeechTranscriptionState): void => {
      const active = ["requesting-permission", "listening"].includes(state.status);
      const processing = state.status === "processing";
      microphone.setText(active ? "Stop" : "Use microphone");
      microphone.setAttribute(
        "aria-label",
        active ? "Stop and transcribe speech" : "Start local speech transcription",
      );
      microphone.disabled = !connected || processing || state.status === "unavailable";
      cancelMicrophone.hidden = !(active || processing);
      voiceStatus.setText(state.message);
      voiceStatus.toggleClass(
        "cauco-error",
        state.status === "permission-denied" || state.status === "error",
      );
    };
    this.voiceController = new VoiceInputController(
      this.speech,
      () => input.value,
      (value) => {
        input.value = value;
        input.focus();
      },
      renderVoiceState,
    );
    microphone.addEventListener("click", () => {
      if (!this.voiceController) return;
      const status = this.voiceController.state.status;
      if (status === "requesting-permission" || status === "listening") {
        this.voiceController.stop();
      } else {
        this.outputController.stop();
        this.voiceController.start(navigator.language || "en");
      }
    });
    cancelMicrophone.addEventListener("click", () => this.voiceController?.cancel());

    const actions = section.createDiv({ cls: "cauco-conversation-actions" });
    const toggleLabel = actions.createEl("label", { cls: "cauco-reasoning-toggle" });
    const useReasoning = toggleLabel.createEl("input", { type: "checkbox" });
    useReasoning.checked = false;
    useReasoning.disabled = !connected;
    toggleLabel.appendText("Use reasoning");
    const submit = actions.createEl("button", { text: "Plan", cls: "mod-cta" });
    submit.disabled = !connected;
    submit.addEventListener("click", () => {
      void this.submit(input, useReasoning, submit);
    });
  }

  entries(): readonly ConversationEntry[] {
    return this.history.entries();
  }

  dispose(): void {
    this.voiceController?.dispose();
    this.outputController.dispose();
    this.unsubscribeOutput();
  }

  private async submit(
    input: HTMLTextAreaElement,
    useReasoning: HTMLInputElement,
    button: HTMLButtonElement,
  ): Promise<void> {
    const instruction = input.value.trim();
    if (!instruction || this.submitting) return;
    this.submitting = true;
    input.disabled = true;
    useReasoning.disabled = true;
    button.disabled = true;
    button.setText("Planning…");
    try {
      const response = await this.client.plan({
        instruction,
        useReasoning: useReasoning.checked,
      });
      this.history.add({ instruction, useReasoning: useReasoning.checked, response });
      input.value = "";
    } catch (error) {
      this.history.add({
        instruction,
        useReasoning: useReasoning.checked,
        error:
          error instanceof Error
            ? error.message
            : "Advisory planning is unavailable. No action was taken.",
      });
    } finally {
      this.submitting = false;
      input.disabled = false;
      useReasoning.disabled = false;
      button.disabled = false;
      button.setText("Plan");
      this.renderHistory();
    }
  }

  private renderHistory(): void {
    if (!this.historyElement) return;
    this.historyElement.empty();
    const entries = this.history.entries();
    if (entries.length === 0) {
      this.historyElement.createEl("p", {
        text: "Conversation results remain here until this dashboard session closes.",
        cls: "cauco-empty",
      });
      return;
    }
    for (const entry of entries) this.renderEntry(this.historyElement, entry);
  }

  private renderEntry(container: HTMLElement, entry: ConversationEntry): void {
    const user = container.createDiv({ cls: "cauco-conversation-message is-user" });
    user.createEl("strong", { text: "You" });
    user.createEl("p", { text: entry.instruction });
    if (entry.error) {
      const response = container.createDiv({ cls: "cauco-conversation-message is-cauco" });
      response.createEl("strong", { text: "Cauco" });
      const message = response.createEl("p", { text: entry.error, cls: "cauco-error" });
      message.setAttribute("role", "alert");
      return;
    }
    if (entry.response) this.renderResponse(container, entry.response);
  }

  private renderResponse(container: HTMLElement, response: ReasoningPlanningResponse): void {
    const view = responseView(response);
    const card = container.createDiv({ cls: "cauco-conversation-message is-cauco" });
    card.createEl("strong", { text: "Cauco" });
    card.createEl("p", { text: response.explanation });
    const speechControls = card.createDiv({ cls: "cauco-speech-output" });
    const speak = speechControls.createEl("button", { text: "Speak" });
    speak.setAttribute("aria-label", "Speak this Cauco response");
    speak.title = "Speak this Cauco response using a local system voice";
    const speechStatus = speechControls.createEl("span", { cls: "cauco-voice-status" });
    speak.addEventListener("click", () => {
      if (this.outputButton === speak && this.outputController.state.status === "speaking") {
        this.outputController.stop();
        return;
      }
      this.resetOutputControl();
      this.outputButton = speak;
      this.outputStatus = speechStatus;
      const started = this.outputController.speak({
        text: spokenPlanningResponse(response),
        locale: navigator.language || "en",
      });
      if (!started) {
        speechStatus.setText("Stop microphone input before speaking this response.");
      }
    });
    const summary = card.createEl("dl", { cls: "cauco-control-details" });
    const rows: Array<[string, string]> = [
      ["Planning status", view.planningStatus],
      ["Selected agent", view.selectedAgent],
      ["Routing match", view.routingMatch],
      ["Reasoning requested", String(response.reasoningRequested)],
      ["Reasoning invoked", String(response.reasoningInvoked)],
      ["Proposal produced", String(response.proposalProduced)],
      ["Proposal validated", String(response.proposalValidated)],
      ["Planning context enriched", String(response.planningContextEnriched)],
      ["Provider", response.provider ?? "None"],
      ["Model", response.model ?? "None"],
    ];
    for (const [name, value] of rows) {
      summary.createEl("dt", { text: name });
      summary.createEl("dd", { text: value });
    }

    const safety = card.createDiv({ cls: "cauco-conversation-safety" });
    safety.createEl("h4", { text: "Safety state" });
    for (const [name, value] of view.safety) {
      const safe = name === "proposal_only" ? value : !value;
      const flag = safety.createEl("span", {
        text: `${name}: ${String(value)}`,
        cls: `cauco-safety-flag ${safe ? "is-safe" : "is-unsafe"}`,
      });
      flag.setAttribute("data-safety-flag", name);
    }

    if (response.planning.plan) {
      const plan = response.planning.plan;
      const planSection = card.createDiv({ cls: "cauco-conversation-plan" });
      planSection.createEl("h4", { text: plan.objective });
      planSection.createEl("small", { text: `${plan.agentName} · ${plan.status}` });
      const steps = planSection.createEl("ol");
      for (const step of plan.steps) {
        const item = steps.createEl("li");
        item.createEl("strong", { text: step.title });
        item.createEl("p", { text: step.description });
      }
    }

    const details = card.createEl("details", { cls: "cauco-conversation-details" });
    details.createEl("summary", { text: "Details / Debug" });
    details.createEl("pre", { text: JSON.stringify(response.raw, null, 2) });
  }

  private microphoneActive(): boolean {
    return Boolean(
      this.voiceController &&
        ["requesting-permission", "listening", "processing"].includes(
          this.voiceController.state.status,
        ),
    );
  }

  private renderOutputState(state: SpeechSynthesisState): void {
    if (!this.outputButton || !this.outputStatus) return;
    const speaking = state.status === "speaking";
    this.outputButton.setText(speaking ? "Stop" : "Speak");
    this.outputButton.setAttribute(
      "aria-label",
      speaking ? "Stop speaking this Cauco response" : "Speak this Cauco response",
    );
    this.outputStatus.setText(state.message);
    this.outputStatus.toggleClass("cauco-error", state.status === "error");
  }

  private resetOutputControl(): void {
    this.outputButton?.setText("Speak");
    this.outputButton?.setAttribute("aria-label", "Speak this Cauco response");
    this.outputStatus?.setText("");
  }
}
