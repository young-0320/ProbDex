# --- prob_data_processer.py ---
import os
import sys
import json
import pandas as pd
import openpyxl as pyxl
import numpy as np     
from pydantic import BaseModel
from typing import List 
import re
import shutil
import time 

# 프로젝트 모듈 임포트
from .model import (
    BaseModel, Field, ValidationError, model_validator,
    List, Dict, Literal, master_data, valid_subjects,
    AiAnalysis, PDFProbData, PDFProbResponse, problem_number_map,
    generate_problem_id, subject_map
)
from .config import path

def clean_str_for_excel(text):
    """
    엑셀 저장 시 오류를 일으키는 제어 문자를 제거
    """
    if not isinstance(text, str):
        return text
    return re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]', '', text)

def create_xlsx(file_name, output_path):
    '''
    빈 엑셀 파일 생성 함수
    '''
    write_wb = pyxl.Workbook()
    write_wb.save(os.path.join(output_path, file_name))
    print(f"✅ 엑셀 파일 생성 완료: {file_name}")   

def initialize_xlsx(problem_image_path, output_excel_path):
    '''
    이미지 폴더를 스캔하여 이미지 파일명을 기반으로 엑셀 파일 초기화
    '''
    print(f"이미지 폴더 스캔 시작: {problem_image_path}")

    # TODO : JPEG 등의 확장자도 지원
    image_files = [file for file in os.listdir(problem_image_path) if file.endswith('.png')]
    if not image_files:
        print(f"{problem_image_path} 폴더에 PNG 파일이 없습니다.")
        return
    print(f"이미지 파일 {len(image_files)}개 발견. 엑셀 초안 생성을 시작합니다...")
    excel_list = []

    for filename in image_files:
        
        parts = os.path.splitext(filename)[0].split('_')
        # 예: ['kice', '2024', '06', 'common', 'p1']
        # 예: ['kice', '2024', '06', 'geo', 'split', 'p1']
        year_data = parts[1] 
        month_data = "11" if parts[2] == "csat" else parts[2]
        # common -> 공통, cal -> 미적분 등으로 변환
        subject_data = subject_map.get(parts[3], parts[3])
        # subject_data = parts[3] 
        page_num = int(parts[-1][1:]) # 'p1'에서 숫자 부분 추출

        if subject_data in problem_number_map and page_num in problem_number_map[subject_data]:
            number_on_page = problem_number_map[subject_data][page_num]
            for number in number_on_page:
                data_row = {
                    "problem_id": np.nan,  # 나중에 채워넣기
                    "problem_image_path": filename,
                    "year": int(year_data),
                    "month": month_data,
                    "subject_name": subject_data,  
                    "source_data": f"{year_data}학년도 {month_data}월 {subject_data} {number}번",
            
                    "ai_analysis": np.nan,  # AI 분석 결과는 나중에 채워넣기
                    "number": int(number),       
                    "unit_name": np.nan,
                       
                }
                excel_list.append(data_row)
        

    # Pandas DataFrame으로 변환
    
    columns_order = [
        "problem_id", "source_data", "subject_name", "unit_name", "year", "month", "number", 
        "ai_analysis", "problem_image_path"
    ]
    df = pd.DataFrame(excel_list, columns=columns_order)
    # 이미지 한 개당 행 1개씩만 생성
    # 엑셀 파일로 저장
    try:
        df.to_excel(output_excel_path, index=False)
        print(f"\n✅ 엑셀 초기화 완료: {output_excel_path}")
        print(f"총 {len(excel_list)}개의 문제 데이터 생성")
        
    except Exception as e:
        print(f"엑셀 파일 저장 중 문제 발생: {e}")

