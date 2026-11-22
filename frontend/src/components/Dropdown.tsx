import { createPortal } from "react-dom";
import {
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
  type CSSProperties,
  type ReactNode,
} from "react";

interface DropdownProps {
  /** Content of the trigger button. */
  label: ReactNode;
  buttonClassName: string;
  /** Accessible name when the label alone is not enough (icon-only triggers). */
  ariaLabel?: string;
  /** Which edge of the trigger the panel lines up with. */
  align?: "left" | "right";
  panelClassName?: string;
  testId?: string;
  /** Panel content; call `close` after a choice. */
  children: (close: () => void) => ReactNode;
}

/**
 * Button with a floating panel. The panel is `position: fixed` in a portal, so it is never
 * clipped by a table with rounded corners; it closes on outside click, Escape, scroll and resize.
 */
export function Dropdown({
  label,
  buttonClassName,
  ariaLabel,
  align = "left",
  panelClassName = "",
  testId,
  children,
}: DropdownProps) {
  const [open, setOpen] = useState(false);
  const [style, setStyle] = useState<CSSProperties>({});
  const button = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLDivElement>(null);

  useLayoutEffect(() => {
    if (!open || !button.current) return;
    const rect = button.current.getBoundingClientRect();
    const below = window.innerHeight - rect.bottom;
    const vertical: CSSProperties =
      below < 320 && rect.top > below
        ? { bottom: window.innerHeight - rect.top + 6 }
        : { top: rect.bottom + 6 };
    setStyle(
      align === "right"
        ? { ...vertical, right: window.innerWidth - rect.right }
        : { ...vertical, left: rect.left },
    );
  }, [open, align]);

  useEffect(() => {
    if (!open) return;
    const close = () => setOpen(false);
    const onPointer = (event: MouseEvent) => {
      const target = event.target as Node;
      if (!panel.current?.contains(target) && !button.current?.contains(target)) close();
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        close();
        button.current?.focus();
      }
    };
    const onScroll = (event: Event) => {
      if (!panel.current?.contains(event.target as Node)) close();
    };
    document.addEventListener("mousedown", onPointer);
    document.addEventListener("keydown", onKey);
    window.addEventListener("scroll", onScroll, true);
    window.addEventListener("resize", close);
    return () => {
      document.removeEventListener("mousedown", onPointer);
      document.removeEventListener("keydown", onKey);
      window.removeEventListener("scroll", onScroll, true);
      window.removeEventListener("resize", close);
    };
  }, [open]);

  return (
    <>
      <button
        ref={button}
        type="button"
        className={buttonClassName}
        aria-label={ariaLabel}
        aria-haspopup="true"
        aria-expanded={open}
        data-testid={testId}
        onClick={(event) => {
          // Rows are links underneath: the menu must not open the finding.
          event.preventDefault();
          event.stopPropagation();
          setOpen((value) => !value);
        }}
      >
        {label}
      </button>
      {open &&
        // A portal: inside a row the panel would share the row's stacking context and the
        // next rows' menu buttons would paint over it.
        createPortal(
          <div ref={panel} className={`popover ${panelClassName}`} style={style}>
            {children(() => setOpen(false))}
          </div>,
          document.body,
        )}
    </>
  );
}
