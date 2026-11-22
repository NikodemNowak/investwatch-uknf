import { pl } from "@/i18n/pl";

/** Same limit as `POST /api/submissions`. */
const MAX_SCREENSHOT_BYTES = 10 * 1024 * 1024;

/** Problem with the chosen screenshot (not a PNG, too large), or null when it can be sent. */
export function screenshotProblem(
  file: Pick<File, "name" | "type" | "size"> | null,
): string | null {
  if (!file) return null;
  if (file.type !== "image/png" && !file.name.toLowerCase().endsWith(".png")) {
    return pl.submitMaterial.pngOnly;
  }
  return file.size > MAX_SCREENSHOT_BYTES ? pl.submitMaterial.tooLarge : null;
}
