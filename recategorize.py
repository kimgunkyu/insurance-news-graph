# ─────────────────────────────────────────────
# recategorize.py
# '보험시장' 카테고리 기사들을 Claude에게 다시 보내
# 나머지 7개 카테고리 중 가장 적합한 것으로 재분류하는 1회성 스크립트
# ─────────────────────────────────────────────

import anthropic
import json
import os

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

UNIFIED_FILE = "data/all_articles.json"

VALID_CATEGORIES = [
    "규제/법률", "손해율", "상품/보험료/가격",
    "전속/GA/채널", "투자/재무/IFRS", "건전성/K-ICS", "기타"
]


def recategorize():
    """'보험시장' 카테고리 기사들을 재분류"""

    with open(UNIFIED_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)

    target_articles = [a for a in data['articles'] if a.get('category') == '보험시장']

    if not target_articles:
        print("✅ '보험시장' 카테고리 기사가 없습니다. 작업할 필요 없어요!")
        return

    print(f"📊 '보험시장' 기사 {len(target_articles)}개 발견. 재분류 시작...")

    # 기사 목록을 프롬프트로 만들기
    articles_text = ""
    for i, a in enumerate(target_articles):
        articles_text += f"""
기사 {i+1} (id: {a['id']}):
제목: {a['title']}
요약: {a['summary']}
---
"""

    prompt = f"""
아래는 기존에 '보험시장'으로 분류됐던 한국 보험업계 뉴스 기사들입니다.
'보험시장' 카테고리는 이제 사용하지 않습니다.
각 기사를 아래 카테고리 중 가장 적합한 것 하나로 재분류해주세요.

[사용 가능한 카테고리]
규제/법률, 손해율, 상품/보험료/가격, 전속/GA/채널, 투자/재무/IFRS, 건전성/K-ICS, 기타

{articles_text}

반드시 순수 JSON만 출력하세요:
{{
  "reclassified": [
    {{"id": "a5", "new_category": "규제/법률"}},
    {{"id": "a12", "new_category": "기타"}}
  ]
}}
"""

    response = client.messages.create(
        model="claude-sonnet-5",
        max_tokens=2000,
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
        print("❌ 재분류 응답 파싱 실패")
        print(raw[:500])
        return

    # id → new_category 매핑
    reclass_map = {}
    for item in parsed.get('reclassified', []):
        new_cat = item.get('new_category', '기타')
        if new_cat not in VALID_CATEGORIES:
            new_cat = '기타'
        reclass_map[item['id']] = new_cat

    # 실제 데이터에 반영
    changed_count = 0
    for a in data['articles']:
        if a['id'] in reclass_map:
            old_cat = a['category']
            a['category'] = reclass_map[a['id']]
            print(f"  {a['id']}: '{old_cat}' → '{a['category']}' ({a['title'][:30]}...)")
            changed_count += 1

    # 혹시 매핑 안 된 기사가 있으면 안전하게 '기타'로
    for a in data['articles']:
        if a.get('category') == '보험시장' and a['id'] not in reclass_map:
            a['category'] = '기타'
            print(f"  {a['id']}: '보험시장' → '기타' (매핑 누락, 안전 처리)")
            changed_count += 1

    with open(UNIFIED_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"\n🎉 재분류 완료! 총 {changed_count}개 기사 카테고리 변경됨")


if __name__ == "__main__":
    recategorize()