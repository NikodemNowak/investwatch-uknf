import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { HttpError } from "@/api/http";
import { pl } from "@/i18n/pl";
import { useSubmitMaterial } from "@/hooks/useSources";
import { screenshotProblem } from "@/lib/submission";
import { useToasts } from "@/state/toastContext";

interface SubmitMaterialDialogProps {
  open: boolean;
  onClose: () => void;
  /** Address to start with (the social-media URL "Sprawdź" could not fetch). */
  initialUrl?: string;
  /** Called once the material is stored. */
  onSubmitted?: () => void;
}

/** Modal "Zgłoś materiał": URL + pasted text + optional screenshot, analysed without fetching. */
export function SubmitMaterialDialog({
  open,
  onClose,
  initialUrl = "",
  onSubmitted,
}: SubmitMaterialDialogProps) {
  const ref = useRef<HTMLDialogElement>(null);
  const submit = useSubmitMaterial();
  const toasts = useToasts();
  const [url, setUrl] = useState(initialUrl);
  const [text, setText] = useState("");
  const [note, setNote] = useState("");
  const [screenshot, setScreenshot] = useState<File | null>(null);
  const t = pl.submitMaterial;

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) {
      setUrl(initialUrl);
      dialog.showModal();
    }
    if (!open && dialog.open) dialog.close();
  }, [open, initialUrl]);

  const close = () => {
    submit.reset();
    onClose();
  };

  const fileProblem = screenshotProblem(screenshot);
  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    if (fileProblem || !text.trim()) return;
    submit.mutate(
      {
        text: text.trim(),
        url: url.trim() || undefined,
        note: note.trim() || undefined,
        screenshot: screenshot ?? undefined,
      },
      {
        onSuccess: () => {
          toasts.show({
            tone: "success",
            title: t.submitted,
            text: t.submittedText,
            action: { label: t.open, to: "/zgloszenia" },
          });
          setText("");
          setNote("");
          setScreenshot(null);
          onSubmitted?.();
          close();
        },
      },
    );
  };

  const serverError =
    submit.isError &&
    (submit.error instanceof HttpError && submit.error.status === 422 && submit.error.detail
      ? submit.error.detail
      : t.error);
  const error = fileProblem ?? serverError;

  return (
    <dialog ref={ref} className="dialog" onClose={close} aria-labelledby="submit-material-h">
      <form className="dialog__form" onSubmit={onSubmit}>
        <h2 id="submit-material-h" className="h2">
          {t.title}
        </h2>
        <p className="dialog__lead">{t.lead}</p>
        <label className="field">
          <span className="field__label">{t.url}</span>
          <input
            className="field__input"
            type="url"
            maxLength={2048}
            placeholder={t.urlPlaceholder}
            value={url}
            onChange={(e) => setUrl(e.target.value)}
          />
        </label>
        <label className="field">
          <span className="field__label">{t.text}</span>
          <textarea
            className="field__input field__input--area"
            required
            maxLength={50_000}
            rows={6}
            placeholder={t.textPlaceholder}
            value={text}
            onChange={(e) => setText(e.target.value)}
          />
        </label>
        <div className="field">
          <span className="field__label" id="submit-shot-l">
            {t.screenshot}
          </span>
          <label className="file-pick">
            <input
              className="file-pick__input"
              type="file"
              aria-labelledby="submit-shot-l"
              accept="image/png,.png"
              onChange={(e) => setScreenshot(e.target.files?.[0] ?? null)}
            />
            <span className="btn btn--outline btn--sm">{t.chooseScreenshot}</span>
            <span className="file-pick__name">{screenshot?.name ?? t.noScreenshot}</span>
          </label>
        </div>
        <label className="field">
          <span className="field__label">{t.note}</span>
          <input
            className="field__input"
            maxLength={2000}
            placeholder={t.notePlaceholder}
            value={note}
            onChange={(e) => setNote(e.target.value)}
          />
        </label>
        {error && (
          <p className="form-error" role="alert">
            {error}
          </p>
        )}
        <div className="dialog__actions">
          <button type="button" className="btn btn--outline btn--md" onClick={close}>
            {pl.common.cancel}
          </button>
          <button
            type="submit"
            className="btn btn--primary btn--md"
            disabled={submit.isPending || Boolean(fileProblem)}
          >
            {t.submit}
          </button>
        </div>
      </form>
    </dialog>
  );
}
