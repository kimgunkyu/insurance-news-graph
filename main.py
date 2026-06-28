# ─────────────────────────────────────────────
# main.py
# FastAPI 백엔드 서버
# 브라우저(HTML 앱)랑 Python을 연결해주는 파일
# ─────────────────────────────────────────────

from fastapi import FastAPI                    # 웹 서버 프레임워크
from fastapi.middleware.cors import CORSMiddleware  # 브라우저 접근 허용
from fastapi.staticfiles import StaticFiles    # HTML 파일 서빙
import json                                    # JSON 읽기
import os                                      # 파일 경로 처리
from crawler import crawl_all                  # 크롤러 불러오기
from analyzer import analyze_articles, save_analyzed_data, load_latest_articles  # 분석기 불러오기

# ── FastAPI 앱 생성 ──────────────────────────
app = FastAPI()

# ── CORS 설정 ────────────────────────────────
# 브라우저에서 이 서버로 요청할 수 있게 허용
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],    # 모든 주소에서 접근 허용
    allow_methods=["*"],    # 모든 방식 허용
    allow_headers=["*"],    # 모든 헤더 허용
)


# ── API 엔드포인트 ───────────────────────────
# 브라우저가 이 주소로 요청하면 데이터를 돌려줘요

@app.get("/api/news")
def get_news():
    """
    가장 최근 분석된 뉴스 데이터를 반환하는 API
    브라우저에서 localhost:8000/api/news 로 접속하면 JSON 반환
    """

    # data 폴더에서 분석된 파일 찾기
    files = [f for f in os.listdir('data') if f.startswith('analyzed_')]

    if not files:
        # 분석된 파일 없으면 빈 데이터 반환
        return {"articles": [], "relationships": []}

    # 가장 최근 파일 불러오기
    latest_file = sorted(files)[-1]
    with open(f"data/{latest_file}", 'r', encoding='utf-8') as f:
        data = json.load(f)

    return data


@app.post("/api/fetch")
def fetch_and_analyze():
    """
    버튼 누르면 크롤링 + 분석을 바로 실행하는 API
    브라우저에서 버튼 누르면 이 함수가 실행됨
    """

    print("🚀 크롤링 + 분석 시작!")

    # 1. 뉴스 크롤링
    articles = crawl_all()

    if not articles:
        return {"status": "error", "message": "크롤링 실패"}

    # 2. Claude AI 분석
    analyzed = analyze_articles(articles)

    if not analyzed:
        return {"status": "error", "message": "분석 실패"}

    # 3. 결과 저장
    filename = save_analyzed_data(analyzed)

    return {
        "status": "success",
        "message": f"완료! 기사 {len(analyzed['articles'])}개 분석됨",
        "filename": filename
    }


@app.get("/api/status")
def get_status():
    """
    서버 상태 확인용 API
    localhost:8000/api/status 접속하면 OK 반환
    """
    files = [f for f in os.listdir('data') if f.startswith('analyzed_')]
    latest = sorted(files)[-1] if files else "없음"

    return {
        "status": "ok",
        "latest_file": latest,
        "total_files": len(files)
    }


# ── 서버 실행 ────────────────────────────────
# HTML 파일을 브라우저에서 볼 수 있게 서빙
from fastapi.responses import FileResponse

@app.get("/")
def serve_index():
    return FileResponse("index.html")

# python main.py 로 실행하면 서버 시작
if __name__ == "__main__":
    import uvicorn
    # host="0.0.0.0" → 내 컴퓨터 어디서든 접속 가능
    # port=8000 → localhost:8000 주소로 접속
    uvicorn.run(app, host="0.0.0.0", port=8000)