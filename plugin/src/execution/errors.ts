import { safeDisplayText } from "./contracts";

export type CoreErrorKind =
  | "network"
  | "timeout"
  | "validation"
  | "conflict"
  | "forbidden"
  | "not-found"
  | "server";

export function executionErrorMessage(kind: CoreErrorKind, message: string): string {
  switch (kind) {
    case "timeout":
      return "The request timed out. Refresh state before retrying a POST action.";
    case "network":
      return "Cauco Core is unavailable at the configured URL.";
    case "forbidden":
      return "Core denied this operation or workspace path.";
    case "not-found":
      return "The requested Core record no longer exists. Core may have restarted.";
    case "conflict":
      return `Lifecycle conflict: ${safeDisplayText(message, 300)}`;
    case "validation":
      return `Core rejected the request controls: ${safeDisplayText(message, 300)}`;
    default:
      return "Cauco Core could not complete the request. No automatic retry was attempted.";
  }
}
