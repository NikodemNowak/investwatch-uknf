import { Icon } from "@/components/Icon";
import { pl } from "@/i18n/pl";

/** Outline download button for a server-rendered PDF; disabled when there is no server. */
export function PdfLink({
  href,
  label,
  size = "md",
}: {
  href: string | null;
  label: string;
  /** `lg` matches the 48 px decision buttons of a finding. */
  size?: "md" | "lg";
}) {
  const cls = `btn btn--outline ${size === "lg" ? "btn--pad20" : "btn--md"}`;
  if (!href) {
    return (
      <button type="button" className={cls} disabled title={pl.pdf.unavailable}>
        <Icon name="download" size={16} />
        {label}
      </button>
    );
  }
  return (
    <a className={cls} href={href} download>
      <Icon name="download" size={16} />
      {label}
    </a>
  );
}