def merge_existing_and_ai(existing_df, ai_df):
    '''
    기존 엑셀(existing_df)과 AI 분석 데이터(ai_df)를 병합하는 함수
    '''

    # 강력한 전처리...
    if 'subject_name' in existing_df.columns:
        existing_df['subject_name'] = existing_df['subject_name'].astype(str).str.strip()
    if 'subject_name' in ai_df.columns:
        ai_df['subject_name'] = ai_df['subject_name'].astype(str).str.strip()
    
    # 식별자
    match_keys = ['year', 'month', 'number', 'skeleton_subject_key']
    # 변환 열
    target_cols = ['problem_id', 'subject_name', 'unit_name', 'ai_analysis']

    existing_df['skeleton_subject_key'] = existing_df['subject_name']

    ai_df['skeleton_subject_key'] = np.where(
    ai_df['subject_name'].isin(['수학1', '수학2']),  # 조건
    '공통',                                         # 참일 때 값
    ai_df['subject_name']                           # 거짓일 때 값 (원래 값 유지)
    )
    # 강력한 전처리...
    for col in ['year', 'month', 'number']:
        for df in [existing_df, ai_df]:
            if col in df.columns:
                # 숫자로 변환 후 -> 정수로 -> 문자로 (소수점 .0 제거 효과)
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int).astype(str)

    # 인덱싱
    existing_df.set_index(match_keys, inplace=True)
    ai_df.set_index(match_keys, inplace=True)

    # 업데이트
    '''
    existing_df.update(ai_df[target_cols])
    existing_df.reset_index(inplace=True)
    '''
    common_indices = existing_df.index.intersection(ai_df.index)

    if not common_indices.empty:
        existing_df.loc[common_indices, target_cols] = ai_df.loc[common_indices, target_cols]
    # 다시 리셋해야한다..
    existing_df.reset_index(inplace=True)

    # skeleton_subject_key 삭제
    if 'skeleton_subject_key' in existing_df.columns:
        existing_df.drop(columns=['skeleton_subject_key'], inplace=True)

    return existing_df

    '''
    is_common = (ai_df['subject_name'] == '공통').all()
    
    if is_common:
        skeleton_keys = ['year', 'month', 'number']
        ai_keys = ['year', 'month', 'number']
    else:
        skeleton_keys = ['year', 'month', 'number', 'subject_name']
        ai_keys = ['year', 'month', 'number', 'subject_name']

    # 타입 통일
    for col in skeleton_keys:
        if col in existing_df.columns:
            existing_df[col] = existing_df[col].astype(str)

    for col in ai_keys:
        if col in ai_df.columns:
            ai_df[col] = ai_df[col].astype(str)

    # 인덱스 설정
    existing_df.set_index(skeleton_keys, inplace=True)
    ai_df.set_index(ai_keys, inplace=True)

    # update
    existing_df.update(ai_df)

    # 신규 행 추가
    new_idx = ai_df.index.difference(existing_df.index)
    if not new_idx.empty:
        existing_df = pd.concat([existing_df, ai_df.loc[new_idx]])

    return existing_df.reset_index()
    '''

def process_source_data(raw_data):
    '''
    엑셀에서 읽어온 source_data를 정제하는 함수
    '''
    if not isinstance(raw_data, str):
        return raw_data # None, NaN 등 비어있는 셀은 그대로 반환
    
    # 양쪽 공백 제거
    text = raw_data.strip()

    # 텍스트를 공백 기준으로 분리
    parts = text.split()

    # 예시 "2022학년도 06 cal"
    year_data = parts[0]
    month_data = parts[1]
    subject_data = parts[2]
    number_data = parts[3]
    if month_data == "csat":
        month_data = "수능"
    elif month_data in [ "06", "09"]:
        month_data = f"{int(month_data)}월"
    else:
        month_data = month_data 
    
    subject_map = {
        "common": "공통",
        "cal": "미적분",
        "geo": "기하",
        "sta": "확률과 통계"
    }

    subject_text = subject_map.get(subject_data, subject_data)    
    return f"{year_data} {month_data} {subject_text} {number_data}"

