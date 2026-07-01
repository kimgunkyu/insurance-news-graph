# ─────────────────────────────────────────────
# crawler.py
# 보험저널 + 한국보험신문 사이트에 직접 접근해서
# 원하는 카테고리의 최신 기사를 정확히 수집하는 파일
# (Render 서버에서 실행 - 두 사이트 모두 Render IP 접근 허용 확인함)
#
# ⚠️ 참고: 두 사이트 모두 페이지네이션/날짜검색 URL 파라미터가
# CDN 캐시 문제로 신뢰할 수 없어서, "최신 20개 목록 + 카테고리 필터"
# 방식만 사용함. 매일 실행하며 제목 중복 제거로 누적 수집.
# ─────────────────────────────────────────────

import requests                          # 인터넷 요청
from bs4 import BeautifulSoup            # HTML 파싱
import re                                # 정규표현식
from datetime import datetime            # 날짜 처리
import json                              # JSON 저장
import os                                # 파일 경로 처리

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

# ── 크롤링할 언론사 + 각각의 대상 카테고리 태그 ────
MEDIA_SOURCES = [
    {
        "name": "보험저널",
        "base_url": "https://www.insjournal.co.kr",
        "list_url": "https://www.insjournal.co.kr/news/articleList.html?view_type=sm",
        "target_categories": {
            "정책", "손보", "GA", "상품",
            "핫 이상품", "상품 전략", "올해의 보험상품", "비교추천", "상품비교",
            "기획", "특집", "기자의 눈", "단독",
            "실적 · 통계 분석"
        },
    },
    {
        "name": "한국보험신문",
        "base_url": "https://www.insnews.co.kr",
        "list_url": "https://www.insnews.co.kr/news/articleList.html?view_type=sm",
        "target_categories": {
            "금융정책", "종합", "생명보험", "손해보험", "GA", "기관", "신상품"
        },
    },
]


def parse_list_page(source):
    """
    목록 페이지에서 기사 후보(제목, 링크, 날짜, 카테고리태그)를 추출하는 함수
    """
    try:
        res = requests.get(source["list_url"], headers=HEADERS, timeout=15)
        soup = BeautifulSoup(res.text, 'html.parser')
    except Exception as e:
        print(f"  ❌ {source['name']} 목록 요청 실패: {e}")
        return []

    articles = []
    seen_idx = set()

    for tag_name in ['h2', 'h3', 'h4']:
        for h in soup.find_all(tag_name):
            a = h.find('a', href=True)
            if not a or 'articleView.html' not in a['href']:
                continue

            idx_match = re.search(r'idxno=(\d+)', a['href'])
            if not idx_match:
                continue
            idxno = idx_match.group(1)

            if idxno in seen_idx:
                continue
            seen_idx.add(idxno)

            title = a.get_text(strip=True)
            if not title:
                continue

            container = h.find_parent('li') or h.parent
            info_text = container.get_text(separator='|', strip=True) if container else ''

            date_match = re.search(r'(\d{2}[-.]\d{2})\s+(\d{2}:\d{2})', info_text)
            list_date = date_match.group(1).replace('-', '.') if date_match else ''

            found_category = None
            for token in info_text.split('|'):
                token = token.strip()
                if token in source["target_categories"]:
                    found_category = token
                    break

            link = a['href'] if a['href'].startswith('http') else source["base_url"] + a['href']

            articles.append({
                'idxno': idxno,
                'title': title,
                'link': link,
                'list_date': list_date,
                'category_tag': found_category,
            })

    return articles


def fetch_article_detail(url):
    """상세 페이지에서 메타태그로 정확한 카테고리/발행시각/요약을 가져오는 함수"""
    res = requests.get(url, headers=HEADERS, timeout=15)
    soup = BeautifulSoup(res.text, 'html.parser')

    def get_meta(prop_name):
        tag = soup.find('meta', property=prop_name)
        return tag['content'] if tag and tag.has_attr('content') else None

    return {
        'section': get_meta('article:section'),
        'section1': get_meta('article:section1'),
        'published_time': get_meta('article:published_time'),
        'description': get_meta('og:description') or '',
    }


def crawl_media(source):
    """언론사 하나에서 원하는 카테고리 기사를 수집하는 함수"""
    print(f"  🔍 '{source['name']}' 수집 중...")

    page_articles = parse_list_page(source)
    candidates = [a for a in page_articles if a['category_tag'] in source["target_categories"]]

    print(f"     후보 {len(candidates)}개 발견 (전체 {len(page_articles)}개 중)")

    results = []
    today_iso = datetime.now().strftime("%Y-%m-%d")

    for cand in candidates:
        try:
            detail = fetch_article_detail(cand['link'])

            # 발행일을 YYYY-MM-DD 형식으로 변환 (없으면 오늘 날짜)
            date_iso = today_iso
            if detail['published_time']:
                date_iso = detail['published_time'][:10]

            results.append({
                "title": cand['title'],
                "description": detail['description'] or '',
                "link": cand['link'],
                "press": source['name'],
                "date": date_iso,
                "original_category": detail['section1'] or cand['category_tag'] or '',
            })
        except Exception as e:
            print(f"     ⚠️ 상세페이지 오류 ({cand['title'][:20]}): {e}")
            continue

    print(f"     ✅ {len(results)}개 수집 완료")
    return results


def crawl_all():
    """전체 크롤링 메인 함수 (모든 언론사 순회)"""
    print("📰 뉴스 수집 시작...")

    all_articles = []
    seen_titles = set()

    for source in MEDIA_SOURCES:
        media_articles = crawl_media(source)
        for art in media_articles:
            if art['title'] not in seen_titles:
                seen_titles.add(art['title'])
                all_articles.append(art)

    print(f"\n✅ 총 {len(all_articles)}개 기사 수집 완료! (중복 제거 후)")

    os.makedirs("data", exist_ok=True)
    today = datetime.now().strftime("%Y_%m_%d")
    filename = f"data/articles_{today}.json"

    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(all_articles, f, ensure_ascii=False, indent=2)

    print(f"💾 저장 완료: {filename}")
    return all_articles


if __name__ == "__main__":
    crawl_all()