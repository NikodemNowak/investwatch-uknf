import type { BBox } from "@/api/types";

interface ShotCropProps {
  url: string;
  /** Page width in CSS px (the screenshot is drawn this wide at zoom 1). */
  pageWidth: number;
  region: BBox;
  zoom: number;
  /** Widest the crop may be (panel px); the rest is cut off. */
  maxWidth?: number;
  alt: string;
}

/** A region of the screenshot drawn at `zoom` (1 = real CSS size). */
export function ShotCrop({ url, pageWidth, region, zoom, maxWidth, alt }: ShotCropProps) {
  const [x, y, w, h] = region;
  const width = Math.min(w * zoom, maxWidth ?? Infinity);
  return (
    <span className="shot-crop" style={{ width: `${width}px`, height: `${h * zoom}px` }}>
      <img
        src={url}
        alt={alt}
        style={{ width: `${pageWidth * zoom}px`, left: `${-x * zoom}px`, top: `${-y * zoom}px` }}
      />
    </span>
  );
}
