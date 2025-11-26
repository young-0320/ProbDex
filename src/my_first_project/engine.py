# --- engine.py ---
import os
import sys
import json
import time
import traceback
import pandas as pd
import pathlib
from pydantic import BaseModel, Field, ValidationError, model_validator
from typing import List, Dict, Literal
from google import genai
from google.genai import types, errors
from dotenv import load_dotenv
# 프로젝트 모듈 임포트
from .model import (
    BaseModel, Field, ValidationError, model_validator,
    List, Dict, Literal, master_data, valid_subjects,
    AiAnalysis, PDFProbData, PDFProbResponse, subject_code_map,
    generate_problem_id, subject_map
)
from .config import path 

# 핵심 AI 분석 엔진 클래스
class ProbDexEngine:
    '''
    ProbDex의 핵심 AI 분석 엔진 클래스
    '''
    # 클래스 상수 정의
    MAX_RETRIES = 3 # 최대 재시도 횟수
    RETRY_DELAY_SECONDS = 15 # 재시도 간 대기 시간 (초)
    TEMPERATURE = 0  # AI의 창의성과 다양성
    # PRO 모델 상수
    TIME_OUT_PRO = 600000  # API 호출 타임아웃 (밀리초)
    THINKING_BUDGET_PRO = 16384 * 2  
    # FLASH 모델 상수
    TIME_OUT_FLASH = 60000  # API 호출 타임아웃 (밀리초)
    THINKING_BUDGET_FLASH = 512

    # [모델 상수 결정]
    TIME_OUT = TIME_OUT_PRO
    THINKING_BUDGET = THINKING_BUDGET_PRO

    # RETRY_CODE_429 = 429
    # TOO_MANY_REQUESTS_CODE_429 = 429
    # SERVER_INTERNAL = 500

    def __init__(self):
        # 구글 AI Studio API 키 활성화
        load_dotenv() 
        try:
            GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
            if not GEMINI_API_KEY:
                raise ValueError("GEMINI_API_KEY가 없습니다. {.env}파일을 저장 했는지 확인하십시오")
            
            self.client = genai.Client(
                api_key=GEMINI_API_KEY,
                http_options={'timeout': self.TIME_OUT} # 밀리초 단위
            )
            print("✅ Gemini API가 성공적으로 설정되었습니다.")

        except (ValueError, Exception) as e:
            print(f"API 키 설정 및 클라이언트 초기화 실패: {e}")
            sys.exit(1) # API 키가 없으면 프로그램 중단
        # 기본 모델 설정
        self.model = 'gemini-2.5-pro'
        print("\nProbDexEngin model\n:", self.model)

    @staticmethod
    def is_ai_analysis_valid(ai_data):
        """
        AI가 생성한 ai_analysis 데이터가 유효한지 판단
        """
        # 1) None, 빈 문자열, 빈 dict 모두 무효
        if not ai_data:
            return False

        # 2) dict가 아닌 경우 무효 (예: 파싱되지 않은 문자열)
        if not isinstance(ai_data, dict):
            return False

        # 3) 난이도 검사: 정수인지, 범위가 1~5인지
        diff = ai_data.get('difficulty_level')
        if not isinstance(diff, int) or not (1 <= diff <= 5):
            return False
        
        # 4) logic_flow 검사: 비어있거나 None이면 무효
        if not ai_data.get('logic_flow'):
            return False

        # 5) core_concepts 검사: 비어있거나 None이면 무효
        if not ai_data.get('core_concepts'):
            return False
        return True
    
    @staticmethod
    def _parse_image_path(img_path: str):
        """
        이미지 파일명에서 stem과 page 번호를 추출합니다.
        예: kice_2024_06_cal_split_p3.png → ("kice_2024_06_cal_split", 3)
        """
        try:
            parts = img_path.rsplit('_p', 1)
            if len(parts) != 2:
                return None, None

            stem = parts[0]
            page_str = parts[1].split('.')[0]
            return stem, int(page_str)
        except Exception:
            return None, None
        
    @staticmethod
    def get_analyzed_page_map(json_path: str) -> dict[str, set]:
        """
        JSON 파일을 분석하여 파일명 -> 분석 완료된 페이지 번호 집합을 반환합니다.
        예: {"kice_2024_06_cal_split": {2, 3, 4}}
        """
        analyzed_map = {}

        # 경로 체크
        if not os.path.exists(json_path):
            return analyzed_map

        # JSON 로드
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                problems = json.load(f)
            print(f" 기존 분석 기록 스캔 중... (총 {len(problems)}개 데이터)")
        except Exception as e:
            print(f" 분석 기록 로드 오류 발생: {e}")
            return analyzed_map
        
        for problem in problems:
            ai_data = problem.get('ai_analysis')

            # 문자열이면 파싱 
            if isinstance(ai_data, str):
                try:
                    ai_data = json.loads(ai_data)
                except Exception:
                    ai_data = None

            # 유효하지 않으면 스킵
            if not ProbDexEngine.is_ai_analysis_valid(ai_data):
                continue

            img_path = problem.get('problem_image_path')
            if not img_path:
                continue

            # 4. 이미지 파일명 파싱
            stem, page_num = ProbDexEngine._parse_image_path(img_path)
            if stem is None or page_num is None:
                continue

            analyzed_map.setdefault(stem, set()).add(page_num)

        return analyzed_map
    
    def __extract_pdf_base_data(self, input_pdf_path):
        '''
        PDF에서 기본 데이터(subject_name, unit_name, problem_text, number) 추출.
        '''
      
        system_instruction = f"""
        당신은 대한민국 수능/평가원 기출문제의 전문 분석가입니다. 
        당신의 유일한 임무는, 지금부터 입력될 PDF 파일을 처음부터 끝까지 정확하게 읽고,
        PDF 파일 내의 모든 수학 문제를 인식하여 
        각 문제의 (1)subject_name, (2)unit_name, (3)problem_text(수식 포함), (4)number를 추출하는 것입니다.
        이때 (1)~(4)는 반드시 PDFProbData Pydantic 스키마에 맞게 추출해야 합니다.

        [규칙]
        [규칙 1: 분류 기준] 
        과목명(subject_name)은 반드시 다음 리스트 중 하나여야 합니다: 
        {list(master_data.keys())}

        [규칙 2: 과목-단원 종속성]
        단원명(unit_name)은 반드시 해당 과목의 다음 리스트 중 하나여야 합니다:
            - 수학1: {master_data['수학1']}
            - 수학2: {master_data['수학2']}
            - 미적분: {master_data['미적분']}
            - 확률과 통계: {master_data['확률과 통계']}
            - 기하: {master_data['기하']}
            - 분류 불가: {master_data['분류 불가']}
        PDF의 텍스트가 문제가 아니거나(예: 표지, 해설) 분류가 불가능하면 "분류 불가"로 지정하십시오.
        문제에 여러 단원의 개념이 포함되어 단원을 하나로 특정하기 어려울 경우, 
        문제 해결 과정에서 핵심 역할을 하는 ‘주요 개념’이 속한 단원을 선택하십시오. 
        주요 개념은 정답 도출에 직접적으로 기여하는 개념으로 정의합니다.

        [규칙 3: 텍스트 추출 정확도(중요)]
        PDF의 시각적 레이아웃을 분석하여 텍스트를 추출해야 합니다.
        수학 기호가 아닌 일반 텍스트는 그대로 유니코드(Unicode)로 저장하십시오.

        [규칙 3-1: LaTeX 변환 (필수)]
        모든 수학 기호와 수식은 유니코드 기호가 아닌 LaTeX 문법으로 표기하십시오.  
        단순 기호부터 구조적 수식까지 일관된 형식을 유지하는 것이 목표입니다.
        가능한 한 수식 전체를 LaTeX 형태로 감싸지 않고, 필요한 부분만 LaTeX 명령으로 표기하십시오.
        
            - 단일 기호는 대응하는 LaTeX 명령을 사용합니다.
            예: θ → \\theta, ∫ → \\int, ∑ → \\sum, → → \\to
            - 지수와 아래첨자는 일반적인 LaTeX 규칙을 따릅니다.
            예: x^n, 2^x, a_n, x_1
            - 분수, 미분, 비율 등의 표현은 \\frac 형태로 작성합니다.
            예: \\frac{{1}}{{2}}, \\frac{{dy}}{{dx}}, \\frac{{1}}{{\\sqrt{{n^2+n+1 - n}}}}
            - 제곱근과 n제곱근은 \\sqrt 또는 \\sqrt[n]{{·}} 형태로 작성합니다.
            예: \\sqrt{{2}}, \\sqrt[3]{{x}}, \\sqrt{{n^2+n+1}}-n

        [규칙 3-2: 극한 표현]
        극한 표현은 반드시 LaTeX 형식으로 변환해야 합니다.
            - 예:  lim (n→∞) -> \\lim_{{n \\to \\infty}}
            - 우극한과 좌극한(예: lim (x→a+) -> \\lim_{{x \\to a^+}})도 명확히 변환해야 합니다                         
               
        [규칙 4: 내용 필터링 (매우 중요)]
        'problem_text'에는 문제 풀이에 필요한 핵심 내용만 포함해야 합니다.
            - [제외] 객관식 선지 (예: ①, ②, ③, ④, ⑤로 시작하는 줄)는 'problem_text'에 절대로 포함하지 마십시오.
            - [제외] "그림과 같이", "다음 그림은..." 등 그림(Figure)이나 그래프(Graph) 자체를 참조하는 구문은 포함하되,
            그림이나 그래프의 시각적 내용을 텍스트로 묘사(Describe)하지 마십시오.
            - [제외] 페이지 번호, 머리글, 꼬리글 등 문제와 관련 없는 텍스트는 제외하십시오.

            - [포함] 문제 번호(예: 23번), 지문, <보기>의 구문 등은 모두 포함해야 합니다.
            - [포함] 문제 끝에 있는 배점(예: [2점], [3점])은 'problem_text'에 반드시 포함해야 합니다.
            
        [규칙 5: 응답 형식]
        다른 설명 없이, 반드시 'PDFProbResponse' Pydantic 스키마에 맞는 JSON 형식으로만 응답해야 합니다.
        PDF에 문제가 여러 개 있으면 "problems" 리스트에 순서대로 모두 추가해야 합니다.

        [규칙 5-1: AI 생성 제외 필드]
        year, month, problem_id 세 개의 필드는 AI가 생성하는 JSON에 포함되어서는 안 됩니다.
        이 필드들은 PDFProbData Pydantic 스키마에 정의되어 있지만, 이는 AI 분석 이후에 시스템이
        다른 정보(파일 명)와 AI의 분석 결과(number, subject_name)를 '조합(combine)'하여 채우는 필드입니다.
        AI는 이 필드들을 null이나 0으로 채우려 시도하지 말고, JSON 응답에서 완전히 '생략(omit)'하십시오.

        [규칙 5-2: number 필드]
        문제 번호(number)는 PDF 내 표시된 "문항 번호"를 오직 정수로만 추출하십시오.
        문항 번호를 찾을 수 없으면 number는 0으로 설정하십시오.
        문제 텍스트에서 추출한 문제 번호 '24번'의  표기는 그대로 problem_text에 포함시키되 
        number에는 숫자만(예: 24) 저장해야 합니다.

        [최종 출력 형식 엄격 준수]
        반드시 다음 "예시 JSON" 구조와 키 이름, 대소문자, 타입을 정확히 따르십시오. 예시 외의 어떤 텍스트도 출력하지 마십시오.

        [예시 JSON]
        {{
            "problems": [
                {{
                    "subject_name": "미적분",
                    "unit_name": "미분법",
                    "problem_text": "문제 24. 함수 f(x)=x^3-3x+1의 극값을 구하시오. [3점]",
                    "number": 24
                }}
               
            ]
        }}
        
        [추출 오류 시 대처법]
        아래 어느 경우에도 JSON 구조를 절대로 변경하지 마십시오.
        필드를 누락하거나 이름을 수정하거나 타입을 바꾸지 마십시오.

        PDF 텍스트가 손상되었거나, 문제를 인식할 수 없거나, 특정 값을 정확하게 판단할 수 없을 때는 
        다음 기본 규칙에 따라 대체값을 넣으십시오.

        [1] 기본 문자열 필드(str)
        다음 필드들은 값 추출에 실패하면 빈 문자열("")로 채우십시오.
        (1) subject_name, (2) unit_name, (3) problem_text 

        [2] 정수 필드(int)
        다음 필드들은 값 추출에 실패하면 정수(0)으로 채우십시오.
        (1) number

        [5] 문제 하나라도 JSON 스키마를 벗어난 결과를 생성하지 마십시오.
        다음과 같은 행위는 절대로 하지 마십시오:
            - JSON 키 이름 변경
            - 스키마에서 정의되지 않은 새로운 키 추가
            - 스키마 필드 누락
            - None/null 반환
            - 임의로 데이터 type 변경 (예: 정수를 문자열로 변환)
            - "에러가 있습니다" 같은 자연어 텍스트 추가
        출력은 오직 Pydantic 스키마에 맞는 JSON 데이터만 생산해야 하며, 구조적 에러가 발생하지 않아야 합니다.
        
        """

        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=0.2, 
            response_mime_type='application/json',
            response_schema=PDFProbResponse 
        )
        
        try:
            from .utility_pdf import extract_pdf_pages_to_bytes, get_pdf_page_count
            filepath = pathlib.Path(input_pdf_path)
            
            end_pages = get_pdf_page_count(input_pdf_path)
            if end_pages == 0:
                print(f" 경고: '{filepath.name}' 파일의 페이지가 0개입니다.")
                return []
                
            print(f"'{filepath.name}' 파일 분할 중... (총 {end_pages} 페이지)")
            
            pdf_page_bytes = extract_pdf_pages_to_bytes(input_pdf_path, 1, end_pages)
            
            base_extracted_problems: List[PDFProbData] = []

            prompt = "해당 PDF '페이지' 내의 모든 문제를 [규칙]을 엄격히 준수하여 'PDFProbResponse' 스키마에 맞게 '기본 데이터'만 추출하십시오."

        except FileNotFoundError: 
            print(f"PDF 파일을 찾을 수 없습니다: {input_pdf_path}", file=sys.stderr)
            return None
        except Exception as e:
            print(f"PDF 페이지 분할/읽기 중 오류 발생: {e}", file=sys.stderr)
            return None

        for i, page_bytes in enumerate(pdf_page_bytes):
            page_num = i + 1
            print(f"\n--- {page_num} / {end_pages} 페이지 Base Data 추출 시작 ---")
            start_time = time.time()
            response_text = None # 페이지마다 초기화

            # API 재시도 루프 (페이지당) 
            for attempt in range(self.MAX_RETRIES):
                try:
                    # --- AI API 호출 ---
                    response = self.client.models.generate_content(
                        model=self.model,
                        contents=[
                            types.Part.from_bytes(data=page_bytes, mime_type='application/pdf'),
                            prompt
                        ],
                        config=config
                    )
                    
                    if response and response.text:
                        response_text = response.text
                        break # [SUCCESS] API 호출 성공, 재시도 루프 탈출
                    else:
                        print(f"  API 응답이 비어있습니다. (시도 {attempt + 1}/{self.MAX_RETRIES})")

                except errors.APIError as e: 
                    status_code = getattr(e, 'status_code', 500)
                    is_retryable = (status_code == 429) or (status_code >= 500)
                    
                    print(f"  API 오류 (HTTP {status_code})... (시도 {attempt + 1}/{self.MAX_RETRIES})")
                    
                    if not is_retryable or (attempt + 1) == self.MAX_RETRIES:
                        print(f"  재시도 불가능 오류({status_code})이거나, 최대 재시도 횟수에 도달했습니다.")
                        break # 재시도 루프 탈출
                    
                    wait_time = 2 ** attempt
                    print(f"  재시도 전 {wait_time}초 대기...")
                    time.sleep(wait_time)
                
                except Exception as e: 
                    print(f"  API 호출 중 예상 못한 오류 (시도 {attempt + 1}/{self.MAX_RETRIES}): {e}")
                    if (attempt + 1) == self.MAX_RETRIES:
                        break # 재시도 루프 탈출
                    time.sleep(1) # 잠시 대기 후 재시도
            
            duration_time = time.time() - start_time
            
            # 페이지별 결과 파싱 
            if response_text:
                try:
                    # Pydantic이 JSON을 검증
                    # 'ai_analysis' 필드가 없으면 default=None으로 자동 처리
                    parsed_data_for_page = PDFProbResponse.model_validate_json(response_text)
                    
                    if parsed_data_for_page.problems:
                        print(f"✅ {page_num} 페이지에서 {len(parsed_data_for_page.problems)}개의 base data를 성공적으로 추출했습니다. (소요 시간: {duration_time:.2f}초)")

                        base_extracted_problems.extend(parsed_data_for_page.problems) 
                    else:
                        print(f"{page_num} 페이지에서 추출된 문제가 없습니다. (소요 시간: {duration_time:.2f}초)")
                
                except ValidationError as e: 
                    # JSON 잘림 오류 감지
                    print(f"데이터 유효성 검증 오류 (AI가 잘못된 JSON 반환): {e}", file=sys.stderr)
                    print(f"  (AI 원본 응답: {response_text[:100]}...)")
                
                except json.JSONDecodeError as e: # (JSON 파싱 실패)
                    print(f"  JSON 파싱 오류: {e}", file=sys.stderr)
                    print(f"  (AI 원본 응답: {response_text[:100]}...)")
            else:
                print(f"  실패: {page_num} 페이지 분석에 최종 실패했습니다 (API 응답 없음).")

        # 최종 반환 전, ai_analysis 필드가 None인지 확인하는 검증 로직
        if any(problem.ai_analysis is not None for problem in base_extracted_problems):
            # None으로 다시 강제 초기화
            for problem in base_extracted_problems:
                problem.ai_analysis = None 
        if any(problem.year is not None for problem in base_extracted_problems):
            # None으로 다시 강제 초기화
            for problem in base_extracted_problems:
                problem.year = None 
        if any(problem.month is not None for problem in base_extracted_problems):
            # None으로 다시 강제 초기화
            for problem in base_extracted_problems:
                problem.month = None 

        if not base_extracted_problems:
            print("--- AI 분석 완료. 추출된 문제가 없습니다. ---")
            return []
        
        # 연도와 월 주입
        from .prob_data_processer import process_pdf_year_and_month
        year_month = process_pdf_year_and_month(input_pdf_path)
        year, month = None, None
        if year_month is not None and len(year_month) == 2:
            year, month = year_month

        for problem in base_extracted_problems:
            problem.year = int(year) if year is not None else None
            problem.month = month
        
        return base_extracted_problems

    def __extract_pdf_ai_analysis_data(self, input_pdf_path):
        '''
        AI가 PDF 내의 모든 문제에서 ai_analysis 데이터 추출 
        '''
        # '시스템 지침' 설정
        system_instruction = f"""
        당신은 대한민국 수능/평가원 기출문제의 전문 분석가입니다. 
        당신의 유일한 임무는, 지금부터 입력될 PDF 파일을 처음부터 끝까지 정확하게 읽고,
        PDF 파일 내의 모든 수학 문제를 인식하여 
        각 문제에서 ai_analysis 필드를 추출하는 것입니다.
        이때 ai_analysis는 반드시 AiAnalysis Pydantic 스키마에 맞게 추출해야 합니다.

        [규칙]
        [규칙 1: 응답 형식]
        다른 설명 없이, 반드시 'PDFProbResponse' Pydantic 스키마에 맞는 JSON 형식으로만 응답해야 합니다.
        PDF에 문제가 여러 개 있으면 "problems" 리스트에 순서대로 모두 추가해야 합니다.
        절대로 ai_analysis 필드 외의 를 응답에 포함하지 마십시오.
        다른 필드
            - subject_name
            - unit_name
            - problem_text
            - number
            - year
            - month
            - problem_id
        는 절대로 응답에 포함하지 마십시오.

        [규칙 2: ai_analysis 추출]
        각각의 수학 문제를 '교육자'의 관점에서 정밀하게 '분석(analyze)'하는 것입니다.  
        이 분석 결과는 ProbDex의 지능형 데이터베이스에 저장되어, 나중에 '개념적 원형'을 검색하는 핵심 인덱스(Index)로 사용될 것입니다.
        당신의 역할은 다음과 같습니다
        입력된 PDF의 각각의 문제 마다 5가지 핵심 '교육적 메타데이터'를 추출해야 합니다.
        다른 설명이나 인사말 없이, 반드시 "AiAnalysis" Pydantic 스키마에 맞는 JSON 형식으로만 응답해 주십시오.

        [ai_analysis field에서 분석할 5가지 핵심 요소]

        1. core_concepts: List[str]
        이 문제를 푸는 데 사용되는 '핵심 개념'입니다. (예: "미분계수의 기하학적 의미", "절댓값 함수의 미분 가능성")

        2. logic_flow: str
        학생이 정답에 도달하기 위한 '이상적인 사고 과정'입니다. (예: "1. f(x) 그래프 개형 추론 -> 2. 조건 (가)를 이용한 ...")

        3.  pattern_type: List[str]
        문항의 '전형적인 유형'입니다. (예: "합답형(ㄱ,ㄴ,ㄷ)", "개념 통합형", "그래프 추론, "단순 계산형")

        4. pitfalls: List[str]
        학생들이 자주 실수하거나 놓치기 쉬운 '주요 함정'입니다. (예: "정의역(x>0) 조건 미고려", "로그에서 진수 조건 누락")

        5. difficulty_level: int
        1(매우 쉬움)부터 5(매우 어려움)까지의 '정수' 난이도입니다.

        문제의 수학적 구조를 단순히 요약하지 말고  
        교사가 문제를 분석하듯 5가지의 핵심 요소 추출에 초점을 맞추십시오.

        [최종 출력 형식 엄격 준수]
        반드시 다음 "예시 JSON" 구조와 키 이름, 대소문자, 타입을 정확히 따르십시오. 예시 외의 어떤 텍스트도 출력하지 마십시오.

        [예시 JSON]
        {{
            "problems": [
                {{
                    "ai_analysis": {{
                        "core_concepts": ["다항함수의 미분", "극값의 정의"],
                        "logic_flow": "1. 함수의 도함수 계산 -> 2. 도함수가 0이 되는 x값을 구한다 -> 3. 해당 x값에서의 도함수 부호 변화를 통해 극값 판별",
                        "pattern_type": ["단순 계산형"],
                        "pitfalls": ["도함수 계산 실수", "부호판정 누락"],
                        "difficulty_level": 1
                    }}
                }}
               
            ]
        }}
        
        [추출 오류 시 대처법]
        아래 어느 경우에도 JSON 구조를 절대로 변경하지 마십시오.
        필드를 누락하거나 이름을 수정하거나 타입을 바꾸지 마십시오.

        PDF 텍스트가 손상되었거나, 문제를 인식할 수 없거나, 특정 값을 정확하게 판단할 수 없을 때는 
        다음 기본 규칙에 따라 대체값을 넣으십시오.

        [1] 기본 문자열 필드(str)
        다음 필드들은 값 추출에 실패하면 빈 문자열("")로 채우십시오.
        (1) logic_flow

        [2] 리스트 필드(list[str])
        다음 필드들은 값 추출에 실패하면 빈 리스트([])로 채우십시오.
        (1) core_concepts, (2) pitfalls, (3) pattern_type

        [3] 정수 필드(int)
        다음 필드들은 값 추출에 실패하면 정수(0)으로 채우십시오.
        (1) difficulty_level
        
        [4] 전체 ai_analysis 블록이 생성 불가능할 때
        ai_analysis 전체를 추론하기 어려운 경우에도 구조는 유지하며 다음의 기본값을 사용하십시오:
        "ai_analysis": {{
            "core_concepts": [],
            "logic_flow": "",
            "pattern_type": [],
            "pitfalls": [],
            "difficulty_level": 0
        }}

        [5] 문제 하나라도 JSON 스키마를 벗어난 결과를 생성하지 마십시오.
        다음과 같은 행위는 절대로 하지 마십시오:
            - JSON 키 이름 변경
            - 스키마에서 정의되지 않은 새로운 키 추가
            - 스키마 필드 누락
            - None/null 반환
            - 임의로 데이터 type 변경 (예: 정수를 문자열로 변환)
            - "에러가 있습니다" 같은 자연어 텍스트 추가
        출력은 오직 Pydantic 스키마에 맞는 JSON 데이터만 생산해야 하며, 구조적 에러가 발생하지 않아야 합니다.
        """
        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=0.2, 
            response_mime_type='application/json',
            response_schema=PDFProbResponse 
        )
        
        
        try:
            from .utility_pdf import extract_pdf_pages_to_bytes, get_pdf_page_count
            filepath = pathlib.Path(input_pdf_path)
            
            end_pages = get_pdf_page_count(input_pdf_path)
            if end_pages == 0:
                print(f" 경고: '{filepath.name}' 파일의 페이지가 0개입니다.")
                return []
                
            print(f"'{filepath.name}' 파일 분할 중... (총 {end_pages} 페이지)")
            
            pdf_page_bytes = extract_pdf_pages_to_bytes(input_pdf_path, 1, end_pages)
            
            ai_analysis_extracted_problems: List[PDFProbData] = []

            prompt = "해당 PDF '페이지' 내의 모든 문제를 [규칙]을 엄격히 준수하여 'PDFProbResponse' 스키마에 맞게 추출하고 분류하십시오."

        except FileNotFoundError: 
            print(f"PDF 파일을 찾을 수 없습니다: {input_pdf_path}", file=sys.stderr)
            return None
        except Exception as e:
            print(f"PDF 페이지 분할/읽기 중 오류 발생: {e}", file=sys.stderr)
            return None

        
        for i, page_bytes in enumerate(pdf_page_bytes):
            page_num = i + 1
            print(f"\n--- {page_num} / {end_pages} 페이지 AI 분석 시작 ---")
            start_time = time.time()
            response_text = None # 페이지마다 초기화

            # API 재시도 루프 (페이지당) 
            for attempt in range(self.MAX_RETRIES):
                try:
                    # --- AI API 호출 ---
                    response = self.client.models.generate_content(
                        model=self.model,
                        contents=[
                            types.Part.from_bytes(data=page_bytes, mime_type='application/pdf'),
                            prompt
                        ],
                        config=config
                    )
                    
                    if response and response.text:
                        response_text = response.text
                        break # [SUCCESS] API 호출 성공, 재시도 루프 탈출
                    else:
                        print(f"  API 응답이 비어있습니다. (시도 {attempt + 1}/{self.MAX_RETRIES})")

                except errors.APIError as e: 
                    status_code = getattr(e, 'status_code', 500)
                    is_retryable = (status_code == 429) or (status_code >= 500)
                    
                    print(f"  API 오류 (HTTP {status_code})... (시도 {attempt + 1}/{self.MAX_RETRIES})")
                    
                    if not is_retryable or (attempt + 1) == self.MAX_RETRIES:
                        print(f"  재시도 불가능 오류({status_code})이거나, 최대 재시도 횟수에 도달했습니다.")
                        break # 재시도 루프 탈출
                    
                    wait_time = 2 ** attempt
                    print(f"  재시도 전 {wait_time}초 대기...")
                    time.sleep(wait_time)
                
                except Exception as e: 
                    print(f"  API 호출 중 예상 못한 오류 (시도 {attempt + 1}/{self.MAX_RETRIES}): {e}")
                    if (attempt + 1) == self.MAX_RETRIES:
                        break # 재시도 루프 탈출
                    time.sleep(1) # 잠시 대기 후 재시도
            duration_time = time.time() - start_time
            
            # 페이지별 결과 파싱 
            if response_text:
                try:
                    data_dict = json.loads(response_text)
                    parsed_data_for_page = PDFProbResponse.model_construct(**data_dict)
                    
                    if parsed_data_for_page.problems:
                        print(f"✅ {page_num} 페이지에서 {len(parsed_data_for_page.problems)}개의 ai_analysis를 성공적으로 분석했습니다. (소요 시간: {duration_time:.2f}초)")

                        ai_analysis_extracted_problems.extend(parsed_data_for_page.problems) 
                    else:
                        print(f"{page_num} 페이지에서 분석된 문제가 없습니다. (소요 시간: {duration_time:.2f}초)")
                
                except ValidationError as e: 
                    print(f"데이터 유효성 검증 오류 (AI가 잘못된 JSON 반환): {e}", file=sys.stderr)
                    print(f"  (AI 원본 응답: {response_text[:100]}...)")
                
                except json.JSONDecodeError as e: # (JSON 파싱 실패)
                    print(f"  JSON 파싱 오류: {e}", file=sys.stderr)
                    print(f"  (AI 원본 응답: {response_text[:100]}...)")
            else:
                print(f"  실패: {page_num} 페이지 분석에 최종 실패했습니다 (API 응답 없음).")
        
        # 최종 결과 처리
        if not ai_analysis_extracted_problems:
            print("--- AI 분석 완료. 추출된 문제가 없습니다. ---")
            return []
        
        print(f"\n--- AI 분석 완료. 총 {len(ai_analysis_extracted_problems)}개의 문제 추출. 연도/월 정보 주입 중... ---")

        return ai_analysis_extracted_problems

    def __return_pdf_meta_data(self, base_data : List[PDFProbData], ai_analysis : dict):
        '''
        PDF의 메타 데이터 반환.
        '''
        # base_extracted_problems, ai_analysis 병합 로직 구현
        # problem_id 생성 및 주입
        
        for problem in base_data:
            if problem.year is not None and problem.month is not None:
                problem.problem_id = generate_problem_id(
                    problem.year, 
                    problem.month, 
                    problem.number, 
                    problem.subject_name
                )
            else:
                # year나 month를 파싱하지 못했다면 problem_id도 None으로 설정
                problem.problem_id = None
        # ai_analysis 데이터 주입
        for problem, ai_problem in zip(base_data, ai_analysis):
            problem.ai_analysis = ai_problem.ai_analysis

        return base_data

    def extract_pdf_meta_data(self, input_pdf_path, skip_pages = None):
        '''
        PDF에서 기본 데이터와 AI 분석 데이터를 모두 추출하여 병합 후 반환.
        '''
        if skip_pages is None:
            skip_pages = set()

        system_instruction = f"""
        당신은 대한민국 수능/평가원 수학 기출 PDF 전문 분석가입니다. 
        입력되는 PDF에서 모든 문항을 읽어 각 문제를 다음 4개 요소로 추출하십시오:
        (1) subject_name, (2) unit_name, (3) number, (4) ai_analysis
        이때 (1)~(3)는 반드시 PDFProbData Pydantic 스키마에 맞게 추출해야 합니다. 
        (4) ai_analysis는 반드시 AiAnalysis Pydantic 스키마에 맞게 추출해야 합니다.

        문제 텍스트 이외의 손필기나 메모는 절대로 분석에 포함시키지 않습니다.
        
        ────────────────────────────────
        [규칙 1: 분류 기준] 과목명(subject_name)은 반드시 다음 리스트 중 하나여야 합니다: 
        {list(master_data.keys())} 
        
        [규칙 2: 과목-단원 종속성] 
        단원명(unit_name)은 반드시 해당 과목의 다음 리스트 중 하나여야 합니다: 
            - 수학1: {master_data['수학1']} 
            - 수학2: {master_data['수학2']} 
            - 미적분: {master_data['미적분']} 
            - 확률과 통계: {master_data['확률과 통계']} 
            - 기하: {master_data['기하']} 
            - 분류 불가: {master_data['분류 불가']} 
        PDF의 텍스트가 문제가 아니거나(예: 표지, 해설) 분류가 불가능하면 "분류 불가"로 지정하십시오. 
        문제에 여러 단원의 개념이 포함되어 단원을 하나로 특정하기 어려울 경우, 
        문제 해결 과정에서 정답 도출에 직접적으로 기여하는 ‘주요 개념’이 속한 단원을 선택하십시오. 

        ────────────────────────────────
        [규칙 3: 문항 번호 규칙]
            - number는 PDF의 문항 번호를 정수로만 추출
            - 번호가 존재하지 않거나 불분명하면 0

        ────────────────────────────────
        [ai_analysis 규칙]
        ai_analysis는 다음 스키마를 반드시 유지:
        {{
            "core_concepts": [str],
            "logic_flow": str,
            "pattern_type": [str],
            "pitfalls": [str],
            "difficulty_level": int(1~5)
        }}

        - difficulty_level 필드 :
        - 1~5 정수
        - 배점([2점],[3점],[4점])은 참고만 하고 결정 기준은 “수학적 복잡성·개념 통합·계산량”
        - 판단 불가 시 0

        ────────────────────────────────
        [에러 처리 규칙(필수)]
        값 추출 실패 시 기본값을 넣되, 스키마 구조는 절대 유지:

        문자열(str) 필드 실패 → ""
        정수(int) 필드 실패 → 0
        리스트(list[str]) 필드 실패 → []
        ai_analysis 전체 생성 불가 시:
        {{
            "core_concepts": [],
            "logic_flow": "",
            "pattern_type": [],
            "pitfalls": [],
            "difficulty_level": 0
        }}

        ────────────────────────────────
        [출력 형식 규칙]
        출력은 오직 Pydantic 스키마에 맞는 JSON 데이터만 생산해야 하며, 구조적 에러가 발생하지 않아야 합니다.
            - year, month, problem_id는 JSON에서 절대 생성하지 않음
            - 스키마 키 이름·대소문자·자료형 절대 변경 금지
            - 새로운 필드 추가 금지
            - 자연어 설명 금지. 오직 JSON만 출력

        ────────────────────────────────
        [예시 JSON]
        {{
            "problems": [
                {{
                    "subject_name": "미적분",
                    "unit_name": "미분법",
                    "number": 24,
                    "ai_analysis": {{
                        "core_concepts": ["초월함수의 미분", "극값의 정의"],
                        "logic_flow": "1. 함수의 도함수 계산 -> 2. 도함수가 0이 되는 x값을 구한다 -> 3. 해당 x값에서의 도함수 부호 변화를 통해 극값 판별",
                        "pattern_type": ["단순 계산형"],
                        "pitfalls": ["도함수 계산 실수", "부호판정 누락"],
                        "difficulty_level": 1
                    }}
                }}
               
            ]
        }}
        
        
        """

        config = types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=self.TEMPERATURE, 
            response_mime_type='application/json',
            response_schema=PDFProbResponse,
            thinking_config=types.ThinkingConfig(thinking_budget= self.THINKING_BUDGET) 
        )
        
        try:
            from .utility_pdf import extract_pdf_pages_to_bytes, get_pdf_page_count
            filepath = pathlib.Path(input_pdf_path)
            
            end_pages = get_pdf_page_count(input_pdf_path)
            if end_pages == 0:
                print(f" 경고: '{filepath.name}' 파일의 페이지가 0개입니다.")
                return []
                
            print(f"'{filepath.name}' 파일 분할 중... (총 {end_pages} 페이지)")
            
            pdf_page_bytes = extract_pdf_pages_to_bytes(input_pdf_path, 1, end_pages)
            
            all_extracted_problems: List[PDFProbData] = []

            prompt = "해당 PDF '페이지' 내의 모든 문제를 [규칙]을 엄격히 준수하여 'PDFProbResponse' 스키마에 맞게 '기본 데이터'만 추출하십시오."

        except FileNotFoundError: 
            print(f"PDF 파일을 찾을 수 없습니다: {input_pdf_path}", file=sys.stderr)
            return None
        except Exception as e:
            print(f"PDF 페이지 분할/읽기 중 오류 발생: {e}", file=sys.stderr)
            return None

        for i, page_bytes in enumerate(pdf_page_bytes):
            page_num = i + 1
            if page_num in skip_pages:
                print(f"  [SKIP] 이미 분석된 {page_num} 페이지")
                continue
            print(f"\n--- {page_num} / {end_pages} 페이지 meta Data 추출 시작 ---")
            start_time = time.time()
            response_text = None # 페이지마다 초기화

            # API 재시도 루프 (페이지당) 
            for attempt in range(self.MAX_RETRIES):
                try:
                    # --- AI API 호출 ---
                    
                    response = self.client.models.generate_content(
                        model=self.model,
                        contents=[
                            types.Part.from_bytes(data=page_bytes, mime_type='application/pdf'),
                            prompt
                        ],
                        config=config
                    )
                    
                    if response and response.text:
                        response_text = response.text
                        break # [SUCCESS] API 호출 성공, 재시도 루프 탈출
                    else:
                        print(f"  API 응답이 비어있습니다. (시도 {attempt + 1}/{self.MAX_RETRIES})")

                except errors.APIError as e: 
                    status_code = getattr(e, 'status_code', 500)
                    is_retryable = (status_code == 429) or (status_code >= 500) 
                    
                    print(f"  API 오류 (HTTP {status_code})... (시도 {attempt + 1}/{self.MAX_RETRIES})")
                    
                    if not is_retryable or (attempt + 1) == self.MAX_RETRIES:
                        print(f"  재시도 불가능 오류({status_code})이거나, 최대 재시도 횟수에 도달했습니다.")
                        break # 재시도 루프 탈출
                    
                    wait_time = self.RETRY_DELAY_SECONDS 
                    print(f"  재시도 전 {wait_time}초 대기...")
                    time.sleep(wait_time)
                
                except Exception as e: 
                    print(f"  API 호출 중 예상 못한 오류 (시도 {attempt + 1}/{self.MAX_RETRIES}): {e}")
                    if (attempt + 1) == self.MAX_RETRIES:
                        break # 재시도 루프 탈출
                    time.sleep(1) # 잠시 대기 후 재시도
            
            duration_time = time.time() - start_time
            
            # 페이지별 결과 파싱 
            if response_text:
                try:
                    # Pydantic이 JSON을 검증
                    # 'ai_analysis' 필드가 없으면 default=None으로 자동 처리
                    parsed_data_for_page = PDFProbResponse.model_validate_json(response_text)
                    
                    if parsed_data_for_page.problems:
                        print(f"✅ {page_num} 페이지에서 {len(parsed_data_for_page.problems)}문제의 meta data를 성공적으로 추출했습니다. (소요 시간: {duration_time:.2f}초)")

                        all_extracted_problems.extend(parsed_data_for_page.problems) 
                    else:
                        print(f"{page_num} 페이지에서 추출된 문제가 없습니다. (소요 시간: {duration_time:.2f}초)")
                
                except ValidationError as e: 
                    # JSON 잘림 오류 감지
                    print(f"데이터 유효성 검증 오류 (AI가 잘못된 JSON 반환): {e}", file=sys.stderr)
                    print(f"  (AI 원본 응답: {response_text[:100]}...)")
                
                except json.JSONDecodeError as e: # (JSON 파싱 실패)
                    print(f"  JSON 파싱 오류: {e}", file=sys.stderr)
                    print(f"  (AI 원본 응답: {response_text[:100]}...)")
            else:
                print(f"  실패: {page_num} 페이지 분석에 최종 실패했습니다 (API 응답 없음).")

        if not all_extracted_problems:
            print("--- AI 분석 완료. 추출된 문제가 없습니다. ---")
            return []
        
        # 연도와 월 주입
        from .prob_data_processer import process_pdf_year_and_month
        year_month = process_pdf_year_and_month(input_pdf_path)
        year, month = None, None

        if year_month is not None and len(year_month) == 2:
            year, month = year_month

        for problem in all_extracted_problems:
            problem.year = int(year) if year is not None else None
            problem.month = month

        for problem in all_extracted_problems:
            if problem.year is not None and problem.month is not None:
                problem.problem_id = generate_problem_id(
                    problem.year, 
                    problem.month, 
                    problem.number, 
                    problem.subject_name
                )
            else:
                problem.problem_id = None # DB가 알아서 채우도록 비워둠
                # print(" (참고) problem_id 없이 진행합니다.")

        return all_extracted_problems

    def analyze_pdf_user_meta_data(self, user_pdf_path):
        '''
        사용자 pdf 파일에서 메타 데이터 분석
        '''
        engine = ProbDexEngine()
        meta_data = engine.extract_pdf_meta_data(
            input_pdf_path= user_pdf_path, 
            skip_pages = None
            )
        return meta_data
    
# TODO: 이미지 메타데이터 추출 기능 구현
    def extract_user_image_meta_data(self, input_image_path):
        '''
        사용자 이미지 파일에서 메타 데이터 추출
        '''
        pass


# TODO 30번 문제의 난이도를 '2'라고 명백히 잘못 분석한 AI의 오류를 자동으로 감지하고 플래그를 지정하는 검증 시스템 구현