def process_subject_name(raw_data):
    '''
    엑셀에서 subject_name을 정제하는 함수
    '''
    if not isinstance(raw_data, str):
        return raw_data # None, NaN 등 비어있는 셀은 그대로 반환
    
    # 양쪽 공백 제거
    subject_name = raw_data.strip()


    # 예시 "2022학년도 06 cal"
    subject_map = {
        "cal": "미적분",
        "geo": "기하",
        "sta": "확률과 통계",
        "common": "공통"
    }

    return subject_map.get(subject_name, subject_name)

def excel_to_json(excel_path, output_path):
    '''
    엑셀 파일을 JSON 형식으로 변환하는 함수
    '''
    print(f"\n엑셀 → JSON 변환 작업 시작...")
    # 엑셀 파일 불러오기
    try:
        df = pd.read_excel(excel_path, engine='openpyxl')
        
    except FileNotFoundError:
        print(f"엑셀 파일({excel_path})이 존재하지 않습니다.")
        return
    except Exception as e:
        print(f"엑셀 파일을 읽는 중 문제 발생: {e}")
        return

    df = df.replace(np.nan, None)
    
    if 'source_data' in df.columns:
        df['source_data'] = df['source_data'].apply(process_source_data)
        print("✅ 'source_data' 컬럼 정제 완료.")
    else:
        print("'source_data' 컬럼이 엑셀에 없습니다.")

    
    if 'subject_name' in df.columns:
        df['subject_name'] = df['subject_name'].apply(process_subject_name)
        print("✅ 'subject_name' 컬럼 정제 완료. ('cal' -> '미적분')")
    else:
        print("'subject_name' 컬럼이 엑셀에 없습니다.")

    df.to_json(
            output_path,
            orient='records',    
            indent=4,            
            force_ascii=False    
        )
    print(f"\n✅ 성공: {output_path} 변환 완료.")
    print(f"총 {len(df)}개의 문제가 JSON 파일로 저장되었습니다.")

