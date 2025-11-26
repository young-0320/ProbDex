## 실행 전 필수 설정

이 프로젝트를 실행하려면 **Google Gemini API 키**가 필요합니다.

1. **Google AI Studio에서 API 키를 발급**받으십시오.
2. `.env` 이름의 파일을 최상위 폴더(my-first-project)에 생성하고 다음과 같이 자신의 API 키를 입력하십시오.
   ```
   GEMINI_API_KEY='여기에_발급받은_API_키를_입력하십시오'
   ```
3. `.env` 파일에 키를 입력 후 꼭 저장을 하십시오.
4. user_input/input_pdf_problems폴더 내부에 분석을 원하는 파일(혹은 test_input_problem폴더의 테스트 문제)를 업로드하십시오.
5. 터미널에서 `poetry install`을 실행한 후, poetry run python -m src.my_first_project.main로 프로그램을 실행하십시오.



폴더 구조
```

ProbDex_Project/
├── .pytest_cache                       # pytest 실행 시 생성되는 캐시 디렉토리 (테스트 속도 향상)
├── .venv                               # [Poetry] 가상 환경 디렉토리 (프로젝트 전용 라이브러리 설치 공간)
├── assets/                             # 시스템 데이터 저장소 (기출 PDF, DB, 이미지 리소스 등)
│   ├── problem_images/                 # PDF에서 페이지/문항별로 추출된 이미지 파일 저장소
│   ├── processed_pdfs/                 # 원본 PDF를 공통/선택 과목 등으로 분할 처리한 파일 저장소
│   ├── raw_problem_pdfs/               # 평가원 원본 기출 문제 PDF 파일 저장소
│   ├── base_problems.json              # 추출된 문제 메타데이터 및 AI 분석 결과 (JSON 포맷)
│   └── base_problems.xlsx              # 추출된 문제 메타데이터 및 AI 분석 결과 (Excel 포맷)
├── src/
│   └── my_first_project/               # 소스 코드 메인 패키지
│       ├── __init__.py                 # 파이썬 패키지 초기화 파일
│       ├── main.py                     # [Entry Point] 프로그램 실행 진입점 (CLI/GUI 모드 분기)
│       ├── config.py                   # 프로젝트 전역 경로, 상수, 파일명 설정 관리
│       ├── model.py                    # Pydantic 기반 데이터 모델 정의 및 유효성 검사
│       ├── engine.py                   # Gemini AI API 연동 및 프롬프트 제어 엔진 (V1)
│       ├── database.py                 # SQLite DB 스키마 생성, 연결, 기본 쿼리 함수 모음
│       ├── prob_data_processer.py      # 데이터 정제, 포맷 변환(Excel↔JSON), 텍스트 전처리 로직
│       ├── utility_pdf.py              # PDF 페이지 분할, 이미지 변환 등 유틸리티 함수
│       ├── similarity.py               # 기초 유사도 계산 알고리즘 (자카드, 텍스트 매칭)
│       ├── similarity_v2.py            # 고급 유사도 알고리즘 (TF-IDF, 코사인 유사도 적용)
│       ├── probdex_pipeline.py         # 시스템 데이터 구축 및 전체 ETL 파이프라인 관리
│       ├── user_pipeline.py            # 사용자 검색 서비스 실행 파이프라인 (초기 버전)
│       ├── user_pipeline_v2.py         # 사용자 검색 서비스 파이프라인 (개선된 로직 적용)
│       ├── user_pipeline_v3.py         # 사용자 검색 서비스 파이프라인 (최신 검색 로직 적용)
│       ├── gui_manager.py              # Tkinter 기반 GUI 인터페이스 컨트롤러 (V1)
│       └── gui_manager_v2.py           # 개선된 GUI 컨트롤러 (이미지 캐러셀, 상세 정보 표시 등)
├── user_input/                         # 사용자 데이터 관련 디렉토리
│   └── input_pdf_problems/             # 사용자가 검색을 위해 업로드하는 PDF 파일 저장소
├── .env                                # API Key(GEMINI_API_KEY) 보안 환경 변수 파일
├── poetry.lock                         # [Poetry] 의존성 패키지 버전 잠금 파일 (환경 재현성 보장)
├── pyproject.toml                      # [Poetry] 프로젝트 설정 및 의존성 명세 파일
├── probdex.db                          # [System DB] 마스터 데이터베이스 (기출 문제 원본 데이터)
├── README.md                           # 프로젝트 설명 및 실행 가이드 문서
└── user_probdex.db                     # [User DB] 사용자 검색 기록 및 분석 데이터 저장용 데이터베이스
```

