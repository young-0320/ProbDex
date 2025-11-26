# ---models.py---

from pydantic import BaseModel, Field, ValidationError, model_validator
from typing import List, Dict, Literal

# 사용 가능 모델 
'''
기본적으로 다음 모델을 사용합니다 google-genai.

일반 텍스트 및 다중 모드 작업: gemini-2.5-flash
코딩 및 복잡한 추론 과제: gemini-2.5-pro
낮은 지연 시간 및 높은 볼륨 작업: gemini-2.5-flash-lite
이미지 편집 및 조작: gemini-2.5-flash-image
고품질 이미지 생성: imagen-4.0-generate-001
빠른 이미지 생성: imagen-4.0-fast-generate-001
고급 이미지 생성: imagen-4.0-ultra-generate-001

사용자가 명시적으로 요청한 경우 다음 모델을 사용하는 것도 허용됩니다.
제미니 2.0 시리즈 : gemini-2.0-flash, gemini-2.0-flash-lite

금지사항: gemini-1.5-flash
금지사항: gemini-1.5-pro
금지사항: gemini-pro
'''
'''
2.5 Pro	동적 사고: 모델이 사고 시점과 사고량을 결정함 thinkingBudget = -1	
생각을 사용 중지할 수 없음	thinkingBudget = 0 : 불가능
thinkingBudget = 128~32768

2.5 Flash 동적 사고: 모델이 사고 시점과 사고량을 결정함	thinkingBudget = -1
사고 중지 가능 thinkingBudget = 0 : 가능
thinkingBudget = 0~24576	
'''
subject_normalization_map = {
    # 수학1 
    '수학1': '수학1',  # (표준)
    '수학 1': '수학1',
    '수학 Ⅰ': '수학1', # (로마자 대문자)
    '수학Ⅰ': '수학1',
    '수학 I': '수학1', # (영어 대문자 I)
    '수학I': '수학1',
    '수학 i': '수학1', # (영어 소문자 i)
    '수학i': '수학1',
    '수1': '수학1',
    '수 1': '수학1',
    '수Ⅰ': '수학1',
    '수 Ⅰ': '수학1',
    '수 I': '수학1',
    '수I': '수학1',

    # 수학2 
    '수학2': '수학2',  # (표준)
    '수학 2': '수학2',
    '수학 Ⅱ': '수학2', # (로마자 대문자 II)
    '수학Ⅱ': '수학2',
    '수학 II': '수학2', # (영어 대문자 II)
    '수학II': '수학2',
    '수학 ii': '수학2', # (영어 소문자 ii)
    '수학ii': '수학2',
    '수2': '수학2',
    '수 2': '수학2',
    '수Ⅱ': '수학2',
    '수 Ⅱ': '수학2',
    '수 II': '수학2',
    '수II': '수학2',

    # 기타 과목 
    '미적': '미적분',
    '미적분': '미적분',
    '확통': '확률과 통계',
    '확률과 통계': '확률과 통계',
    '기벡': '기하', 
    '기하': '기하',
    '기하와 벡터': '기하'
}

problem_number_map = {
    # 'common' 파일의 페이지별 문제 번호 리스트
    "공통": {
        1: [1, 2, 3, 4],
        2: [5, 6, 7],
        3: [8, 9, 10],
        4: [11, 12],
        5: [13, 14],
        6: [15, 16, 17],
        7: [18, 19, 20],
        8: [21, 22]
    },
    # '선택 과목' 파일의 페이지별 문제 번호 리스트
    "미적분": {
        1: [23, 24],
        2: [25, 26],
        3: [27, 28],
        4: [29, 30]
    },
    "기하": {
        1: [23, 24],
        2: [25, 26],
        3: [27, 28],
        4: [29, 30]
    },
    "확률과 통계": {
        1: [23, 24],
        2: [25, 26],
        3: [27, 28],
        4: [29, 30]
    }
}

subject_code_map = {
    "수학1": "01",
    "수학2": "02",
    "미적분": "03",
    "기하": "04",
    "확률과 통계": "05",
    "분류 불가": "99"
}

