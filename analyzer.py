# ─────────────────────────────────────────────
# analyzer.py
# 크롤링한 기사를 Claude AI로 분석하는 파일
# 10개씩 나눠서 분석 후 관계도 통합
# ─────────────────────────────────────────────

import anthropic        # Claude API 라이브러리
import json             # JSON 파일 읽기/쓰기
import os               # 파일/폴더 경로 처리
from datetime import datetime  # 날짜 처리

# ── Claude API 키 설정 ───────────────────────
import os
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# ── 한 번에 분석할 기사 수 ───────────────────
BATCH_SIZE = 8


def analyze_batch(articles, batch_num, total_batches):
    """
    기사 10개씩 묶어서 Claude AI로 분석하는 함수
    articles: 분석할 기사 목록 (최대 10개)
    batch_num: 현재 배치 번호
    total_batches: 전체 배치 수
    """

    print(f"  📦 배치 {batch_num}/{total_batches} 분석 중... ({len(articles)}개 기사)")

    # Claude에게 보낼 기사 텍스트 만들기
    articles_text = ""
    for i, article in enumerate(articles):
        articles_text += f"""
기사 {i+1}:
제목: {article['title']}
언론사: {article['press']}
날짜: {article['date']}
내용: {article['description']}
---
"""

    prompt = f"""
아래 한국 보험업계 뉴스 기사들을 분석해주세요.

{articles_text}

[규칙]
1. 내용이 비슷한 기사는 가장 상세한 것 1개만 남기고 제거
2. 원본 기사의 실제 날짜를 YYYY-MM-DD 형식으로. 날짜를 알 수 없으면 빈 문자열로
3. 반드시 순수 JSON만 출력 (마크다운 없이)

다음 JSON 형식으로만 응답하세요:
{{
  "articles": [
    {{
      "id": "a1",
      "title": "기사 제목",
      "category": "규제/법률|손해율|상품/보험료/가격|전속/GA/채널|투자/재무/IFRS|건전성/K-ICS|보험시장|기타 중 하나",
      "date": "YYYY-MM-DD 또는 빈 문자열",
      "source": "언론사명",
      "summary": "기사 핵심 내용을 5~7문장으로 상세하게 요약. 구체적 수치, 시행 시기, 관련 기관명, 영향 범위 등을 포함. 업계 종사자가 읽었을 때 원문을 안 봐도 핵심을 파악할 수 있을 정도로 작성.",
      "keywords": ["키워드1", "키워드2", "키워드3"]
    }}
  ]
}}
"""

    try:
        response = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=3000,
            messages=[{"role": "user", "content": prompt}]
        )

        raw = response.content[0].text

        # JSON 파싱 시도
        parsed = None
        for attempt in [
            lambda: json.loads(raw),
            lambda: json.loads(raw.replace("```json", "").replace("```", "").strip()),
            lambda: json.loads(raw[raw.index('{'):raw.rindex('}')+1])
        ]:
            try:
                parsed = attempt()
                break
            except:
                pass

        if not parsed:
            print(f"  ❌ 배치 {batch_num} 파싱 실패")
            return []

        return parsed.get('articles', [])

    except Exception as e:
        print(f"  ❌ 배치 {batch_num} API 오류: {e}")
        return []


def analyze_relationships(all_articles):
    """
    전체 기사들 사이의 관계를 한번에 분석하는 함수
    개별 배치 분석 후 마지막에 한 번만 호출
    """

    print("  🔗 기사 간 관계 분석 중...")

    # 기사 제목 목록만 추출 (관계 분석용)
    articles_text = ""
    for article in all_articles:
        articles_text += f"- {article['id']}: {article['title']} ({article['category']})\n"

    prompt = f"""
아래 보험 뉴스 기사들 사이의 관계를 분석해주세요.

{articles_text}

관련있는 기사끼리 연결해주세요. 반드시 순수 JSON만 출력하세요:
{{
  "relationships": [
    {{
      "source": "a1",
      "target": "a2",
      "label": "관계설명(5자이내)",
      "strength": 0.8
    }}
  ]
}}

규칙:
- 실제로 관련있는 기사끼리만 연결
- strength는 0.1~1.0 (연관성 강도)
- 최소 10개 이상 관계 추출
"""

    try:
        response = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}]
        )

        raw = response.content[0].text

        parsed = None
        for attempt in [
            lambda: json.loads(raw),
            lambda: json.loads(raw.replace("```json", "").replace("```", "").strip()),
            lambda: json.loads(raw[raw.index('{'):raw.rindex('}')+1])
        ]:
            try:
                parsed = attempt()
                break
            except:
                pass

        if not parsed:
            print("  ❌ 관계 분석 파싱 실패")
            return []

        return parsed.get('relationships', [])

    except Exception as e:
        print(f"  ❌ 관계 분석 API 오류: {e}")
        return []