def latex_to_unicode(latex_text: str):
    '''
    LaTeX 형식의 텍스트를 사람이 읽기 쉬운 유니코드 텍스트로 변환합니다.
    '''
    if not isinstance(latex_text, str):
        return str(latex_text)
    
    # 시작
    text = latex_text

    # \frac{A}{B} -> (A)/(B)
    text = re.sub(r'\\frac{(.*?)}{(.*?)}', r'(\1)/(\2)', text)

    # \lim_{...} -> lim(...)
    def lim_replacer(match):
        inside = match.group(1).strip()

        # 내부의 LaTeX → 변환 후 결과 정리
        inside = inside.replace(" ", "")
        inside = inside.replace("^+", "+").replace("^-", "-")
        inside = inside.replace("^\\+", "+").replace("^\\-", "-")

        return f"lim({inside})"
    text = re.sub(r'\\lim_\{(.*?)\}', lim_replacer, text)

    # \int_{a}^{b} -> ∫_(a)^(b)
    def integral_replacer(match):
        lower = match.group(1).strip()
        upper = match.group(2).strip()
        return f"∫_({lower})^({upper})"
    text = re.sub(r'\\int_\{(.*?)\}\^\{(.*?)\}', integral_replacer, text)

    # 위첨자/아래첨자가 하나만 있는 경우
    text = re.sub(r'\\int_\{(.*?)\}', r'∫_(\1)', text)
    text = re.sub(r'\\int\^\{(.*?)\}', r'∫^(\1)', text)

    # 기타 위첨자/아래첨자: A_{...} -> A_(...), B^{...} -> B^(...)
    text = re.sub(r'([a-zA-Z0-9])_\{(.*?)\}', r'\1_(\2)', text)
    text = re.sub(r'([a-zA-Z0-9])\^\{(.*?)\}', r'\1^(\2)', text)
    
    # 단순 대치
    REPLACEMENTS = {
        # Greek
        r"\\alpha": "α",
        r"\\beta": "β",
        r"\\gamma": "γ",
        r"\\delta": "δ",
        r"\\epsilon": "ε",
        r"\\theta": "θ",
        r"\\lambda": "λ",
        r"\\pi": "π",
        r"\\mu": "μ",
        r"\\sigma": "σ",
        r"\\phi": "φ",
        r"\\psi": "ψ",
        r"\\omega": "ω",

        # Operators
        r"\\times": "×",
        r"\\cdot": "·",
        r"\\div": "÷",
        r"\\pm": "±",
        r"\\mp": "∓",
        r"\\sqrt": "√",
        r"\\infty": "∞",
        r"\\to": "->",
        r"\\Rightarrow": "⇒",
        r"\\Leftarrow": "⇐",
        r"\\Leftrightarrow": "⇔",

        # Set / logic symbols
        r"\\in": "∈",
        r"\\notin": "∉",
        r"\\subset": "⊂",
        r"\\subseteq": "⊆",
        r"\\supset": "⊃",
        r"\\cup": "∪",
        r"\\cap": "∩",
        r"\\emptyset": "∅",
        r"\\forall": "∀",
        r"\\exists": "∃",

        # Calculus
        r"\\int": "∫",
        r"\\sum": "∑",
        r"\\ln": "ln",
        r"\\log": "log",

        # Geometry
        r"\\angle": "∠",
        r"\\triangle": "△",
        r"\\perp": "⊥",
        r"\\parallel": "∥",
        r"\\circ": "°",

        # Comparison
        r"\\ge": "≥",
        r"\\le": "≤",
        r"\\ne": "≠",
        r"\\approx": "≈",

        # Escaped characters
        r"\\_": "_",
        r"\\%": "%",
        r"\\&": "&",
        r"\\{": "{",
        r"\\}": "}",
        r"\\\^": "^",
    }
    for pattern, replacement in REPLACEMENTS.items():
        latex_text = re.sub(pattern, replacement, latex_text)

    text = text.replace("{", "").replace("}", "")
    
    return text
    
