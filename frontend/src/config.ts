/** True when the UI runs on bundled fixtures instead of the backend (`VITE_USE_MOCKS=1`). */
export const USE_MOCKS: boolean = import.meta.env.VITE_USE_MOCKS === "1";

/** One-click examples under the "Sprawdź" form (fictional pages from `demo-sites/`). */
export const EXAMPLE_URLS: string[] = USE_MOCKS
  ? ["https://primefx24.example/pl/promo-zloto", "https://wislacapital.example/portfel-dywidendowy"]
  : [
      "http://demo-sites/hidden-risk.html",
      "http://demo-sites/tiny-font.html",
      "http://demo-sites/compliant.html",
    ];
