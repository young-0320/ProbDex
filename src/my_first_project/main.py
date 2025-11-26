# --- main.py: ProbDex 시작 및 종료 메시지 출력 ---
import sys
import os
import argparse
import tkinter as tk

# 프로젝트 모듈 경로 설정
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# 파이프라인 임포트
from .probdex_pipeline import run_ProbDex_pipeline
# [V3 변경] user_pipeline_v2 대신 user_pipeline_v3사용
from .user_pipeline_v3 import run_problem_search_service_v3
from .gui_manager_v2 import ProbDexGUI
from .config import path

def main():
    # 파라미터 파싱
    parser = argparse.ArgumentParser(description="ProbDex Controller")
    
    parser.add_argument(
        '--mode', 
        type=str, 
        choices=['system', 'user'], 
        default='user',
        help="실행 모드 선택: 'system' (DB관리) 또는 'user' (문제검색)"
    )
    
    parser.add_argument(
        '--file', 
        type=str, 
        help="[User Mode] 분석할 PDF 파일명 (예: 2023_03.pdf)"
    )
    
    parser.add_argument(
        '--init', 
        action='store_true', 
        help="[System Mode] 전체 시스템 초기화(DB삭제 등) 수행 여부"
    )

    args = parser.parse_args()

    # 파이프라인 실행 콜백 정의
    def pipeline_callback(gui_instance):
        if args.mode == "system":
            print(f"--- System Pipeline 시작 (초기화: {args.init}) ---")
            run_ProbDex_pipeline(initialization=args.init)
            
        elif args.mode == "user":
            # 처리할 파일 리스트 담기
            files_to_process = []

            # 1. 사용자가 파일명을 직접 입력한 경우 -> 해당 파일 1개만 리스트에 추가
            if args.file:
                files_to_process.append(args.file)
            
            # 2. 입력하지 않은 경우 -> 폴더 내 모든 PDF 탐색하여 리스트에 추가
            else:
                folder_path = path['user_pdf_problems']
                # PDF 파일만 골라서 리스트 생성
                files_to_process = [f for f in os.listdir(folder_path) if f.lower().endswith('.pdf')]
                
                if not files_to_process:
                    print(f"❌ 오류: '{folder_path}' 폴더에 PDF 파일이 없습니다.")
                    return
                print(f"📂 파일명 미지정: 폴더 내의 모든 PDF 파일 {len(files_to_process)}개를 순차적으로 처리합니다.")

            # 3. 리스트에 있는 모든 파일에 대해 반복 실행
            for i, target_file in enumerate(files_to_process, 1):
                print(f"\n" + "="*60)
                print(f"🚀 [파일 처리 중 {i}/{len(files_to_process)}] : {target_file}")
                print("="*60)
                
                # [V3 변경] V3 파이프라인 실행
                try:
                    run_problem_search_service_v3(target_file)
                except Exception as e:
                    print(f"'{target_file}' 처리 중 오류 발생: {e}")
                    continue # 오류가 나도 다음 파일로 계속 진행

    # GUI 실행
    root = tk.Tk()
    app = ProbDexGUI(root, mode=args.mode, filename=args.file, init_flag=args.init, pipeline_callback=pipeline_callback)
    root.mainloop()

if __name__ == "__main__":
    # poetry run python -m src.my_first_project.main
    main()