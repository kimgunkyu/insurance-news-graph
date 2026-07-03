# ─────────────────────────────────────────────
# analyzer.py
# 크롤링한 기사를 Claude AI로 분석하는 파일
# 통합 파일(all_articles.json) 방식으로 관리
# 최근 30일치 기존 기사와도 관계를 분석함
# 사용자가 삭제/추가한 관계 기록도 참고함
# ─────────────────────────────────────────────

import anthropic        # Claude API 라이브러리
import json             # JSON 파일 읽기/쓰기
import os               # 파일/폴더 경로 처리
import base64           # GitHub API 응답 디코딩
import requests         # GitHub API 호출
from datetime import datetime, timedelta  # 날짜 처리

# ── Claude API 키 설정 ───────────────────────
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

# ── GitHub 설정 (거부/승인된 관계 기록 조회용) ─
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO = "kimgunkyu/insurance-news-graph"

# ── 설정값 ────────────────────────────────────
BATCH_SIZE = 6              # 새 기사 분석 시 배치 크기
RELATION_WINDOW_DAYS = 30   # 관계 분석 시 참고할 기존 기사 기간
UNIFIED_FILE = "data/all_articles.json"   # 통합 데이터 파일


def load_unified_data():
    """통합 파일을 불러오는 함수. 없으면 빈 구조 반환"""
    if os.path.exists(UNIFIED_FILE):
        with open(UNIFIED_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"articles": [], "relationships": []}


def save_unified_data(data):
    """통합 파일에 저장하는 함수"""
    os.makedirs("data", exist_ok=True)
    with open(UNIFIED_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"💾 저장 완료: {UNIFIED_FILE} (전체 기사 {len(data['articles'])}개)")
    return UNIFIED_FILE


def get_next_id(existing_articles):
    """기존 기사들 중 가장 큰 숫자 ID 다음 번호를 반환"""
    max_num = 0
    for a in existing_articles:
        try:
            num = int(a['id'].replace('a', ''))
            max_num = max(max_num, num)
        except (ValueError, KeyError):
            continue
    return max_num + 1


def load_feedback_from_github(path):
    """
    GitHub에서 rejected/approved 관계 기록을 불러오는 함수
    로컬 실행이든 GitHub Actions든 항상 GitHub 원본을 참고 (최신 사용자 피드백 반영 위해)
    """
    if not GITHUB_TOKEN:
        return None

    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{path}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    try:
        res = requests.get(url, headers=headers, timeout=10)
        if res.status_code == 200:
            content = res.json()
            decoded = base64.b64decode(content['content']).decode('utf-8')
            return json.loads(decoded)
    except Exception as e:
        print(f"  ⚠️ 피드백 파일 로드 실패 ({path}): {e}")
    return None


def get_feedback_prompt_section():
    """
    사용자가 삭제(rejected)하거나 추가(approved)한 관계 기록을
    프롬프트에 넣을 텍스트로 만드는 함수
    """
    rejected = load_feedback_from_github("data/rejected_relationships.json")
    approved = load_feedback_from_github("data/approved_relationships.json")

    section = ""

    if rejected and rejected.get('rejected'):
        recent_rejected = rejected['rejected'][-20:]   # 최근 20개만 참고
        rejected_lines = "\n".join([
            f"  - \"{r['source_title']}\" ↔ \"{r['target_title']}\" (사유: 실제 연관성 부족으로 판단됨)"
            for r in recent_rejected
        ])
        section += f"""
[사용자가 부적절하다고 판단해 삭제한 관계 예시 - 이런 유형의 억지 연결은 피하세요]
{rejected_lines}
"""

    if approved and approved.get('approved'):
        recent_approved = approved['approved'][-20:]
        approved_lines = "\n".join([
            f"  - \"{a['source_title']}\" ↔ \"{a['target_title']}\" (관계: {a['label']})"
            for a in recent_approved
        ])
        section += f"""
[사용자가 직접 추가한 관계 예시 - 이런 유형의 관계를 적극적으로 찾아주세요]
{approved_lines}
"""

    return section


def analyze_batch(articles, batch_num, total_batches):
    """
    새로 크롤링한 기사 8개씩 묶어서 Claude AI로 요약/분류하는 함수
    (관계 분석은 이 단계에서 하지 않고, 나중에 별도로 함)
    """
    print(f"  📦 배치 {batch_num}/{total_batches} 분석 중... ({len(articles)}개 기사)")

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
1. 아래 기준으로 불필요한 기사는 제외해주세요:
   - 2025년 이전 기사 제외 (2025년, 2026년 기사만 선택)
   - 단순 인사/부고/채용 기사 제외
   - 정책, 규제, 시장트렌드, 상품변화, GA채널, 실적/통계 관련 기사 선택
