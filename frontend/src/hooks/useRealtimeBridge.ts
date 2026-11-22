import { useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { getRealtime } from "@/api/client";
import { queryKeys } from "@/api/queryKeys";
import type { FindingWithPost } from "@/api/types";
import { pl } from "@/i18n/pl";
import { domainOf } from "@/lib/format";
import { describeFinding, modelSignalOf, subjectOf } from "@/lib/problems";
import { useCheck } from "@/state/checkContext";
import { useToasts } from "@/state/toastContext";

const REPEAT_WINDOW_MS = 60_000;

/**
 * Connects Socket.IO to the UI: high-risk alerts become toasts, model reviews update cached
 * findings in place. Returns whether the realtime channel is connected.
 */
export function useRealtimeBridge(): boolean {
  const queryClient = useQueryClient();
  const toasts = useToasts();
  const { run } = useCheck();
  const [live, setLive] = useState(false);
  const runRef = useRef(run);
  runRef.current = run;
  const lastShown = useRef(new Map<string, number>());

  useEffect(() => {
    let cancelled = false;
    const unsubscribers: (() => void)[] = [];
    void getRealtime().then((realtime) => {
      if (cancelled) return;
      setLive(realtime.isConnected());
      unsubscribers.push(
        realtime.on("connection", setLive),
        realtime.on("finding_updated", (finding) => {
          queryClient.setQueryData<FindingWithPost>(queryKeys.finding(finding.id), (old) =>
            old ? { ...old, ...finding } : old,
          );
          void queryClient.invalidateQueries({ queryKey: queryKeys.findings });
        }),
        realtime.on("alert", ({ finding, post }) => {
          void queryClient.invalidateQueries({ queryKey: queryKeys.findings });
          if (finding.risk_level !== "high") return;
          const current = runRef.current;
          // The check page already shows this page's result and says "Gotowe" itself.
          if (current && domainOf(current.url) === domainOf(post.url)) return;
          const now = Date.now();
          if (now - (lastShown.current.get(finding.id) ?? 0) < REPEAT_WINDOW_MS) return;
          lastShown.current.set(finding.id, now);
          toasts.show({
            key: `alert-${finding.id}`,
            tone: "danger",
            title: (modelSignalOf(finding) ? pl.toast.signalTitle : pl.toast.alertTitle)(
              subjectOf({ ...finding, post }) || domainOf(post.url),
            ),
            text: describeFinding(finding),
            action: { label: pl.common.open, to: `/zgloszenia/${finding.id}` },
          });
        }),
      );
    });
    return () => {
      cancelled = true;
      unsubscribers.forEach((off) => off());
    };
  }, [queryClient, toasts]);

  return live;
}
