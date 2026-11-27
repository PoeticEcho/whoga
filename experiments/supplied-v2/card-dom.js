// Used by collection, pagination and the NAS diagnostics snapshot.
(() => {
  // CSS modules may render Component__field__hash or hash_field.
  const field = name => `:is([class*="__${name}"],[class$="_${name}"],[class*="_${name} "])`;
  const name = field('name'), summary = field('item-summary'), price = field('price');
  const group = field('text-more');
  function rows() {
    const panel = document.querySelector('#complex_detail');
    if (!panel) return [];
    const heading = [...panel.querySelectorAll('h1,h2,h3,h4,h5,h6,[role="heading"]')]
      .find(el => /^매물\s*[\d,]+/.test(el.textContent.trim()) && el.getClientRects().length);
    if (!heading) return [];
    const result = new Set();
    for (const item of panel.querySelectorAll(summary)) {
      if (item.closest('[data-sentry-component="ArticleCardSub"]') ||
          !(heading.compareDocumentPosition(item) & Node.DOCUMENT_POSITION_FOLLOWING)) continue;
      // Summary entries can themselves be <li>. Walk up to the enclosing card.
      for (let el = item.parentElement; el && el !== panel; el = el.parentElement) {
        if (el.contains(heading)) break;
        const isRow = el.matches('li,article,[role="listitem"]') ||
          el.parentElement.matches('ul,ol,[role="list"]') ||
          el.matches('[data-sentry-component="ArticleCard"]') &&
            !el.closest('li,article,[role="listitem"]');
        if (isRow && el.querySelector(name) && el.querySelector(price)) {
          if (el.getClientRects().length) result.add(el);
          break;
        }
      }
    }
    return [...result];
  }
  return {rows, name, summary, price, group};
})()
