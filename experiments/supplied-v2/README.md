# 사용자 제공 v2 비교 실험

2026-10-20 첨부 ZIP의 collector.py와 requirements.txt, target-url.txt를 그대로 분리 보관한다. 운영 WhoGa 수집기나 데이터 스키마를 교체하지 않는다.

원본 collector.py SHA256: e99d8f5434674ecbf410bcb3262bc3fe09e9fcd3e7fd0555ddfc3a0a40842b54

원본 전체 패키지의 오프라인 테스트 10개를 로컬에서 통과했다. 원본 매물 전체 자료는 공개 저장소에 추가하지 않았다.

.github/workflows/map_supplied_probe.yml은 정확한 기본 지도 URL에 대해 Ubuntu headless 및 Xvfb headed를 순차 시험한다. 3개 표본이 통과할 때만 전체 수집한다. 결과는 7일 artifact이며 운영 최신 데이터나 Pages를 변경하지 않는다.

원본 코드의 스키마는 cards/articles, 기존 앱은 schemaVersion 2/items이므로 직접 대체할 수 없다. 대표 카드 수와 개별 중개 등록 수는 다른 단위다.

전체 검토 및 실제 실행 결과: ../../ACTIONS_REVIEW.md
