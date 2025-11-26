# --- run_ai_analysis.py ---
import glob
import json
import sys
import os
from typing import List, Dict

# 프로젝트 모듈 임포트
from .engine import ProbDexEngine
from .model import (
    BaseModel, Field, ValidationError, model_validator,
    List, Dict, Literal, master_data, valid_subjects,
    AiAnalysis, PDFProbData, PDFProbResponse, problem_number_map
)
from .prob_data_processer import (
    initialize_xlsx, excel_to_json,
    update_problems_xlsx, update_problems_json,
    process_pdf_year_and_month, append_images_excel
)
from .database import (
    create_database, populate_subjects_and_units_tables,
    sync_database_from_json, initialize_database,
    insert_meta_data_user_db
)
from .utility_pdf import (
    process_all_raw_problem_pdfs,
    process_pdf_to_images,
    check_new_raw_pdf, process_raw_pdf_to_images
)
from .config import path
# --- ProbDex DB 파이프라인 단계 함수 정의 ---
# 1단계 DB 초기화
def run_initialize_database(is_user_db : bool = False):
    """
    [1단계] ProbDex DB 초기화
    DB 스키마 생성 및 마스터 테이블(subjects, units)을 채움
    """
    print("\n--- [1단계] ProbDex DB 초기화 시작 ---")
    try:
        initialize_database(is_user_db = is_user_db)
        print("  ✅ ProbDex DB 스키마 및 마스터 테이블 생성 완료.")
    except Exception as e:
        print(f"ProbDex DB 초기화 실패: {e}")
        return False
    return True

# 2단계 PDF 전처리
def run_preprocessing(source_pdf_path, processed_pdf_path, image_output_path):
    """
    [2단계] PDF 전처리
    원본 PDF를 분할하고 이미지로 변환
    """
 
    print("\n--- [2단계] PDF 전처리 (분할 및 이미지 변환) 시작 ---")
    
    # 2-1. PDF 분할
    try:
        process_all_raw_problem_pdfs(
            pdf_source_folder=source_pdf_path,
            pdf_output_folder=processed_pdf_path
        )
        print("  ✅ PDF 분할 완료.")
    except Exception as e:
        print(f"PDF 분할 중 오류: {e}")
        return False
        
    # 2-2. 이미지 변환
    try:
        process_pdf_to_images(
            pdf_input_path=processed_pdf_path,
            img_output_path=image_output_path
        )
        print("  ✅ PDF 이미지 변환 완료.")
    except Exception as e:
        print(f"이미지 변환 중 오류: {e}")
        return False
    
    return True

# 3단계 엑셀과 JSON 초기화
def run_initialize_base_files(image_path, excel_path, json_path):
    """
    [3단계] 생성된 이미지를 기반으로 엑셀과 JSON 초기화
    """

    print("\n--- [3단계] 기본 데이터 파일(XLSX, JSON) 생성 시작 ---")
    
    # 3-1. 엑셀 초기화 
    try:
        initialize_xlsx(
            problem_image_path=image_path,
            output_excel_path=excel_path
        )
        print("  ✅ 엑셀 파일(base_problems.xlsx) 생성 완료.")
    except Exception as e:
        print(f"엑셀 파일 생성 실패: {e}")
        return False
        
    # 3-2. JSON 변환 (엑셀 -> JSON)
    try:
        excel_to_json(
            excel_path=excel_path,
            output_path=json_path
        )
        print("  ✅ JSON 파일(base_problems.json) 생성 완료.")
    except Exception as e:
        print(f"JSON 파일 변환 실패: {e}")
        return False
        
    return True

