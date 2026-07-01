# ─────────────────────────────────────────────
# re_analyze.py
# 기존에 수집된 원본 기사(articles_*.json)들을
# 최신 analyzer.py 기준으로 처음부터 다시 분석하는 1회성 스크립트
# ─────────────────────────────────────────────

import json
import os
from analyzer import analyze_articles, save_analyzed_data, UNIFIED_FILE


def collect_all_raw_articles():
    """
    data 폴더의 모든 articles_*.json (원본 크롤링 데이터)을
    모아서 중복 제거 후 반환하는 함수
    """
    files = sorted([
        f for f in os.listdir('data')
        if f.startswith('articles_') and f.endswith('.json')
    ])

    if not files:
        print("❌ 원본 크롤링 파일이 없습니다.")
        return []

    print(f"📂 발견된 원본 파일: {files}")

    all_articles = []
    seen_titles = set()

    for filename in files:
        filepath = f"data/{filename}"
        with open(filepath, 'r', encoding='utf-8') as f:
            articles = json.load(f)

        added = 0
        for article in articles:
            if article['title'] not in seen_titles:
                seen_titles.add(article['title'])
                all_articles.append(article)
                added += 1

        print(f"  ✅ {filename}: {len(articles)}개 중 {added}개 신규 추가")

    print(f"\n📊 전체 원본 기사(중복제거): {len(all_articles)}개")
    return all_articles


def re_analyze():
    """
    기존 통합 파일을 초기화하고,
    모든 원본 기사를 최신 프롬프트 기준으로 재분석
    """
    # 1. 기존 통합 파일 삭제 (처음부터 다시 만들기 위해)
    if os.path.exists(UNIFIED_FILE):
        os.remove(UNIFIED_FILE)
        print(f"🗑️ 기존 통합 파일 삭제: {UNIFIED_FILE}")

    # 2. 원본 기사 전체 수집
    raw_articles = collect_all_raw_articles()
    if not raw_articles:
        return

    # 3. 최신 analyzer.py 기준으로 재분석
    print("\n🤖 최신 기준으로 전체 재분석 시작...")
    analyzed = analyze_articles(raw_articles)

    if not analyzed:
        print("❌ 분석 실패")
        return

    # 4. 통합 파일로 저장
    save_analyzed_data(analyzed)

    print(f"\n🎉 재분석 완료!")
    print(f"   최종 기사: {len(analyzed['articles'])}개")
    print(f"   최종 관계: {len(analyzed['relationships'])}개")


if __name__ == "__main__":
    re_analyze()