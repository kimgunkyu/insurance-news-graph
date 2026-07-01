# ─────────────────────────────────────────────
# main.py
# FastAPI 백엔드 서버
# 브라우저(HTML 앱)랑 Python을 연결해주는 파일
# 통합 파일(all_articles.json) 구조로 관리
# ─────────────────────────────────────────────

from fastapi import FastAPI, UploadFile, Form, File
from typing import Optional
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import json
import os
import base64
import requests
import anthropic
from datetime import datetime, timedelta
from crawler import crawl_all
from analyzer import analyze_articles, save_analyzed_data, load_latest_articles, RELATION_WINDOW_DAYS

# ── FastAPI 앱 생성 ──────────────────────────
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── 환경변수에서 키 가져오기 ──────────────────
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
GITHUB_REPO = "kimgunkyu/insurance-news-graph"
UNIFIED_PATH = "data/all_articles.json"

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


# ── GitHub 파일 읽기/쓰기 함수 ────────────────

def get_github_file(path):
    """GitHub에서 파일 내용 가져오기 (raw 데이터 + SHA)"""
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{path}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    res = requests.get(url, headers=headers)

    if res.status_code == 200:
        content = res.json()
        decoded = base64.b64decode(content['content']).decode('utf-8')
        return json.loads(decoded), content['sha']
    else:
        return None, None


def update_github_file(path, data, sha=None, message=None):
    """GitHub에 파일 업데이트(또는 새로 생성)하는 함수"""
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{path}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}

    content_str = json.dumps(data, ensure_ascii=False, indent=2)
    content_b64 = base64.b64encode(content_str.encode('utf-8')).decode('utf-8')

    payload = {
        "message": message or f"업데이트: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "content": content_b64,
    }
    if sha:
        payload["sha"] = sha

    res = requests.put(url, headers=headers, json=payload)
    return res.status_code in [200, 201]


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


# ── API 엔드포인트 ───────────────────────────