실행 구문

base_problems.xlsx와 json, probdex 동기화 :

poetry run python -m src.my_first_project.database

probdex 실행 :

poetry run python -m src.my_first_project.main


### 1. 프로젝트 소개 및 핵심 가치

ProbDex는 수학 문제의 **표면적인 형태를 넘어** 그 안에 내재된 **교육적 맥락**과 **개념적 원형**을 탐색하는 것을 목표로 합니다. 

이는 교육자의 전문적인 수작업 분석 과정을 AI로 자동화하여, **문제의 본질**을 파악하고 색인화하는

고도의 **지능형 교육 파트너**로서의 역할을 수행합니다.

ProbDex의 모든 가치는 단 하나의 핵심 기능인 개념의 원형 분석으로부터 구현됩니다.


### 2. 핵심 기능 및 3개의 모듈

**ProbDex는 문제를 해결하기 위해 유기적으로 연결된 세 가지 핵심 모듈로 구성됩니다**.

| **모듈**                        | **기능 및 역할**                                                                                                                                                                                                | **핵심 기술 요소**                                      |
| ------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------- |
| **2.1. 데이터베이스 구축 모듈** | 사전에**전체 평가원 기출문제**를 분석하여, 각 문항의 **개념적 원형**과 논리 구조를 추출하고 색인화합니다.<br />이 과정에는 평가원의 출제 철학에 특화되도록 **미세 조정된 언어 모델**이 사용됩니다. | 미세 조정(Fine-tuning) AI, 구조화된 메타데이터 저장(Pydantic) |
| **2.2. 입력 문제 분석 모듈**    | 사용자가 업로드한 PDF 문제를 실시간으로 분석하여,<br />해당 문제 **고유의 메타데이터**를 추출합니다. <br />**추출되는 메타데이터에는 수학적 개념, 논리적 흐름, 함정 등이 포함됩니다**.                  | AI 기반 실시간**LaTeX**수식 및 텍스트 분석              |
| **2.3. 유사도 매칭 모듈**       | 입력 문제의 메타데이터를 데이터베이스의 수많은**개념적 원형**과 비교하여,  <br />가장 높은 개념적 유사도를 가진 원형 기출문제를 찾아냅니다.                                                                    | 다차원적 유사도 알고리즘 (TF-IDF, Cosine/Jaccard Similarity)  |



### 3. 유사도 매칭 로직 

ProbDex는 단순히 **키워드 일치율**이나 **텍스트 유사도**를 넘어, 다차원적인 기준을 종합하여 유사도를 판단합니다.

**다차원적 유사도 계산** 

* **핵심 개념 일치도 (Core Concepts)** : 두 문제가 동일한 수학적 개념을 얼마나 공유하는가? **(Jaccard Similarity)**
* **논리 구조 유사도 (Logic Flow)** : 두 문제의 풀이 과정과 논리적 흐름이 얼마나 유사한가? **(TF-IDF + Cosine Similarity)**
* **평가 목표 유사도 (Pattern/Pitfalls)** : 두 문제가 학생의 동일한 사고 능력을 평가하는가? **(Cosine Similarity)** 


ProbDex는 **미세 조정된 AI**를 활용하여 입력 문제의 **개념적 원형**을 추출하고,

이를 **다차원적 유사도 알고리즘**과 **하이브리드 매칭 로직**을 통해 정확한 **유사도**를 보장하며 

원형 기출문제를 검색하는 **지능형 교육 솔루션**입니다.
