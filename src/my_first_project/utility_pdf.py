# --- PyPDF2 ---
from PyPDF2 import PdfReader, PdfWriter  
import pandas as pd
import os
import time
import io
import fitz
import glob
# 프로젝트 모듈 임포트
from .config import path, pdf_constant
from .model import problem_number_map, subject_map
import numpy as np
start = time.time()

# 반복되는 상수 값 정의 
years = ["2022", "2023", "2024", "2025", "2026"]
months = ["06", "09", "csat"]
subjects = ["cal","geo", "sta"]
common_pages = (1, 8)
split_pages = (9, 12)

# 초기화용 함수
def save_pdf_page_range_to_file(input_pdf_path, output_pdf_path, start_page, end_page):
    """
    하나의 PDF 파일에서 지정된 페이지 범위만 추출하여 새 PDF 파일로 저장합니다.
      반환 형식: List[bytes]
    [
        b'%PDF-1.7 .... page1 ...',
        b'%PDF-1.7 .... page2 ...',
        b'%PDF-1.7 .... page3 ...',
        ...
    ]
    """
    
    # 원본 PDF 파일 읽기
    try:
        reader = PdfReader(input_pdf_path) 
    except FileNotFoundError:
        print(f"오류: 원본 PDF 파일이 존재하지 않음. 경로: {input_pdf_path}")
        return
    except Exception as e:
        print(f"PDF 읽기 실패: {e}")
        return

    # 새 PDF 파일을 만들기 위한 'Writer' 객체 생성
    writer = PdfWriter() 

    # 원하는 페이지만큼 반복
   
    try:
        for i in range(start_page - 1, end_page):
            writer.add_page(reader.pages[i]) #
    except IndexError:
        print(f"오류: PDF의 전체 페이지 수({len(reader.pages)})를 초과하는 페이지를 요청했습니다.")
        return

    # 작업한 내용을 새 파일로 저장
    try:
        # 출력 폴더가 없으면 자동 생성
        os.makedirs(os.path.dirname(output_pdf_path), exist_ok=True)
        
        with open(output_pdf_path, "wb") as output_file:
            writer.write(output_file) #
        print(f"✅ 성공: '{output_pdf_path}' (페이지 {start_page}-{end_page}) 생성 완료")
    except Exception as e:
        print(f"PDF 저장 실패: {e}")

def process_all_raw_problem_pdfs(pdf_source_folder, pdf_output_folder):
    """
    정의된 연도, 월, 과목 목록을 순회하며 PDF를 일괄 분리 처리합니다.
    """
    print("PDF 일괄 분리 처리 시작...")

    
    # 모든 조합을 순회하는 3중 루프
    
    # [연도]와 [월] 루프 (2022년 6월, 2022년 9월, 2023년 6월 등등)
    for year in pdf_constant["years"]:
        for month in pdf_constant["months"]:
            prefix = f"kice_{year}_{month}"
            
            # 공통 부분 파일 생성 로직 
            
            # 공통 부분 원본 파일 경로 조합 (예: kice_2024_06_cal.pdf)
            # 파일명 규칙: kice_[연도]_[월]_[과목].pdf
            common_source_name = f"kice_{year}_{month}_{pdf_constant['subjects'][0]}.pdf"
            common_source_path = os.path.join(pdf_source_folder, common_source_name)
            
            common_output_name = f"kice_{year}_{month}_common.pdf"
            
            # 파일 존재 여부 확인 후 공통 파일 생성 (중복 방지)
            if os.path.exists(os.path.join(pdf_output_folder, common_output_name)):
                print(f"\n[SKIP] {year}년 {month} 시험 공통 부분 파일이 이미 존재합니다. 건너뜁니다. ")
            # continue를 사용하면 선택과목 분리도 건너뛰게 됨    
            else:
                common_source_path = None
                
                for subject in pdf_constant["subjects"]: 
                # 원본 파일명 조합 (예: kice_2024_06_cal.pdf)
                    source_name = f"{prefix}_{subject}.pdf"
                    source_path = os.path.join(pdf_source_folder, source_name)
                
                    if os.path.exists(source_path):
                        # 파일이 존재하면 그 경로를 사용하고 즉시 루프 중단
                        common_source_path = source_path 
                        break
                if common_source_path : 
                    print(f"  > {year}년 {month} 시험 공통 부분 추출 중...")
                
                    save_pdf_page_range_to_file(
                        input_pdf_path=common_source_path,
                        output_pdf_path=os.path.join(pdf_output_folder, common_output_name),
                        start_page=pdf_constant["common_pages"][0],
                        end_page=pdf_constant["common_pages"][1]
                    )
                else:
                    print(f"{year}년 {month} 시험의 원본 PDF 파일을 찾을 수 없습니다. 건너뜁니다.")
            
            # 선택과목별 분리 파일 생성 로직
            for subject in pdf_constant["subjects"]:
                # 선택 과목 원본 파일 경로 조합
                source_file_name = f"kice_{year}_{month}_{subject}.pdf"
                source_file_path = os.path.join(pdf_source_folder, source_file_name)
                
                # 선택 과목 분리 파일명 조합 (예: kice_2024_06_cal_split.pdf)
                output_file_name = f"kice_{year}_{month}_{subject}_split.pdf"
                output_file_path = os.path.join(pdf_output_folder, output_file_name)
                if os.path.exists(output_file_path):
                    print(f"\n[SKIP] {subject} 선택 파일 ({output_file_name})이 이미 존재합니다. 건너뜁니다.")
                    continue 
                if os.path.exists(source_file_path):
                    print(f"  > {subject} 선택과목 추출 중...")
                    
                    save_pdf_page_range_to_file(
                        input_pdf_path=source_file_path,
                        output_pdf_path=output_file_path,
                        start_page=pdf_constant["split_pages"][0],
                        end_page=pdf_constant["split_pages"][1]
                    )
    
    print("\n✅ PDF 일괄 분리 작업이 모두 완료되었습니다.")