# 4단계 AI 분석 및 파일 업데이트
def run_ai_analysis_for_all_pdfs(processed_pdf_path, json_path, excel_path):
    """
    [4단계] processed_pdfs 폴더의 모든 PDF를 순회하며 AI 분석을 실행하고
    JSON/XLSX 파일을 업데이트
    """

    print("\n--- [4단계] AI 일괄 분석 및 파일 업데이트 시작 ---")
    # skip 로직
    analyzed_pages_map = ProbDexEngine.get_analyzed_page_map(json_path)
    if analyzed_pages_map:
        print(f"  ✅ {len(analyzed_pages_map)}개 파일의 분석 기록을 확인했습니다.")
    
    '''
    # PDF 'subject_part' -> JSON 'subject_name' 매핑
    pdf_subject_to_json_subject = {
        "common": "공통",
        "cal": "미적분",
        "geo": "기하",
        "sta": "확률과 통계"
    }
    '''
    # (year, month, json_subject, stem) 튜플을 저장할 세트
    analyzed_pdf_stems = set() 
    
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            all_problems_data = json.load(f)
        
        for problem in all_problems_data:
            ai_data = problem.get('ai_analysis')

            if isinstance(ai_data, str):
                try:
                    ai_data = json.loads(ai_data)
                except json.JSONDecodeError:
                    ai_data = None  # 파싱 실패 시 None 처리

            # ai_analysis 필드가 비어있지 않다면 (None이나 빈 dict가 아님) 스킵
            if ProbDexEngine.is_ai_analysis_valid(ai_data):
                img_path = problem.get('problem_image_path', "")
                if img_path:
                    '''
                    # analyzed_files.add(stem)
                    stem = img_path.split('_p')[0]
                    year = problem.get('year')
                    month = problem.get('month')
                    subject = problem.get('subject_name')
                    analyzed_pdf_stems.add((year, month, subject, stem))
                    '''
                    stem = img_path.split('_p')[0]
                    analyzed_pdf_stems.add(stem)

        if analyzed_pdf_stems:
            print(f"  ✅ 기존 JSON(base_problems.json) 로드 완료. {len(analyzed_pdf_stems)}개의 분석 파일 그룹을 확인")
        else:
            print(f"정보: base_problems.json을 로드했으나, 분석된 데이터가 없습니다.")
            
    except FileNotFoundError:
        print(f"정보: base_problems.json을 찾을 수 없습니다. 모든 파일을 신규 분석합니다.")
    except Exception as e:
        print(f"경고: base_problems.json 로드 중 오류: {e}.")

    # AI 엔진 초기회
    try:
        engine = ProbDexEngine()
    except Exception as e:
        print(f"AI 엔진 초기화 실패: {e}")
        return False
        
    # 처리할 PDF 목록 탐색
    pdf_files_to_process = glob.glob(os.path.join(processed_pdf_path, "*.pdf"))
    
    if not pdf_files_to_process:
        print("분석할 PDF 파일이 'processed_pdfs' 폴더에 없습니다.")
        return False
        
    print(f"총 {len(pdf_files_to_process)}개의 PDF 파일을 분석합니다.")

    for pdf_path in pdf_files_to_process:
        filename = os.path.basename(pdf_path) # 예: kice_2024_06_cal_split.pdf
        current_stem = os.path.splitext(filename)[0] # 예: kice_2024_06_cal_split
        # 스킵 로직
        skip_pages = analyzed_pages_map.get(current_stem, set())
        '''
        if current_stem in analyzed_pdf_stems:
            print(f"\n  [SKIP] {filename} (이미 분석 완료됨)")
            continue # <-- 이 코드가 있어야 API를 호출하지 않고 건너뜁니다!
        
        if current_stem in analyzed_pdf_stems:
            print(f"\n  [SKIP] {filename} (이미 분석 완료됨)")
            continue # API호출하지 않고 건너뜀
        '''
        print(f"\n  --- [AI 분석 시작] {os.path.basename(pdf_path)} ---")
        if skip_pages:
            print(f" 이미 완료된 {len(skip_pages)}개 페이지는 건너뜁니다. {sorted(list(skip_pages))}")
        try:
            # AI 분석 호출 및 메타데이터 추출
            
            all_prob_data = engine.extract_pdf_meta_data(pdf_path, skip_pages=skip_pages)

            if all_prob_data:
                print(f"  ✅ {os.path.basename(pdf_path)} 분석 완료. {len(all_prob_data)}개 문제 발견.")
                '''
                # JSON 업데이트
                update_problems_json(
                    problems=all_prob_data, 
                    json_path=path["base_problems_json"]
                )
                '''
                # XLSX 업데이트
                update_problems_xlsx(
                    problems=all_prob_data, 
                    excel_path=excel_path,
                    unicode_text=True,
                    backup=False # (일괄 처리 중에는 백업 비활성화)
                )
                # XLSX -> JSON 동기화
                excel_to_json(
                    excel_path=excel_path,
                    output_path=json_path
                )
                print(f"  ✅ JSON/XLSX 파일에 all_prob_data 업데이트 완료.")
                analyzed_pdf_stems.add(current_stem)
                
            else:
                print(f"{os.path.basename(pdf_path)}에서 AI가 추출한 문제가 없습니다.")
                
        except Exception as e:
            print(f"{os.path.basename(pdf_path)} 처리 중 심각한 오류 발생: {e}")
            
    print("\n  ✅ AI 일괄 분석 작업 완료.")
    return True

