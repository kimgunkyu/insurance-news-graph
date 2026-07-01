# ─────────────────────────────────────────────
# migrate.py
# 기존 날짜별 analyzed_*.json 파일들을
# 하나의 통합 파일(all_articles.json)로 합치는 1회성 스크립트
# ─────────────────────────────────────────────

import json
import os

def migrate():
    """data 폴더의 analyzed_*.json 파일들을 시간순으로 합쳐서
    all_articles.json 하나로 만드는 함수"""

    # 통합할 날짜별 파일 목록 (오래된 것부터 순서대로)
    files = sorted([
        f for f in os.listdir('data')
        if f.startswith('analyzed_') and f.endswith('.json')
    ])

    if not files:
        print("❌ 합칠 파일이 없습니다.")
        return

    print(f"📂 발견된 파일: {files}")

    all_articles = []
    all_relationships = []
    seen_titles = set()   # 중복 제목 방지
    next_id = 1

    for filename in files:
        filepath = f"data/{filename}"
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)

        old_to_new_id = {}   # 이 파일 안에서의 id → 새로 부여할 통합 id

        for article in data.get('articles', []):
            # 중복 제목은 건너뜀 (먼저 나온 것 우선)
            if article['title'] in seen_titles:
                continue
            seen_titles.add(article['title'])

            old_id = article['id']
            new_id = f"a{next_id}"
            next_id += 1
            old_to_new_id[old_id] = new_id

            new_article = {**article, "id": new_id}
            all_articles.append(new_article)

        for rel in data.get('relationships', []):
            # 관계의 source/target도 새 id로 치환
            # (둘 다 이 파일 안에서 살아남은 기사여야 함)
            s = old_to_new_id.get(rel['source'])
            t = old_to_new_id.get(rel['target'])
            if s and t:
                all_relationships.append({
                    **rel,
                    "source": s,
                    "target": t
                })

        print(f"  ✅ {filename} 처리 완료 ({len(data.get('articles', []))}개 기사)")

    # 통합 데이터 저장
    unified = {
        "articles": all_articles,
        "relationships": all_relationships
    }

    with open('data/all_articles.json', 'w', encoding='utf-8') as f:
        json.dump(unified, f, ensure_ascii=False, indent=2)

    print(f"\n🎉 통합 완료!")
    print(f"   전체 기사: {len(all_articles)}개")
    print(f"   전체 관계: {len(all_relationships)}개")
    print(f"   저장 위치: data/all_articles.json")


if __name__ == "__main__":
    migrate()