def pdf_to_images(pdf_file_path, output_image_path):
    """
    PDF 파일을 이미지로 변환하는 함수.
    """
    # pdf_file_path에 있는 pdf 파일을 열어서
    # output_image_path 폴더에 페이지별로 png 이미지로 저장

    prefix = os.path.splitext(os.path.basename(pdf_file_path))[0]

    # 출력 폴더가 없으면 자동 생성
    os.makedirs(output_image_path, exist_ok=True)

    try:
        doc = fitz.open(pdf_file_path)
    except FileNotFoundError:
        print(f"오류: PDF 파일을 찾을 수 없습니다. 경로: {pdf_file_path}")
        return
    except Exception as e:
        print(f"오류: PDF를 여는 중 문제 발생: {e}")
        return

    print(f"  > 이미지 변환 시작: {os.path.basename(pdf_file_path)}")

    # 이미지 렌더링 설정 
    # OCR 정확도를 위해 200 DPI 사용 
    dpi = 200 # 300이나 200이나 똑같은거같은데
    zoom = dpi / 72 
    matrix = fitz.Matrix(zoom, zoom)

    # 각 페이지를 순회하며 이미지로 변환
    for i in range(doc.page_count):
        page = doc.load_page(i)
        # 파일명 및 경로 설정: [접두사]_[페이지번호].png (예: kice_2024_06_common_p1.png)
        page_number = i + 1
        output_file_name = f"{prefix}_p{page_number}.png"
        output_file_path = os.path.join(output_image_path, output_file_name)
        # 스킵 구문
        if os.path.exists(output_file_path):
            print(f"\n[SKIP] 이미지 이미 존재: {output_file_name}")
            continue

        try:
            # 페이지 추출 및 이미지 데이터 생성
            pix = page.get_pixmap(matrix=matrix)
            
            # 이미지 파일로 저장
            pix.save(output_file_path)
            print(f"\n✅저장 완료: {output_file_name}")

        except Exception as e:
            print(f"오류: {output_file_name} 문제 발생: {e}")
            
    
    doc.close()
    print(f"\n✅ 성공: 이미지 변환 완료.")