# TODO : 일단 라텍스 -> 유니코드 변환 함수 개발
def update_problems_xlsx(problems: List[PDFProbData], excel_path: str, unicode_text: bool = True, backup: bool = True):
    """
    AI가 분석한 PDFProbData 리스트를 기존 엑셀 파일에 업데이트하거나 추가하는 함수.
    """
    if not problems:
        print("업데이트할 AI 분석 데이터가 없습니다.")
        return 
    
    try:
        existing_df = pd.read_excel(
            excel_path, 
            engine='openpyxl', 
            dtype={
                'year': str,        # 키 1
                'month': str,       # 키 2
                'number': str,      # 키 3
                'subject_name': str, # 키 4
                'ai_analysis': str,
                'unit_name': str  
            }
        )
        existing_df.dropna(subset=['year', 'month', 'number', 'subject_name'], inplace=True)
        
    except FileNotFoundError:
        print(f"기존 엑셀 파일({excel_path})을 찾을 수 없습니다. 'initialize_xlsx'를 먼저 실행하십시오.")
        return
    except Exception as e:
        print(f"엑셀 읽기 실패: {e}")
        return

    # AI 분석 데이터를 DataFrame으로 변환
    ai_data = []
    for problem in problems:
        if not all([problem.year, problem.month, problem.number is not None, problem.subject_name]):
            print(f"경고: AI 분석 항목의 키(year, month, number, subject)가 없습니다 (Num: {problem.number}), 스킵합니다.")
            continue
        
        item = problem.model_dump()
        if problem.ai_analysis:
            item['ai_analysis'] = json.dumps(problem.ai_analysis.model_dump(), ensure_ascii=False)
        
        ai_subject = str(problem.subject_name)
        if ai_subject in ['수학1', '수학2']:
            item['skeleton_subject_key'] = '공통'
        else:
            item['skeleton_subject_key'] = ai_subject 

        ai_data.append(item)

    if not ai_data:
        print("업데이트할 유효한 AI 분석 데이터(키 포함)가 없습니다.")
        return

    ai_df = pd.DataFrame(ai_data)

    if unicode_text and 'problem_text' in ai_df.columns:
        ai_df['problem_text'] = ai_df['problem_text'].apply(latex_to_unicode)
    '''
    # 병합 로직
    # 뼈대(existing_df)의 키 컬럼명
    skeleton_merge_keys = ['year', 'month', 'number', 'subject_name']
    # AI(ai_df)의 키 컬럼명
    ai_merge_keys = ['year', 'month', 'number', 'skeleton_subject_key']

    # 1. 키(Key) 컬럼의 타입을 병합을 위해 '문자열'로 통일
    if not existing_df.empty:
        for col in skeleton_merge_keys:
             if col in existing_df.columns:
                existing_df[col] = existing_df[col].astype(str)
    
    for col in ai_merge_keys:
        if col in ai_df.columns:
            ai_df[col] = ai_df[col].astype(str)

    # 2. (year, month, number, subject_name)를 복합 키 인덱스로 설정
    if not existing_df.empty:
        existing_df.set_index(skeleton_merge_keys, inplace=True)
    
    ai_df.set_index(ai_merge_keys, inplace=True) # AI는 매칭용 키를 인덱스로 설정

    # 3. 병합 및 신규 항목 추가
    if not existing_df.empty:
        # (Update) 
        # existing_df의 인덱스 (..., '공통')와
        # ai_df의 인덱스 (..., '공통')가 일치하는 행을 찾아 덮어씁니다.
        print(f"  병합 기준(4-part key)으로 {len(ai_df)}개 항목 업데이트 시도...")
        existing_df.update(ai_df)

        
        update_indices = existing_df.index.intersection(ai_df.index)
        
        if not update_indices.empty:
            
            # 1. ai_df에서 올바른 subject_name 값을 추출 (갱신 대상 인덱스로 필터링)
            new_subject_names = ai_df.loc[update_indices, 'subject_name']
            
            # 2. existing_df의 인덱스에서 레벨 3 (subject_name) 값을 추출하여 시리즈로 만듭니다.
            current_level_3 = existing_df.index.get_level_values(3).to_series()
            
            # 3. 인덱스가 일치하는 부분에 대해 new_subject_names의 값으로 덮어씁니다.
            current_level_3.update(new_subject_names) 
            
            # 4. 기존 모든 인덱스 레벨을 추출하고, 모두 리스트로 변환합니다. (오류 수정)
            level_arrays = [existing_df.index.get_level_values(i).to_list() for i in range(existing_df.index.nlevels)]
            
            # 5. 마지막 레벨(subject_name)을 갱신된 Series의 '값 리스트'로 교체
            level_arrays[-1] = current_level_3.to_list()
            
            # 6. 새 MultiIndex를 생성하여 기존 인덱스를 대체합니다.
            existing_df.index = pd.MultiIndex.from_arrays(
                level_arrays,
                names=skeleton_merge_keys
            )
        
        # (Concat)
        new_indices = ai_df.index.difference(existing_df.index)
        if not new_indices.empty:
            print(f"  추가: {len(new_indices)}개의 신규 문제(인덱스)를 엑셀에 추가합니다.")
            new_rows_df = ai_df.loc[new_indices]
            existing_df = pd.concat([existing_df, new_rows_df])
            
        existing_df.reset_index(inplace=True) 
        final_df = existing_df
    else:
        final_df = ai_df.reset_index()

    # AI가 매칭용으로 사용한 임시 키 삭제
    if 'skeleton_subject_key' in final_df.columns:
        final_df.drop(columns=['skeleton_subject_key'], inplace=True)
    
    # --- [병합 로직 종료] ---
    '''
    final_df = merge_existing_and_ai(existing_df, ai_df)

    # 컬럼 순서 재정렬
    original_columns_order = [
        "problem_id", "source_data", "subject_name", "unit_name", 
        "year", "month", "number", "ai_analysis", "problem_image_path"
    ]

    ordered_cols = [col for col in original_columns_order if col in final_df.columns]
    extra_cols = [col for col in final_df.columns if col not in ordered_cols]
    final_df = final_df[ordered_cols + extra_cols]

    # 엑셀 저장 전 문자열 정제
    try:
        string_columns_to_clean = [
            'ai_analysis', 'unit_name', 
            'subject_name', 'source_data'
        ]
        print(f"  데이터 정제(Sanitizing) 시작 (제어 문자 제거)...")
        for col in string_columns_to_clean:
            if col in final_df.columns:
                final_df[col] = final_df[col].apply(clean_str_for_excel)
        
        final_df.replace('nan', np.nan, inplace=True)

    except Exception as e:
        print(f"  경고: 엑셀 저장 전 문자열 정제(sanitize) 실패: {e}")
    
    # year, number를 정수형으로 변환
    try:
        final_df['year'] = pd.to_numeric(final_df['year'], errors='coerce').astype('Int64')
        final_df['number'] = pd.to_numeric(final_df['number'], errors='coerce').astype('Int64')
    except Exception as e:
        print(f"  경고: 최종 'year'/'number' 정수 변환 실패: {e}")

    # 백업 생성 로직
    if backup and os.path.exists(excel_path):
        backup_path = excel_path + ".bak"
        try:
            shutil.copy(excel_path, backup_path)
            print(f" {backup_path}에 백업 파일 생성 완료.")
        except Exception as e:
            print(f"백업 파일 생성 실패: {e}")

    # 최종 저장 
    try:
        final_df.to_excel(excel_path, index=False, engine='openpyxl')
        print(f"✅ 엑셀 업데이트/추가 완료: {excel_path}")
        
    except PermissionError:
        print(f"엑셀 저장 실패: {excel_path} 파일이 다른 프로그램에 열려있는지 확인하십시오.")
            
    except Exception as e:
        print(f"--- 엑셀 저장 중 오류 발생 (일괄 저장 실패) ---")
        print(f"  (원본 오류: {e})")
        print(f"  오류 원인이 되는 행(row) 탐색 시작...")
        
        illegal_char_re = re.compile(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]')
        string_columns = ['problem_text', 'ai_analysis', 'unit_name', 'subject_name', 'source_data']
        found_culprit = False

        try:
            for index, row in final_df.iterrows():
                for col in string_columns:
                    if col in row and isinstance(row[col], str):
                        if illegal_char_re.search(row[col]):
                            problem_id = row.get('problem_id', f"ID 없음 (Index {index})")
                            print(f"--- [오류 원인 발견] ---")
                            print(f"  문제 ID: {problem_id}")
                            print(f"  필드: {col}")
                            print(f"  사유: 엑셀에 저장할 수 없는 특수 제어 문자가 포함되어 있습니다.")
                            found_culprit = True
                            break
                if found_culprit:
                    break
            
            if not found_culprit:
                print(f"  오류 원인: 특수 제어 문자 외의 다른 오류일 수 있습니다.")
                
        except Exception as search_e:
            print(f"  오류 원인 탐색 중 추가 오류 발생: {search_e}")

