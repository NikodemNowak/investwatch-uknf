import { Link } from "react-router-dom";
import type { Toast } from "@/state/toastContext";
import { Icon } from "@/components/Icon";
import { pl } from "@/i18n/pl";

interface ToastStackProps {
  toasts: Toast[];
  onDismiss: (id: number) => void;
}

/** Bottom-right stack of notifications; announced politely to screen readers. */
export function ToastStack({ toasts, onDismiss }: ToastStackProps) {
  return (
    <div className="toasts" role="region" aria-live="polite" aria-label="Powiadomienia">
      {toasts.map((toast) => (
        <div key={toast.id} className={`toast toast--${toast.tone}`}>
          <span className="toast__icon">
            <Icon
              name={toast.tone === "danger" ? "alert" : toast.tone === "success" ? "check" : "dash"}
              size={toast.tone === "danger" ? 18 : 16}
              color="#ffffff"
              strokeWidth={toast.tone === "danger" ? 2.8 : 3}
            />
          </span>
          <div className="toast__body">
            <div className="toast__title">{toast.title}</div>
            {toast.text && (
              <div className={toast.fullText ? "toast__text toast__text--full" : "toast__text"}>
                {toast.text}
              </div>
            )}
            {toast.action && (
              <Link
                className="btn btn--dark btn--sm toast__action"
                to={toast.action.to}
                onClick={() => onDismiss(toast.id)}
              >
                {toast.action.label}
              </Link>
            )}
          </div>
          <button
            type="button"
            className="toast__close"
            aria-label={pl.toast.close}
            onClick={() => onDismiss(toast.id)}
          >
            <Icon name="close" size={16} />
          </button>
        </div>
      ))}
    </div>
  );
}