2. 내용이 비슷한 기사들은 가장 상세한 것 1개만 남기고 나머지는 제거해주세요
3. [날짜 규칙 - 중요] 위 "날짜" 항목에 이미 원본 기사의 정확한 게재일이 주어져 있습니다.
   이 값을 그대로 YYYY-MM-DD 형식으로만 변환해서 사용하세요. 절대로 본문 내용을 보고
   날짜를 임의로 추측하거나 다른 날짜로 바꾸지 마세요. 주어진 날짜가 비어있을 때만
   빈 문자열로 두세요.
4. 반드시 순수 JSON만 출력 (마크다운 없이)

다음 JSON 형식으로만 응답하세요:
{{
  "articles": [
    {{
      "title": "기사 제목",
      "category": "규제/법률|손해율|상품/보험료/가격|전속/GA/채널|투자/재무/IFRS|건전성/K-ICS|기타 중 하나",
      "date": "YYYY-MM-DD 또는 빈 문자열",
      "source": "언론사명",
      "brief_summary": "핵심만 3줄 이내로 아주 간결하게 요약. 가장 중요한 사실 위주.",
      "summary": "10줄(문장) 이내로 상세하게 요약. 구체적 수치, 시행 시기, 관련 기관명, 영향 범위 등을 포함.",
      "keywords": ["키워드1", "키워드2", "키워드3"]
    }}
  ]
}}
"""

    try:
        response = client.messages.create(
            model="claude-sonnet-5",
            max_tokens=6000,
            messages=[{"role": "user", "content": prompt}]
        )

        raw = next((block.text for block in response.content if block.type == "text"), "")

        parsed = None
        for attempt in [
            lambda: json.loads(raw),
            lambda: json.loads(raw.replace("```json", "").replace("```", "").strip()),
            lambda: json.loads(raw[raw.index('{'):raw.rindex('}')+1])
        ]:
            try:
                parsed = attempt()
                break
            except Exception:
                pass

        if not parsed:
            print(f"  ❌ 배치 {batch_num} 파싱 실패, 응답 길이: {len(raw)}자")
            print(f"  🔍 원본 응답 마지막 300자: {raw[-300:]}")
            return []

        return parsed.get('articles', [])

    except Exception as e:
        print(f"  ❌ 배치 {batch_num} API 오류: {e}")
        return []


def analyze_relationships(new_articles, recent_existing_articles):
    """
    새 기사들과, (새 기사끼리 + 최근 기존 기사와) 관계를 분석하는 함수
    사용자가 남긴 삭제/추가 피드백도 참고자료로 함께 전달
    """
    print("  🔗 기사 간 관계 분석 중... (카테고리 무관, 최근 30일 + 사용자 피드백 참고)")

    new_text = "\n".join([f"- NEW_{i}: {a['title']} ({a['category']})" for i, a in enumerate(new_articles)])
    existing_text = "\n".join([f"- {a['id']}: {a['title']} ({a['category']})" for a in recent_existing_articles])
    feedback_text = get_feedback_prompt_section()

    prompt = f"""
아래는 [새로 추가되는 보험 뉴스 기사]와 [최근 30일간 기존에 분석된 기사] 목록입니다.

[새 기사]
{new_text}

[최근 30일 기존 기사]
{existing_text if existing_text else "(없음)"}
{feedback_text}
관련있는 기사끼리 연결해주세요. 아래 두 종류를 모두 찾아주세요:
1. 새 기사끼리의 관계
2. 새 기사와 기존 기사 사이의 관계 (특히 인과관계, 후속보도, 정책→시장 영향 등)

[중요] 카테고리가 다른 기사끼리도 적극적으로 연결하세요.
예: 규제 변화(규제/법률)가 손해율(손해율)에 미치는 영향, GA 채널 변화(전속/GA/채널)가
상품 가격(상품/보험료/가격)에 미치는 영향처럼 카테고리를 넘나드는 인과관계를
우선적으로 찾아주세요. 단순히 같은 카테고리라서 연결하지 말고, 실제 내용상
연관성(원인-결과, 시간 순서, 같은 정책/이슈의 다른 측면 등)이 있는 것만 연결하세요.

위에 제공된 "사용자가 삭제한 관계 예시"와 비슷한 패턴(억지 연결)은 피하고,
"사용자가 직접 추가한 관계 예시"와 비슷한 패턴(실제 유의미한 인과관계)은 적극 반영하세요.

