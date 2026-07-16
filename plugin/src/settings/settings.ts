import { DEFAULT_CORE_URL } from "../constants";
import type { CaucoSettings } from "../types";

export const DEFAULT_SETTINGS: CaucoSettings = {
  coreUrl: DEFAULT_CORE_URL,
  selectedModel: "",
};

export function normalizeCoreUrl(value: string): string {
  const trimmed = value.trim().replace(/\/+$/, "");
  try {
    const url = new URL(trimmed);
    if (url.protocol !== "http:" && url.protocol !== "https:") {
      return DEFAULT_CORE_URL;
    }
    return url.toString().replace(/\/$/, "");
  } catch {
    return DEFAULT_CORE_URL;
  }
}
