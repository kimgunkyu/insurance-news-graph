# ─────────────────────────────────────────────
# main.py
# FastAPI 백엔드 서버
# 브라우저(HTML 앱)랑 Python을 연결해주는 파일
# ─────────────────────────────────────────────

from fastapi import FastAPI, UploadFile, Form, File   # 웹 서버 프레임워크 + 파일업로드
from typing import Optional
from fastapi.middleware.cors import CORSMiddleware  # 브라우저 접근 허용
from fastapi.staticfiles import StaticFiles    # HTML 파일 서빙
from fastapi.responses import FileResponse     # HTML 파일 응답용
import json                                    # JSON 읽기
import os                                      # 파일 경로 처리
import base64                                  # 이미지 인코딩
import requests                                # GitHub API 호출
import anthropic                               # Claude API
from datetime import datetime
from crawler import crawl_all                  # 크롤러 불러오기
from analyzer import analyze_articles, save_analyzed_data, load_latest_articles  # 분석기 불러오기

# ── FastAPI 앱 생성 ──────────────────────────
app = FastAPI()

# ── CORS 설정 ────────────────────────────────
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

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


# ── API 엔드포인트 ───────────────────────────

@app.get("/api/news")
def get_news():
    """
    가장 최근 분석된 뉴스 데이터를 반환하는 API (단일 파일용, 참고용으로 유지)
    """
    files = [f for f in os.listdir('data') if f.startswith('analyzed_')]
    if not files:
        return {"articles": [], "relationships": []}
    latest_file = sorted(files)[-1]
    with open(f"data/{latest_file}", 'r', encoding='utf-8') as f:
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
        "message": f"완료! 기사 {len(analyzed['articles'])}개 분석됨",
        "filename": filename
    }


@app.get("/api/status")
def get_status():
    """서버 상태 확인용 API"""
    files = [f for f in os.listdir('data') if f.startswith('analyzed_')]
    latest = sorted(files)[-1] if files else "없음"
    return {
        "status": "ok",
        "latest_file": latest,
        "total_files": len(files)
    }


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


def update_github_file(path, data, sha=None):
    """GitHub에 파일 업데이트(또는 새로 생성)하는 함수"""
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{path}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}

    content_str = json.dumps(data, ensure_ascii=False, indent=2)
    content_b64 = base64.b64encode(content_str.encode('utf-8')).decode('utf-8')

    payload = {
        "message": f"수동 소식 추가: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "content": content_b64,
    }
    if sha:
        payload["sha"] = sha

    res = requests.put(url, headers=headers, json=payload)
    return res.status_code in [200, 201]


@app.post("/api/add-news")
async def add_news(
    text: Optional[str] = Form(None),           # 텍스트로 입력한 경우
    image: Optional[UploadFile] = File(None),   # 이미지로 입력한 경우
):
    """
    사용자가 텍스트나 이미지를 붙여넣으면
    Claude가 분석해서 오늘 날짜의 analyzed 파일에 추가하는 API
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

    today = datetime.now().strftime("%Y_%m_%d")
    filepath = f"data/analyzed_{today}.json"
    existing_data, sha = get_github_file(filepath)

    if not existing_data:
        existing_data = {"articles": [], "relationships": []}

    existing_titles = [a['title'] for a in existing_data['articles']]

    prompt = f"""
당신은 한국 보험업계 전문 애널리스트입니다.

기존에 이미 분석된 기사 제목들:
{json.dumps(existing_titles, ensure_ascii=False)}

{"위 이미지에 담긴 보험 관련 소식을 분석해줘." if image else f"아래 보험 관련 소식을 분석해줘:\\n\\n{text}"}

다음 JSON 형식으로만 응답하세요 (마크다운, 설명 없이 순수 JSON만):
{{
  "title": "소식 제목",
  "category": "규제/법률|손해율|상품/보험료/가격|전속/GA/채널|투자/재무/IFRS|건전성/K-ICS|보험시장|기타 중 하나",
  "date": "YYYY-MM-DD (알 수 없으면 오늘 날짜 {datetime.now().strftime('%Y-%m-%d')})",
  "source": "출처 (알 수 없으면 '수동입력')",
  "summary": "5~7문장으로 상세 요약. 구체적 수치, 시행시기, 관련기관 포함.",
  "keywords": ["키워드1", "키워드2", "키워드3"],
  "related_titles": ["기존 기사 중 관련있는 제목들, 최대 3개"],
  "relationship_labels": ["각 관련기사와의 관계를 5자 이내로, related_titles와 같은 순서로"]
}}
"""
    content_blocks.append({"type": "text", "text": prompt})

    try:
        response = client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=1500,
            messages=[{"role": "user", "content": content_blocks}]
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
            except Exception:
                pass

        if not parsed:
            return {"status": "error", "message": "분석 결과 파싱 실패"}

        new_id = f"a{len(existing_data['articles']) + 1}"
        new_article = {
            "id": new_id,
            "title": parsed.get("title", ""),
            "category": parsed.get("category", "기타"),
            "date": parsed.get("date", datetime.now().strftime("%Y-%m-%d")),
            "source": parsed.get("source", "수동입력"),
            "summary": parsed.get("summary", ""),
            "keywords": parsed.get("keywords", []),
        }

        related_titles = parsed.get("related_titles", [])
        relationship_labels = parsed.get("relationship_labels", [])

        new_relationships = []
        for i, rel_title in enumerate(related_titles):
            matched = next((a for a in existing_data['articles'] if a['title'] == rel_title), None)
            if matched:
                label = relationship_labels[i] if i < len(relationship_labels) else "연관"
                new_relationships.append({
                    "source": new_id,
                    "target": matched['id'],
                    "label": label,
                    "strength": 0.7
                })

        existing_data['articles'].append(new_article)
        existing_data['relationships'].extend(new_relationships)

        success = update_github_file(filepath, existing_data, sha)

        if success:
            return {"status": "success", "message": f"'{new_article['title']}' 추가 완료!", "article": new_article}
        else:
            return {"status": "error", "message": "GitHub 저장 실패"}

    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.delete("/api/delete-news/{article_id}")
def delete_news(article_id: str, date: str = None):
    """
    특정 기사를 삭제하고 관련 관계선도 함께 제거하는 API
    date: YYYY_MM_DD 형식 (예: 2026_07_01). 없으면 오늘 날짜 파일에서 찾음
    """
    target_date = date or datetime.now().strftime("%Y_%m_%d")
    filepath = f"data/analyzed_{target_date}.json"
    existing_data, sha = get_github_file(filepath)

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

    success = update_github_file(filepath, existing_data, sha)

    if success:
        return {"status": "success", "message": "삭제 완료"}
    else:
        return {"status": "error", "message": "GitHub 저장 실패"}


@app.get("/api/dates")
def get_available_dates():
    """
    GitHub data 폴더에 있는 analyzed 파일들의 날짜 목록을 반환하는 API
    (index.html에서 어떤 날짜들이 있는지 알아야 fetch할 수 있어서 필요해요)
    """
    url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/data"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    res = requests.get(url, headers=headers)

    if res.status_code != 200:
        return {"dates": []}

    files = res.json()
    dates = []
    for f in files:
        name = f['name']
        if name.startswith('analyzed_') and name.endswith('.json'):
            date_part = name.replace('analyzed_', '').replace('.json', '')
            dates.append(date_part)

    dates.sort(reverse=True)   # 최신 날짜 먼저
    return {"dates": dates}


# ── HTML 파일 서빙 ────────────────────────────
@app.get("/")
def serve_index():
    return FileResponse("index.html")


# ── 서버 실행 ────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)