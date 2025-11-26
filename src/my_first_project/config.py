# --- config.py: 프로젝트 전역 설정 파일 ---

import os
from pathlib import Path

# 경로 설정
script_dir = os.path.dirname(os.path.abspath(__file__))
# 프로젝트 루트 경로 
project_root_path = os.path.dirname(os.path.dirname(script_dir))
# assets 폴더 경로
assets_path = os.path.join(project_root_path, "assets")
assets_raw_problem_pdfs = os.path.join(assets_path, "raw_problem_pdfs")
assets_processed_pdfs = os.path.join(assets_path, "processed_pdfs")
assets_problem_images = os.path.join(assets_path, "problem_images")
assets_base_problems_JSON = os.path.join(assets_path, "base_problems.json")
assets_base_problems_xlsx = os.path.join(assets_path, "base_problems.xlsx")
# DB 파일 경로
probdex_db_path = os.path.join(project_root_path, "probdex.db")
user_db_path = os.path.join(project_root_path, "user_probdex.db")
# user 폴더 경로
user_input_path = os.path.join(project_root_path, "user_input")
user_input_pdf_problems = os.path.join(user_input_path, "input_pdf_problems")
user_input_images_problems = os.path.join(user_input_path, "input_images_problems")
user_input_processed_pdfs = os.path.join(user_input_path, "user_processed_pdfs")
user_input_problem_images = os.path.join(user_input_path, "user_problem_images")
# 테스트 PDF 파일 경로 설정
test_pdf_name = "kice_2022_06_cal_split.pdf"
test_pdf_path = os.path.join(assets_processed_pdfs, test_pdf_name)

# 전체 경로 딕셔너리
path = {
    "root" : project_root_path,
    "assets" : assets_path,

    "problem_images" : assets_problem_images,
    "processed_pdfs" : assets_processed_pdfs,

    "raw_problem_pdfs" : assets_raw_problem_pdfs,
    "base_problems_json" : assets_base_problems_JSON,
    "base_problems_xlsx" : assets_base_problems_xlsx,

    "user_pdf_problems" : user_input_pdf_problems,
    "user_images_problems" : user_input_images_problems,
    "user_base_problems_json" : os.path.join(user_input_path, "user_base_problems.json"),
    "user_base_problems_xlsx" : os.path.join(user_input_path, "user_base_problems.xlsx"),

    "user_problem_images" : user_input_problem_images,
    "user_processed_pdfs" : user_input_processed_pdfs,

    "db" : probdex_db_path,
    "user_db" : user_db_path,
    
    "test_pdf" : test_pdf_path
}

# 상수 설정 - utility_pdf.py에서 사용
pdf_constant = {
    "years": ["2022", "2023", "2024", "2025", "2026"],
    "months": ["06", "09", "csat"],
    "subjects": ["cal", "geo", "sta"],
    "common_pages": (1, 8),
    "split_pages": (9, 12)
}