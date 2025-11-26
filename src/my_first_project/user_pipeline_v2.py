# --- user_pipeline_v2.py ---
import os
import sys
import sqlite3
# 프로젝트 모듈 임포트
from .config import path
from .engine import ProbDexEngine
from .database import (
    initialize_database, 
    get_problem_candidates_by_unit,
    connect_db,
    find_unit_id,
    upsert_problem,
    sync_concepts
)
from .similarity_v2 import calculate_advanced_score, get_recommendations

def safe_insert_meta_data_user_db(problems: list, is_user_db: bool = True):
    """
    [수정된 DB 저장 함수]
    기존 database.insert_meta_data_user_db의 문제를 해결하기 위해 재정의함.
    - unit_id가 None일 경우 예외 처리
    - 상세한 에러 로깅 추가
    """
    if not problems:
        print("저장할 문제 데이터가 없습니다.")
        return

    # 대상 DB 연결
    db_path = path["user_db"] if is_user_db else path["db"]
    
    # [수정] 출력 문구 변경
    db_label = 'User DB' if is_user_db else 'System DB'
    print(f"\n--- [V2] {db_label}  저장 시작 ---")
    
    connection = None
    try:
        connection = sqlite3.connect(db_path)
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys = ON;")

        success_count = 0

        for prob in problems:
            try:
                # Pydantic 모델 -> 딕셔너리 변환
                item = prob.model_dump(exclude_none=True)

                # Unit ID 찾기
                unit_id = find_unit_id(cursor, prob.subject_name, prob.unit_name)
                
                # 만약 unit_id를 못 찾으면 '분류 불가'로 재시도하거나, 그래도 없으면 에러 로깅 후 스킵
                if unit_id is None:
                    # print(f"  [경고] 단원 ID를 찾을 수 없음: {prob.subject_name} > {prob.unit_name}") # 경고 최소화
                    # '분류 불가' 시도
                    unit_id = find_unit_id(cursor, prob.subject_name, "분류 불가")
                    # if unit_id:
                    #      print(f"   -> '분류 불가' 단원으로 대체 저장합니다.")
                
                if unit_id is None:
                    print(f"   -> 저장 실패: 유효한 단원 ID가 없습니다. (Subject: {prob.subject_name})")
                    continue

                ai_obj = prob.ai_analysis
                
                # upsert_problem이 기대하는 ai 딕셔너리 구조 생성
                ai_data_formatted = {
                    "pattern_type": ", ".join(ai_obj.pattern_type) if ai_obj else "",
                    "logic_flow": ai_obj.logic_flow if ai_obj else "",
                    "pitfalls": ", ".join(ai_obj.pitfalls) if ai_obj else "",
                    "difficulty": ai_obj.difficulty_level if ai_obj else 0,
                }

                # item 딕셔너리에 필요한 키가 없으면 채워넣음 
                if "source_data" not in item:
                    item["source_data"] = f"{prob.year} {prob.month} {prob.subject_name} {prob.number}번"
                
                # DB 저장 (upsert)
                upsert_problem(cursor, item, unit_id, ai_data_formatted)

                # 방금 저장된 ID 확인
                current_pid = item.get("problem_id")
                if not current_pid:
                    current_pid = cursor.lastrowid 
                
                # 개념 태그 동기화
                if ai_obj and ai_obj.core_concepts and current_pid:
                    sync_concepts(cursor, current_pid, ai_obj.core_concepts)
                
                success_count += 1

            except Exception as e:
                print(f"  [오류] 문제 저장 실패 (Num: {prob.number}): {e}")

        connection.commit()
        print(f"✅ 총 {success_count}개의 문제를 DB에 성공적으로 저장했습니다.")

    except Exception as e:
        print(f"DB 저장 중 치명적 오류: {e}")
        if connection: connection.rollback()
    finally:
        if connection: connection.close()

