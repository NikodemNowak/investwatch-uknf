import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter } from "react-router-dom";
// Inter, self-hosted (SIL OFL 1.1), variable weight, latin + latin-ext for Polish.
import "@fontsource-variable/inter";
import "@/styles/app.css";
import App from "@/App";
import { CheckProvider } from "@/state/CheckProvider";
import { ToastProvider } from "@/state/ToastProvider";
import { retryUnlessGone } from "@/lib/polling";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 30_000, retry: retryUnlessGone, refetchOnWindowFocus: false },
  },
});

const root = document.getElementById("root");
if (!root) throw new Error("Missing #root element");
createRoot(root).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <ToastProvider>
          <CheckProvider>
            <App />
          </CheckProvider>
        </ToastProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