def process_pdf_to_images(pdf_input_path, img_output_path):
    '''
    pdf_to_images함수를 이용하여 모든 pdf파일을 이미지로 변환하는 함수
    '''
    if not os.path.exists(pdf_input_path):
        print(f"오류: PDF 폴더({pdf_input_path})가 존재하지 않습니다.")
        return
    
    try:
        processed_files = [f for f in os.listdir(pdf_input_path) if f.endswith('.pdf')]
    except FileNotFoundError:
         print(f"오류: PDF 입력 폴더({pdf_input_path})를 찾을 수 없습니다.")
         return
    
    if not processed_files:
        print("오류: 입력 폴더에 변환할 PDF 파일이 없습니다.")
        return
    
    print(f"총 {len(processed_files)}개의 PDF 파일을 이미지로 변환합니다.")

    # 파일별로 이미지 변환 함수 호출
    for filename in processed_files:
        
        # 파일 경로 조합
        pdf_file_path = os.path.join(pdf_input_path, filename)
        
        # 파일명에서 확장자(.pdf)를 제거하여 이미지 접두사로 사용
        file_prefix = os.path.splitext(filename)[0] 
        
        # 4. 핵심 작업자 함수(pdf_to_images) 호출
        pdf_to_images(
            pdf_file_path=pdf_file_path,
            output_image_path=img_output_path, # 모든 이미지를 이 폴더에 저장
        )
        
    print("\n✅ 모든 PDF 파일의 이미지 변환 작업이 최종 완료되었습니다.")

def pdf_to_raw_data(pdf_input_path):
    '''
    PDF 파일에서 데이터를 추출하는 함수
    '''
    problem_raw_data = []
    doc = fitz.open(pdf_input_path)
    print(f"PDF 파일 로드 중. (총 {len(doc)} 페이지)")
    for page in range(len(doc)):
            page = doc.load_page(page)
            problem_raw_data = page.get_text("dict")

    print(f"📄 PDF에서 raw 데이터를 성공적으로 추출했습니다.")
    return problem_raw_data

# TODO : pdf 파일을 페이지 단위로 분할하여 바이트로 리턴하는 함수
def extract_pdf_pages_to_bytes(pdf_input_path,start_page, end_page):
    '''
    PDF 파일을 페이지 단위로 분할하는 함수. (ai 전달용)

    반환 형식: List[bytes]
    [
        b'%PDF-1.7 .... page1 ...',
        b'%PDF-1.7 .... page2 ...',
        b'%PDF-1.7 .... page3 ...',
        ...
    ]
    '''
    reader = PdfReader(pdf_input_path)
    extract_pdf_list_bytes = []
    total_pages = len(reader.pages)

    if start_page < 1 or end_page > total_pages or start_page > end_page:
        print(f"잘못된 페이지 범위입니다. 총 페이지 수: {total_pages}")
        return []
    
    for page_index in range(start_page - 1, end_page):
        pdf_writer = PdfWriter()
        pdf_writer.add_page(reader.pages[page_index])

        buffer = io.BytesIO()
        pdf_writer.write(buffer)

        extract_pdf_list_bytes.append(buffer.getvalue())
        buffer.close()

    return extract_pdf_list_bytes

# 업데이트용 함수
def get_pdf_page_count(pdf_input_path):
    '''
    PDF 파일의 총 페이지 수를 반환하는 함수
    '''
    try:
        reader = PdfReader(pdf_input_path)
        return len(reader.pages)
    except FileNotFoundError:
        print(f"오류: PDF 파일을 찾을 수 없습니다. 경로: {pdf_input_path}")
        return 0
    except Exception as e:
        print(f"오류: PDF를 여는 중 문제 발생: {e}")
        return 0

def check_new_raw_pdf(pdf_input_path, processed_pdf_path):
    """
    로직: raw_problem(_cal, _geo, _sta)에 대응하는 _split 파일이 
    processed_pdfs 폴더에 없으면 신규 raw 파일로 판단
    """
    raw_pdfs = glob.glob(os.path.join(pdf_input_path, "kice_*.pdf"))
    new_pdfs = []
    
    print(f"신규 파일 탐색 중... (raw pdf 파일: {len(raw_pdfs)}개)")

    for raw_path in raw_pdfs:
        filename = os.path.basename(raw_path)
        # 원본: kice_2024_06_cal.pdf
        # 프로세싱: kice_2024_06_cal_split.pdf
        # 처리된 파일은 반드시 '_split'이 존재
        target_split_name = filename.replace(".pdf", "_split.pdf")
        target_split_path = os.path.join(processed_pdf_path, target_split_name)
 
        # 존재 여부 확인
        if not os.path.exists(target_split_path):
            print(f"신규 발견: {filename}")
            new_pdfs.append(raw_path)

    if not new_pdfs:
        print("✅ 모든 파일이 이미 처리되었습니다.")
        
    return new_pdfs

