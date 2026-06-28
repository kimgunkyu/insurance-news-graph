# ─────────────────────────────────────────────
# scheduler.py
# 매일 자동으로 크롤링 + 분석을 실행하는 파일
# 이 파일을 실행해두면 매일 아침 8시에 자동으로 돌아가요
# ─────────────────────────────────────────────

import schedule          # 스케줄러 라이브러리
import time              # 시간 처리
from datetime import datetime
from crawler import crawl_all
from analyzer import analyze_articles, save_analyzed_data, load_latest_articles


def run_pipeline():
    """
    크롤링 → 분석 → 저장 전체 과정 실행
    """
    print(f"\n{'='*50}")
    print(f"🚀 자동 실행 시작: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*50}")

    # 1단계: 크롤링
    articles = crawl_all()
    if not articles:
        print("❌ 크롤링 실패")
        return

    # 2단계: AI 분석
    analyzed = analyze_articles(articles)
    if not analyzed:
        print("❌ 분석 실패")
        return

    # 3단계: 저장
    save_analyzed_data(analyzed)

    print(f"✅ 완료! 기사 {len(analyzed['articles'])}개 처리됨")
    print(f"{'='*50}\n")


# ── 매일 오전 8시 자동 실행 ──────────────────
schedule.every().day.at("08:00").do(run_pipeline)

if __name__ == "__main__":
    print("⏰ 스케줄러 시작!")
    print("매일 오전 8시에 자동으로 뉴스를 수집합니다.")
    print("종료하려면 Ctrl+C 를 누르세요.\n")

    # 시작하자마자 한 번 실행
    run_pipeline()

    # 이후 매일 8시에 자동 실행
    while True:
        schedule.run_pending()
        time.sleep(60)   # 1분마다 스케줄 체크