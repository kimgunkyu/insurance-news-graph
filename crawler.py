# ─────────────────────────────────────────────
# crawler.py
# 구글 뉴스 RSS로 보험 기사를 가져오는 파일
# 구글 뉴스는 GitHub Actions에서도 차단 없이 작동해요
# ─────────────────────────────────────────────

import requests                 # 인터넷 요청
from bs4 import BeautifulSoup   # XML 파싱
from datetime import datetime   # 날짜 처리
import json                     # JSON 저장
import os                       # 폴더 생성

# ── 보험 전문 언론사 RSS 목록 ─────────────────
# 구글 뉴스에서 언론사별로 최신 기사를 가져와요
# 언론사 추가하고 싶으면 여기에만 추가하면 돼요!
INSURANCE_MEDIA = [
    {
        "name": "보험저널",
        "url": "https://news.google.com/rss/search?q=site:insjournal.co.kr+보험&hl=ko&gl=KR&ceid=KR:ko&sort=date",
    },
    {
        "name": "뉴스포트",
        "url": "https://news.google.com/rss/search?q=site:newsport.co.kr+보험&hl=ko&gl=KR&ceid=KR:ko&sort=date",
    },
]

# ── 언론사별 최대 기사 수 ──────────────────────
MAX_ARTICLES_PER_MEDIA = 20


def get_articles(media, max_articles=MAX_ARTICLES_PER_MEDIA):
    """
    구글 뉴스 RSS에서 기사를 가져오는 함수
    media: 언론사 정보 {"name": ..., "url": ...}
    """

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }

    try:
        # RSS 피드 요청
        response = requests.get(media['url'], headers=headers, timeout=15)
        response.encoding = 'utf-8'

        # XML 파싱
        soup = BeautifulSoup(response.content, 'xml')
        items = soup.find_all('item')[:max_articles]

        articles = []
        for item in items:
            try:
                # 제목 추출
                title = item.find('title').get_text(strip=True) if item.find('title') else ""
                # 본문 요약 추출
                description = item.find('description').get_text(strip=True) if item.find('description') else ""
                # 링크 추출
                link = item.find('link').get_text(strip=True) if item.find('link') else ""
                # 날짜 추출
                pub_date = item.find('pubDate').get_text(strip=True) if item.find('pubDate') else ""

                if not title:
                    continue

                articles.append({
                    "title": title,
                    "description": description,
                    "link": link,
                    "press": media['name'],
                    "date": pub_date,
                })

            except Exception:
                continue

        return articles

    except Exception as e:
        print(f"  ❌ 오류 ({media['name']}): {e}")
        return []


def crawl_all():
    """
    모든 언론사에서 기사 수집 후 JSON 저장
    """
    print("📰 뉴스 수집 시작...")

    all_articles = []
    seen_titles = set()     # 중복 제거용

    for media in INSURANCE_MEDIA:
        print(f"  🔍 '{media['name']}' 수집 중...")
        articles = get_articles(media)

        for article in articles:
            if article['title'] not in seen_titles:
                seen_titles.add(article['title'])
                all_articles.append(article)

        print(f"     → {len(articles)}개 수집")

    print(f"\n✅ 총 {len(all_articles)}개 기사 수집 완료!")

    # data 폴더 없으면 자동 생성
    os.makedirs("data", exist_ok=True)

    # 오늘 날짜로 JSON 저장
    today = datetime.now().strftime("%Y_%m_%d")
    filename = f"data/articles_{today}.json"

    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(all_articles, f, ensure_ascii=False, indent=2)

    print(f"💾 저장 완료: {filename}")
    return all_articles


if __name__ == "__main__":
    crawl_all()