def update_problems_json(problems: List[PDFProbData], json_path: str):
    '''
    AI가 분석한 PDFProbData 리스트 -> JSON 파일로 업데이트하는 함수
    [수정] (year, month, number, subject_name) 4-part 키를 사용.
    [수정] AI가 반환한 '수학1', '수학2'를 뼈대의 '공통' 키와 매칭시킴.
    '''
    
    # JSON 파일 로드
    print(f"\n JSON 파일 업데이트 시작: {json_path}")
    existing_json_list = []

    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            existing_json_list = json.load(f)
    except FileNotFoundError:
        print(f"  정보: {json_path} 파일이 없어 새로 생성합니다.")
    except json.JSONDecodeError:
        print(f"  경고: {json_path} 파일이 비어있거나 손상되었습니다. 새로 생성합니다.")
        
    # 인덱싱을 위한 딕셔너리 변환: (year, month, number, subject_name)을 키로 사용
    existing_data_map = {}
    for item in existing_json_list:
        try:
            # 병합 키 생성 (문자열로 통일)
            key = (
                str(item.get('year')), 
                str(item.get('month')), 
                str(item.get('number')),
                str(item.get('subject_name')) # 4번째 키 '공통', '미적분' 등
            )
            
            if all(k != 'None' for k in key):
                existing_data_map[key] = item
            else:
                print(f"  경고: 기존 항목의 키(year, month, number, subject)가 불완전하여 스킵합니다.")
        except Exception as e:
            print(f"  경고: 기존 항목 {item.get('source_data')} 처리 중 오류: {e}")

    # AI 분석 데이터로 업데이트
    update_count = 0
    new_item_count = 0
    
    for problem in problems:
        # AI 데이터에서 병합 키 생성
        try:
            ai_subject = str(problem.subject_name)
            
            # AI가 '수학1' 또는 '수학2'를 반환했는지 확인합니다.
            skeleton_subject = ai_subject
            if ai_subject in ['수학1', '수학2']:
                skeleton_subject = '공통'
            
            key = (
                str(problem.year), 
                str(problem.month), 
                str(problem.number),
                skeleton_subject # '공통', '미적분', '기하' 등
            )
        except Exception:
            print(f"  경고: AI 분석 항목(Num: {problem.number})의 키가 불완전하여 스킵합니다.")
            continue

        # Pydantic 모델을 딕셔너리로 변환 (AI가 생성한 올바른 ID 포함)
        ai_data_dict = problem.model_dump(exclude_none=True) 
        if problem.ai_analysis:
            ai_data_dict['ai_analysis'] = problem.ai_analysis.model_dump()
        
        # 기존 항목에 AI 분석 결과 업데이트
        if key in existing_data_map:
            # 뼈대의 (..., 5, '공통') 키를 찾아
            # AI의 (..., 5, '수학1') 데이터를 덮어씁니다.
            # 이 때 'problem_id'와 'subject_name'도 '수학1'로 올바르게 업데이트됩니다.
            existing_data_map[key].update(ai_data_dict)
            update_count += 1
        else:
            # 선택과목이거나, 뼈대에 없던 신규 문제
            # print(f"  정보: 키 {key} (문제 {problem.number}번)가 JSON에 없어 새로 추가합니다.")
            existing_data_map[key] = ai_data_dict
            new_item_count += 1
            
    # 맵의 값들(딕셔너리)을 리스트로 변환하여 파일에 저장
    final_data_list = list(existing_data_map.values())
    
    try:
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(final_data_list, f, ensure_ascii=False, indent=4)
        print(f"✅ JSON 파일 업데이트 완료. (총 {len(final_data_list)}개 항목, {update_count}개 업데이트, {new_item_count}개 신규 추가)")
    except Exception as e:
        print(f"JSON 파일 저장 실패: {e}")

