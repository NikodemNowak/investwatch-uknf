import { useEffect, useState } from "react";

/** Current time, re-rendering every `ms` while `active`. */
export function useNow(active: boolean, ms = 100): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!active) return undefined;
    const timer = setInterval(() => setNow(Date.now()), ms);
    return () => clearInterval(timer);
  }, [active, ms]);
  return now;
}
