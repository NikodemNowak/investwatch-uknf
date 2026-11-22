import { Link } from "react-router-dom";
import { Icon } from "@/components/Icon";
import { pl } from "@/i18n/pl";

/** Link back to a list (the review list by default). */
export function BackLink({
  to = "/zgloszenia",
  label = pl.finding.back,
}: {
  to?: string;
  label?: string;
}) {
  return (
    <Link to={to} className="back-link">
      <Icon name="back" size={16} />
      {label}
    </Link>
  );
}
