import { useEffect, useLayoutEffect, useRef, useState } from "react";
import type { Post, RenderSnapshot, Viewport } from "@/api/types";
import { EvidenceMagnifier } from "@/components/EvidenceMagnifier";
import { PageThumbnail } from "@/components/PageThumbnail";
import { QuotedText } from "@/components/QuotedText";
import { ShotCrop } from "@/components/ShotCrop";
import { pl } from "@/i18n/pl";
import {
  VIEWPORT_WIDTH,
  blockAt,
  clampBox,
  focusView,
  magnifierZoom,
  overlapRatio,
  sampleBlock,
  textBox,
} from "@/lib/evidence";
import type { ShotBox } from "@/lib/evidence";
import { VIEWPORTS } from "@/lib/enums";
import { formatContrast, formatNumber } from "@/lib/format";
import type { Problem, WarningMeasures } from "@/lib/problems";

interface ScreenshotPanelProps {
  post: Post;
  problems: Problem[];
  activeRuleId: string | null;
  viewport: Viewport;
  onViewport: (viewport: Viewport) => void;
  render: RenderSnapshot | null | undefined;
  shotUrl: (viewport: Viewport) => string | null;
  measures: WarningMeasures;
}

/** Tallest whole-page view, when nothing is selected (panel px). */
const MAX_VIEW_HEIGHT = 600;
/** Largest magnification of the screenshot's own pixels. */
const MAX_UPSCALE = 3;
/** Thumbnail width and tallest thumbnail (panel px). */
const THUMB_WIDTH = 176;
const THUMB_MAX_HEIGHT = 220;
/** Magnified view: context above and below the text, and its height limits (panel px). */
const ZOOM_PAD_Y = 48;
const ZOOM_MIN_HEIGHT = 120;
const ZOOM_MAX_HEIGHT = 360;
/** Padding of the overview row (panel px), see `.shot__overview`. */
const OVERVIEW_PAD = 16;

let canvas: HTMLCanvasElement | undefined;

/** Width of `text` set in a generic sans-serif at `fontPx` (approximates the page font). */
function measureText(text: string, fontPx: number, weight = 400): number {
  canvas ??= document.createElement("canvas");
  const context = canvas.getContext("2d");
  if (!context) return text.length * fontPx * 0.5;
  context.font = `${weight} ${fontPx}px Arial, Helvetica, sans-serif`;
  return context.measureText(text).width;
}

/** Evidence regions of the numbered problems in one viewport; near-identical regions merge. */
function boxesFor(
  problems: Problem[],
  viewport: Viewport,
  pageWidth: number,
  pageHeight: number,
): ShotBox[] {
  const boxes: ShotBox[] = [];
  problems.forEach((problem, index) => {
    for (const evidence of problem.rule.evidence) {
      if (!evidence.bbox || evidence.viewport !== viewport) continue;
      const bbox = clampBox(evidence.bbox, pageWidth, pageHeight);
      if (bbox[2] <= 0 || bbox[3] <= 0) continue;
      let box = boxes.find((b) => overlapRatio(b.bbox, bbox) > 0.6);
      if (!box) {
        box = {
          key: bbox.map((v) => Math.round(v)).join(","),
          bbox,
          numbers: [],
          ruleIds: [],
          soft: true,
        };
        boxes.push(box);
      }
      if (!box.numbers.includes(index + 1)) box.numbers.push(index + 1);
      if (!box.ruleIds.includes(problem.rule.rule_id)) box.ruleIds.push(problem.rule.rule_id);
      box.soft &&= !problem.severe;
    }
  });
  return boxes;
}

