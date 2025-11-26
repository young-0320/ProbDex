# --- sqlite3 ---
import sqlite3
import os
import json
# 프로젝트 모듈 임포트
from .model import subject_normalization_map, master_data
from .config import path
from .prob_data_processer import (
    initialize_xlsx, excel_to_json,
    update_problems_xlsx, update_problems_json,
    process_pdf_year_and_month, append_images_excel
)


def _ensure_columns(cursor, table_name, required_columns):
    """
    특정 테이블에 필요한 컬럼이 모두 존재하는지 점검하고,
    누락된 컬럼은 자동으로 추가
    """
    try:
        cursor.execute(f"PRAGMA table_info({table_name})")
        existing = {row[1] for row in cursor.fetchall()}  # row[1] = column name
    except Exception as e:
        print(f"[스키마 조회 실패] {table_name}: {e}")
        return

    for col, col_type in required_columns:
        if col not in existing:
            print(f"컬럼 추가: {table_name}.{col} ({col_type})")
            try:
                cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {col} {col_type}")
            except Exception as e:
                print(f"추가 실패 → {col}: {e}")

def _drop_all_tables(db_path, tables):
    """
    모든 테이블 삭제 함수
    """
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()

        cursor.execute("PRAGMA foreign_keys = OFF;")

        for table in tables:
            cursor.execute(f"DROP TABLE IF EXISTS {table}")
        conn.commit()

        print(f"  - 기존 테이블 삭제 완료 ({len(tables)}개)")

        cursor.execute("PRAGMA foreign_keys = ON;")

def create_database(is_user_db : bool = False):

    """
    DB 생성 및 스키마 자동 동기화.
    - 모든 테이블이 없으면 생성
    - 기존 테이블은 누락된 컬럼 자동 추가

    is_user_db=False : probdex.db 생성
    is_user_db=True  : user_probdex.db 생성
    """
    
    connection = None # 변수 초기화 
    db_path = path["user_db"] if is_user_db else path["db"]

    try:
        connection = sqlite3.connect(db_path)
        cursor = connection.cursor()
        
        cursor.execute("PRAGMA foreign_keys = ON;") 

        # ----- subjects -----
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS subjects (
            subject_id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject_name TEXT UNIQUE NOT NULL
        )
        ''')

        # ----- units -----
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS units (
            unit_id INTEGER PRIMARY KEY AUTOINCREMENT,
            unit_name TEXT NOT NULL,
            subject_id INTEGER,
            FOREIGN KEY(subject_id) REFERENCES subjects(subject_id)
        )
        ''')

        # ----- concepts -----
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS concepts (
            concept_id INTEGER PRIMARY KEY AUTOINCREMENT,
            concept_name TEXT UNIQUE NOT NULL
        )
        ''')

        # ----- problems -----
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS problems (
            problem_id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_text TEXT NOT NULL,
            year INTEGER,
            month INTEGER,
            number INTEGER,
            unit_id INTEGER,
            problem_type TEXT,
            logic_structure TEXT,
            pitfalls TEXT,
            problem_image_path TEXT,
            difficulty_level INTEGER,
            FOREIGN KEY(unit_id) REFERENCES units(unit_id)
        )
        ''')

        # 테이블이 이미 존재하더라도, 아래 컬럼들이 없으면 자동으로 추가
        if '_ensure_columns' in globals(): # 함수 존재 여부 확인 
             _ensure_columns(cursor, "problems", [
                ("problem_type", "TEXT"),
                ("logic_structure", "TEXT"),
                ("pitfalls", "TEXT"),
                ("problem_image_path", "TEXT"),
                ("difficulty_level", "INTEGER")
            ])

        # ----- problem_concept_map -----
        cursor.execute('''
        CREATE TABLE IF NOT EXISTS problem_concept_map (
            map_id INTEGER PRIMARY KEY AUTOINCREMENT,
            problem_id INTEGER,
            concept_id INTEGER,
            UNIQUE(problem_id, concept_id),
            FOREIGN KEY(problem_id) REFERENCES problems(problem_id) ON DELETE CASCADE,
            FOREIGN KEY(concept_id) REFERENCES concepts(concept_id) ON DELETE CASCADE
        )
        ''')

        connection.commit()
        print("✅ DB 생성 및 스키마 점검 완료")

    except Exception as e:
        print(f"[DB 구성 중 오류] {e}")
        # 필요하다면 여기서 connection.rollback()을 호출할 수도 있습니다.

    finally:
        if connection:
            connection.close()