def process_pdf_year_and_month(pdf_path):
    '''
    PDF 파일 경로를 입력받아 파일명에서 year와 month를  파싱합니다.
    '''
    try:
        # "kice_2022_06_cal_split.pdf"
        filename = os.path.basename(pdf_path) 

        parts = os.path.splitext(filename)[0].split('_')

        # "kice", "2022", "06", "cal", "split"
        if len(parts) >= 3 and parts[0] == 'kice':
            year = parts[1]  # "2022"
            month = parts[2] # "06"

            # prob_data_processer.py의 정제 로직 적용
            if month == "csat":
                month = "11" 
            if month in ["06", "09", "11"]:
                return year, month
            else:
                # [수정] 경고 메시지 주석 처리 또는 삭제
                # print(f"경고: {filename}에서 유효한 월('06', '09', 'csat') 패턴을 찾을 수 없습니다.")
                return None, None

        else:
            # [수정] 경고 메시지 주석 처리 또는 삭제
            # print(f"경고: {filename}에서 'kice_연도_월' 패턴을 찾을 수 없습니다.")
            return None, None

    except Exception as e:
        
        print(f"파일명({pdf_path}) 파싱 중 오류 발생: {e}")
        return None, None

def append_images_excel(image_paths, excel_path):
    """
    이미지 경로 리스트를 받아 엑셀에 없는 이미지만 신규 등록합니다.
    """
    if not image_paths:
        print(" 등록할 이미지가 없습니다.")
        return

    # 엑셀 로드(없으면 빈 DF)
    if os.path.exists(excel_path):
        try:
            existing_df = pd.read_excel(excel_path, engine="openpyxl")
        except Exception:
            existing_df = pd.DataFrame()
    else:
        existing_df = pd.DataFrame()

    # 이미 등록된 이미지 파일명 집합
    registered = set()
    if "problem_image_path" in existing_df.columns:
        registered = set(existing_df["problem_image_path"].dropna().unique())

    new_rows = []

    for img_path in image_paths:
        img_file = os.path.basename(img_path)

        # 중복 차단
        if img_file in registered:
            continue
        # kice_2024_06_common_p1
        stem = os.path.splitext(img_file)[0]   
        # ['kice','2024','06','common','p1']          
        parts = stem.split("_")                          

        # 기본 구조 위반 시 스킵
        if len(parts) < 5:
            print(f" 무시됨(형식 오류): {img_file}")
            continue

        year = int(parts[1])
        month_raw = parts[2]
        subj_raw = parts[3]
        page_num = int(parts[-1].replace("p", ""))

        # 월 수정
        real_month = "11" if month_raw == "csat" else month_raw

        # 과목 변환(common → 공통)
        real_subject = subject_map.get(subj_raw, subj_raw)

        # 문제번호 매핑 실패하면 스킵
        if real_subject not in problem_number_map:
            print(f"매핑 불가 과목: {img_file}")
            continue
        if page_num not in problem_number_map[real_subject]:
            print(f"매핑 불가 페이지: {img_file}")
            continue

        # 1개 이미지 → 여러 문제 등록 가능
        for num in problem_number_map[real_subject][page_num]:
            new_rows.append({
                "problem_id": np.nan,
                "source_data": f"{year}학년도 {real_month}월 {real_subject} {num}번",
                "subject_name": real_subject,
                "unit_name": np.nan,
                "year": year,
                "month": real_month,
                "number": int(num),
                "ai_analysis": np.nan,
                "problem_image_path": img_file,
            })

    if not new_rows:
        print("엑셀에 추가할 새로운 데이터가 없습니다.")
        return

    new_df = pd.DataFrame(new_rows)

    # 기존 엑셀과 컬럼 정렬 
    if not existing_df.empty:
        new_df = new_df.reindex(columns=existing_df.columns, fill_value=np.nan)
        final_df = pd.concat([existing_df, new_df], ignore_index=True)
    else:
        # 최초 생성인 경우 컬럼 순서 보정
        columns = [
            "problem_id", "source_data", "subject_name", "unit_name",
            "year", "month", "number", "ai_analysis", "problem_image_path",
        ]
        final_df = new_df.reindex(columns=columns, fill_value=np.nan)

    final_df.to_excel(excel_path, index=False, engine="openpyxl")
    print(f"✅ 엑셀 추가 완료: {len(new_rows)}개 행 업데이트됨.")



