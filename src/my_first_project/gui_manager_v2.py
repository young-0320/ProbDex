# --- gui_manager_v2.py ---
import sys
import os
import threading
import tkinter as tk
from tkinter import scrolledtext
from PIL import Image, ImageTk
from .config import path

class ProbDexGUI:
    def __init__(self, root, mode, filename=None, init_flag=False, pipeline_callback=None):
        self.root = root
        self.mode = mode
        self.filename = filename
        self.init_flag = init_flag
        self.pipeline_callback = pipeline_callback 
        
        # 데이터 저장소
        self.results = [] 
        self.current_index = 0
        self.current_tk_image = None 
        
        self.root.title(f"ProbDex Controller V2 - [{mode.upper()} MODE]")
        self.root.geometry("1200x900")
        
        self.create_widgets()
        
        # 표준 출력 리다이렉트
        self.original_stdout = sys.stdout
        sys.stdout = self
        
        # 작업 스레드 시작
        self.thread = threading.Thread(target=self.run_task)
        self.thread.daemon = True
        self.thread.start()

    def create_widgets(self):
        # 1. 상단 로그 영역
        log_frame = tk.Frame(self.root)
        log_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10, side=tk.TOP)
        
        tk.Label(log_frame, text="[System Log & Analysis Result]", font=("Arial", 12, "bold")).pack(anchor=tk.W)
        
        self.log_area = scrolledtext.ScrolledText(log_frame, height=10, state='disabled', bg="#f0f0f0")
        self.log_area.pack(fill=tk.BOTH, expand=True)
        
        # 2. 하단 이미지 캐러셀 영역
        if self.mode == 'user':
            carousel_frame = tk.Frame(self.root, bg="white", relief="groove", bd=2)
            carousel_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10, side=tk.BOTTOM)
            
            header_frame = tk.Frame(carousel_frame, bg="white")
            header_frame.pack(fill=tk.X, padx=10, pady=5)
            tk.Label(header_frame, text="[Recommended Problems]", bg="white", font=("Arial", 14, "bold")).pack(side=tk.LEFT)

            content_frame = tk.Frame(carousel_frame, bg="white")
            content_frame.pack(fill=tk.BOTH, expand=True, pady=10)
            
            self.btn_prev = tk.Button(content_frame, text="<", font=("Arial", 24, "bold"), command=self.prev_image, state="disabled", bg="#f0f0f0", relief="flat")
            self.btn_prev.pack(side=tk.LEFT, fill=tk.Y, padx=10)
            
            info_frame = tk.Frame(content_frame, bg="white", width=250)
            info_frame.pack(side=tk.LEFT, fill=tk.Y, padx=10, pady=20)
            info_frame.pack_propagate(False)
            
            tk.Label(info_frame, text="[Problem Info]", bg="white", font=("Arial", 11, "bold"), fg="#888").pack(anchor="w", pady=(0, 10))
            
            self.info_label = tk.Label(info_frame, text="-", bg="white", font=("Arial", 12), fg="#333", justify="left", wraplength=230)
            self.info_label.pack(anchor="w", pady=5)
            
            self.counter_label = tk.Label(info_frame, text="0 / 0", bg="white", font=("Arial", 12, "bold"), fg="#0055ff")
            self.counter_label.pack(anchor="w", pady=20)

            self.image_label = tk.Label(content_frame, text="Waiting for results...", bg="#f8f8f8")
            self.image_label.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            
            self.btn_next = tk.Button(content_frame, text=">", font=("Arial", 24, "bold"), command=self.next_image, state="disabled", bg="#f0f0f0", relief="flat")
            self.btn_next.pack(side=tk.RIGHT, fill=tk.Y, padx=10)

    # [핵심 수정 1] 스레드 충돌 방지를 위해 메인 스레드로 작업 토스
    def write(self, text):
        self.root.after(0, self._safe_write, text)

    def _safe_write(self, text):
        self.log_area.config(state='normal')
        self.log_area.insert(tk.END, text)
        self.log_area.see(tk.END)
        self.log_area.config(state='disabled')
        
        # 터미널에도 출력 확인용
        self.original_stdout.write(text)

        if self.mode == 'user':
            self.parse_gui_data(text)

    def flush(self):
        pass

    def parse_gui_data(self, text):
        """
        구조화된 데이터 파싱
        Format: ||GUI_DATA||{image_path}||{score}||{title}||{user_prob_num}||{runners_up_str}
        """
        if "||GUI_DATA||" in text:
            try:
                parts = text.strip().split("||")
                if "GUI_DATA" in parts:
                    idx = parts.index("GUI_DATA")
                    if len(parts) > idx + 5:
                        img_path = parts[idx+1].strip()
                        score = parts[idx+2].strip()
                        title = parts[idx+3].strip()
                        user_prob_num = parts[idx+4].strip()
                        runners_up_str = parts[idx+5].strip()
                        
                        # 경로 찾기 실행
                        valid_path = self.resolve_image_path(img_path)
                        
                        # [핵심 수정] 
                        # 기존: 이미지 경로(path)가 같으면 중복으로 처리해서 2번 문제가 무시됨.
                        # 수정: '입력 문제 번호(user_prob_num)'가 다르면, 이미지가 같아도 추가하도록 변경!
                        
                        is_duplicate = any(r['user_prob_num'] == user_prob_num for r in self.results)
                        
                        if not is_duplicate:
                            self.results.append({
                                "path": valid_path,
                                "score": score,
                                "title": title,
                                "user_prob_num": user_prob_num,
                                "runners_up_str": runners_up_str,
                                "raw_path": img_path
                            })
                            
                            # 첫 번째 결과가 들어오면 바로 화면에 표시
                            if len(self.results) == 1:
                                self.show_current_image()
                            
                            self.update_buttons()
                            
            except Exception as e:
                self.original_stdout.write(f"\n[GUI Error] 데이터 파싱 실패: {e}\n")
    # [핵심 수정 2] 검색 우선순위 변경 (problem_images 폴더 최우선)
    def resolve_image_path(self, img_path_raw):
        if not img_path_raw:
            return None
            
        filename = os.path.basename(img_path_raw)
        
        # 검색 후보 순서 재배치: 가장 유력한 폴더부터 검색
        candidates = [
            os.path.join(path['problem_images'], filename),      # 1순위: assets/problem_images
            os.path.join(path['user_problem_images'], filename), # 2순위: user_input/problem_images
            img_path_raw,                                        # 3순위: 절대 경로 등 원본
            os.path.join(path['root'], img_path_raw)             # 4순위: 프로젝트 루트 기준
        ]
        
        for p in candidates:
            if os.path.exists(p) and os.path.isfile(p):
                return p
        
        # 못 찾았을 경우 로그 (디버깅용)
        self.original_stdout.write(f"\n[Image Not Found] {filename}\n")
        return None

    def show_current_image(self):
        if not self.results:
            return
            
        data = self.results[self.current_index]
        img_path = data['path']
        
        if img_path:
            try:
                pil_img = Image.open(img_path)
                base_height = 500
                h_percent = (base_height / float(pil_img.size[1]))
                w_size = int((float(pil_img.size[0]) * float(h_percent)))
                pil_img = pil_img.resize((w_size, base_height), Image.Resampling.LANCZOS)
                
                tk_img = ImageTk.PhotoImage(pil_img)
                self.image_label.config(image=tk_img, text="")
                self.current_tk_image = tk_img 
            except Exception as e:
                self.image_label.config(image="", text=f"이미지 로드 실패\n{e}")
        else:
            self.image_label.config(image="", text=f"이미지 파일 없음\n({data['raw_path']})")

        runners_up_display = ""
        if data.get('runners_up_str'):
            runners_list = data['runners_up_str'].split('^')
            runners_up_display = "\n\n[추가 유사 문항]\n" + "\n".join(runners_list)

        info_text = (
            f"문제 번호: {data.get('user_prob_num', '?')}번\n"
            f"유사도: {data['score']}\n"
            f"원형 기출 문제:\n"
            f"{data['title']}"
            f"{runners_up_display}"
        )
        self.info_label.config(text=info_text)
        self.counter_label.config(text=f"page {self.current_index + 1}/{len(self.results)}")

    def prev_image(self):
        if self.current_index > 0:
            self.current_index -= 1
            self.show_current_image()
            self.update_buttons()

    def next_image(self):
        if self.current_index < len(self.results) - 1:
            self.current_index += 1
            self.show_current_image()
            self.update_buttons()

    def update_buttons(self):
        self.btn_prev.config(state="normal" if self.current_index > 0 else "disabled")
        self.btn_next.config(state="normal" if self.current_index < len(self.results) - 1 else "disabled")

    def run_task(self):
        try:
            if self.pipeline_callback:
                self.pipeline_callback(self)
            else:
                print("실행할 파이프라인 콜백이 없습니다.")
        except Exception as e:
            print(f"\n!!! 치명적 오류 발생: {e}")
        finally:
            print("\n--- 작업이 종료되었습니다. ---")