def initialize_database(is_user_db: bool = False):
    """
    DB 초기화: 모든 테이블 삭제 후 재생성 및 기초 데이터 주입
    """
    db_path = path["user_db"] if is_user_db else path["db"]
    db_label = "user_probdex.db" if is_user_db else "probdex.db"

    print(f"  - 대상 DB: {db_label} : ({db_path})")
    print(f"  - {db_label} 초기화 중...")

    tables = [
        "problem_concept_map",
        "problems",
        "concepts",
        "units",
        "subjects"
    ]

    try:
        # 테이블 삭제
        _drop_all_tables(db_path, tables)

        # 재생성
        print("  - 테이블 재생성 중...")
        create_database(is_user_db=is_user_db)

        # 기초 데이터 주입
        print("  - 기초 데이터 주입 중...")
        populate_subjects_and_units_tables(is_user_db=is_user_db)

        print(f"✅ {db_label} 초기화 완료\n")
        return True

    except Exception as e:
        print(f"DB 초기화 중 오류 발생: {e}")
        return False

def get_or_create_normalized_subject_id(cursor, messy_subject_name):
    """
    정제되지 않은 과목 이름을 받아, 표준화하고, 
    DB에서 ID를 찾아 반환하거나, 없으면 새로 생성하여 ID를 반환
    """
    
    # 정제 : "수학 Ⅰ" -> "수학1"
    # 맵에 없으면, 일단 소문자로 바꾸고 공백을 제거 (예: "Math 1" -> "math1")
    normalized_name = subject_normalization_map.get(
        messy_subject_name, 
        messy_subject_name.lower().replace(" ", "")
    )

    # 조회 : "수학1"의 ID를 찾습니다.
    cursor.execute("SELECT subject_id FROM subjects WHERE subject_name = ?", (normalized_name,))
    result = cursor.fetchone()

    if result:
        #  ID 반환 : 해당하는 ID를 반환
        return result[0]
    else:
        #  생성 및 ID 반환 : "수학1"을 새로 삽입하고 그 ID를 반환
        print(f"새로운 과목 발견: '{normalized_name}'. 마스터 테이블에 추가합니다.")
        cursor.execute("INSERT INTO subjects (subject_name) VALUES (?)", (normalized_name,))
        return cursor.lastrowid # 방금 삽입한 행의 ID를 반환
    
def populate_subjects_and_units_tables(is_user_db: bool = False):
    """
    'subjects'와 'units' 마스터 테이블을 표준 데이터로 초기화합니다.
    """

    connection = None
    db_path = path["user_db"] if is_user_db else path["db"]
    
    try:
        connection = sqlite3.connect(db_path)
        cursor = connection.cursor()

        print("마스터 테이블(subjects, units) 데이터 삽입을 시작합니다...")

        # 'subjects' 테이블(과목) 채우기
        for subject_name in master_data.keys():
            # 'INSERT OR IGNORE'로 과목 이름 삽입
            cursor.execute("INSERT OR IGNORE INTO subjects (subject_name) VALUES (?)", (subject_name,))
            
            # 'units' 테이블(단원) 채우기 (과목 ID와 연결)
            
            # 방금 삽입(하거나 무시)한 과목의 subject_id를 다시 조회하여 가져옵니다.
            cursor.execute("SELECT subject_id FROM subjects WHERE subject_name = ?", (subject_name,))
            subject_id_result = cursor.fetchone() 
            
            if subject_id_result:
                subject_id = subject_id_result[0] # ID 추출
                
                # 해당 과목에 속한 단원들을 'units' 테이블에 삽입
                for unit_name in master_data[subject_name]:
                    cursor.execute("INSERT OR IGNORE INTO units (unit_name, subject_id) VALUES (?, ?)", 
                                   (unit_name, subject_id))
            
        # 모든 변경사항을 최종 저장
        connection.commit()
        print("마스터 테이블 데이터 삽입/업데이트가 완료되었습니다.")

    except sqlite3.Error as e:
        print(f"데이터베이스 작업 중 오류 발생: {e}")
        if connection:
            connection.rollback() # 오류 발생 시, 작업 되돌리기
    finally:
        if connection:
            connection.close()

