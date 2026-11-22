// Click an obvious "accept" button inside a cookie / consent banner so it does not cover the
// page in screenshots. Returns true when something was clicked. Deliberately conservative: the
// button must sit inside an element whose id/class/aria-label says cookie/consent.
() => {
  const scope = /cookie|consent|gdpr|rodo|cmp|privacy|prywatno|ciasteczk/i;
  const accept = new RegExp(
    "^\\s*(akceptuj|zaakceptuj|akceptuję|zgadzam|zgoda|rozumiem|ok\\b|przejdź|accept|agree|" +
      "allow|got it|zamknij)",
    "i",
  );
  const buttons = document.querySelectorAll(
    'button, a[role="button"], [type="button"], [type="submit"]',
  );
  for (const b of buttons) {
    let inBanner = false;
    for (let a = b, i = 0; a && i < 8; i++, a = a.parentElement) {
      const cls = typeof a.className === "string" ? a.className : "";
      const label = a.getAttribute ? a.getAttribute("aria-label") || "" : "";
      if (scope.test(`${a.id || ""} ${cls} ${label}`)) {
        inBanner = true;
        break;
      }
    }
    if (inBanner && accept.test(b.innerText || b.value || "")) {
      b.click();
      return true;
    }
  }
  return false;
}
