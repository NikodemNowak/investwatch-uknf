import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { HttpError } from "@/api/http";
import type { ConnectorInfo, ImportFormat } from "@/api/types";
import { pl } from "@/i18n/pl";
import { useConnectors, useCreateSource, useImportFile } from "@/hooks/useSources";
import { useToasts } from "@/state/toastContext";

interface AddSourceDialogProps {
  open: boolean;
  onClose: () => void;
}

type Mode = keyof typeof pl.sources.dialog.modes;

const MODES = Object.keys(pl.sources.dialog.modes) as Mode[];
/** Collectors an analyst can schedule (the rest are internal: manual checks, samples). */
const SCHEDULABLE = Object.keys(pl.sources.collectors);
const FORMATS = Object.keys(pl.sources.dialog.formats) as ImportFormat[];

const detailOf = (error: unknown): string | null =>
  error instanceof HttpError && error.status === 422 ? error.detail : null;

/** Modal: add a scheduled source or import a file ("Zgłoś materiał" has its own dialog). */
export function AddSourceDialog({ open, onClose }: AddSourceDialogProps) {
  const ref = useRef<HTMLDialogElement>(null);
  const connectors = useConnectors();
  const create = useCreateSource();
  const importFile = useImportFile();
  const toasts = useToasts();
  const [mode, setMode] = useState<Mode>("source");
  const [name, setName] = useState("");
  const [collector, setCollector] = useState(SCHEDULABLE[0] ?? "web");
  const [target, setTarget] = useState("");
  const [cron, setCron] = useState<string>(pl.sources.schedules[0][0]);
  const [format, setFormat] = useState<ImportFormat>(FORMATS[0] ?? "meta_ads_csv");
  const [file, setFile] = useState<File | null>(null);
  const d = pl.sources.dialog;

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  const infoOf = (key: string): ConnectorInfo | undefined =>
    connectors.data?.find((c) => (c.collector ?? c.name) === key);
  const selected = infoOf(collector);
  const notReady = selected && selected.status !== "ready" ? selected : undefined;

  const close = () => {
    create.reset();
    importFile.reset();
    onClose();
  };

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    if (mode === "source") {
      create.mutate(
        { name: name.trim(), collector, target: target.trim(), cron, enabled: true },
        {
          onSuccess: () => {
            toasts.show({ tone: "success", title: d.added, text: name.trim() });
            setName("");
            setTarget("");
            close();
          },
        },
      );
    } else if (mode === "file" && file) {
      importFile.mutate(
        { file, format },
        {
          onSuccess: (result) => {
            toasts.show({
              tone: "success",
              title: d.imported(result.items),
              text: d.importedText(result.queued_for_analysis),
            });
            setFile(null);
            close();
          },
        },
      );
    }
  };

  const error =
    mode === "source"
      ? create.isError && (detailOf(create.error) ?? d.error)
      : importFile.isError && (detailOf(importFile.error) ?? d.importError);
  const pending = create.isPending || importFile.isPending;

  return (
    <dialog ref={ref} className="dialog" onClose={close} aria-labelledby="add-source-h">
      <form className="dialog__form" onSubmit={onSubmit}>
        <h2 id="add-source-h" className="h2">
          {d.title}
        </h2>
        <div className="seg seg--sm" role="tablist">
          {MODES.map((key) => (
            <button
              key={key}
              type="button"
              role="tab"
              className="seg__tab"
              aria-selected={mode === key}
              onClick={() => setMode(key)}
            >
              {d.modes[key]}
            </button>
          ))}
        </div>

        {mode === "source" && (
          <>
            <label className="field">
              <span className="field__label">{d.name}</span>
              <input
                className="field__input"
                required
                maxLength={200}
                placeholder={d.namePlaceholder}
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </label>
            <label className="field">
              <span className="field__label">{d.collector}</span>
              <select
                className="field__input"
                value={collector}
                onChange={(e) => setCollector(e.target.value)}
              >
                {SCHEDULABLE.map((key) => {
                  const suffix = pl.sources.connectorState[infoOf(key)?.status ?? "ready"];
                  const label = pl.sources.collectors[key] ?? key;
                  return (
                    <option key={key} value={key}>
                      {suffix ? `${label} (${suffix})` : label}
                    </option>
                  );
                })}
              </select>
              {notReady && (
                <span className="field__hint">
                  {notReady.how_to} {d.notReadyHint}
                </span>
              )}
            </label>
            <label className="field">
              <span className="field__label">{d.target}</span>
              <input
                className="field__input"
                required
                maxLength={2048}
                placeholder={d.targetPlaceholder}
                value={target}
                onChange={(e) => setTarget(e.target.value)}
              />
            </label>
            <label className="field">
              <span className="field__label">{d.schedule}</span>
              <select
                className="field__input"
                value={cron}
                onChange={(e) => setCron(e.target.value)}
              >
                {pl.sources.schedules.map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
          </>
        )}

        {mode === "file" && (
          <>
            <label className="field">
              <span className="field__label">{d.format}</span>
              <select
                className="field__input"
                value={format}
                onChange={(e) => setFormat(e.target.value as ImportFormat)}
              >
                {FORMATS.map((key) => (
                  <option key={key} value={key}>
                    {d.formats[key]}
                  </option>
                ))}
              </select>
            </label>
            <div className="field">
              <span className="field__label" id="import-file-l">
                {d.file}
              </span>
              <label className="file-pick">
                <input
                  className="file-pick__input"
                  type="file"
                  required
                  aria-labelledby="import-file-l"
                  accept=".csv,.json,.jsonl,text/csv,application/json"
                  onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                />
                <span className="btn btn--outline btn--sm">{d.chooseFile}</span>
                <span className="file-pick__name">{file?.name ?? d.noFile}</span>
              </label>
            </div>
          </>
        )}

        {error && (
          <p className="form-error" role="alert">
            {error}
          </p>
        )}
        <div className="dialog__actions">
          <button type="button" className="btn btn--outline btn--md" onClick={close}>
            {pl.common.cancel}
          </button>
          <button type="submit" className="btn btn--primary btn--md" disabled={pending}>
            {mode === "source" ? d.submit : d.importSubmit}
          </button>
        </div>
      </form>
    </dialog>
  );
}
