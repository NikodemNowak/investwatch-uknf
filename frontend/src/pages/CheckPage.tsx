import { useState } from "react";
import type { FormEvent } from "react";
import { EXAMPLE_URLS } from "@/config";
import { pl } from "@/i18n/pl";
import { useCheck } from "@/state/checkContext";
import { CheckResult } from "@/components/CheckResult";
import { SubmitMaterialDialog } from "@/components/SubmitMaterialDialog";

/** Accept "firma.pl/x" as https://firma.pl/x; null when it is not a web address. */
function normaliseUrl(input: string): string | null {
  const text = input.trim();
  if (!text) return null;
  const withScheme = /^[a-z][a-z0-9+.-]*:\/\//i.test(text) ? text : `https://${text}`;
  try {
    const url = new URL(withScheme);
    return url.protocol === "http:" || url.protocol === "https:" ? url.toString() : null;
  } catch {
    return null;
  }
}

/** "Sprawdź": paste a URL, watch the steps arrive live, read the verdict. */
export function CheckPage() {
  const { run, submit, submitting, submitError, clearSubmitError } = useCheck();
  const [value, setValue] = useState(run?.url ?? "");
  const [invalid, setInvalid] = useState(false);
  const [reporting, setReporting] = useState(false);

  const start = (raw: string) => {
    const url = normaliseUrl(raw);
    setInvalid(url === null);
    if (url) {
      setValue(url);
      submit(url);
    }
  };
  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    start(value);
  };

  const error = invalid ? pl.check.invalidUrl : submitError?.message;
  const offerForm = !invalid && Boolean(submitError?.submitInstead);
  return (
    <div className="page page--wide-gap">
      <section className="check-intro">
        <div>
          <h1 className="title">{pl.check.title}</h1>
          <p className="lead">{pl.check.lead}</p>
        </div>
        <form className="check-form" onSubmit={onSubmit} noValidate>
          <label htmlFor="url" className="sr-only">
            {pl.check.inputLabel}
          </label>
          <input
            id="url"
            className="url-input"
            type="url"
            inputMode="url"
            autoComplete="url"
            spellCheck={false}
            autoCapitalize="off"
            placeholder={pl.check.placeholder}
            value={value}
            onChange={(event) => setValue(event.target.value)}
            aria-invalid={invalid || undefined}
            aria-describedby={error ? "url-error" : undefined}
          />
          <button type="submit" className="btn btn--primary btn--check" disabled={submitting}>
            {pl.check.submit}
          </button>
        </form>
        {error && (
          <div id="url-error" className="form-error" role="alert">
            <p>{error}</p>
            {offerForm && (
              <button
                type="button"
                className="btn btn--primary btn--sm form-error__action"
                onClick={() => setReporting(true)}
              >
                {pl.submitMaterial.title}
              </button>
            )}
          </div>
        )}
        {!run && (
          <div className="examples">
            <span>{pl.check.examples}</span>
            {EXAMPLE_URLS.map((url) => (
              <button
                key={url}
                type="button"
                className="link-button"
                onClick={() => {
                  setValue(url);
                  start(url);
                }}
              >
                {url.replace(/^https?:\/\//, "")}
              </button>
            ))}
          </div>
        )}
      </section>
      {run && <CheckResult run={run} />}
      <SubmitMaterialDialog
        open={reporting}
        onClose={() => setReporting(false)}
        initialUrl={value}
        onSubmitted={clearSubmitError}
      />
    </div>
  );
}
