# --- gui_manager.py ---
import sys
import os
import threading
import re
import tkinter as tk
from tkinter import scrolledtext
from PIL import Image, ImageTk
# 프로젝트 모듈 임포트
from .config import path

class ProbDexGUI:
    def __init__(self, root, mode, filename=None, init_flag=False, pipeline_callback=None):
        self.root = root
        self.mode = mode
        self.filename = filename
        self.init_flag = init_flag
        self.pipeline_callback = pipeline_callback # 메인에서 주입받을 실행 함수
        
        # 가비지 컬렉션 방지를 위한 이미지 참조 변수
        self.current_image = None 
        
        # 윈도우 설정
        self.root.title(f"ProbDex Controller - [{mode.upper()} MODE]")
        self.root.geometry("1000x800")
        
        # 레이아웃 구성
        self.create_widgets()
        
        # 표준 출력(print)을 GUI 텍스트 박스로 리다이렉트
        self.original_stdout = sys.stdout
        sys.stdout = self
        
        # 작업 스레드 시작
        self.thread = threading.Thread(target=self.run_task)
        self.thread.daemon = True
        self.thread.start()

    def create_widgets(self):
        # 상단: 로그 영역
        log_frame = tk.Frame(self.root)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        tk.Label(log_frame, text="[System Log & Analysis Result]", font=("Arial", 12, "bold")).pack(anchor=tk.W)
        
        self.log_area = scrolledtext.ScrolledText(log_frame, height=20, state='disabled', bg="#f0f0f0")
        self.log_area.pack(fill=tk.BOTH, expand=True)
        
        # 하단: 이미지 뷰어 영역 (User Mode일 때만 유효)
        if self.mode == 'user':
            img_frame = tk.Frame(self.root, height=400, bg="white")
            img_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
            
            tk.Label(img_frame, text="[Best Match Problem Image]", bg="white", font=("Arial", 12, "bold")).pack(anchor=tk.W)
            
            self.image_label = tk.Label(img_frame, text="Waiting for results...", bg="#e0e0e0")
            self.image_label.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

    def write(self, text):
        """stdout을 가로채서 텍스트 박스에 출력하고, 이미지 경로가 있으면 이미지를 띄움"""
        self.log_area.config(state='normal')
        self.log_area.insert(tk.END, text)
        self.log_area.see(tk.END)
        self.log_area.config(state='disabled')
        
        # 터미널에도 같이 출력
        self.original_stdout.write(text)

        # "이미지 경로: " 텍스트가 감지되면 이미지 업데이트 로직 실행
        if self.mode == 'user':
            self.check_and_show_image(text)

    def flush(self):
        pass

    def check_and_show_image(self, text):
        """로그 텍스트에서 이미지 경로를 파싱하여 화면에 출력"""
        # 정규표현식 개선: 확장자(.png, .jpg) 뒤에 공백이나 줄바꿈이 있어도 매칭되도록 수정
        # 또한 경로에 공백이 포함될 수 있으므로 탐욕적 매칭을 하되, 줄바꿈 전까지만 매칭
        match = re.search(r"이미지 경로:\s*(.+?(?:\.png|\.jpg|\.jpeg))", text, re.IGNORECASE)
        
        if match:
            img_path_raw = match.group(1).strip()
            self.original_stdout.write(f"\n[DEBUG] 이미지 경로 감지됨: '{img_path_raw}'\n")
            
            # 1. 절대 경로인지 확인
            if os.path.isabs(img_path_raw) and os.path.exists(img_path_raw):
                self.display_image(img_path_raw)
                return

            # 2. 프로젝트 루트 기준 상대 경로 확인
            full_path_root = os.path.join(path['root'], img_path_raw)
            if os.path.exists(full_path_root):
                self.display_image(full_path_root)
                return
                
            # 3. 현재 작업 디렉토리 기준 확인
            if os.path.exists(img_path_raw):
                self.display_image(img_path_raw)
                return

            # 4. assets/problem_images 폴더 확인
            full_path_assets = os.path.join(path['problem_images'], os.path.basename(img_path_raw))
            if os.path.exists(full_path_assets):
                self.display_image(full_path_assets)
                return

            # 5. user_input/user_problem_images 폴더 확인
            full_path_user = os.path.join(path['user_problem_images'], os.path.basename(img_path_raw))
            if os.path.exists(full_path_user):
                self.display_image(full_path_user)
                return
            
            self.original_stdout.write(f"[GUI Warning] 이미지 파일을 찾을 수 없습니다: {img_path_raw}\n")
            self.original_stdout.write(f"  - 시도한 경로 1 (Root): {full_path_root}\n")
            self.original_stdout.write(f"  - 시도한 경로 2 (Assets): {full_path_assets}\n")
            self.original_stdout.write(f"  - 시도한 경로 3 (User): {full_path_user}\n")

    def display_image(self, img_path):
        try:
            # Pillow를 사용하여 이미지 로드 및 리사이징
            pil_img = Image.open(img_path)
            
            # 화면에 맞게 리사이징 (비율 유지)
            base_height = 350
            h_percent = (base_height / float(pil_img.size[1]))
            w_size = int((float(pil_img.size[0]) * float(h_percent)))
            pil_img = pil_img.resize((w_size, base_height), Image.Resampling.LANCZOS)
            
            tk_img = ImageTk.PhotoImage(pil_img)
            
            self.image_label.config(image=tk_img, text="")
            
            # [핵심 수정] Label 속성에 할당하지 않고, 클래스 인스턴스 변수에 저장
            self.current_image = tk_img 
            
            self.original_stdout.write(f"\n[GUI] 이미지를 화면에 로드했습니다: {img_path}\n")
            
        except Exception as e:
            self.original_stdout.write(f"\n[GUI Error] 이미지 로드 실패: {e}\n")

    def run_task(self):
        """
        별도 스레드에서 파이프라인 실행
        """
        try:
            if self.pipeline_callback:
                self.pipeline_callback(self)
            else:
                print("실행할 파이프라인 콜백이 없습니다.")
                
        except Exception as e:
            print(f"\n!!! 치명적 오류 발생: {e}")
        finally:
            print("\n--- 작업이 종료되었습니다. 창을 닫아도 됩니다. ---")
