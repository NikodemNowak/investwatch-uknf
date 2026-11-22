import { HttpError } from "@/api/http";
import type { ConnectorInfo, Source } from "@/api/types";
import { Icon } from "@/components/Icon";
import { StatusPill } from "@/components/StatusPill";
import type { PillTone } from "@/components/StatusPill";
import { useRunSource } from "@/hooks/useSources";
import { pl } from "@/i18n/pl";
import { formatLastRun } from "@/lib/format";
import { formatInt } from "@/lib/plural";
import { accessLabel, sourceState, sourceSubtitle } from "@/lib/sources";
import type { SourceState } from "@/lib/sources";
import { useToasts } from "@/state/toastContext";

const TONE: Record<SourceState, PillTone> = {
  ok: "ok",
  key: "medium",
  approval: "medium",
  blocked: "low",
  off: "low",
  error: "high",
  running: "info",
  new: "low",
};

interface SourceRowProps {
  source: Source;
  /** The source's connector, when known: a not-ready one explains itself without a request. */
  connector?: ConnectorInfo;
}

/** One monitored source: what, how, state, last run, items found, run now. */
export function SourceRow({ source, connector }: SourceRowProps) {
  const state = sourceState(source);
  const run = useRunSource();
  const toasts = useToasts();

  const notReady = (status: ConnectorInfo["status"], howTo: string | null | undefined) =>
    toasts.show({
      key: `run-${source.id}`,
      tone: "info",
      title: pl.sources.notReady[status],
      text: howTo ?? undefined,
      fullText: true,
    });

  const onRun = () => {
    if (source.connector_reason) {
      notReady("disabled", source.connector_reason);
      return;
    }
    if (connector && connector.status !== "ready") {
      notReady(connector.status, connector.how_to);
      return;
    }
    run.mutate(source.id, {
      onSuccess: () =>
        toasts.show({
          key: `run-${source.id}`,
          tone: "info",
          title: pl.sources.started,
          text: source.name,
        }),
      onError: (error) => {
        // 409: the connector is not ready; the server says how to get access.
        if (error instanceof HttpError && error.status === 409) {
          notReady(error.blocked?.status ?? "disabled", error.detail);
          return;
        }
        toasts.show({ key: `run-${source.id}`, tone: "danger", title: pl.sources.runError });
      },
    });
  };

  return (
    <div className="table__row">
      <span className="table__main">
        <span className="table__title">{source.name}</span>
        <span className="table__sub">{source.connector_reason ?? sourceSubtitle(source)}</span>
      </span>
      <span className="table__cell table__cell--nowrap">{accessLabel(source)}</span>
      <span>
        <StatusPill tone={TONE[state]} label={pl.sources.states[state]} />
      </span>
      <span className="table__cell table__cell--nowrap">{formatLastRun(source.last_run_at)}</span>
      <span className="table__cell table__cell--strong table__cell--right">
        {source.last_run_at ? formatInt(source.last_run_items) : pl.common.dash}
      </span>
      <span className="table__cell--right">
        <button
          type="button"
          className="icon-btn"
          aria-label={pl.sources.runLabel(source.name)}
          title={pl.sources.run}
          disabled={run.isPending || state === "running" || !source.enabled}
          onClick={onRun}
        >
          <Icon name="play" size={16} />
        </button>
      </span>
    </div>
  );
}
