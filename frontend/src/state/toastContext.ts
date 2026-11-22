import { createContext, useContext } from "react";

export type ToastTone = "danger" | "success" | "info";

export interface ToastInput {
  tone: ToastTone;
  title: string;
  text?: string;
  /** Show the whole text (instructions); otherwise it is clamped to four lines. */
  fullText?: boolean;
  /** In-app route opened by the action button ("Otwórz"). */
  action?: { label: string; to: string };
  /** Same key replaces an earlier toast instead of stacking. */
  key?: string;
}

export interface Toast extends ToastInput {
  id: number;
}

export interface ToastApi {
  show: (toast: ToastInput) => void;
  dismiss: (id: number) => void;
}

export const ToastContext = createContext<ToastApi | null>(null);

/** Show and dismiss toasts (bottom-right stack). */
export function useToasts(): ToastApi {
  const api = useContext(ToastContext);
  if (!api) throw new Error("useToasts outside ToastProvider");
  return api;
}
