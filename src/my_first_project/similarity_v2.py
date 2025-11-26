# --- similarity_advanced.py ---
import numpy as np
import re
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

def normalize_text(text):
    """
    [강력한 정규화]
    1. 태그를 먼저 완벽하게 제거
    2. 그 후 특수문자와 공백을 제거하여 순수 내용만 남김
    """
    if not isinstance(text, str): return ""
    
    text = re.sub(r'\\\\', '', text)

    text = re.sub(r'\\', '', text)

    text = re.sub(r'[^가-힣a-zA-Z0-9]', '', text)
    
    return text

def calculate_jaccard_similarity(list1, list2):
    """
    자카드 유사도: (교집합 개수) / (합집합 개수)
    (기존 로직 유지 - 태그/개념 매칭용)
    """
    set1 = set(list1)
    set2 = set(list2)
    
    if not set1 and not set2: return 0.0
    
    intersection = len(set1.intersection(set2))
    union = len(set1.union(set2))
    return intersection / union if union > 0 else 0.0

def calculate_cosine_similarity_text(text1: str, text2: str) -> float:
    """
    TF-IDF + Cosine Similarity for text fields.
    """
    if not text1 or not text2:
        return 0.0
    
    try:
        # 2개의 텍스트를 벡터화
        vectorizer = TfidfVectorizer()
        tfidf_matrix = vectorizer.fit_transform([text1, text2])
        
        # 코사인 유사도 계산 (1x1 행렬 반환)
        score = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:2])[0][0]
        return float(score)
    except ValueError:
        # 어휘가 없거나 너무 짧아서 벡터화 실패 시 0점 처리
        return 0.0

def calculate_advanced_score(user_prob, candidate):
    """
    [고급 유사도 점수 계산]
    1. 핵심 개념 (Core Concepts): 30% (Jaccard)
    2. 논리 구조 (Logic Flow): 40% (TF-IDF Cosine)
    3. 패턴/함정 (Pattern/Pitfalls): 20% (Jaccard or Text)
    4. 난이도 (Difficulty): 10% (Distance based)
    
    * problem_id는 사용하지 않음.
    """
    
    # 1. 핵심 개념 일치도 (30%) - 태그 성격이므로 Jaccard 유지
    user_concepts = user_prob.ai_analysis.core_concepts
    cand_concepts = candidate['core_concepts']
    score_concepts = calculate_jaccard_similarity(user_concepts, cand_concepts) * 30

    # 2. 논리 구조 유사도 (40%) - 문장형이므로 TF-IDF 적용
    user_logic = user_prob.ai_analysis.logic_flow
    cand_logic = candidate['logic_flow']
    score_logic = calculate_cosine_similarity_text(user_logic, cand_logic) * 40

    # 3. 평가 목표(패턴/함정) 유사도 (20%) - 텍스트 결합 후 TF-IDF 적용이 더 나을 수 있음
    # 기존 Jaccard 방식보다 텍스트 유사도가 뉘앙스를 더 잘 잡을 수 있음
    user_pattern_str = " ".join(user_prob.ai_analysis.pattern_type + user_prob.ai_analysis.pitfalls)
    cand_pattern_str = " ".join(candidate['pattern_type'] + candidate['pitfalls'])
    
    # 텍스트가 너무 짧으면 Jaccard가 나을 수도 있지만, 일관성을 위해 Cosine 시도
    # 혹은 리스트 형태가 강하다면 Jaccard로 회귀. 여기서는 텍스트 유사도로 시도해봄.
    score_goal = calculate_cosine_similarity_text(user_pattern_str, cand_pattern_str) * 20

    # 4. 난이도 유사도 (10%)
    user_diff = user_prob.ai_analysis.difficulty_level
    cand_diff = candidate['difficulty_level']
    diff_gap = abs(user_diff - cand_diff)
    score_diff = max(0, (4 - diff_gap) * 2.5) # (4 - 차이) * 2.5 => 0차이:10, 1차이:7.5

    total_score = score_concepts + score_logic + score_goal + score_diff
    
    return {
        "total_score": round(total_score, 2),
        "details": {
            "concept": round(score_concepts, 1),
            "logic": round(score_logic, 1),
            "goal": round(score_goal, 1),
            "diff": round(score_diff, 1)
        }
    }

def get_recommendations(user_prob, db_candidates, top_k=3):
    """
    사용자 문제와 DB 후보군을 비교하여 추천 문항을 반환하는 메인 함수
    """
    
    # [Step 1: 완전 일치 우선 탐색]
    # 1. 사용자 입력 텍스트 정규화 (공백, 태그 제거)
    user_logic_norm = normalize_text(user_prob.ai_analysis.logic_flow)
    
    # 2. DB 전체를 순회하며 "완전 일치" 여부 확인
    for idx, candidate in enumerate(db_candidates):
        # DB 데이터 정규화
        db_logic_norm = normalize_text(candidate.get('logic_flow', ''))
        
        # 3. 내용이 포함되거나 일치하면 즉시 반환 (계산 생략)
        if user_logic_norm and (user_logic_norm in db_logic_norm or db_logic_norm in user_logic_norm):
            print(f" 100% 일치하는 원본 문제를 발견했습니다! (ID: {candidate['problem_id']})")
            
            # 강제 100점 부여 후 즉시 리턴
            return [{
                'id': candidate['problem_id'],
                'score': 100.0,
                'data': candidate,
                'similarity_details': {'exact_match': True, 'concept': 30, 'logic': 40, 'goal': 20, 'diff': 10}
            }]

    # [Step 2: 기존 유사도 점수 계산 로직] (기존 코드 실행)
    results = []
    for candidate in db_candidates:
        # 위에서 정의한 calculate_advanced_score 함수 호출
        score_data = calculate_advanced_score(user_prob, candidate)
        
        results.append({
            'id': candidate['problem_id'],
            'score': score_data['total_score'],
            'data': candidate,
            'similarity_details': score_data['details']
        })

    # 점수순 정렬 및 상위 k개 반환
    results.sort(key=lambda x: x['score'], reverse=True)
    return results[:top_k]