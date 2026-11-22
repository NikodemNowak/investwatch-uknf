import { Link, NavLink } from "react-router-dom";
import { Icon } from "@/components/Icon";
import { pl } from "@/i18n/pl";
import { formatInt } from "@/lib/plural";

interface TopNavProps {
  /** Findings waiting for a decision; hidden while unknown. */
  openCount: number | undefined;
  live: boolean;
  mock: boolean;
}

const linkClass = ({ isActive }: { isActive: boolean }) =>
  isActive ? "nav__link nav__link--active" : "nav__link";

/** Top bar: brand, main tabs (active one underlined) and the live indicator. */
export function TopNav({ openCount, live, mock }: TopNavProps) {
  return (
    <header className="topbar">
      <div className="topbar__inner">
        <Link to="/sprawdz" className="brand">
          <span className="brand__mark">
            <Icon name="shield" size={16} color="#ffffff" />
          </span>
          <span className="brand__name">{pl.appName}</span>
        </Link>
        <nav aria-label={pl.nav.label} className="nav">
          <NavLink to="/sprawdz" className={linkClass}>
            {pl.nav.check}
          </NavLink>
          <NavLink to="/zgloszenia" className={linkClass}>
            {pl.nav.review}
            {openCount !== undefined && openCount > 0 && (
              <span className="count-pill">{formatInt(openCount)}</span>
            )}
          </NavLink>
          <NavLink to="/podmioty" className={linkClass}>
            {pl.nav.entities}
          </NavLink>
          <NavLink to="/monitoring" className={linkClass}>
            {pl.nav.monitoring}
          </NavLink>
          <NavLink to="/czulosc" className={linkClass}>
            {pl.nav.sensitivity}
          </NavLink>
          <NavLink to="/rejestr" className={linkClass}>
            {pl.nav.registry}
          </NavLink>
        </nav>
        <div className="live" title={mock ? pl.nav.mock : undefined}>
          <span className={live ? "dot" : "dot dot--off"} />
          {live ? pl.nav.live : pl.nav.offline}
        </div>
      </div>
    </header>
  );
}
