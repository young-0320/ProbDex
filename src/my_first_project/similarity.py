# --- similarity.py ---
import re

def calculate_jaccard_similarity(list1, list2):
    """
    자카드 유사도: (교집합 개수) / (합집합 개수)
    """
    set1 = set(list1)
    set2 = set(list2)
    
    if not set1 and not set2: return 0.0
    
    intersection = len(set1.intersection(set2))
    union = len(set1.union(set2))
    return intersection / union if union > 0 else 0.0

def calculate_text_similarity(text1, text2):
    """
    단순 텍스트 유사도 (키워드 매칭 방식)
    """
    if not text1 or not text2: return 0.0
    
    # 간단하게 단어 단위로 쪼개서 자카드 유사도 적용 (한국어 형태소 분석기 없이)
    # 실제로는 KoNLPy 등을 쓰면 더 정확함
    words1 = set(re.findall(r'\w+', text1))
    words2 = set(re.findall(r'\w+', text2))
    
    intersection = len(words1.intersection(words2))
    union = len(words1.union(words2))
    return intersection / union if union > 0 else 0.0

def calculate_total_score(user_prob, candidate):
    """
    [종합 유사도 점수 계산]
    1. 핵심 개념 (Core Concepts): 40%
    2. 논리 구조 (Logic Flow): 30%
    3. 패턴/함정 (Pattern/Pitfalls): 20%
    4. 난이도 (Difficulty): 10% (가까울수록 점수 높음)
    """
    
    # 1. 핵심 개념 일치도 (40%)
    # user_prob.ai_analysis.core_concepts는 리스트임
    user_concepts = user_prob.ai_analysis.core_concepts
    cand_concepts = candidate['core_concepts']
    score_concepts = calculate_jaccard_similarity(user_concepts, cand_concepts) * 40

    # 2. 논리 구조 유사도 (30%)
    user_logic = user_prob.ai_analysis.logic_flow
    cand_logic = candidate['logic_flow']
    score_logic = calculate_text_similarity(user_logic, cand_logic) * 30

    # 3. 평가 목표(패턴/함정) 유사도 (20%)
    user_pattern = user_prob.ai_analysis.pattern_type + user_prob.ai_analysis.pitfalls
    cand_pattern = candidate['pattern_type'] + candidate['pitfalls']
    score_goal = calculate_jaccard_similarity(user_pattern, cand_pattern) * 20

    # 4. 난이도 유사도 (10%)
    # 차이가 0이면 10점, 1이면 7.5점, 2면 5점...
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