/** "Zrzut strony": real screenshot per device with red boxes over the evidence. */
export function ScreenshotPanel({
  post,
  problems,
  activeRuleId,
  viewport,
  onViewport,
  render,
  shotUrl,
  measures,
}: ScreenshotPanelProps) {
  const available = VIEWPORTS.filter((v) => shotUrl(v) !== null);
  const url = shotUrl(viewport);
  const [natural, setNatural] = useState<{ w: number; h: number } | null>(null);
  const [failed, setFailed] = useState(false);
  const [panelWidth, setPanelWidth] = useState(0);
  const frame = useRef<HTMLDivElement>(null);

  // Natural size first: every box is drawn in the image's own coordinates.
  useEffect(() => {
    setNatural(null);
    setFailed(false);
    if (!url) return;
    const image = new Image();
    image.onload = () => setNatural({ w: image.naturalWidth, h: image.naturalHeight });
    image.onerror = () => setFailed(true);
    image.src = url;
    return () => {
      image.onload = null;
      image.onerror = null;
    };
  }, [url]);

  // The zoom depends on the panel width, so follow it.
  useLayoutEffect(() => {
    const container = frame.current;
    if (!container) return;
    setPanelWidth(container.clientWidth);
    const observer = new ResizeObserver(([entry]) => {
      if (entry) setPanelWidth(entry.contentRect.width);
    });
    observer.observe(container);
    return () => observer.disconnect();
  }, [url, failed]);

  const cssWidth = VIEWPORT_WIDTH[viewport];
  const scale = natural ? natural.w / cssWidth : 1;
  const cssHeight = natural ? natural.h / scale : (render?.page_height[viewport] ?? 0);
  const boxes = natural && cssHeight ? boxesFor(problems, viewport, cssWidth, cssHeight) : [];
  const active =
    boxes.find((box) => activeRuleId && box.ruleIds.includes(activeRuleId)) ??
    boxes.find((box) => !box.soft) ??
    boxes[0];

  // The selected evidence: its text block (font size, text) and the region of the text itself.
  const blocks = render?.viewports[viewport] ?? [];
  const block = active ? blockAt(blocks, active.bbox) : undefined;
  const fontPx = block?.font_px;
  const focus = active
    ? clampBox(
        block
          ? textBox(active.bbox, block.text, block.font_px, (t, px) =>
              measureText(t, px, block.font_weight),
            )
          : active.bbox,
        cssWidth,
        cssHeight,
      )
    : null;
  const zoom =
    focus && panelWidth
      ? magnifierZoom(fontPx, focus[2], panelWidth - 2 * 28, MAX_UPSCALE * scale)
      : panelWidth && cssHeight
        ? focusView(null, cssWidth, cssHeight, panelWidth, MAX_VIEW_HEIGHT).zoom
        : 0;
  const zoomHeight = focus
    ? Math.round(
        Math.min(
          ZOOM_MAX_HEIGHT,
          cssHeight * zoom,
          Math.max(ZOOM_MIN_HEIGHT, focus[3] * zoom + 2 * ZOOM_PAD_Y),
        ),
      )
    : Math.round(Math.min(MAX_VIEW_HEIGHT, cssHeight * zoom));

  // "This is normal text": a line of the page's main font at real size, next to the thumbnail.
  const sample = focus ? sampleBlock(blocks, measures.pagePx ?? undefined) : undefined;
  const sampleRegion = sample
    ? clampBox(
        textBox(
          [
            sample.bbox[0],
            sample.bbox[1],
            sample.bbox[2],
            Math.min(sample.bbox[3], sample.font_px * 1.5),
          ],
          sample.text.split("\n")[0] ?? "",
          sample.font_px,
          (t, px) => measureText(t, px, sample.font_weight),
        ),
        cssWidth,
        cssHeight,
      )
    : null;
  const sideWidth = panelWidth - THUMB_WIDTH - 3 * OVERVIEW_PAD;

  const items: { label: string; value: string; bad: boolean }[] = [];
  if (measures.warningPx !== undefined)
    items.push({
      label: pl.finding.measures.warning,
      value: `${formatNumber(measures.warningPx)} px`,
      bad: measures.fontFailed,
    });
  if (measures.pagePx !== undefined)
    items.push({
      label: pl.finding.measures.page,
      value: `${formatNumber(measures.pagePx)} px`,
      bad: false,
    });
  if (measures.contrast !== undefined)
    items.push({
      label: pl.finding.measures.contrast,
      value: formatContrast(measures.contrast, true),
      bad: measures.contrastFailed,
    });

  const hasShots = available.length > 0;
  return (
    <section id="zrzut" aria-labelledby="shot-h" className="stack-12">
      <div className="section-head">
        <h2 id="shot-h" className="h2">
          {hasShots ? pl.finding.screenshot : pl.finding.content}
        </h2>
        {hasShots && (
          <div role="tablist" className="seg seg--sm">
            {VIEWPORTS.map((v) => (
              <button
                key={v}
                type="button"
                role="tab"
                aria-selected={viewport === v}
                className="seg__tab"
                disabled={!available.includes(v)}
                onClick={() => onViewport(v)}
              >
                {pl.viewports[v]}
              </button>
            ))}
          </div>
        )}
      </div>
      <figure className="shot">
        {hasShots ? (
          url && !failed ? (
            <div ref={frame}>
              {natural && zoom > 0 && (
                <>
                  {focus && (
                    <div className="shot__overview">
                      <PageThumbnail
                        url={url}
                        pageWidth={cssWidth}
                        pageHeight={cssHeight}
                        boxes={boxes}
                        active={active}
                        width={THUMB_WIDTH}
                        maxHeight={THUMB_MAX_HEIGHT}
                      />
                      <div className="shot__compare">
                        <div className="shot__compare-label">{pl.finding.whereOnPage}</div>
                        <p className="shot__compare-text">{pl.finding.whereHint}</p>
                        {sample && sampleRegion && (
                          <>
                            <div className="shot__compare-label">
                              {pl.finding.pageSample(formatNumber(sample.font_px))}
                            </div>
                            <ShotCrop
                              url={url}
                              pageWidth={cssWidth}
                              region={sampleRegion}
                              zoom={1}
                              maxWidth={Math.max(80, sideWidth)}
                              alt={sample.text}
                            />
                          </>
                        )}
                      </div>
                    </div>
                  )}
                  <EvidenceMagnifier
                    url={url}
                    pageWidth={cssWidth}
                    pageHeight={cssHeight}
                    boxes={boxes}
                    active={active}
                    focus={focus}
                    zoom={zoom}
                    width={panelWidth}
                    height={zoomHeight}
                    label={focus ? pl.finding.zoomLabel(formatNumber(zoom), zoom > 1) : null}
                    alt={`${pl.finding.screenshot}: ${pl.viewports[viewport]}`}
                  />
                </>
              )}
            </div>
          ) : (
            <div className="shot__empty">{failed ? pl.finding.shotError : pl.finding.noShot}</div>
          )
        ) : (
          <QuotedText
            text={post.text}
            quotes={problems.flatMap((p) => p.rule.evidence.map((e) => e.quote ?? ""))}
          />
        )}
        {items.length > 0 && (
          <figcaption
            className="measures"
            style={{ gridTemplateColumns: `repeat(${Math.max(3, items.length)}, minmax(0, 1fr))` }}
          >
            {items.map((item) => (
              <div key={item.label}>
                <div className="measure__label">{item.label}</div>
                <div className={item.bad ? "measure__value measure__value--bad" : "measure__value"}>
                  {item.value}
                </div>
              </div>
            ))}
          </figcaption>
        )}
      </figure>
    </section>
  );
}
