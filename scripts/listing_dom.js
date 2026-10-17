function inspectListingPanel(advance = false) {
  const headline = [...document.querySelectorAll('h3')]
    .find(e => /매물\s*[\d,]+\s*개/.test(e.innerText));
  const candidates = [...document.querySelectorAll('[class*="ScrollBox"][class*="scroller"]')];
  let panel = candidates.find(e => headline && e.contains(headline));
  if (!panel && headline) {
    for (let e = headline.parentElement; e; e = e.parentElement) {
      if (e.clientHeight > 100 && e.scrollHeight > e.clientHeight + 60
          && ['auto', 'scroll'].includes(getComputedStyle(e).overflowY)) {
        panel = e;
        break;
      }
    }
  }
  panel ||= document.scrollingElement;
  const text = panel?.innerText || document.body.innerText;
  const total = text.match(/매물\s*([\d,]+)\s*개/);
  const result = {
    text,
    declaredCount: total ? Number(total[1].replaceAll(',', '')) : null,
    cardCount: (text.match(/(?:수성범어더블유|수성범어W)\s*\d+동/g) || []).length,
    scrollTop: panel?.scrollTop || 0,
    scrollHeight: panel?.scrollHeight || 0,
    clientHeight: panel?.clientHeight || 0,
    atBottom: Boolean(panel && panel.scrollTop + panel.clientHeight >= panel.scrollHeight - 8),
    sourceReady: Boolean(headline && /오피스텔/.test(text)),
  };
  // Only the listing panel moves. Map scrolling does not load more cards.
  if (advance && panel) panel.scrollTop = panel.scrollHeight;
  return result;
}