def analyze_articles(articles):
    """
    전체 기사를 10개씩 나눠서 분석 후 통합하는 메인 함수
    """

    print(f"🤖 Claude AI 분석 시작... (총 {len(articles)}개 기사)")

    if not articles:
        print("분석할 기사가 없습니다.")
        return None

    # 10개씩 배치로 나누기
    batches = [articles[i:i+BATCH_SIZE] for i in range(0, len(articles), BATCH_SIZE)]
    total_batches = len(batches)
    print(f"📦 총 {total_batches}개 배치로 나눠서 분석합니다.")

    all_analyzed = []   # 전체 분석된 기사 모음
    article_counter = 1  # 전체 기사 ID 카운터

    # 배치별로 분석
    for i, batch in enumerate(batches):
        batch_articles = analyze_batch(batch, i+1, total_batches)

        # ID를 전체 순서에 맞게 재부여 (a1, a2, a3...)
        for article in batch_articles:
            article['id'] = f"a{article_counter}"
            article_counter += 1
            all_analyzed.append(article)

    print(f"✅ 기사 분석 완료! 총 {len(all_analyzed)}개")

    # 전체 기사 관계 분석
    relationships = analyze_relationships(all_analyzed)
    print(f"✅ 관계 분석 완료! 총 {len(relationships)}개")

    return {
        "articles": all_analyzed,
        "relationships": relationships
    }


def save_analyzed_data(data):
    """분석된 데이터를 JSON 파일로 저장 (수동 추가분은 보존)"""
    # data 폴더 없으면 자동 생성
    os.makedirs("data", exist_ok=True)

    today = datetime.now().strftime("%Y_%m_%d")
    filename = f"data/analyzed_{today}.json"

    # 기존 파일이 있으면 수동 추가 기사들을 보존
    manual_articles = []
    manual_relationships = []

    if os.path.exists(filename):
        with open(filename, 'r', encoding='utf-8') as f:
            existing = json.load(f)
        manual_articles = [a for a in existing.get('articles', []) if a.get('source') == '수동입력']
        manual_ids = {a['id'] for a in manual_articles}
        manual_relationships = [
            r for r in existing.get('relationships', [])
            if r['source'] in manual_ids or r['target'] in manual_ids
        ]

    # 새 크롤링 데이터의 ID와 겹치지 않도록 수동 데이터 ID 재조정
    new_id_start = len(data['articles']) + 1
    id_map = {}
    for i, article in enumerate(manual_articles):
        old_id = article['id']
        new_id = f"a{new_id_start + i}"
        id_map[old_id] = new_id
        article['id'] = new_id

    for rel in manual_relationships:
        if rel['source'] in id_map:
            rel['source'] = id_map[rel['source']]
        if rel['target'] in id_map:
            rel['target'] = id_map[rel['target']]

    # 합치기 (크롤링 데이터 + 보존된 수동 데이터)
    data['articles'] = data['articles'] + manual_articles
    data['relationships'] = data['relationships'] + manual_relationships

    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"💾 저장 완료: {filename} (수동 추가 {len(manual_articles)}개 보존)")
    return filename


def load_latest_articles():
    """data 폴더에서 가장 최근 크롤링 파일 불러오기"""
    files = [f for f in os.listdir('data') if f.startswith('articles_')]

    if not files:
        print("❌ 크롤링된 파일이 없습니다. crawler.py를 먼저 실행하세요.")
        return None

    latest_file = sorted(files)[-1]
    filepath = f"data/{latest_file}"

    with open(filepath, 'r', encoding='utf-8') as f:
        articles = json.load(f)

    print(f"📂 파일 로드: {filepath} ({len(articles)}개 기사)")
    return articles


# ── 직접 실행 ────────────────────────────────
if __name__ == "__main__":
    articles = load_latest_articles()

    if articles:
        analyzed = analyze_articles(articles)

        if analyzed:
            save_analyzed_data(analyzed)