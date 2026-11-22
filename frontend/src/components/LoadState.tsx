import { pl } from "@/i18n/pl";

interface LoadStateProps {
  error?: boolean;
  empty?: string;
  onRetry?: () => void;
}

/** Placeholder for loading, failed and empty data. */
export function LoadState({ error, empty, onRetry }: LoadStateProps) {
  if (error) {
    return (
      <div className="state state--error" role="alert">
        <div>{pl.common.error}</div>
        {onRetry && (
          <button type="button" className="btn btn--outline btn--md" onClick={onRetry}>
            {pl.common.retry}
          </button>
        )}
      </div>
    );
  }
  return (
    <div className="state" aria-busy={empty ? undefined : true}>
      {empty ?? pl.common.loading}
    </div>
  );
}
