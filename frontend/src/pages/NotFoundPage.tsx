import { Link } from "react-router-dom";
import { pl } from "@/i18n/pl";

/** Unknown route. */
export function NotFoundPage() {
  return (
    <div className="page">
      <h1 className="title">{pl.notFound.title}</h1>
      <Link to="/sprawdz" className="back-link">
        {pl.notFound.back}
      </Link>
    </div>
  );
}