@app.get("/api/news")
def get_news():
    """
    통합 파일 전체를 반환하는 API
    (기간 필터는 브라우저에서 처리)
    """
    files = [f for f in os.listdir('data')] if os.path.exists('data') else []
    if 'all_articles.json' not in files:
        return {"articles": [], "relationships": []}

    with open(UNIFIED_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data


@app.post("/api/fetch")
def fetch_and_analyze():
    """
    버튼 누르면 크롤링 + 분석을 바로 실행하는 API
    """
    print("🚀 크롤링 + 분석 시작!")
    articles = crawl_all()
    if not articles:
        return {"status": "error", "message": "크롤링 실패"}
    analyzed = analyze_articles(articles)
    if not analyzed:
        return {"status": "error", "message": "분석 실패"}
    filename = save_analyzed_data(analyzed)
    return {
        "status": "success",
        "message": f"완료! 전체 기사 {len(analyzed['articles'])}개",
        "filename": filename
    }


@app.get("/api/status")
def get_status():
    """서버 상태 확인용 API"""
    exists = os.path.exists(UNIFIED_PATH)
    count = 0
    if exists:
        with open(UNIFIED_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
            count = len(data.get('articles', []))
    return {
        "status": "ok",
        "unified_file_exists": exists,
        "total_articles": count
    }


@app.post("/api/add-news")
async def add_news(
    text: Optional[str] = Form(None),
    image: Optional[UploadFile] = File(None),
):
    """
    사용자가 텍스트나 이미지를 붙여넣으면
    Claude가 분석해서 통합 파일에 추가하는 API
    최근 30일치 기존 기사와도 관계를 분석함
    """

    content_blocks = []

    if image:
        image_bytes = await image.read()
        image_b64 = base64.b64encode(image_bytes).decode('utf-8')
        media_type = image.content_type or "image/png"

        content_blocks.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": media_type,
                "data": image_b64,
            }
        })
    elif not text:
        return {"status": "error", "message": "텍스트나 이미지를 입력해주세요."}

    # 1. 통합 파일 가져오기
    existing_data, sha = get_github_file(UNIFIED_PATH)
    if not existing_data:
        existing_data = {"articles": [], "relationships": []}

    # 2. 전체 기존 기사를 관계 분석 참고자료로 사용
    recent_existing = existing_data['articles']

    recent_text = "\n".join([f"- {a['id']}: {a['title']} ({a['category']})" for a in recent_existing])

    # 3. Claude에게 보낼 프롬프트 구성 (요약 + 관계 한번에)
    prompt = f"""
당신은 한국 보험업계 전문 애널리스트입니다.

최근 30일간 기존에 분석된 기사 목록 (관계 파악용 참고자료):
{recent_text if recent_text else "(없음)"}

{"위 이미지에 담긴 보험 관련 소식을 분석해줘." if image else f"아래 보험 관련 소식을 분석해줘:\\n\\n{text}"}

다음 JSON 형식으로만 응답하세요 (마크다운, 설명 없이 순수 JSON만):
{{
  "title": "소식 제목",
  "category": "규제/법률|손해율|상품/보험료/가격|전속/GA/채널|투자/재무/IFRS|건전성/K-ICS|기타 중 하나",
  "date": "YYYY-MM-DD (알 수 없으면 오늘 날짜 {datetime.now().strftime('%Y-%m-%d')})",
  "source": "출처 (알 수 없으면 '수동입력')",
  "brief_summary": "핵심만 3줄 이내로 아주 간결하게 요약. 가장 중요한 사실 위주.",
  "summary": "10줄(문장) 이내로 상세 요약. 구체적 수치, 시행시기, 관련기관 포함.",
  "keywords": ["키워드1", "키워드2", "키워드3"],
  "related_article_ids": ["기존 기사 중 관련있는 기사의 id, 최대 4개. 카테고리가 달라도 실제 인과관계/연관성이 있으면 적극적으로 포함"],
  "relationship_labels": ["각 관련기사와의 관계를 5자 이내로, related_article_ids와 같은 순서로"]
}}

[중요] 관계는 카테고리가 같아서가 아니라 실제 내용상 연관성(원인-결과, 정책의 다른 측면, 같은 이슈의 후속 등)이 있을 때만 연결하세요.
"""
    content_blocks.append({"type": "text", "text": prompt})

    try:
        response = client.messages.create(
            model="claude-sonnet-5",
            max_tokens=1500,
            messages=[{"role": "user", "content": content_blocks}]
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
            return {"status": "error", "message": "분석 결과 파싱 실패"}

        # 4. 새 기사 ID 부여
        new_id = f"a{get_next_id(existing_data['articles'])}"
        new_article = {
            "id": new_id,
            "title": parsed.get("title", ""),
            "category": parsed.get("category", "기타"),
            "date": parsed.get("date", datetime.now().strftime("%Y-%m-%d")),
            "source": parsed.get("source", "수동입력"),
            "brief_summary": parsed.get("brief_summary", ""),
            "summary": parsed.get("summary", ""),
            "keywords": parsed.get("keywords", []),
        }

        # 5. 관계 추가 (id로 직접 매칭)
        related_ids = parsed.get("related_article_ids", [])
        relationship_labels = parsed.get("relationship_labels", [])
        existing_ids = {a['id'] for a in existing_data['articles']}

        new_relationships = []
        for i, rel_id in enumerate(related_ids):
            if rel_id in existing_ids:
                label = relationship_labels[i] if i < len(relationship_labels) else "연관"
                new_relationships.append({
                    "source": new_id,
                    "target": rel_id,
                    "label": label,
                    "strength": 0.7
                })

        # 6. 통합 데이터에 추가
        existing_data['articles'].append(new_article)
        existing_data['relationships'].extend(new_relationships)

        # 7. GitHub에 저장
        success = update_github_file(
            UNIFIED_PATH, existing_data, sha,
            message=f"수동 소식 추가: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
        )

        if success:
            return {"status": "success", "message": f"'{new_article['title']}' 추가 완료!", "article": new_article}
        else:
            return {"status": "error", "message": "GitHub 저장 실패"}

    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.delete("/api/delete-news/{article_id}")
def delete_news(article_id: str):
    """
    특정 기사를 삭제하고 관련 관계선도 함께 제거하는 API
    (통합 파일 구조라 날짜 파라미터 불필요)
    """
    existing_data, sha = get_github_file(UNIFIED_PATH)

    if not existing_data:
        return {"status": "error", "message": "파일을 찾을 수 없습니다."}

    original_count = len(existing_data['articles'])
    existing_data['articles'] = [a for a in existing_data['articles'] if a['id'] != article_id]

    if len(existing_data['articles']) == original_count:
        return {"status": "error", "message": "해당 기사를 찾을 수 없습니다."}

    existing_data['relationships'] = [
        r for r in existing_data['relationships']
        if r['source'] != article_id and r['target'] != article_id
    ]

    success = update_github_file(
        UNIFIED_PATH, existing_data, sha,
        message=f"소식 삭제: {article_id} ({datetime.now().strftime('%Y-%m-%d %H:%M')})"
    )

    if success:
        return {"status": "success", "message": "삭제 완료"}
    else:
        return {"status": "error", "message": "GitHub 저장 실패"}


@app.delete("/api/delete-relationship")
def delete_relationship(source: str, target: str):
    """
    특정 관계선(엣지) 하나만 삭제하는 API
    삭제된 관계는 rejected_relationships.json에 기록해서
    나중에 Claude가 비슷한 관계를 다시 만들지 않도록 참고자료로 씀
    """
    existing_data, sha = get_github_file(UNIFIED_PATH)

    if not existing_data:
        return {"status": "error", "message": "파일을 찾을 수 없습니다."}

    target_rel = None
    for r in existing_data['relationships']:
        if (r['source'] == source and r['target'] == target) or \
           (r['source'] == target and r['target'] == source):
            target_rel = r
            break

    if not target_rel:
        return {"status": "error", "message": "해당 관계를 찾을 수 없습니다."}

    source_article = next((a for a in existing_data['articles'] if a['id'] == target_rel['source']), None)
    target_article = next((a for a in existing_data['articles'] if a['id'] == target_rel['target']), None)

    existing_data['relationships'] = [
        r for r in existing_data['relationships'] if r != target_rel
    ]

    success1 = update_github_file(
        UNIFIED_PATH, existing_data, sha,
        message=f"관계 삭제: {source}-{target} ({datetime.now().strftime('%Y-%m-%d %H:%M')})"
    )

    # 거부된 관계 기록
    rejected_path = "data/rejected_relationships.json"
    rejected_data, rejected_sha = get_github_file(rejected_path)
    if not rejected_data:
        rejected_data = {"rejected": []}

    rejected_data['rejected'].append({
        "source_title": source_article['title'] if source_article else target_rel['source'],
        "target_title": target_article['title'] if target_article else target_rel['target'],
        "label": target_rel.get('label', ''),
        "deleted_at": datetime.now().strftime("%Y-%m-%d")
    })
    rejected_data['rejected'] = rejected_data['rejected'][-50:]

    update_github_file(
        rejected_path, rejected_data, rejected_sha,
        message=f"거부된 관계 기록 업데이트: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    )

    if success1:
        return {"status": "success", "message": "관계 삭제 완료"}
    else:
        return {"status": "error", "message": "GitHub 저장 실패"}


@app.post("/api/add-relationship")
async def add_relationship(
    source: str = Form(...),
    target: str = Form(...),
    label: str = Form("연관"),
):
    """
    사용자가 그래프에서 직접 두 기사를 선택해 관계를 추가하는 API
    승인된 관계는 approved_relationships.json에 기록해서
    나중에 Claude가 비슷한 관계를 잘 찾아내도록 참고자료로 씀
    """
    existing_data, sha = get_github_file(UNIFIED_PATH)

    if not existing_data:
        return {"status": "error", "message": "파일을 찾을 수 없습니다."}

    source_article = next((a for a in existing_data['articles'] if a['id'] == source), None)
    target_article = next((a for a in existing_data['articles'] if a['id'] == target), None)

    if not source_article or not target_article:
        return {"status": "error", "message": "기사를 찾을 수 없습니다."}

    already_exists = any(
        (r['source'] == source and r['target'] == target) or
        (r['source'] == target and r['target'] == source)
        for r in existing_data['relationships']
    )
    if already_exists:
        return {"status": "error", "message": "이미 존재하는 관계입니다."}

    new_relationship = {
        "source": source,
        "target": target,
        "label": label,
        "strength": 0.8,
        "manual": True
    }

    existing_data['relationships'].append(new_relationship)

    success1 = update_github_file(
        UNIFIED_PATH, existing_data, sha,
        message=f"관계 수동 추가: {source}-{target} ({datetime.now().strftime('%Y-%m-%d %H:%M')})"
    )

    # 승인된 관계 기록
    approved_path = "data/approved_relationships.json"
    approved_data, approved_sha = get_github_file(approved_path)
    if not approved_data:
        approved_data = {"approved": []}

    approved_data['approved'].append({
        "source_title": source_article['title'],
        "target_title": target_article['title'],
        "label": label,
        "added_at": datetime.now().strftime("%Y-%m-%d")
    })
    approved_data['approved'] = approved_data['approved'][-50:]

    update_github_file(
        approved_path, approved_data, approved_sha,
        message=f"승인된 관계 기록 업데이트: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    )

    if success1:
        return {"status": "success", "message": "관계 추가 완료"}
    else:
        return {"status": "error", "message": "GitHub 저장 실패"}


@app.get("/api/test-direct-access")
def test_direct_access():
    """
    [테스트용 임시 엔드포인트 - 확인 후 삭제 예정]
    보험저널 상세페이지 메타태그 파싱 테스트
    """
    import re
    from bs4 import BeautifulSoup

    BASE_URL = "https://www.insjournal.co.kr"
    HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

    test_idxnos = ["32105", "32111", "32104"]  # 방금 찾은 후보 기사들

    results = []

    for idxno in test_idxnos:
        url = f"{BASE_URL}/news/articleView.html?idxno={idxno}"
        try:
            res = requests.get(url, headers=HEADERS, timeout=15)
            soup = BeautifulSoup(res.text, 'html.parser')

            def get_meta(prop_name):
                tag = soup.find('meta', property=prop_name)
                return tag['content'] if tag and tag.has_attr('content') else None

            results.append({
                "idxno": idxno,
                "section": get_meta('article:section'),
                "section1": get_meta('article:section1'),
                "published_time": get_meta('article:published_time'),
                "description": get_meta('og:description'),
            })
        except Exception as e:
            results.append({"idxno": idxno, "error": str(e)})

    return {"results": results}

# ── HTML 파일 서빙 ────────────────────────────
@app.get("/")
def serve_index():
    return FileResponse("index.html")


# ── 서버 실행 ────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)