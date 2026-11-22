import type { RegistryStatus } from "@/api/types";
import { useSyncRegistry } from "@/hooks/useRegistry";
import { pl } from "@/i18n/pl";
import { formatWhen } from "@/lib/format";
import { useToasts } from "@/state/toastContext";

/** Register freshness and the "Pobierz teraz" button. */
export function SyncState({ status }: { status: RegistryStatus | undefined }) {
  const sync = useSyncRegistry();
  const toasts = useToasts();
  const last = status?.last_sync;
  const tone = !status?.synced_at
    ? "dot--off"
    : last?.error
      ? "dot--bad"
      : last?.source === "snapshot"
        ? "dot--warn"
        : "";
  const title = !status?.synced_at
    ? pl.registry.neverSynced
    : last?.error
      ? pl.registry.failed
      : last?.source === "snapshot"
        ? pl.registry.snapshot
        : pl.registry.current;
  return (
    <div className="sync">
      {status && (
        <div className="sync__state">
          <div className="sync__title">
            <span className={`dot ${tone}`} />
            {title}
          </div>
          {status.synced_at && (
            <div className="sync__when">{pl.registry.fetchedAt(formatWhen(status.synced_at))}</div>
          )}
        </div>
      )}
      <button
        type="button"
        className="btn btn--outline btn--md"
        disabled={sync.isPending}
        onClick={() =>
          sync.mutate(undefined, {
            onSuccess: () =>
              toasts.show({ key: "sync", tone: "info", title: pl.registry.syncQueued }),
            onError: () =>
              toasts.show({ key: "sync", tone: "danger", title: pl.registry.syncError }),
          })
        }
      >
        {pl.registry.syncNow}
      </button>
    </div>
  );
}
