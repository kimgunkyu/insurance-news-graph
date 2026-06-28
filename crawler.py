# ─────────────────────────────────────────────
# crawler.py
# 보험저널 특정 탭에서 직접 기사를 가져오는 파일
# ─────────────────────────────────────────────

import requests                 # 인터넷 요청
from bs4 import BeautifulSoup   # HTML 파싱
from datetime import datetime   # 날짜 처리
import json                     # JSON 저장

# ── 크롤링할 보험저널 탭 목록 ─────────────────
# 나중에 탭 추가/삭제하고 싶으면 여기만 수정하면 돼요!
# ── 크롤링할 보험저널 탭 목록 ─────────────────
INSJOURNAL_SECTIONS = [
    {
        "name": "보험저널_정책",
        "url": "https://www.insjournal.co.kr/news/articleList.html?sc_sub_section_code=S2N1&view_type=sm",
    },
    {
        "name": "보험저널_손보",
        "url": "https://www.insjournal.co.kr/news/articleList.html?sc_sub_section_code=S2N3&view_type=sm",
    },
    {
        "name": "보험저널_GA",
        "url": "https://www.insjournal.co.kr/news/articleList.html?sc_sub_section_code=S2N16&view_type=sm",
    },
    {
        "name": "보험저널_상품",
        "url": "https://www.insjournal.co.kr/news/articleList.html?sc_sub_section_code=S2N17&view_type=sm",
    },
    {
        "name": "보험저널_경제종합",
        "url": "https://www.insjournal.co.kr/news/articleList.html?sc_sub_section_code=S2N20&view_type=sm",
    },
]

# ── 크롤링할 뉴스포트 탭 목록 ─────────────────
NEWSPORT_SECTIONS = [
    {
        "name": "뉴스포트_손해보험",
        "url": "https://www.newsport.co.kr/news/articleList.html?sc_sub_section_code=S2N2&view_type=sm",
    },
    {
        "name": "뉴스포트_GA",
        "url": "https://www.newsport.co.kr/news/articleList.html?sc_sub_section_code=S2N3&view_type=sm",
    },
    {
        "name": "뉴스포트_상품",
        "url": "https://www.newsport.co.kr/news/articleList.html?sc_section_code=S1N2&view_type=sm",
    },
    {
        "name": "뉴스포트_정책일반",
        "url": "https://www.newsport.co.kr/news/articleList.html?sc_sub_section_code=S2N4&view_type=sm",
    },
    {
        "name": "뉴스포트_상품정책",
        "url": "https://www.newsport.co.kr/news/articleList.html?sc_sub_section_code=S2N5&view_type=sm",
    },
]

# ── 전체 섹션 합치기 ───────────────────────────
ALL_SECTIONS = INSJOURNAL_SECTIONS + NEWSPORT_SECTIONS

# ── 탭별 최대 기사 수 ──────────────────────────
MAX_ARTICLES_PER_SECTION = 30


def get_articles(section, max_articles=MAX_ARTICLES_PER_SECTION):
    """
    보험저널 특정 탭에서 기사 목록을 가져오는 함수
    section: 탭 정보 {"name": ..., "url": ...}
    """

    headers = {
        # 브라우저인 척 하는 헤더 (없으면 막힐 수 있어요)
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    try:
        # 페이지 요청
        response = requests.get(section['url'], headers=headers, timeout=10)
        response.encoding = 'utf-8'

        # HTML 파싱
        soup = BeautifulSoup(response.text, 'html.parser')

        articles = []

        # 언론사별로 다른 HTML 구조 처리
        # 보험저널: ul.type1, 뉴스포트: ul.types
        if 'newsport' in section['url']:
            news_items = soup.select('ul.types li')[:max_articles]
        else:
            news_items = soup.select('ul.type1 li')[:max_articles]

        for item in news_items:
            try:
                # 제목 추출
                title_tag = item.select_one('.titles') or item.select_one('h4') or item.select_one('strong')
                if not title_tag:
                    continue
                title = title_tag.get_text(strip=True)

                # 링크 추출
                link_tag = item.select_one('a')
                if link_tag and link_tag.get('href'):
                    href = link_tag['href']
                    # 상대경로면 도메인 붙이기
                    if href.startswith('/'):
                        domain = section['url'].split('/news/')[0]
                        link = domain + href
                    else:
                        link = href
                else:
                    link = ""

                # 날짜 추출
                date_tag = item.select_one('.byline em') or item.select_one('.dated') or item.select_one('em')
                date = date_tag.get_text(strip=True) if date_tag else ""

                # 요약 추출
                desc_tag = item.select_one('.lead') or item.select_one('p')
                description = desc_tag.get_text(strip=True) if desc_tag else ""

                if not title:
                    continue

                articles.append({
                    "title": title,
                    "description": description,
                    "link": link,
                    "press": section['name'].split('_')[0],  # "보험저널" or "뉴스포트"
                    "date": date,
                    "section": section['name'],
                })

            except Exception:
                continue

        return articles

    except Exception as e:
        print(f"  ❌ 오류 ({section['name']}): {e}")
        return []


def crawl_all():
    """
    모든 탭에서 기사 수집 후 JSON 저장
    """
    print("📰 뉴스 수집 시작...")

    all_articles = []
    seen_titles = set()     # 중복 제거용

    for section in ALL_SECTIONS:
        print(f"  🔍 '{section['name']}' 수집 중...")
        articles = get_articles(section)

        for article in articles:
            if article['title'] not in seen_titles:
                seen_titles.add(article['title'])
                all_articles.append(article)

        print(f"     → {len(articles)}개 수집")

    print(f"\n✅ 총 {len(all_articles)}개 기사 수집 완료!")

    # 오늘 날짜로 JSON 저장
    today = datetime.now().strftime("%Y_%m_%d")
    filename = f"data/articles_{today}.json"

    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(all_articles, f, ensure_ascii=False, indent=2)

    print(f"💾 저장 완료: {filename}")
    return all_articles


if __name__ == "__main__":
    crawl_all()