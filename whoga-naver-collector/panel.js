(advance) => {
  const panels = [...document.querySelectorAll('[class*="ScrollBox"][class*="scroller"]')];
  const panel = panels.find(e => /매물\s*[\d,]+\s*개/.test(e.innerText));
  const body = document.body.innerText;
  const text = panel?.innerText || '';
  const total = text.match(/매물\s*([\d,]+)\s*개/);
  const nodes = panel ? [...panel.querySelectorAll('[data-sentry-component="ArticleCard"]')] : [];
  const rows = nodes.map(e => {
    // Retain only listing facts; never save brokerage names, phone numbers or descriptions.
    const raw = e.innerText;
    const name = raw.match(/(?:수성범어더블유|수성범어W)\s*\d+동/);
    const price = raw.match(/매매[^\n]+/);
    const property = raw.match(/오피스텔[^\n]+/);
    const confirmed = raw.match(/(?:현장|집주인)?확인매물\s*\d{4}\.\d{2}\.\d{2}/);
    const agencies = raw.match(/중개사\s*\d+곳/);
    const links = [...e.querySelectorAll('a[href]')].map(a => a.getAttribute('href'))
      .filter(h => /^\/articles\/\d+(?:\/|\?|$)/.test(h));
    const ids = [...new Set(links.map(h => h.match(/^\/articles\/(\d+)/)[1]))];
    return {text:[name?.[0],price?.[0],property?.[0],confirmed?.[0],agencies?.[0]].filter(Boolean).join('\n'),
      representativeArticleId: ids.length === 1 ? ids[0] : null,
      grouped: /매물목록 펼치기|중개사\s*\d+곳/.test(raw)};
  });
  const state = {declaredCount: total ? Number(total[1].replaceAll(',', '')) : null,
    panelFound: !!panel, rows, cardCount:nodes.length,
    sourceReady: !!panel && /수성범어더블유|수성범어W/.test(text) && /오피스텔/.test(text),
    scope: {sale:/^매매$/m.test(text),allAreas:/전체면적/.test(text),allBuildings:/전체동/.test(text)},
    viewport: {width:innerWidth,height:innerHeight},
    atBottom: !!panel && panel.scrollTop+panel.clientHeight >= panel.scrollHeight-8,
    scrollTop:panel?.scrollTop || 0,scrollHeight:panel?.scrollHeight || 0,
    loading: !!panel && /로딩중/.test(text),
    blocked:/비정상적인 접근|접근이 제한|서비스 이용이 제한|자동입력 방지|로봇이 아닙니다|verify you are human/i.test(body),
    notFound:/페이지를 찾을 수 없|잘못된 주소이거나/.test(body)};
  if (advance === 'next' && panel) panel.scrollBy({top:panel.clientHeight*.85,behavior:'instant'});
  if (advance === 'top' && panel) panel.scrollTo({top:0,behavior:'instant'});
  return state;
}
