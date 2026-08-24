import type {
  WakeWordConfiguration,
  WakeWordDetector,
  WakeWordObserver,
} from "./wakeWord";

/**
 * Production wake detection belongs behind a narrow native-host event seam.
 * The current host has no microphone permission, model, or host-to-plugin event channel,
 * so this adapter intentionally performs no capture and exposes no generic audio access.
 */
export class UnavailableNativeWakeWordDetector implements WakeWordDetector {
  readonly available = false;

  start(_configuration: WakeWordConfiguration, observer: WakeWordObserver): void {
    observer.failed("unavailable");
  }

  stop(): void {}

  dispose(): void {}
}

export function createNativeWakeWordDetector(): WakeWordDetector {
  return new UnavailableNativeWakeWordDetector();
}
