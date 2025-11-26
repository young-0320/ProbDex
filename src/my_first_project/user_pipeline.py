# --- user_pipeline.py ---
import os
import sys
# 프로젝트 모듈 임포트
from .config import path
from .engine import ProbDexEngine
from .database import (
    initialize_database, 
    insert_meta_data_user_db, 
    get_problem_candidates_by_unit
)
from .similarity import calculate_total_score

def run_problem_search_service(input_pdf_filename: str):
    """
    [검색 서비스 메인 함수]
    1. 사용자 PDF 입력 -> AI 분석 -> User DB 저장 (Direct)
    2. Master DB(probdex.db)와 유사도 매칭
    3. 결과 출력 (유사도 점수 및 이미지 경로)
    """
    
    # 1. 입력 파일 경로 설정 (config.py의 user_pdf_problems 경로 사용)
    user_pdf_path = os.path.join(path["user_pdf_problems"], input_pdf_filename)
    
    if not os.path.exists(user_pdf_path):
        print(f"입력 파일을 찾을 수 없습니다: {user_pdf_path}")
        return

    print(f"\n [ProbDex 검색 서비스] 시작: {input_pdf_filename}")

    # [1단계] 사용자 DB 초기화 (Reset)

    print("\n[1단계] 사용자 DB 초기화...")
    if not initialize_database(is_user_db=True):
        print(" DB 초기화 실패로 중단합니다.")
        return

    # [2단계] AI 분석 (User PDF -> Metadata)
    print("\n[Step 2] AI 문제 분석 중...")
    try:
        engine = ProbDexEngine() 
        
        # PDF 분석 (페이지 분할 및 AI 추출 포함)
        analyzed_problems = engine.extract_pdf_meta_data(user_pdf_path)
        
        if not analyzed_problems:
            print(" 문제 분석 실패: 추출된 데이터가 없습니다.")
            return
            
    except Exception as e:
        print(f"AI 분석 중 오류 발생: {e}")
        return

    # [3단계] 분석 결과 User DB 저장 (Direct)
    print("\n[Step 3] 분석 데이터 User DB 저장...")
    try:
        insert_meta_data_user_db(analyzed_problems, is_user_db=True)
    except Exception as e:
        print(f"DB 저장 실패: {e}")
        return
    
    # [4단계] 유사도 매칭 및 결과 리포트
    print("\n [4단계] 유사 문항 검색 및 매칭 시작...\n")

    for user_prob in analyzed_problems:
        print(f"[검색 대상] {user_prob.subject_name} > {user_prob.unit_name} (입력 번호: {user_prob.number})")
        
        # 후보군 조회 (Master DB에서 같은 과목/단원 문제 가져오기)
        candidates = get_problem_candidates_by_unit(user_prob.subject_name, user_prob.unit_name)
        
        if not candidates:
            print(f" 해당 단원({user_prob.unit_name})의 기출문제가 데이터베이스에 없습니다.")
            continue
            
        print(f"  -> DB 후보군 {len(candidates)}개 발견. 정밀 유사도 계산 중...")

        # 유사도 점수 계산 
        scored_candidates = []
        for cand in candidates:
            # calculate_total_score는 점수 딕셔너리를 반환함
            score_data = calculate_total_score(user_prob, cand)
            
            # 후보 딕셔너리에 점수 정보 추가
            cand['match_score'] = score_data
            scored_candidates.append(cand)
            
        # 점수순 정렬 (높은 점수 우선)
        scored_candidates.sort(key=lambda x: x['match_score']['total_score'], reverse=True)
        
        # Top Matches 출력
        if scored_candidates:
            top_match = scored_candidates[0]
            
            print("\n" + "═"*60)
            print(f"유사도: {top_match['match_score']['total_score']}%")
            print("─"*60)
            print(f"• 원본 출처: {top_match.get('source_text', '출처 미상')}")
            print(f"• 이미지 경로: {top_match.get('problem_image_path', '이미지 없음')}")
            print(f"• 난이도 비교: 입력({user_prob.ai_analysis.difficulty_level}) vs 원본({top_match['difficulty_level']})")
            print(f"• 매칭 상세 점수: {top_match['match_score']['details']}")
            print("─"*60)
            
            # 추가 유사 문제 
            runners_up = scored_candidates[1:4]
            if runners_up:
                print(f"[추가 추천 문항 (Top {len(runners_up)})]")
                for idx, runner in enumerate(runners_up, 1):
                    print(f"  {idx}. [{runner['match_score']['total_score']}%] {runner.get('source_text')} (ID: {runner['problem_id']})")
                    # print(f"     이미지: {runner.get('problem_image_path')}")
            print("═"*60 + "\n")
        else:
            print("  (매칭되는 유사 문제가 없습니다.)\n")

if __name__ == "__main__":
    # 테스트 실행
    # poetry run python -m src.my_first_project.user_pipeline
    # user_input/input_pdf_problems 폴더 안에 해당 파일이 있어야 합니다.
    test_file = "2023_03.pdf" 
    run_problem_search_service(test_file)