master_data = {
        "수학1": ["지수함수와 로그함수", "삼각함수", "수열"],
        "수학2": ["함수의 극한과 연속", "미분", "적분"],
        "미적분": ["수열의 극한", "미분법", "적분법"], 
        "확률과 통계": ["경우의 수", "확률", "통계"],
        "기하": ["이차곡선", "평면벡터", "공간도형과 공간좌표"],
        "분류 불가": ["분류 불가"] # 이 결과가 나오면 수작업 분석
    }

subject_map = {
    "common": "공통",
    "cal": "미적분",
    "geo": "기하",
    "sta": "확률과 통계"
}
valid_subjects = Literal["수학1", "수학2", "미적분", "확률과 통계", "기하", "분류 불가"]

class AiAnalysis(BaseModel):
    """
    PDF에서 추출한 ai_analysis field를 구조화하기 위한 Pydantic 모델
    """
    core_concepts: list[str] = Field(..., description="이 문제를 푸는 데 사용되는 '핵심 개념' 리스트입니다.")
    logic_flow: str = Field(..., description="학생이 정답에 도달하기 위한 '이상적인 사고 과정'입니다. (단계별 서술)")
    pattern_type: list[str] = Field(..., description="문항의 '전형적인 유형'입니다. (예: '합답형(ㄱ,ㄴ,ㄷ)', '그래프 추론')")
    pitfalls: list[str] = Field(..., description="학생들이 자주 실수하거나 놓치기 쉬운 '주요 함정' 리스트입니다.")
    difficulty_level: int = Field(..., description="1(매우 쉬움)부터 5(매우 어려움)까지의 '정수' 난이도입니다.")

class PDFProbData(BaseModel):
    """
    PDF에서 추출한 각 문제의 메타데이터를 구조화하기 위한 Pydantic 모델
    """
    subject_name: valid_subjects = Field(..., description="문제의 과목명 master_data의 키 중 하나(예: '수학 I', '미적분')")
    unit_name: str = Field(..., description="문제의 핵심 단원명 (예: '지수함수와 로그함수')")
    number: int = Field(..., description="문제 번호 (예: 30)")
    year: int | None = Field(default=None)
    month: str | None = Field(default=None)
    ai_analysis: AiAnalysis | None = Field(default=None, description="AI가 분석한 문제 메타데이터 딕셔너리")
    problem_id: int | None = Field(default=None, description="고유 ID (예: 2022062303)")

    @model_validator(mode='after')
    def validate_subject_unit_pair(self) -> 'PDFProbData':
        """
        subject와 unit의 관계가 master_data와 일치하는지 검증합니다.
        """
        subject = self.subject_name
        unit = self.unit_name
        
        # unit만 검사
        if unit not in master_data[subject]:
            # AI가 잘못된 조합을 생성했을 경우 오류 발생
            raise ValueError(f"'{unit}'은(는) '{subject}' 과목의 유효한 단원이 아닙니다. "
                             f"유효한 단원: {master_data[subject]}")
        return self
    
    
class PDFProbResponse(BaseModel):
    """
    PDF 전체를 분석하여 문제 리스트를 반환하는 스키마
    """
    problems: List[PDFProbData] = Field(..., description="PDF에서 추출된 모든 문제의 리스트")

# TODO : problem_text 내에 latex 수식이 올바른지 검증
# TODO : number가 1~30 사이의 정수인지 검증
# TODO : ai_analysis의 각 필드 타입 및 값 검증
# TODO : year, month 필드 검증

def generate_problem_id(year, month, number, subject) -> int | None:
    """
    입력된 정보를 조합하여 고유 ID(정수)를 생성
    """
    try:
        subject_code = subject_code_map.get(subject, "00")

        # month와 number를 2자리 문자열로 포맷팅
        month_formatted = f"{int(month):02d}"
        number_formatted = f"{int(number):02d}"

        id_str = f"{year}{month_formatted}{number_formatted}{subject_code}"
        return int(id_str)

    except (ValueError, TypeError):
        print(f"경고: ID 생성 실패 (year:{year}, month:{month}, num:{number})")
        return None