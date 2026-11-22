import { useLayoutEffect, useRef } from "react";
import { pl } from "@/i18n/pl";
import type { ShotBox } from "@/lib/evidence";

interface PageThumbnailProps {
  url: string;
  pageWidth: number;
  pageHeight: number;
  boxes: ShotBox[];
  active: ShotBox | undefined;
  /** Thumbnail width (panel px). */
  width: number;
  maxHeight: number;
}

/** Whole page in miniature with every evidence box: shows where on the page the evidence is. */
export function PageThumbnail({
  url,
  pageWidth,
  pageHeight,
  boxes,
  active,
  width,
  maxHeight,
}: PageThumbnailProps) {
  const scroller = useRef<HTMLDivElement>(null);
  const zoom = width / pageWidth;
  const activeY = active ? (active.bbox[1] + active.bbox[3] / 2) * zoom : 0;

  // A long page (phone) does not fit: keep the selected box in the middle.
  useLayoutEffect(() => {
    scroller.current?.scrollTo({ top: Math.max(0, activeY - maxHeight / 2), behavior: "smooth" });
  }, [activeY, maxHeight]);

  return (
    <div
      ref={scroller}
      className="shot-thumb"
      style={{ width: `${width}px`, maxHeight: `${maxHeight}px` }}
      aria-label={pl.finding.whereOnPage}
    >
      <div className="shot-thumb__page" style={{ height: `${pageHeight * zoom}px` }}>
        <img src={url} alt={pl.finding.whereOnPage} />
        {boxes.map((box) => {
          const [x, y, w, h] = box.bbox;
          return (
            <span
              key={box.key}
              className={[
                "shot-thumb__box",
                box.soft ? "shot-thumb__box--soft" : "",
                box === active ? "shot-thumb__box--active" : "",
              ].join(" ")}
              style={{
                left: `${x * zoom - 2}px`,
                top: `${y * zoom - 2}px`,
                width: `${w * zoom + 4}px`,
                height: `${Math.max(h * zoom, 2) + 4}px`,
              }}
            />
          );
        })}
      </div>
    </div>
  );
}
