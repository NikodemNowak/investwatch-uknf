import { useLayoutEffect, useRef } from "react";
import type { BBox } from "@/api/types";
import { layoutMarkers } from "@/lib/evidence";
import type { MarkerSpot, Rect, ShotBox } from "@/lib/evidence";

interface EvidenceMagnifierProps {
  url: string;
  pageWidth: number;
  pageHeight: number;
  boxes: ShotBox[];
  active: ShotBox | undefined;
  /** Region to bring into view (the text of the selected evidence), or null for the page top. */
  focus: BBox | null;
  /** Panel px per page CSS px. */
  zoom: number;
  /** Visible width and height of the view (panel px). */
  width: number;
  height: number;
  /** "Powiększenie 1,6×", shown over the view. */
  label: string | null;
  alt: string;
}

/** Box outline drawn this far outside the evidence (panel px). */
const BOX_OUTSET = 3;
/** Space kept left of the focused text when panning to it (panel px). */
const LEAD = 28;

/** Scrollable screenshot at `zoom`, panned to the selected evidence, with boxes and markers. */
export function EvidenceMagnifier({
  url,
  pageWidth,
  pageHeight,
  boxes,
  active,
  focus,
  zoom,
  width,
  height,
  label,
  alt,
}: EvidenceMagnifierProps) {
  const scroller = useRef<HTMLDivElement>(null);
  const page = { x: 0, y: 0, w: pageWidth * zoom, h: pageHeight * zoom };
  const clamp = (v: number, max: number) => Math.round(Math.max(0, Math.min(v, Math.max(0, max))));
  const left = focus ? clamp(focus[0] * zoom - LEAD, page.w - width) : 0;
  const top = focus ? clamp((focus[1] + focus[3] / 2) * zoom - height / 2, page.h - height) : 0;

  // Text longer than the view continues to the right: a fade says "scroll for more".
  const overflows = focus !== null && (focus[0] + focus[2]) * zoom > left + width;

  useLayoutEffect(() => {
    scroller.current?.scrollTo({ left, top, behavior: "smooth" });
  }, [left, top, zoom]);

  // The selected box is drawn around its text only; the active box picks its marker spot first.
  const ordered = active ? [active, ...boxes.filter((b) => b !== active)] : boxes;
  const rects: Rect[] = ordered.map((box) => {
    const [x, y, w, h] = box === active && focus ? focus : box.bbox;
    const l = Math.max(0, x * zoom - BOX_OUTSET);
    const t = Math.max(0, y * zoom - BOX_OUTSET);
    const r = Math.min(page.w, (x + w) * zoom + BOX_OUTSET);
    const b = Math.min(page.h, (y + h) * zoom + BOX_OUTSET);
    return { x: l, y: t, w: r - l, h: b - t };
  });
  const markers: MarkerSpot[] = layoutMarkers(
    rects,
    ordered.map((box) => box.numbers.length),
    page,
    { x: left, y: top, w: Math.min(width, page.w), h: height },
  );

  return (
    <div className={overflows ? "shot-zoom shot-zoom--more" : "shot-zoom"}>
      {label && <span className="shot-zoom__label">{label}</span>}
      <div className="shot__viewport" ref={scroller} style={{ height: `${height}px` }}>
        <div
          className="shot__page"
          style={{
            width: `${page.w}px`,
            marginLeft: `${Math.max(0, (width - page.w) / 2)}px`,
          }}
        >
          <img src={url} alt={alt} />
          {ordered.map((box, i) => {
            const rect = rects[i];
            return (
              rect && (
                <span
                  key={box.key}
                  className={[
                    "shot__box",
                    box.soft ? "shot__box--soft" : "",
                    box === active ? "shot__box--active" : "",
                  ].join(" ")}
                  style={{
                    left: `${rect.x}px`,
                    top: `${rect.y}px`,
                    width: `${rect.w}px`,
                    height: `${rect.h}px`,
                  }}
                />
              )
            );
          })}
          {ordered.map((box, i) => {
            const marker = markers[i];
            return (
              marker && (
                <span
                  key={`m-${box.key}`}
                  className={[
                    "shot__markers",
                    `shot__markers--${marker.direction}`,
                    box.soft ? "shot__markers--soft" : "",
                  ].join(" ")}
                  style={{ left: `${marker.x}px`, top: `${marker.y}px` }}
                >
                  {box.numbers.map((n) => (
                    <span key={n} className="shot__badge">
                      {n}
                    </span>
                  ))}
                </span>
              )
            );
          })}
        </div>
      </div>
    </div>
  );
}
