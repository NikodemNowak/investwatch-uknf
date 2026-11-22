import { useCallback, useMemo, useRef, useState } from "react";
import type { ReactNode } from "react";
import { ToastContext } from "@/state/toastContext";
import type { Toast, ToastApi, ToastInput } from "@/state/toastContext";
import { ToastStack } from "@/components/ToastStack";

/** Alerts stay long enough to act on; confirmations go quickly so they never sit over content. */
const LIFETIME_MS = { danger: 9000, success: 5000, info: 5000 } as const;
const MAX_TOASTS = 3;
// Instructions (how to get an API key) need time to read.
const LONG_TEXT_MS = 12000;

/** Owns the toast list and renders the stack. */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const nextId = useRef(1);
  const timers = useRef(new Map<number, ReturnType<typeof setTimeout>>());

  const dismiss = useCallback((id: number) => {
    const timer = timers.current.get(id);
    if (timer) clearTimeout(timer);
    timers.current.delete(id);
    setToasts((list) => list.filter((toast) => toast.id !== id));
  }, []);

  const show = useCallback(
    (input: ToastInput) => {
      const id = nextId.current++;
      setToasts((list) => {
        const kept = input.key ? list.filter((toast) => toast.key !== input.key) : list;
        return [...kept, { ...input, id }].slice(-MAX_TOASTS);
      });
      timers.current.set(
        id,
        setTimeout(() => dismiss(id), input.fullText ? LONG_TEXT_MS : LIFETIME_MS[input.tone]),
      );
    },
    [dismiss],
  );

  const api = useMemo<ToastApi>(() => ({ show, dismiss }), [show, dismiss]);
  return (
    <ToastContext.Provider value={api}>
      {children}
      <ToastStack toasts={toasts} onDismiss={dismiss} />
    </ToastContext.Provider>
  );
}