# JSON 파일과 DB 동기화 함수
def load_json(json_path):
    """
    JSON 파일을 읽어 Python 객체(dict/list)로 반환하는 데이터 로더
    """
    if not os.path.exists(json_path):
        raise FileNotFoundError(f"JSON 파일 없음: {json_path}")
    with open(json_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def connect_db(db_path):
    """
    SQLite DB 연결 객체를 반환하는 함수
    """
    return sqlite3.connect(db_path)

def find_unit_id(cursor, subject_name, unit_name):
    """
    과목명·단원명으로부터 unit_id를 찾아 반환
    """
    if not subject_name or not unit_name:
        return None

    cursor.execute("SELECT subject_id FROM subjects WHERE subject_name = ?", (subject_name,))
    res = cursor.fetchone()
    if not res:
        return None

    subject_id = res[0]
    cursor.execute(
        "SELECT unit_id FROM units WHERE unit_name = ? AND subject_id = ?",
        (unit_name, subject_id)
    )
    unit_res = cursor.fetchone()
    return unit_res[0] if unit_res else None

def parse_ai_data(raw):
    """
    AI 분석 데이터(ai_analysis)를 정리하여 db에 넣기 좋은 형태로 반환.
    """
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            raw = {}
    if not isinstance(raw, dict):
        raw = {}

    pattern = raw.get('pattern_type', [])
    pitfalls = raw.get('pitfalls', [])

    return {
        "pattern_type": ", ".join(pattern) if isinstance(pattern, list) else str(pattern),
        "pitfalls": ", ".join(pitfalls) if isinstance(pitfalls, list) else str(pitfalls),
        "logic_flow": raw.get('logic_flow', ''),
        "difficulty": raw.get('difficulty_level', 0),
        "core_concepts": raw.get('core_concepts', []),
    }

def upsert_problem(cursor, item, unit_id, ai):
    """
    problem 데이터를 INSERT OR REPLACE로 db에 저장
    """
    cursor.execute("""
        INSERT OR REPLACE INTO problems (
            problem_id, source_text, year, month, number,
            unit_id, problem_type,
            logic_structure, pitfalls, problem_image_path, difficulty_level
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        item.get("problem_id"), 
        item.get("source_data", ""),
        item.get("year"),
        item.get("month"),
        item.get("number"),
        unit_id,
        ai["pattern_type"],
        ai["logic_flow"],
        ai["pitfalls"],
        item.get("problem_image_path", ""),
        ai["difficulty"]
    ))

def sync_concepts(cursor, problem_id, concepts):
    """
    문제와 개념의 연결 관계를 최신 상태로 동기화
    """
    cursor.execute("DELETE FROM problem_concept_map WHERE problem_id = ?", (problem_id,))

    for name in concepts:
        name = name.strip()
        if not name:
            continue

        cursor.execute("SELECT concept_id FROM concepts WHERE concept_name = ?", (name,))
        res = cursor.fetchone()

        if res:
            concept_id = res[0]
        else:
            cursor.execute("INSERT INTO concepts (concept_name) VALUES (?)", (name,))
            concept_id = cursor.lastrowid

        cursor.execute(
            "INSERT OR IGNORE INTO problem_concept_map (problem_id, concept_id) VALUES (?, ?)",
            (problem_id, concept_id)
        )

def sync_database_from_json(json_path, db_path = None,  is_user_db : bool = False):
    """
    1) JSON 로드
    2) DB 연결
    3) 문제 단위 반복 처리
    4) find_unit_id()
    5) parse_ai_data()
    6) upsert_problem()
    7) sync_concepts()
    8) 커밋
    9) 로그 출력
    """

    print(f"\n--- DB 동기화 시작 ---")
    print(f"Source: {json_path}")

    try:
        data = load_json(json_path)
    except Exception as e:
        print(f"JSON Load 실패: {e}")
        return

    if db_path is None:
        db_path = path["user_db"] if is_user_db else path["db"]

    try:
        conn = connect_db(db_path)
        cur = conn.cursor()
        # 외래키 제약 활성화
        cur.execute("PRAGMA foreign_keys = ON;") 
    except Exception as e:
        print(f"DB 연결 실패: {e}")
        return
    updated = 0

    for item in data:
        try:
            problem_id = item.get("problem_id")
            if not problem_id:
                continue

            unit_id = find_unit_id(cur, item.get("subject_name"), item.get("unit_name"))
            ai = parse_ai_data(item.get("ai_analysis"))

            upsert_problem(cur, item, unit_id, ai)
            sync_concepts(cur, problem_id, ai["core_concepts"])

            updated += 1

        except Exception as e:
            print(f"ID {item.get('problem_id')} 처리 실패: {e}")

    conn.commit()
    conn.close()

    print(f"--- 동기화 완료: {updated}개 업데이트 ---")

def __sync_database_from_json():
    """
    JSON 파일의 문제 데이터를 db의 'problems' 테이블과 동기화하는 함수.
    - problems 테이블 업데이트
    - concepts 테이블 업데이트 (새로운 개념 발견 시 추가)
    - problem_concept_map 테이블 업데이트 (문제-개념 연결)
    """
    json_path = path["base_problems_json"]
    db_path = path["db"]

    print(f"\n--- DB 동기화 시작 (Source: {json_path}) ---")

    if not os.path.exists(json_path):
        print(f"오류: JSON 파일({json_path})이 존재하지 않습니다.")
        return

    # 1. JSON 파일 로드
    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            problems_data = json.load(f)
    except Exception as e:
        print(f"JSON 파일 로드 실패: {e}")
        return

    connection = None
    try:
        connection = sqlite3.connect(db_path)
        cursor = connection.cursor()
        
        success_count = 0
        
        for item in problems_data:
            try:
                # -------------------------------------------------------
                # 1. 외래 키(Unit ID) 찾기
                # -------------------------------------------------------
                subject_name = item.get('subject_name')
                unit_name = item.get('unit_name')
                unit_id = None

                if subject_name and unit_name:
                    # 과목 ID 찾기
                    cursor.execute("SELECT subject_id FROM subjects WHERE subject_name = ?", (subject_name,))
                    subj_res = cursor.fetchone()
                    
                    if subj_res:
                        subject_id = subj_res[0]
                        # 단원 ID 찾기
                        cursor.execute("SELECT unit_id FROM units WHERE unit_name = ? AND subject_id = ?", (unit_name, subject_id))
                        unit_res = cursor.fetchone()
                        if unit_res:
                            unit_id = unit_res[0]

                # -------------------------------------------------------
                # 2. AI Analysis 데이터 파싱 및 가공
                # -------------------------------------------------------
                ai_analysis_raw = item.get('ai_analysis')
                ai_data = {}

                # JSON 파일 내 ai_analysis가 문자열로 저장되어 있는 경우 파싱
                if isinstance(ai_analysis_raw, str):
                    try:
                        ai_data = json.loads(ai_analysis_raw)
                    except json.JSONDecodeError:
                        pass # 파싱 실패 시 빈 딕셔너리
                elif isinstance(ai_analysis_raw, dict):
                    ai_data = ai_analysis_raw
                
                # 리스트 형태의 필드는 콤마로 구분된 문자열로 변환하여 DB에 저장
                pattern_type_list = ai_data.get('pattern_type', [])
                pattern_type_str = ", ".join(pattern_type_list) if isinstance(pattern_type_list, list) else str(pattern_type_list)

                pitfalls_list = ai_data.get('pitfalls', [])
                pitfalls_str = ", ".join(pitfalls_list) if isinstance(pitfalls_list, list) else str(pitfalls_list)

                logic_structure = ai_data.get('logic_flow', '')
                difficulty_level = ai_data.get('difficulty_level', 0)
                
                # -------------------------------------------------------
                # 3. Problems 테이블 Upsert (삽입 또는 교체)
                # -------------------------------------------------------
                problem_id = item.get('problem_id')
                if not problem_id:
                    continue # ID가 없으면 스킵

                source_text = item.get('source_data', '')
                problem_text = item.get('problem_text', '')
                year = item.get('year')
                month = item.get('month')
                number = item.get('number')
                problem_image_path = item.get('problem_image_path', '')

                cursor.execute('''
                    INSERT OR REPLACE INTO problems (
                        problem_id, source_text, year, month, number, 
                        unit_id, problem_text, problem_type, 
                        logic_structure, pitfalls, problem_image_path, difficulty_level
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    problem_id, source_text, year, month, number,
                    unit_id, problem_text, pattern_type_str,
                    logic_structure, pitfalls_str, problem_image_path, difficulty_level
                ))

                # -------------------------------------------------------
                # 4. Concepts 및 Mapping 테이블 동기화
                # -------------------------------------------------------
                core_concepts = ai_data.get('core_concepts', [])
                if isinstance(core_concepts, list):
                    # 기존 매핑 삭제 (최신 상태로 갱신하기 위함)
                    cursor.execute("DELETE FROM problem_concept_map WHERE problem_id = ?", (problem_id,))

                    for concept_name in core_concepts:
                        concept_name = concept_name.strip()
                        if not concept_name:
                            continue
                        
                        # 개념 ID 조회 (없으면 생성)
                        cursor.execute("SELECT concept_id FROM concepts WHERE concept_name = ?", (concept_name,))
                        concept_res = cursor.fetchone()
                        
                        if concept_res:
                            concept_id = concept_res[0]
                        else:
                            cursor.execute("INSERT INTO concepts (concept_name) VALUES (?)", (concept_name,))
                            concept_id = cursor.lastrowid
                        
                        # 문제-개념 연결
                        cursor.execute("INSERT OR IGNORE INTO problem_concept_map (problem_id, concept_id) VALUES (?, ?)", (problem_id, concept_id))
                
                success_count += 1

            except Exception as e:
                print(f"⚠️ 문제(ID: {item.get('problem_id')}) 처리 중 오류 발생: {e}")

        connection.commit()
        print(f"✅ DB 동기화 완료. 총 {success_count}개의 문제가 업데이트되었습니다.")

    except sqlite3.Error as e:
        print(f"❌ 데이터베이스 연결 오류: {e}")
    finally:
        if connection:
            connection.close()

def insert_meta_data_user_db(problems: list, is_user_db: bool = True):
    """
    AI가 분석한 PDFProbData를 바로 DB에 저장
    """
    if not problems:
        print("저장할 문제 데이터가 없습니다.")
        return

    # 대상 DB 연결
    db_path = path["user_db"] if is_user_db else path["db"]
    print(f"\n--- DB 직접 저장 시작 ({'User DB' if is_user_db else 'System DB'}) ---")
    
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

                unit_id = find_unit_id(cursor, prob.subject_name, prob.unit_name)

                ai_obj = prob.ai_analysis
                
                # upsert_problem이 기대하는 ai 딕셔너리 구조 생성
                ai_data_formatted = {
                    "pattern_type": ", ".join(ai_obj.pattern_type) if ai_obj else "",
                    "logic_flow": ai_obj.logic_flow if ai_obj else "",
                    "pitfalls": ", ".join(ai_obj.pitfalls) if ai_obj else "",
                    "difficulty": ai_obj.difficulty_level if ai_obj else 0,
                    # core_concepts는 별도 sync_concepts에서 사용
                }

                # item 딕셔너리에 필요한 키가 없으면 채워넣음 
                if "source_data" not in item:
                    item["source_data"] = f"{prob.year} {prob.month} {prob.subject_name} {prob.number}번"
                
                upsert_problem(cursor, item, unit_id, ai_data_formatted)

                current_pid = item.get("problem_id")
                if not current_pid:
                    current_pid = cursor.lastrowid # 방금 INSERT된 행의 ID (Auto Increment)

                if ai_obj and ai_obj.core_concepts and current_pid:
                    sync_concepts(cursor, current_pid, ai_obj.core_concepts)
                
                success_count += 1

            except Exception as e:
                print(f" 문제 저장 실패 (Num: {prob.number}): {e}")

        connection.commit()
        print(f"✅ 총 {success_count}개의 문제를 DB에 성공적으로 저장했습니다.")

    except Exception as e:
        print(f"DB 저장 중 치명적 오류: {e}")
        if connection: connection.rollback()
    finally:
        if connection: connection.close()

def get_problem_candidates_by_unit(subject_name: str, unit_name: str):
    """
    [검색] 
    probdex.db에서 동일한 과목/단원을 가진 문제들의
    핵심 정보(ID, AI분석, 이미지경로)를 모두 가져옵니다.
    """
    db_path = path["db"] # 시스템 DB
    candidates = []
    
    try:
        with sqlite3.connect(db_path) as conn:
            cursor = conn.cursor()
            
            # 해당 과목/단원의 unit_id 찾기
            unit_id = find_unit_id(cursor, subject_name, unit_name)
            if not unit_id:
                print(f"검색 대상 단원({subject_name} > {unit_name})이 DB에 없습니다.")
                return []

            # 유사도 분석에 필요한 컬럼만 조회
            query = """
                SELECT 
                    p.problem_id, 
                    p.problem_type, 
                    p.logic_structure, 
                    p.pitfalls, 
                    p.difficulty_level,
                    p.problem_image_path,
                    p.source_text
                FROM problems p
                WHERE p.unit_id = ?
            """
            cursor.execute(query, (unit_id,))
            rows = cursor.fetchall()
            
            # 각 문제별 Core Concepts 조회 
            for row in rows:
                p_id = row[0]
                
                # 개념 조회
                cursor.execute("""
                    SELECT c.concept_name 
                    FROM concepts c
                    JOIN problem_concept_map pcm ON c.concept_id = pcm.concept_id
                    WHERE pcm.problem_id = ?
                """, (p_id,))
                concepts = [c[0] for c in cursor.fetchall()]
                
                # 딕셔너리로 구조화
                candidate = {
                    "problem_id": p_id,
                    "pattern_type": row[1].split(', ') if row[1] else [],
                    "logic_flow": row[2],
                    "pitfalls": row[3].split(', ') if row[3] else [],
                    "difficulty_level": row[4],
                    "problem_image_path": row[5],
                    "source_text": row[6],
                    "core_concepts": concepts
                }
                candidates.append(candidate)
                
    except Exception as e:
        print(f"후보 문제 조회 실패: {e}")
        return []
        
    return candidates

def sync_excel_to_db():
    """
    사용자가 수동으로 수정한 base_problems.xlsx 파일을
    JSON으로 변환하고, DB(probdex.db)에 동기화하는 스크립트
    """
    # 이 부분에 excel_to_json 임포트가 필요하다면 상단이 아닌 함수 안에서 임포트하거나, 
    # prob_data_processer에서 가져와야 합니다. (보통 상단에 이미 있을 것입니다)
    from .prob_data_processer import excel_to_json 

    print("\n[Excel -> DB 수동 동기화 시작]")
    
    # 1. Excel -> JSON 변환
    print(f"\n1. 엑셀 파일 읽기 및 JSON 변환: {path['base_problems_xlsx']}")
    try:
        excel_to_json(
            excel_path=path['base_problems_xlsx'],
            output_path=path['base_problems_json']
        )
    except Exception as e:
        print(f" 엑셀 -> JSON 변환 실패: {e}")
        return

    # 2. JSON -> DB 동기화 (run_sync_database 대신 직접 실행)
    print(f"\n2. 데이터베이스 동기화: {path['db']}")
    try:
        # [수정됨] 파이프라인 함수 대신 내부 함수 직접 호출
        is_user_db = False
        create_database(is_user_db=is_user_db)
        populate_subjects_and_units_tables(is_user_db=is_user_db)
        sync_database_from_json(path["base_problems_json"], path["db"], is_user_db=is_user_db)
        
        print("\n✅ 모든 동기화 작업이 완료되었습니다.")
            
    except Exception as e:
        print(f" DB 동기화 실패: {e}")

if __name__ == "__main__":
    # poetry run python -m src.my_first_project.database
    sync_excel_to_db()