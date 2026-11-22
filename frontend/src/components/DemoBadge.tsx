import type { FindingWithPost } from "@/api/types";
import { pl } from "@/i18n/pl";

/**
 * "dane syntetyczne" / "firma fikcyjna (demo)" next to fictional demo material. `compact`
 * (table rows) shows a single badge so it is never cut off; its tooltip gives both reasons.
 */
export function DemoBadge({
  finding,
  compact = false,
}: {
  finding: FindingWithPost;
  compact?: boolean;
}) {
  const synthetic = finding.post?.provenance?.synthetic === true;
  const fictionalFirm = finding.firm?.fictional === true;
  if (!synthetic && !fictionalFirm) return null;
  if (compact) {
    const hints = [
      synthetic ? pl.demoBadge.syntheticHint : "",
      fictionalFirm ? pl.demoBadge.fictionalFirmHint : "",
    ];
    return (
      <span className="demo-badge" title={hints.filter(Boolean).join(" ")} data-testid="demo-badge">
        {synthetic ? pl.demoBadge.synthetic : pl.demoBadge.fictionalFirm}
      </span>
    );
  }
  return (
    <>
      {synthetic && (
        <span className="demo-badge" title={pl.demoBadge.syntheticHint} data-testid="demo-badge">
          {pl.demoBadge.synthetic}
        </span>
      )}
      {fictionalFirm && (
        <span
          className="demo-badge"
          title={pl.demoBadge.fictionalFirmHint}
          data-testid="demo-badge"
        >
          {pl.demoBadge.fictionalFirm}
        </span>
      )}
    </>
  );
}