반드시 순수 JSON만 출력하세요:
{{
  "relationships": [
    {{
      "source": "NEW_0 또는 기존기사ID(예: a5)",
      "target": "NEW_1 또는 기존기사ID(예: a12)",
      "label": "관계설명(5자이내)",
      "strength": 0.8
    }}
  ]
}}

규칙:
- source/target에는 반드시 "NEW_숫자" 형식이거나 기존 기사의 정확한 id(예: a5)를 사용
- strength는 0.1~1.0 (연관성 강도)
- 실제로 관련있는 기사끼리만 연결 (억지 연결 금지)
"""

    try:
        response = client.messages.create(
            model="claude-sonnet-5",
            max_tokens=8000,
            messages=[{"role": "user", "content": prompt}]
        )

        raw = next((block.text for block in response.content if block.type == "text"), "")

        parsed = None
        for attempt in [
            lambda: json.loads(raw),
            lambda: json.loads(raw.replace("```json", "").replace("```", "").strip()),
            lambda: json.loads(raw[raw.index('{'):raw.rindex('}')+1])
        ]:
            try:
                parsed = attempt()
                break
            except Exception:
                pass

        if not parsed:
            print("  ❌ 관계 분석 파싱 실패")
            print(f"  🔍 원본 응답 (앞 300자): {raw[:300]}")
            print(f"  🔍 원본 응답 길이: {len(raw)}자")
            return []

        return parsed.get('relationships', [])

    except Exception as e:
        print(f"  ❌ 관계 분석 API 오류: {e}")
        return []


def analyze_articles(articles):
    """
    전체 기사를 배치로 나눠서 분석 후, 통합 파일에 병합 저장하는 메인 함수
    """
    print(f"🤖 Claude AI 분석 시작... (총 {len(articles)}개 기사)")

    if not articles:
        print("분석할 기사가 없습니다.")
        return None

    # 1. 새 기사들 요약/분류 (배치 처리)
    batches = [articles[i:i+BATCH_SIZE] for i in range(0, len(articles), BATCH_SIZE)]
    total_batches = len(batches)
    print(f"📦 총 {total_batches}개 배치로 나눠서 분석합니다.")

    new_articles_raw = []
    for i, batch in enumerate(batches):
        batch_result = analyze_batch(batch, i+1, total_batches)
        new_articles_raw.extend(batch_result)

    print(f"✅ 새 기사 요약 완료! 총 {len(new_articles_raw)}개")

    if not new_articles_raw:
        print("분석 결과 남은 기사가 없습니다.")
        return None

    # 2. 통합 파일 불러오기
    unified = load_unified_data()

    # 3. 이미 있는 제목과 중복되는 새 기사는 제외
    existing_titles = {a['title'] for a in unified['articles']}
    new_articles_raw = [a for a in new_articles_raw if a['title'] not in existing_titles]

    if not new_articles_raw:
        print("모두 이미 존재하는 기사라 추가할 내용이 없습니다.")
        return unified

    # 4. 전체 기존 기사를 관계 분석용 참고자료로 사용
    recent_existing = unified['articles']

    # 5. 관계 분석 (새 기사끼리 + 새 기사 vs 최근 기존 기사, 사용자 피드백 반영)
    raw_relationships = analyze_relationships(new_articles_raw, recent_existing)
    print(f"✅ 관계 분석 완료! 총 {len(raw_relationships)}개")

    # 6. 새 기사에 고유 ID 부여
    next_id_num = get_next_id(unified['articles'])
    new_id_map = {}   # "NEW_0" → "a37" 매핑용
    for i, article in enumerate(new_articles_raw):
        new_id = f"a{next_id_num + i}"
        new_id_map[f"NEW_{i}"] = new_id
        article['id'] = new_id

    # 7. 관계의 source/target을 실제 ID로 치환
    final_relationships = []
    for rel in raw_relationships:
        source = new_id_map.get(rel['source'], rel['source'])
        target = new_id_map.get(rel['target'], rel['target'])
        final_relationships.append({
            "source": source,
            "target": target,
            "label": rel.get('label', '연관'),
            "strength": rel.get('strength', 0.5)
        })

    # 8. 통합 파일에 병합
    unified['articles'].extend(new_articles_raw)
    unified['relationships'].extend(final_relationships)

    print(f"✅ 통합 완료! 전체 기사 {len(unified['articles'])}개, 전체 관계 {len(unified['relationships'])}개")

    return unified


def save_analyzed_data(data):
    """통합 파일로 저장 (analyze_articles의 결과를 그대로 저장)"""
    return save_unified_data(data)


def load_latest_articles():
    """data 폴더에서 가장 최근 크롤링 파일(articles_*.json) 불러오기"""
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