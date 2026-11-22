// Layout facts for every element that carries its own text (RenderSnapshot).
// Evaluated in the page by `investwatch.render.capture` once per viewport; returns plain data
// matching `TextBlock`. It only measures: every judgement happens in the ai service.
(opts) => {
  const maxBlocks = opts.maxBlocks;
  const maxText = opts.maxText;
  const root = document.documentElement;
  const body = document.body;
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  const pageHeight = Math.max(root.scrollHeight, body ? body.scrollHeight : 0, vh, 1);
  const pageWidth = Math.max(root.clientWidth, vw);
  const SKIP = new Set([
    "SCRIPT", "STYLE", "NOSCRIPT", "TEMPLATE", "SVG", "HEAD", "IFRAME", "OBJECT", "CANVAS",
    "VIDEO", "AUDIO", "SELECT", "OPTION", "TEXTAREA",
  ]);
  const LEGAL = /legal|disclaimer|footnote|fine-?print|footer|stopka|przypis|nota-?prawna/i;
  const INLINE = /^(inline|contents|ruby)/;
  const HIDDEN_OVERFLOW = /hidden|clip/;

  const styles = new Map();
  const css = (el) => {
    let s = styles.get(el);
    if (!s) {
      s = getComputedStyle(el);
      styles.set(el, s);
    }
    return s;
  };

  const parseColor = (s) => {
    const m = s && s.match(/rgba?\(([^)]+)\)/);
    if (!m) return null;
    const p = m[1].split(/[\s,/]+/).filter(Boolean).map((v) =>
      v.endsWith("%") ? parseFloat(v) / 100 : parseFloat(v));
    if (p.length < 3 || p.some(Number.isNaN)) return null;
    return [p[0], p[1], p[2], p.length > 3 ? p[3] : 1];
  };
  const over = (top, bottom) => {
    const a = top[3];
    return [0, 1, 2].map((i) => top[i] * a + bottom[i] * (1 - a)).concat([1]);
  };
  const hex = (c) => "#" + c.slice(0, 3)
    .map((v) => Math.round(Math.min(255, Math.max(0, v))).toString(16).padStart(2, "0"))
    .join("");

  // Background actually painted behind an element: own colour, gradients (average of their
  // stops) and translucent layers composited over the ancestors, white canvas at the bottom.
  const backgrounds = new Map();
  const backgroundOf = (el) => {
    if (!el || el.nodeType !== 1) return [255, 255, 255, 1];
    if (backgrounds.has(el)) return backgrounds.get(el);
    const s = css(el);
    const own = parseColor(s.backgroundColor);
    let base;
    if (own && own[3] >= 0.999) base = own;
    else if (own && own[3] > 0) base = over(own, backgroundOf(el.parentElement));
    else base = backgroundOf(el.parentElement);
    const image = s.backgroundImage;
    if (image && image !== "none" && image.includes("gradient")) {
      const stops = [...image.matchAll(/rgba?\([^)]+\)/g)]
        .map((m) => parseColor(m[0]))
        .filter(Boolean);
      if (stops.length) {
        const avg = [0, 1, 2, 3].map((i) => stops.reduce((a, c) => a + c[i], 0) / stops.length);
        base = over(avg, base);
      }
    }
    backgrounds.set(el, base);
    return base;
  };

  const opacities = new Map();
  const opacityOf = (el) => {
    if (!el || el.nodeType !== 1) return 1;
    if (opacities.has(el)) return opacities.get(el);
    const v = parseFloat(css(el).opacity) * opacityOf(el.parentElement);
    opacities.set(el, v);
    return v;
  };

  // Collapsed: display:none, [hidden], aria-hidden, content-visibility:hidden or a zero-height
  // overflow:hidden accordion panel on the element or an ancestor; closed <details> below.
  const collapsedSelf = new Map();
  const collapsedOf = (el) => {
    if (!el || el === root || el === body) return false;
    if (collapsedSelf.has(el)) return collapsedSelf.get(el);
    const s = css(el);
    let v =
      s.display === "none" ||
      el.hidden ||
      el.getAttribute("aria-hidden") === "true" ||
      s.contentVisibility === "hidden" ||
      (HIDDEN_OVERFLOW.test(s.overflowY) && el.getBoundingClientRect().height < 2);
    v = v || collapsedOf(el.parentElement);
    collapsedSelf.set(el, v);
    return v;
  };
  const inClosedDetails = (el) => {
    const d = el.closest("details:not([open])");
    if (!d) return false;
    const summary = d.querySelector(":scope > summary");
    return !(summary && summary.contains(el));
  };

  const legalCache = new Map();
  const legalOf = (el) => {
    if (!el || el === root) return false;
    if (legalCache.has(el)) return legalCache.get(el);
    const tag = el.tagName;
    const cls = typeof el.className === "string" ? el.className : "";
    const v =
      tag === "FOOTER" || tag === "SMALL" || tag === "SUP" ||
      el.getAttribute("role") === "contentinfo" ||
      LEGAL.test(cls) || LEGAL.test(el.id || "") ||
      legalOf(el.parentElement);
    legalCache.set(el, v);
    return v;
  };

  const tagPath = (el) => {
    const parts = [];
    for (let a = el; a && a.nodeType === 1; a = a.parentElement) {
      let p = a.tagName.toLowerCase();
      const cls = typeof a.className === "string" ? a.className.trim().split(/\s+/)[0] : "";
      if (cls && /^[\w-]+$/.test(cls)) p += "." + cls;
      parts.push(p);
    }
    return parts.reverse().join(">");
  };

  const isInline = (el) => INLINE.test(css(el).display);

  // Own text plus inline descendants ("Kup <b>teraz</b>!"), but not nested blocks.
  const gather = (el) => {
    let out = "";
    for (const n of el.childNodes) {
      if (n.nodeType === 3) out += n.nodeValue;
      else if (n.nodeType === 1 && !SKIP.has(n.tagName)) {
        if (n.tagName === "BR") out += " ";
        else if (isInline(n) && css(n).display !== "none") out += gather(n);
        else out += " ";
      }
    }
    return out;
  };
  const hasOwnText = (el) => {
    for (const n of el.childNodes) if (n.nodeType === 3 && n.nodeValue.trim()) return true;
    return false;
  };

  const pageRect = (el) => {
    const r = el.getBoundingClientRect();
    return { x: r.left + scrollX, y: r.top + scrollY, w: r.width, h: r.height, r };
  };
  // Hidden text has no box of its own on screen: point at the closest painted ancestor
  // (for a closed <details> that is its summary line).
  const painted = (a) => typeof a.checkVisibility !== "function" ||
    a.checkVisibility({ contentVisibilityAuto: false, visibilityProperty: true });
  const visibleBox = (el) => {
    for (let a = el.parentElement; a && a !== root; a = a.parentElement) {
      const b = pageRect(a);
      if (b.w > 0 && b.h > 0 && painted(a)) return b;
    }
    return { x: 0, y: 0, w: 0, h: 0, r: null };
  };

  const clippedOf = (el, s, r) => {
    const block = !isInline(el);
    const overflowsX = block && el.scrollWidth > el.clientWidth + 1;
    const overflowsY = block && el.scrollHeight > el.clientHeight + 1;
    if (overflowsX && (s.textOverflow === "ellipsis" || HIDDEN_OVERFLOW.test(s.overflowX))) {
      return true;
    }
    if (overflowsY && HIDDEN_OVERFLOW.test(s.overflowY)) return true;
    if (overflowsX && r.left + el.scrollWidth > vw + 1) return true;
    if (r.right > vw + 1 || r.left < -1) return true;
    for (let a = el.parentElement; a && a !== body && a !== root; a = a.parentElement) {
      const as = css(a);
      if (!HIDDEN_OVERFLOW.test(as.overflowX) && !HIDDEN_OVERFLOW.test(as.overflowY)) continue;
      const ar = a.getBoundingClientRect();
      const width = overflowsX ? el.scrollWidth : r.width;
      if (r.left < ar.left - 1 || r.left + width > ar.right + 1) return true;
      if (r.top < ar.top - 1 || r.bottom > ar.bottom + 1) return true;
    }
    return false;
  };

  const out = [];
  const emitted = new Map(); // element -> style signature
  const walker = document.createTreeWalker(body || root, NodeFilter.SHOW_ELEMENT, {
    acceptNode: (n) => (SKIP.has(n.tagName) ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT),
  });
  for (let el = walker.currentNode; el && out.length < maxBlocks; el = walker.nextNode()) {
    if (el.nodeType !== 1 || !hasOwnText(el)) continue;
    const s = css(el);
    const signature = s.fontSize + "|" + s.color;
    if (isInline(el)) {
      // Inline text styled like its block is part of that block's text, not a block itself.
      let host = el.parentElement;
      while (host && host !== body && isInline(host)) host = host.parentElement;
      if (host && emitted.get(host) === signature) continue;
    }
    const raw = (isInline(el) ? el.textContent : gather(el)).replace(/\s+/g, " ").trim();
    if (!raw) continue;
    emitted.set(el, signature);

    const collapsed = collapsedOf(el) || inClosedDetails(el);
    const opacity = Math.max(0, Math.min(1, opacityOf(el)));
    const own = pageRect(el);
    const rendered =
      own.w > 0 && own.h > 0 &&
      s.visibility !== "hidden" && s.visibility !== "collapse" &&
      painted(el) &&
      opacity > 0.01 &&
      own.r.right > 0 && own.y + own.h > 0 && own.r.left < pageWidth &&
      !(own.w <= 2 && own.h <= 2);
    const visible = rendered && !collapsed;
    const box = rendered ? own : visibleBox(el);
    const bg = backgroundOf(el);
    const fg = parseColor(s.color) || [0, 0, 0, 1];
    out.push({
      el,
      block: {
        text: raw.length > maxText ? raw.slice(0, maxText) : raw,
        bbox: [box.x, box.y, box.w, box.h].map((v) => Math.round(v * 10) / 10),
        font_px: Math.round(parseFloat(s.fontSize) * 10) / 10 || 0,
        font_weight: parseInt(s.fontWeight, 10) || 400,
        color: hex(fg[3] < 1 ? over(fg, bg) : fg),
        background: hex(bg),
        opacity: Math.round(opacity * 1000) / 1000,
        visible,
        occluded: false,
        clipped: visible ? clippedOf(el, s, own.r) : false,
        in_footer: legalOf(el),
        in_collapsed: Boolean(collapsed),
        y_ratio: Math.round(Math.min(1, Math.max(0, box.y / pageHeight)) * 1000) / 1000,
        tag_path: tagPath(el),
      },
    });
  }

  // Occlusion: hit-test three points across the middle of each visible block, with the block
  // where a reader would see it (first screen at the top, otherwise scrolled to the centre).
  const maxScroll = Math.max(0, pageHeight - vh);
  for (const { el, block } of out) {
    if (!block.visible) continue;
    const [x, y, w, h] = block.bbox;
    const cy = y + h / 2;
    const top = cy < vh ? 0 : Math.min(maxScroll, Math.max(0, cy - vh / 2));
    if (Math.abs(scrollY - top) > 0.5) window.scrollTo({ top, left: 0, behavior: "instant" });
    let foreign = 0;
    let tested = 0;
    for (const fx of [0.2, 0.5, 0.8]) {
      const px = Math.min(vw - 1, Math.max(0, x + w * fx));
      const py = cy - scrollY;
      if (py < 0 || py >= vh) continue;
      const hit = document.elementFromPoint(px, py);
      if (!hit) continue;
      tested += 1;
      if (!(el.contains(hit) || hit.contains(el))) foreign += 1;
    }
    block.occluded = tested > 0 && foreign * 2 > tested;
  }
  window.scrollTo({ top: 0, left: 0, behavior: "instant" });

  return { blocks: out.map((o) => o.block), page_height: pageHeight };
}
