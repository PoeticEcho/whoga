// Firecrawl interact code: prepend the contents of scripts/listing_dom.js.
// The documented Firecrawl runtime supplies `page`. No natural-language agent
// navigation is needed. Reuse the same scrapeId for further bounded batches.
let previousTotal = null;
let previousCount = -1;
let bottomStalls = 0;
let fullReads = 0;
const progress = [];
let result;
for (let round = 0; round < 10; round++) {
  result = await page.evaluate(inspectListingPanel, false);
  progress.push({count: result.cardCount, declared: result.declaredCount,
    top: result.scrollTop, height: result.scrollHeight});
  if (/비정상적인 접근|접근이 제한|서비스 이용이 제한|자동입력 방지|로봇이 아닙니다/.test(result.text)) {
    result.reason = 'access-restricted';
    break;
  }
  if (result.declaredCount > 0) {
    if (previousTotal && previousTotal !== result.declaredCount) {
      result.reason = 'headline-changed';
      break;
    }
    previousTotal = result.declaredCount;
  }
  const full = result.sourceReady && result.declaredCount > 0
    && result.cardCount === result.declaredCount;
  fullReads = full ? fullReads + 1 : 0;
  if (fullReads >= 2) {
    result.complete = true;
    break;
  }
  // Unchanged counts while travelling down a long list are expected.
  bottomStalls = result.atBottom && result.cardCount === previousCount
    ? bottomStalls + 1 : 0;
  if (bottomStalls >= 5) {
    result.reason = 'no-more-cards-after-bottom-wait';
    break;
  }
  previousCount = result.cardCount;
  if (!full && result.sourceReady) await page.evaluate(inspectListingPanel, true);
  await page.waitForTimeout(1200);
}
console.log(JSON.stringify({...result, complete: Boolean(result?.complete), progress}));