def run_problem_search_service_v2(input_pdf_filename: str):
    """
    [검색 서비스 V2 메인 함수]
    1. 사용자 PDF 입력 -> AI 분석 -> User DB 저장 (Fixed Logic)
    2. Master DB(probdex.db)와 유사도 매칭 (Advanced Logic)
    3. 결과 출력
    """
    
    # 1. 입력 파일 경로 설정
    user_pdf_path = os.path.join(path["user_pdf_problems"], input_pdf_filename)
    
    if not os.path.exists(user_pdf_path):
        print(f"입력 파일을 찾을 수 없습니다: {user_pdf_path}")
        return

    # [수정] 시작 문구 변경
    print(f"\n [ProbDex V2 프로그램 시작] 입력 파일: {input_pdf_filename}")

    # [1단계] 사용자 DB 초기화 (Reset)
    print("\n[1단계] 사용자 DB 초기화...")
    if not initialize_database(is_user_db=True):
        print(" DB 초기화 실패로 중단합니다.")
        return

    # [2단계] AI 분석 (User PDF -> Metadata)
    # [수정] [Step 2] 제거
    print("\nAI 문제 분석 중...")
    try:
        engine = ProbDexEngine() 
        
        # PDF 분석
        analyzed_problems = engine.extract_pdf_meta_data(user_pdf_path)
        
        if not analyzed_problems:
            print(" 문제 분석 실패: 추출된 데이터가 없습니다.")
            return
            
    except Exception as e:
        print(f"AI 분석 중 오류 발생: {e}")
        return

    # [3단계] 분석 결과 User DB 저장 (Fixed)
    # [수정] [Step 3] 제거
    print("\n분석 데이터 User DB 저장 (V2)...")
    try:
        safe_insert_meta_data_user_db(analyzed_problems, is_user_db=True)
    except Exception as e:
        print(f"DB 저장 실패: {e}")
        return
    
    # [4단계] 유사도 매칭 및 결과 리포트 (Advanced)
    print("\n 유사 문항 검색 및 매칭 시작 (TF-IDF 적용)...\n")

    for user_prob in analyzed_problems:
        print(f"[검색 대상] {user_prob.subject_name} > {user_prob.unit_name} (입력 번호: {user_prob.number})")
        
        # 후보군 조회
        candidates = get_problem_candidates_by_unit(user_prob.subject_name, user_prob.unit_name)
        
        if not candidates:
            print(f" 해당 단원({user_prob.unit_name})의 기출문제가 데이터베이스에 없습니다.")
            continue
            
        print(f"  -> DB 후보군 {len(candidates)}개 발견. 정밀 유사도(TF-IDF) 계산 중...")
        
        # 유사도 점수 계산 
        scored_candidates = []
        for cand in candidates:
            # V2: Advanced Score Calculation
            score_data = calculate_advanced_score(user_prob, cand)
            
            cand['match_score'] = score_data
            scored_candidates.append(cand)
            
        # 점수순 정렬
        scored_candidates.sort(key=lambda x: x['match_score']['total_score'], reverse=True)
        
            # Top Matches 출력
        if scored_candidates:
            top_match = scored_candidates[0]
            
            print("\n" + "═"*60)
            print(f"🏆 최고 유사도: {top_match['match_score']['total_score']}%")
            print("─"*60)
            print(f"• 원본 출처: {top_match.get('source_text', '출처 미상')}")
            print(f"• 이미지 경로: {top_match.get('problem_image_path', '이미지 없음')}")
            print(f"• 난이도 비교: 입력({user_prob.ai_analysis.difficulty_level}) vs 원본({top_match['difficulty_level']})")
            print(f"• 매칭 상세 점수: {top_match['match_score']['details']}")
            print("─"*60)
            
            # [GUI Data Protocol] Best Match
            # Runners-up info construction
            runners_up_str = ""
            runners_up = scored_candidates[1:4]
            if runners_up:
                runners_list = []
                for idx, runner in enumerate(runners_up, 1):
                    runners_list.append(f"{idx}. [유사도: {runner['match_score']['total_score']}%] {runner.get('source_text', 'Unknown')}")
                runners_up_str = "^".join(runners_list) # Use ^ as delimiter for runners-up

            # Format: ||GUI_DATA||{image_path}||{score}||{title}||{user_prob_num}||{runners_up_str}
            print(f"||GUI_DATA||{top_match.get('problem_image_path', '')}||{top_match['match_score']['total_score']}%||{top_match.get('source_text', 'Unknown')}||{user_prob.number}||{runners_up_str}")
            
            img_path = best_data.get('problem_image_path', '')
            src_text = best_data.get('source_data') or best_data.get('source_text', '출처 미상')
            
            # 추가 유사 문제 (Console Output)
            if runners_up:
                print(f"[추가 유사 문항 (Top {len(runners_up)})]")
                for idx, runner in enumerate(runners_up, 1):
                    # [수정] ID 출력 부분 삭제
                    print(f"  {idx}. [{runner['match_score']['total_score']}%] {runner.get('source_text')}")
            print("═"*60 + "\n")
        else:
            print("  (매칭되는 유사 문제가 없습니다.)\n")