# 5단계 DB 동기화
def run_sync_database(json_path, db_path,is_user_db: bool):
    """
    [5단계] JSON 데이터를 DB에 동기화
    """
    print("\n--- [5단계] DB 동기화 시작 ---")
    try:
        print("DB 스키마 점검 중...")
        create_database(is_user_db = is_user_db) 
    except Exception as e:
        print(f"DB 스키마 점검 실패 (무시하고 진행): {e}")
    
    try:
        print("마스터 데이터(과목/단원) 점검 중...")
        populate_subjects_and_units_tables(is_user_db = is_user_db)
    except Exception as e:
        print(f"마스터 데이터 입력 실패: {e}")

    try:
        sync_database_from_json(json_path, db_path, is_user_db)
        print("  ✅ DB 동기화 완료.")
    except Exception as e:
        print(f"DB 동기화 실패: {e}")
        return False
    return True


# --- 실행 파이프라인 ---

# 시스템 초기화 파이프라인
def run_system_initialization():
    """
    [초기화 파이프라인]
    경고: 기존 데이터를 모두 지우고 새로 생성합니다.
    실행 단계: 1(DB) -> 2(PDF) -> 3(File Init)
    """
    print("\n" + "="*50)
    print("[경고] 시스템 초기화 모드 실행")
    print("이 작업은 'base_problems.xlsx' 및 'base_problems.json'의")
    print("모든 기존 분석 데이터를 삭제하고 초기화합니다.")
    print("="*50)
    
    user_input = input("정말 초기화하시겠습니까? (y/n): ").strip().lower()
    if user_input != 'y':
        print("초기화 작업을 취소합니다.")
        return
    #  DB 초기화
    if not run_initialize_database(): return
    # PDF 전처리
    if not run_preprocessing(path["raw_problem_pdfs"], path["processed_pdfs"], path["problem_images"]): return
    # 엑셀 및 JSON 초기화
    if not run_initialize_base_files(
        path["problem_images"],
        path["base_problems_xlsx"], 
        path["base_problems_json"]
        ): return 

    print("\n 시스템 초기화가 완료되었습니다. 모든 데이터가 초기 상태로 재설정되었습니다.")

# 시스템 동작 전처리 파이프라인
def run_add_new_files():
    """
    전처리 파이프라인
    1) 신규 raw PDF 탐색
    2) PDF → 분할 → 이미지 생성
    3) 이미지 기반 문제 Excel 추가
    4) JSON 동기화
    """
    print("\n" + "="*50)
    print("신규 파일 감지 및 업데이트")
    print("="*50)

    new_files = check_new_raw_pdf(
        pdf_input_path=path["raw_problem_pdfs"],
        processed_pdf_path=path["processed_pdfs"]
    )

    if not new_files:
        print("새로운 PDF 파일이 없습니다.")
        return

    for raw_pdf_path in new_files:
        filename = os.path.basename(raw_pdf_path)
        print(f"\n처리 대상: {filename}")

        # PDF → 이미지 변환
        generated_images = process_raw_pdf_to_images(
            raw_pdf_path=raw_pdf_path,
            processed_pdf_path=path["processed_pdfs"],
            image_path=path["problem_images"]
        )

        # 이미지 기반 엑셀 append
        append_images_excel(
            image_paths=generated_images,
            excel_path=path["base_problems_xlsx"]
        )

    # JSON 동기화
    excel_to_json(path["base_problems_xlsx"], path["base_problems_json"])

    print("\n모든 신규 파일 처리 완료.")

