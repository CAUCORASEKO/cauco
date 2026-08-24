import type { ReasoningPlanningResponse } from "../reasoning/types";
import type {
  SpeechOutput,
  SpeechSynthesisRequest,
  SpeechSynthesisState,
  SpeechSynthesizer,
} from "./types";

const MESSAGES: Record<SpeechSynthesisState["status"], string> = {
  idle: "Ready to speak this response.",
  speaking: "Speaking…",
  unavailable: "Local speech output is unavailable. The written response remains available.",
  error: "Cauco could not speak this response. The written response remains available.",
};

export function spokenPlanningResponse(response: ReasoningPlanningResponse): string {
  const parts = [response.explanation.trim()];
  const plan = response.planning.plan;
  if (plan) {
    parts.push(plan.agentName.trim(), plan.objective.trim());
    for (const step of plan.steps) {
      parts.push(step.title.trim(), step.description.trim());
    }
  }
  return parts.filter(Boolean).join(". ").slice(0, 3000);
}

export class SpeechOutputService implements SpeechOutput {
  private listeners = new Set<(state: SpeechSynthesisState) => void>();
  private current: SpeechSynthesisState;
  private generation = 0;

  constructor(private readonly synthesizer: SpeechSynthesizer) {
    this.current = this.createState(synthesizer.available ? "idle" : "unavailable");
  }

  get state(): SpeechSynthesisState {
    return this.current;
  }

  async speak(request: SpeechSynthesisRequest): Promise<void> {
    const text = request.text.trim().slice(0, 3000);
    if (!text || !this.synthesizer.available) {
      this.update("unavailable");
      return;
    }
    const generation = ++this.generation;
    try {
      this.synthesizer.stop();
      this.update("speaking");
      await this.synthesizer.speak({ text, locale: request.locale });
      if (generation === this.generation) this.update("idle");
    } catch {
      if (generation === this.generation) this.update("error");
    }
  }

  stop(): void {
    this.generation += 1;
    try {
      this.synthesizer.stop();
    } catch {
      // A failed cancellation is not exposed with provider/runtime details.
    }
    this.update(this.synthesizer.available ? "idle" : "unavailable");
  }

  subscribe(listener: (state: SpeechSynthesisState) => void): () => void {
    this.listeners.add(listener);
    listener(this.current);
    return () => this.listeners.delete(listener);
  }

  private update(status: SpeechSynthesisState["status"]): void {
    this.current = this.createState(status);
    for (const listener of this.listeners) listener(this.current);
  }

  private createState(status: SpeechSynthesisState["status"]): SpeechSynthesisState {
    return Object.freeze({ status, message: MESSAGES[status] });
  }
}
