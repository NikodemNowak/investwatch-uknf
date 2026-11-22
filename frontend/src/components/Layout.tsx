import { useLayoutEffect } from "react";
import { Outlet, useLocation, useNavigationType } from "react-router-dom";
import { TopNav } from "@/components/TopNav";
import { USE_MOCKS } from "@/config";
import { useRealtimeBridge } from "@/hooks/useRealtimeBridge";
import { useSummary } from "@/hooks/useSummary";

/**
 * A new page starts at the top. Without this a link clicked low on one page ("Otwórz
 * zgłoszenie" under a long check result) opens the next page scrolled to the same offset.
 * Back/forward (POP) keep the browser's position; `#anchor` links scroll themselves.
 */
function useScrollToTopOnNavigate() {
  const { pathname, hash } = useLocation();
  const navigationType = useNavigationType();
  useLayoutEffect(() => {
    if (navigationType !== "POP" && !hash) window.scrollTo(0, 0);
    // Only a change of page counts; filters in the query string keep the position.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pathname]);
}

/** App shell: top bar over the routed page; wires realtime events to toasts. */
export function Layout() {
  const live = useRealtimeBridge();
  const summary = useSummary();
  useScrollToTopOnNavigate();
  return (
    <>
      <TopNav openCount={summary.data?.open_findings} live={live} mock={USE_MOCKS} />
      <main>
        <Outlet />
      </main>
    </>
  );
}