# AI 분석 및 DB 동기화 파이프라인
def run_ai_analysis_and_sync():
    """
    [분석 및 업데이트 파이프라인]
    기존 데이터를 유지하며 AI 분석 결과를 추가/업데이트합니다.
    실행 단계: 4(AI Analysis) -> 5(DB Sync)
    """
    print("\n" + "="*50)
    print("AI 분석 및 데이터 동기화 모드 실행")
    print("="*50)

    if not run_ai_analysis_for_all_pdfs(
        path["processed_pdfs"],
        path["base_problems_json"],
        path["base_problems_xlsx"]
    ): return
    if not run_sync_database(
        path["base_problems_json"],
        path["db"],
        is_user_db = False
    ): return

    print("\n모든 분석 및 동기화 작업이 완료되었습니다.")

# 전체 파이프라인 실행 함수
def run_ProbDex_pipeline(initialization: bool = False):
    """
    ProbDex 전체 파이프라인 실행을 통제하는 마스터 함수
    initialization이 True이면 초기화 파이프라인을 실행
    """
    if initialization == True:
        # [초기화] 모든 데이터 삭제 후 재구축
        run_system_initialization()
    else:
        # [평상시 실행]
        run_add_new_files()
        run_ai_analysis_and_sync()


# --- user_probdex.db 파이프라인 단계 함수 정의 ---

# user 초기화 파이프라인
def run_user_initialization():
    """
    [초기화 파이프라인]
    경고: 기존 데이터를 모두 지우고 새로 생성합니다.
    실행 단계: 1(DB) -> 2(PDF) -> 3(File Init)
    """
    print("\n" + "="*50)
    print("[경고] 시스템 초기화 모드 실행")
    print("이 작업은 'user_base_problems.xlsx' 및 'user_base_problems.json'의")
    print("모든 기존 분석 데이터를 삭제하고 초기화합니다.")
    print("="*50)
    
    user_input = input("정말 초기화하시겠습니까? (y/n): ").strip().lower()
    if user_input != 'y':
        print("초기화 작업을 취소합니다.")
        return
    #  DB 초기화
    if not run_initialize_database(is_user_db=True): return
    # PDF 전처리
    if not run_preprocessing(path["user_pdf_problems"], path["user_processed_pdfs"], path["user_problem_images"]): return
    # 엑셀 및 JSON 초기화
    if not run_initialize_base_files(
        path["user_problem_images"],
        path["user_base_problems_xlsx"], 
        path["user_base_problems_json"]
        ): return 

    print("\n 시스템 초기화가 완료되었습니다. 모든 데이터가 초기 상태로 재설정되었습니다.")

# user 전처리 파이프라인
def run_user_add_new_files():
    """
    전처리 파이프라인
    1) 신규 raw PDF 탐색
    2) PDF → 분할 → 이미지 생성
    3) 이미지 기반 문제 Excel 추가
    4) JSON 동기화
    """
    print("\n" + "="*50)
    print("신규 파일 감지 및 업데이트")
    print("="*50)

    new_files = check_new_raw_pdf(
        pdf_input_path=path["user_pdf_problems"],
        processed_pdf_path=path["user_processed_pdfs"]
    )

    if not new_files:
        print("새로운 PDF 파일이 없습니다.")
        return

    for raw_pdf_path in new_files:
        filename = os.path.basename(raw_pdf_path)
        print(f"\n처리 대상: {filename}")

        # PDF → 이미지 변환
        generated_images = process_raw_pdf_to_images(
            raw_pdf_path=raw_pdf_path,
            processed_pdf_path=path["user_processed_pdfs"],
            image_path=path["user_problem_images"]
        )

        # 이미지 기반 엑셀 append
        append_images_excel(
            image_paths=generated_images,
            excel_path=path["user_base_problems_xlsx"]
        )

    # JSON 동기화
    excel_to_json(path["user_base_problems_xlsx"], path["user_base_problems_json"])
    print("\n모든 신규 파일 처리 완료.")

