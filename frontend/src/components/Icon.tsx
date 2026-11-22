export type IconName =
  | "shield"
  | "check"
  | "cross"
  | "alert"
  | "spinner"
  | "download"
  | "search"
  | "plus"
  | "back"
  | "dash"
  | "close"
  | "play"
  | "chevron"
  | "more"
  | "calendar";

interface IconProps {
  name: IconName;
  size?: number;
  /** Stroke colour; defaults to the current text colour. */
  color?: string;
  strokeWidth?: number;
}

const DEFAULT_STROKE: Record<IconName, number> = {
  shield: 2.4,
  check: 3,
  cross: 3.4,
  alert: 2.6,
  spinner: 3,
  download: 2.2,
  search: 2.2,
  plus: 2.6,
  back: 2.4,
  dash: 3,
  close: 2.4,
  play: 2.2,
  chevron: 2.4,
  more: 3,
  calendar: 2.2,
};

/** Stroke icons drawn on a 24×24 grid, as in the approved mockups. */
export function Icon({ name, size = 16, color = "currentColor", strokeWidth }: IconProps) {
  const stroke = strokeWidth ?? DEFAULT_STROKE[name];
  const common = {
    "aria-hidden": true,
    width: size,
    height: size,
    viewBox: "0 0 24 24",
    fill: "none",
    strokeWidth: stroke,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    focusable: false,
  };
  switch (name) {
    case "spinner":
      return (
        <svg {...common} className="spin">
          <circle cx="12" cy="12" r="9" stroke="#bfdbfe" />
          <path d="M12 3a9 9 0 0 1 9 9" stroke="#1d4ed8" />
        </svg>
      );
    case "shield":
      return (
        <svg {...common} stroke={color}>
          <path d="M12 3l8 3v6c0 4.5-3.4 8.3-8 9-4.6-.7-8-4.5-8-9V6l8-3z" />
        </svg>
      );
    case "check":
      return (
        <svg {...common} stroke={color}>
          <path d="M5 12.5l4.5 4.5L19 7.5" />
        </svg>
      );
    case "cross":
    case "close":
      return (
        <svg {...common} stroke={color}>
          <path d="M6 6l12 12" />
          <path d="M18 6L6 18" />
        </svg>
      );
    case "play":
      return (
        <svg {...common} stroke={color}>
          <path d="M8 5.5v13l10.5-6.5L8 5.5z" />
        </svg>
      );
    case "alert":
      return (
        <svg {...common} stroke={color}>
          <path d="M12 7v6" />
          <path d="M12 17h.01" />
        </svg>
      );
    case "download":
      return (
        <svg {...common} stroke={color}>
          <path d="M12 4v11" />
          <path d="M7 10l5 5 5-5" />
          <path d="M5 20h14" />
        </svg>
      );
    case "search":
      return (
        <svg {...common} stroke={color}>
          <circle cx="11" cy="11" r="7" />
          <path d="M21 21l-4.3-4.3" />
        </svg>
      );
    case "plus":
      return (
        <svg {...common} stroke={color}>
          <path d="M12 5v14" />
          <path d="M5 12h14" />
        </svg>
      );
    case "back":
      return (
        <svg {...common} stroke={color}>
          <path d="M15 18l-6-6 6-6" />
        </svg>
      );
    case "chevron":
      return (
        <svg {...common} stroke={color}>
          <path d="M6 9l6 6 6-6" />
        </svg>
      );
    case "more":
      return (
        <svg {...common} stroke={color}>
          <path d="M5 12h.01" />
          <path d="M12 12h.01" />
          <path d="M19 12h.01" />
        </svg>
      );
    case "calendar":
      return (
        <svg {...common} stroke={color}>
          <rect x="4" y="5" width="16" height="15" rx="2" />
          <path d="M4 10h16" />
          <path d="M9 3v4" />
          <path d="M15 3v4" />
        </svg>
      );
    case "dash":
      return (
        <svg {...common} stroke={color}>
          <path d="M7 12h10" />
        </svg>
      );
  }
}