def process_raw_pdf_to_images(raw_pdf_path, processed_pdf_path, image_path):
    """
    raw_problem PDF 파일을 받아 '공통/선택'으로 분할하고 이미지 생성
    """
    filename = os.path.basename(raw_pdf_path)
    print(f"\n [PDF 처리 시작] {filename}")

    # 파일명: kice_2024_06_cal.pdf → year=2024, month=06, subject=cal
    year, month, subject = os.path.splitext(filename)[0].split('_')[1:4]

    # 작업 목록
    task_specs = {
        "common": {
            "pages": pdf_constant["common_pages"],
            "output": f"kice_{year}_{month}_common.pdf",
            "prefix": f"kice_{year}_{month}_common",
        },
        "split": {
            "pages": pdf_constant["split_pages"],
            "output": f"kice_{year}_{month}_{subject}_split.pdf",
            "prefix": f"kice_{year}_{month}_{subject}_split",
        }
    }

    generated_images = []

    for kind, spec in task_specs.items():
        output_path = os.path.join(processed_pdf_path, spec["output"])

        # PDF 분할 (존재하지 않을 때만)
        if not os.path.exists(output_path):
            print(f"  📄 PDF 생성: {spec['output']}")
            save_pdf_page_range_to_file(
                input_pdf_path=raw_pdf_path,
                output_pdf_path=output_path,
                start_page=spec["pages"][0],
                end_page=spec["pages"][1],
            )

        # 이미지 변환
        pdf_to_images(output_path, image_path)

        # 파일 이름 규칙에 맞는 이미지 수집
        pattern = os.path.join(image_path, f"{spec['prefix']}_p*.png")
        generated_images.extend(glob.glob(pattern))

    return generated_images
















'''
# 테스트 코드
if __name__ == "__main__":
    
    print("PDF 분리 시작...")
    
    # 경로 설정
    script_dir = os.path.dirname(os.path.abspath(__file__))
    # 프로젝트 루트 경로 
    project_root_path = os.path.dirname(os.path.dirname(script_dir))
    pdf_source_folder = os.path.join(project_root_path, "assets", "raw_problem_pdfs")
    pdf_output_folder = os.path.join(project_root_path, "assets", "processed_pdfs")
    output_image_path = os.path.join(project_root_path, "assets", "problem_images")

    test_pdf_name = "kice_2022_06_common.pdf"
    test_pdf_path = os.path.join(pdf_output_folder, test_pdf_name)
    print(f"테스트 PDF 경로: {test_pdf_path}")
    process_all_raw_problem_pdfs(pdf_source_folder, pdf_output_folder) 
    print(f"전체 작동 시간: {time.time() - start:.2f}초")
    # 초기 시간: 5.92초
    # [SKIP] 기능 추가 후 0.03초 

    print("PDF 이미지 변환 시작...")
    process_pdf_to_images(
        pdf_input_path=pdf_output_folder,
        img_output_path=output_image_path
    )

    
    test_prefix = os.path.splitext(test_pdf_name)[0]
    output_image_path = os.path.join(project_root_path, "assets", "problem_images", test_prefix)

    if os.path.exists(test_pdf_path):
        print(f"테스트 파일 경로: {test_pdf_path}")
        pdf_to_images(
            pdf_file_path=test_pdf_path,
            output_image_path=output_image_path
        )
    else:
        print(f"경고: 단일 테스트 파일 '{test_pdf_name}'을(를) 찾을 수 없습니다. 일괄 처리를 건너뜁니다.")

print(f"전체 작동 시간: {time.time() - start:.2f}초")
# 초기 시간 : 60.88초
# 스킵 후 시간 : 0.14초
'''