# user AI 분석 및 DB 동기화 파이프라인
def run_user_ai_analysis_and_sync():
    """
    [분석 및 업데이트 파이프라인]
    기존 데이터를 유지하며 AI 분석 결과를 추가/업데이트합니다.
    실행 단계: 4(AI Analysis) -> 5(DB Sync)
    """
    print("\n" + "="*50)
    print("AI 분석 및 데이터 동기화 모드 실행")
    print("="*50)

    if not run_ai_analysis_for_all_pdfs(
        path["user_processed_pdfs"],
        path["user_base_problems_json"],
        path["user_base_problems_xlsx"]
    ): return
    if not run_sync_database(
        path["user_base_problems_json"],
        path["user_db"],
        is_user_db = True
    ): return

    print("\n모든 분석 및 동기화 작업이 완료되었습니다.")

# user 전체 파이프라인 실행 함수
def run_user_ProbDex_pipeline(initialization: bool = False):
    """
    ProbDex 전체 파이프라인 실행을 통제하는 마스터 함수
    initialization이 True이면 초기화 파이프라인을 실행
    """
    if initialization == True:
        # [초기화] 모든 데이터 삭제 후 재구축
        run_user_initialization()
    else:
        # [평상시 실행]
        run_user_add_new_files()
        run_user_ai_analysis_and_sync()



# __user_probdex.db 이전 파이프라인
def __run_preprocessing_user():
    """
    [2단계] PDF 전처리
    원본 PDF를 분할하고 이미지로 변환
    """
 
    print("\n--- [2단계] PDF 전처리 (분할 및 이미지 변환) 시작 ---")
    
    # 2-1. PDF 분할
    try:
        process_all_raw_problem_pdfs(
            pdf_source_folder=path["user_pdf_problems"],
            pdf_output_folder=path["user_processed_pdfs"]
        )
        print("  ✅ PDF 분할 완료.")
    except Exception as e:
        print(f"PDF 분할 중 오류: {e}")
        return False
        
    # 2-2. 이미지 변환
    try:
        process_pdf_to_images(
            pdf_input_path=path["processed_pdfs"],
            img_output_path=path["problem_images"]
        )
        print("  ✅ PDF 이미지 변환 완료.")
    except Exception as e:
        print(f"이미지 변환 중 오류: {e}")
        return False
    
    return True

def __run_user_initialization():
    """
    [초기화 파이프라인]
    경고: 기존 데이터를 모두 지우고 새로 생성합니다.
    실행 단계: 1(DB) -> 2(PDF) 
    """
    print("\n" + "="*50)
    print("[경고] 시스템 초기화 모드 실행")
    print("이 작업은 'user_probdex.db'의")
    print("모든 기존 분석 데이터를 삭제하고 초기화합니다.")
    print("="*50)
    
    user_input = input("정말 초기화하시겠습니까? (y/n): ").strip().lower()
    if user_input != 'y':
        print("초기화 작업을 취소합니다.")
        return
    #  DB 초기화
    if not run_initialize_database(is_user_db=True): return
    # PDF 전처리
    # if not run_preprocessing(path["user_raw_problems"]): return

def __run_user_database_pipeline(initialization: bool = False):
    """
    user_probdex.db 파이프라인 실행함수
    """
    if initialization == True:
        # [초기화] user_probdex.db 초기화
        run_initialize_database(is_user_db = True)
    else:
        # [평상시 실행]
        engine = ProbDexEngine()
        meta_data = engine.analyze_pdf_user_meta_data(
            user_pdf_path = path["user_processed_pdfs"]
            )
        insert_meta_data_user_db(problems=meta_data, is_user_db=True)




if __name__ == "__main__":
    # 이 스크립트를 직접 실행하면 전체 파이프라인이 작동합니다.
    # poetry run python -m src.my_first_project.probdex_pipeline
    
    # (경로 설정이 config.py에서 올바르게 되었는지 확인)
    print(f"프로젝트 루트: {path['root']}")
    print(f"원본 PDF 폴더: {path['raw_problem_pdfs']}")
    print(f"처리된 PDF 폴더: {path['processed_pdfs']}")
    print(f"이미지 폴더: {path['problem_images']}")

    run_ProbDex_pipeline(initialization= False)
    # run_user_ProbDex_pipeline(initialization= False)







