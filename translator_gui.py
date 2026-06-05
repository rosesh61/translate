import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading, os, time, tempfile

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

try:
    from deep_translator import GoogleTranslator
except ImportError:
    raise SystemExit("pip install deep-translator")

try:
    from google import genai
    _genai_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None
except ImportError:
    genai = None
    _genai_client = None

try:
    from gtts import gTTS
    import pygame
    pygame.mixer.init()
    TTS_OK = True
except ImportError:
    TTS_OK = False

try:
    import pdfplumber
    PDF_OK = True
except ImportError:
    PDF_OK = False

# ── 상수 ──────────────────────────────────────────────
LANGUAGES = {
    "한국어": "ko", "English": "en", "日本語": "ja",
    "中文": "zh-CN", "Français": "fr", "Deutsch": "de", "Español": "es",
    "자동 감지": "auto",
}
LANG_NAMES  = list(LANGUAGES.keys())
LANG_NOTGT  = [k for k in LANG_NAMES if k != "자동 감지"]
CHUNK       = 4500

C_BG     = "#f0f4ff"
C_CARD   = "#ffffff"
C_BORDER = "#e2e8f0"
C_INDIGO = "#6366f1"
C_INDIGO2= "#4f46e5"
C_SLATE  = "#475569"
C_GRAY   = "#94a3b8"
C_GREEN  = "#16a34a"
C_RED    = "#dc2626"
C_AMBER  = "#f59e0b"
C_TEAL   = "#0d9488"
C_PURPLE = "#7c3aed"
C_BTNBG  = "#f1f5f9"


def split_text(text, size):
    import re
    parts = re.split(r'(?<=[.!?\n。！？])\s*', text)
    chunks, cur = [], ""
    for p in parts:
        if len(cur) + len(p) > size and cur:
            chunks.append(cur.strip())
            cur = p
        else:
            cur += p
    if cur.strip():
        chunks.append(cur.strip())
    return chunks or [text]


def make_text(parent, readonly=False, height=None, bg=C_CARD):
    """스크롤바가 달린 텍스트 위젯 프레임을 반환."""
    frame = tk.Frame(parent, bg=C_CARD, highlightbackground=C_BORDER,
                     highlightthickness=1)
    kw = dict(wrap="word", font=("Segoe UI", 10), bg=bg, fg="#1e293b",
              relief="flat", padx=10, pady=8, selectbackground="#c7d2fe",
              state="disabled" if readonly else "normal")
    if height:
        kw["height"] = height
    t = tk.Text(frame, **kw)
    sb = ttk.Scrollbar(frame, orient="vertical", command=t.yview)
    t.configure(yscrollcommand=sb.set)
    t.pack(side="left", fill="both", expand=True)
    sb.pack(side="right", fill="y")
    return frame, t


def btn(parent, text, cmd, bg=C_BTNBG, fg=C_SLATE, bold=False, state="normal"):
    fw = "bold" if bold else "normal"
    b = tk.Button(parent, text=text, command=cmd, bg=bg, fg=fg,
                  font=("Segoe UI", 9, fw), relief="flat", bd=0,
                  padx=14, pady=6, cursor="hand2",
                  activebackground=bg, state=state)
    return b


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("문서 번역기  |  AI 요약  |  TTS")
        self.geometry("1000x780")
        self.minsize(800, 600)
        self.configure(bg=C_BG)

        self._busy     = False
        self._tts_play = False
        self._cur_file = None
        self._tmp_mp3  = None

        self._ui()
        self._center()

    def _center(self):
        self.update_idletasks()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        w, h   = self.winfo_width(), self.winfo_height()
        self.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")

    # ════════════════════════════════════════════════════
    # UI
    # ════════════════════════════════════════════════════
    def _ui(self):
        self._ui_header()
        self._ui_toolbar()
        self._ui_editor()
        self._ui_summary()
        self._ui_statusbar()

    # ── 헤더 ──────────────────────────────────────────
    def _ui_header(self):
        hdr = tk.Frame(self, bg=C_INDIGO)
        hdr.pack(fill="x")

        tk.Label(hdr, text="📄  문서 번역기", bg=C_INDIGO, fg="white",
                 font=("Segoe UI", 16, "bold"), padx=20, pady=12).pack(side="left")

        api_ok  = bool(GEMINI_API_KEY and _genai_client)
        api_txt = "✅ Gemini 연결됨" if api_ok else "⚠ API키 없음"
        api_col = "#bbf7d0" if api_ok else "#fde68a"
        tk.Label(hdr, text=api_txt, bg=C_INDIGO, fg=api_col,
                 font=("Segoe UI", 8), padx=16).pack(side="right")

    # ── 툴바 (언어 선택 + 파일 열기) ─────────────────
    def _ui_toolbar(self):
        bar = tk.Frame(self, bg=C_CARD, highlightbackground=C_BORDER,
                       highlightthickness=1)
        bar.pack(fill="x", padx=12, pady=(10, 0))

        # 1행: 언어 선택
        row1 = tk.Frame(bar, bg=C_CARD)
        row1.pack(fill="x", padx=12, pady=(8, 4))

        tk.Label(row1, text="원본", bg=C_CARD, fg=C_SLATE,
                 font=("Segoe UI", 9, "bold")).pack(side="left")

        self.var_src = tk.StringVar(value="한국어")
        ttk.Combobox(row1, textvariable=self.var_src, values=LANG_NAMES,
                     state="readonly", width=11,
                     font=("Segoe UI", 9)).pack(side="left", padx=(4, 6))

        tk.Button(row1, text=" ⇄ ", bg=C_BTNBG, fg=C_SLATE, relief="flat", bd=0,
                  font=("Segoe UI", 10), cursor="hand2",
                  command=self._swap).pack(side="left", padx=4)

        tk.Label(row1, text="번역", bg=C_CARD, fg=C_SLATE,
                 font=("Segoe UI", 9, "bold")).pack(side="left", padx=(6, 0))

        self.var_tgt = tk.StringVar(value="English")
        ttk.Combobox(row1, textvariable=self.var_tgt, values=LANG_NOTGT,
                     state="readonly", width=11,
                     font=("Segoe UI", 9)).pack(side="left", padx=(4, 0))

        # 2행: 파일 열기
        row2 = tk.Frame(bar, bg=C_CARD)
        row2.pack(fill="x", padx=12, pady=(0, 8))

        btn(row2, "📂  파일 열기", self._open_file, bold=True).pack(side="left", padx=(0, 8))

        self.lbl_file = tk.Label(row2, text="파일 미선택", bg=C_CARD, fg=C_GRAY,
                                 font=("Segoe UI", 8))
        self.lbl_file.pack(side="left")

    # ── 에디터 (원본 | 번역) ──────────────────────────
    def _ui_editor(self):
        wrap = tk.Frame(self, bg=C_BG)
        wrap.pack(fill="both", expand=True, padx=12, pady=(10, 0))
        wrap.rowconfigure(1, weight=1)
        wrap.columnconfigure(0, weight=1)

        # 레이블 행
        lbl_row = tk.Frame(wrap, bg=C_BG)
        lbl_row.grid(row=0, column=0, sticky="ew", pady=(0, 4))

        self.lbl_src_n = tk.Label(lbl_row, text="원본  0 자", bg=C_BG, fg=C_SLATE,
                                  font=("Segoe UI", 9, "bold"))
        self.lbl_src_n.pack(side="left")

        self.lbl_tgt_n = tk.Label(lbl_row, text="번역결과  0 자", bg=C_BG, fg=C_SLATE,
                                  font=("Segoe UI", 9, "bold"))
        self.lbl_tgt_n.pack(side="right")

        # PanedWindow — 드래그로 좌우 크기 조절 가능
        pane = tk.PanedWindow(wrap, orient="horizontal", bg=C_BG,
                              sashwidth=6, sashrelief="flat",
                              sashpad=2, handlesize=0)
        pane.grid(row=1, column=0, sticky="nsew")

        src_frm, self.src = make_text(pane)
        self.src.configure(insertbackground=C_INDIGO)
        self.src.bind("<KeyRelease>", lambda _: self._count())
        pane.add(src_frm, stretch="always", minsize=200)

        tgt_frm, self.tgt = make_text(pane, readonly=True, bg="#f8fafc")
        pane.add(tgt_frm, stretch="always", minsize=200)

        # 번역 버튼 행
        btn_row = tk.Frame(wrap, bg=C_BG)
        btn_row.grid(row=2, column=0, sticky="ew", pady=(8, 0))

        self.btn_tr = btn(btn_row, "🌐  번역하기", self._translate,
                          bg=C_INDIGO, fg="white", bold=True)
        self.btn_tr.pack(side="left", padx=(0, 6))

        btn(btn_row, "🗑  초기화", self._clear).pack(side="left", padx=4)

        self.btn_copy = btn(btn_row, "📋  복사", self._copy,
                            bg="#10b981", fg="white", state="disabled")
        self.btn_copy.pack(side="left", padx=4)

        self.btn_save = btn(btn_row, "💾  저장", self._save,
                            bg="#3b82f6", fg="white", state="disabled")
        self.btn_save.pack(side="left", padx=4)

        self.prog_tr = ttk.Progressbar(btn_row, mode="indeterminate", length=100)
        self.prog_tr.pack(side="left", padx=12)

        self.lbl_tr = tk.Label(btn_row, text="", bg=C_BG, fg=C_GRAY,
                               font=("Segoe UI", 9))
        self.lbl_tr.pack(side="left")

        self.bind("<Control-Return>", lambda _: self._translate())
        self.bind("<Control-o>",      lambda _: self._open_file())

    # ── AI 요약 + TTS 패널 ────────────────────────────
    def _ui_summary(self):
        outer = tk.Frame(self, bg=C_CARD, highlightbackground=C_BORDER,
                         highlightthickness=1)
        outer.pack(fill="x", padx=12, pady=(0, 8))

        # 헤더
        hdr = tk.Frame(outer, bg="#faf5ff")
        hdr.pack(fill="x")
        tk.Label(hdr, text="✨  AI 3줄 요약  +  TTS", bg="#faf5ff", fg=C_PURPLE,
                 font=("Segoe UI", 10, "bold"), padx=14, pady=7).pack(side="left")

        tk.Label(hdr, text="TTS 언어:", bg="#faf5ff", fg=C_SLATE,
                 font=("Segoe UI", 8)).pack(side="right", padx=(0, 4))
        self.var_tts_lang = tk.StringVar(value="한국어")
        ttk.Combobox(hdr, textvariable=self.var_tts_lang, values=LANG_NOTGT,
                     state="readonly", width=10,
                     font=("Segoe UI", 9)).pack(side="right", padx=(0, 12))

        # 요약 텍스트
        body = tk.Frame(outer, bg=C_CARD, padx=12, pady=6)
        body.pack(fill="x")
        sum_frm, self.sum = make_text(body, readonly=True, height=5, bg="#faf5ff")
        sum_frm.pack(fill="x")

        # 버튼 행
        brow = tk.Frame(outer, bg=C_CARD, padx=12, pady=8)
        brow.pack(fill="x")

        self.btn_sum = btn(brow, "✨  3줄 요약 생성", self._summarize,
                           bg=C_AMBER, fg="white", bold=True)
        self.btn_sum.pack(side="left", padx=(0, 6))

        self.btn_tts = btn(brow, "🔊  TTS 재생", self._tts_start,
                           bg=C_TEAL, fg="white", state="disabled")
        self.btn_tts.pack(side="left", padx=4)

        self.btn_stop = btn(brow, "⏹  중지", self._tts_stop,
                            bg="#ef4444", fg="white", state="disabled")
        self.btn_stop.pack(side="left", padx=4)

        self.prog_sum = ttk.Progressbar(brow, mode="indeterminate", length=90)
        self.prog_sum.pack(side="left", padx=12)

        self.lbl_sum = tk.Label(brow, text="", bg=C_CARD, fg=C_GRAY,
                                font=("Segoe UI", 9))
        self.lbl_sum.pack(side="left")

        self.bind("<Control-s>", lambda _: self._summarize())

    # ── 상태바 ────────────────────────────────────────
    def _ui_statusbar(self):
        bar = tk.Frame(self, bg=C_INDIGO, height=3)
        bar.pack(fill="x", side="bottom")

    # ════════════════════════════════════════════════════
    # 헬퍼
    # ════════════════════════════════════════════════════
    def _count(self):
        n = len(self.src.get("1.0", "end-1c"))
        self.lbl_src_n.configure(text=f"원본  {n:,} 자")

    def _set_tr(self, msg, color=C_GRAY):
        self.lbl_tr.configure(text=msg, fg=color)

    def _set_sum(self, msg, color=C_GRAY):
        self.lbl_sum.configure(text=msg, fg=color)

    def _write(self, widget, text):
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        if text:
            widget.insert("1.0", text)
        widget.configure(state="disabled")

    # ════════════════════════════════════════════════════
    # 언어 교환
    # ════════════════════════════════════════════════════
    def _swap(self):
        s, t = self.var_src.get(), self.var_tgt.get()
        if s == "자동 감지":
            return
        if t in LANG_NAMES:
            self.var_src.set(t)
        if s in LANG_NOTGT:
            self.var_tgt.set(s)
        src_txt = self.src.get("1.0", "end-1c")
        tgt_txt = self.tgt.get("1.0", "end-1c")
        if tgt_txt:
            self.src.delete("1.0", "end")
            self.src.insert("1.0", tgt_txt)
            self._write(self.tgt, src_txt)
            self._count()

    # ════════════════════════════════════════════════════
    # 파일 열기 (txt / pdf)
    # ════════════════════════════════════════════════════
    def _open_file(self):
        filetypes = [
            ("지원 파일", "*.txt *.md *.csv *.json *.html *.py *.js *.ts *.pdf"),
            ("PDF", "*.pdf"),
            ("텍스트", "*.txt *.md *.csv *.json"),
            ("모든 파일", "*.*"),
        ]
        path = filedialog.askopenfilename(title="파일 선택", filetypes=filetypes)
        if not path:
            return

        name = os.path.basename(path)
        content = ""

        if path.lower().endswith(".pdf"):
            if not PDF_OK:
                messagebox.showerror("오류", "pip install pdfplumber 실행 필요")
                return
            self._set_tr(f"PDF 읽는 중...", C_INDIGO)
            self.update()
            try:
                with pdfplumber.open(path) as pdf:
                    pages = [f"[{i+1}페이지]\n{p.extract_text()}"
                             for i, p in enumerate(pdf.pages)
                             if p.extract_text()]
                content = "\n\n".join(pages)
                if not content.strip():
                    messagebox.showwarning("경고", "텍스트를 추출할 수 없습니다.\n(이미지 PDF는 지원 안 됨)")
                    return
            except Exception as e:
                messagebox.showerror("PDF 오류", str(e))
                return
        else:
            for enc in ("utf-8", "cp949", "latin-1"):
                try:
                    with open(path, encoding=enc) as f:
                        content = f.read()
                    break
                except UnicodeDecodeError:
                    continue

        self.src.delete("1.0", "end")
        self.src.insert("1.0", content)
        self._count()
        self._cur_file = name
        self.lbl_file.configure(text=f"📄 {name}", fg=C_SLATE)
        self._set_tr(f"불러옴: {name}", C_INDIGO)

    # ════════════════════════════════════════════════════
    # 번역
    # ════════════════════════════════════════════════════
    def _translate(self):
        if self._busy:
            return
        src = self.src.get("1.0", "end-1c").strip()
        if not src:
            messagebox.showwarning("입력 필요", "번역할 텍스트를 입력하세요.")
            return
        self._busy = True
        self.btn_tr.configure(state="disabled", bg="#a5b4fc")
        self.btn_copy.configure(state="disabled")
        self.btn_save.configure(state="disabled")
        self.prog_tr.start(10)
        self._set_tr("번역 중...", C_INDIGO)
        self._write(self.tgt, "")
        sl = LANGUAGES[self.var_src.get()]
        tl = LANGUAGES[self.var_tgt.get()]
        threading.Thread(target=self._do_translate, args=(src, sl, tl), daemon=True).start()

    def _do_translate(self, src, sl, tl):
        try:
            chunks  = split_text(src, CHUNK)
            results = []
            for i, chunk in enumerate(chunks):
                self.after(0, self._set_tr, f"번역 중... ({i+1}/{len(chunks)})", C_INDIGO)
                results.append(GoogleTranslator(source=sl, target=tl).translate(chunk) or "")
                if i < len(chunks) - 1:
                    time.sleep(0.3)
            self.after(0, self._done_translate, "\n".join(results))
        except Exception as e:
            self.after(0, self._err_translate, str(e))

    def _done_translate(self, result):
        self._write(self.tgt, result)
        self.lbl_tgt_n.configure(text=f"번역결과  {len(result):,} 자")
        self.prog_tr.stop()
        self.btn_tr.configure(state="normal", bg=C_INDIGO)
        self.btn_copy.configure(state="normal")
        self.btn_save.configure(state="normal")
        self._set_tr("✅ 번역 완료!", C_GREEN)
        self._busy = False

    def _err_translate(self, msg):
        self.prog_tr.stop()
        self.btn_tr.configure(state="normal", bg=C_INDIGO)
        self._set_tr(f"오류: {msg}", C_RED)
        messagebox.showerror("번역 오류", msg)
        self._busy = False

    # ════════════════════════════════════════════════════
    # AI 요약 (Gemini 2.5 Flash)
    # ════════════════════════════════════════════════════
    def _summarize(self):
        if self._busy:
            return
        src = self.src.get("1.0", "end-1c").strip()
        if not src:
            messagebox.showwarning("입력 필요", "요약할 텍스트를 입력하세요.")
            return
        if not _genai_client:
            messagebox.showerror("API 키 없음", ".env 파일에 GEMINI_API_KEY가 필요합니다.")
            return
        self._busy = True
        self.btn_sum.configure(state="disabled", bg="#fbbf24")
        self.btn_tts.configure(state="disabled")
        self.prog_sum.start(10)
        self._set_sum("Gemini로 요약 중...", C_AMBER)
        self._write(self.sum, "")
        threading.Thread(target=self._do_summarize, args=(src,), daemon=True).start()

    def _do_summarize(self, src):
        try:
            prompt = (
                "다음 문서를 읽고 핵심 내용을 한국어로 정확히 3줄로 요약해줘. "
                "각 줄은 '1. ', '2. ', '3. '으로 시작하고 간결하게 작성해.\n\n"
                f"[문서]\n{src[:15000]}"
            )
            resp = _genai_client.models.generate_content(
                model="gemini-2.5-flash", contents=prompt)
            self.after(0, self._done_summarize, resp.text.strip())
        except Exception as e:
            self.after(0, self._err_summarize, str(e))

    def _done_summarize(self, text):
        self._write(self.sum, text)
        self.prog_sum.stop()
        self.btn_sum.configure(state="normal", bg=C_AMBER)
        self.btn_tts.configure(state="normal")
        self._set_sum("✅ 요약 완료!", C_GREEN)
        self._busy = False

    def _err_summarize(self, msg):
        self.prog_sum.stop()
        self.btn_sum.configure(state="normal", bg=C_AMBER)
        self._set_sum(f"오류: {msg}", C_RED)
        messagebox.showerror("요약 오류", msg)
        self._busy = False

    # ════════════════════════════════════════════════════
    # TTS
    # ════════════════════════════════════════════════════
    _TTS_MAP = {"한국어":"ko","English":"en","日本語":"ja",
                "中文":"zh-CN","Français":"fr","Deutsch":"de","Español":"es"}

    def _tts_start(self):
        if not TTS_OK:
            messagebox.showerror("TTS 불가", "pip install gtts pygame")
            return
        text = self.sum.get("1.0", "end-1c").strip()
        if not text:
            messagebox.showwarning("요약 없음", "먼저 요약을 생성하세요.")
            return
        if self._tts_play:
            self._tts_stop()
        lang = self._TTS_MAP.get(self.var_tts_lang.get(), "ko")
        self.btn_tts.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self.prog_sum.start(10)
        self._set_sum("🔊 음성 생성 중...", C_TEAL)
        threading.Thread(target=self._do_tts, args=(text, lang), daemon=True).start()

    def _do_tts(self, text, lang):
        try:
            tmp = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
            tmp.close()
            self._tmp_mp3 = tmp.name
            gTTS(text=text, lang=lang, slow=False).save(self._tmp_mp3)
            self.after(0, self._set_sum, "🔊 재생 중...", C_TEAL)
            self._tts_play = True
            pygame.mixer.music.load(self._tmp_mp3)
            pygame.mixer.music.play()
            while pygame.mixer.music.get_busy() and self._tts_play:
                time.sleep(0.1)
            self.after(0, self._done_tts)
        except Exception as e:
            self.after(0, self._err_tts, str(e))

    def _done_tts(self):
        self._tts_play = False
        self.prog_sum.stop()
        self.btn_tts.configure(state="normal")
        self.btn_stop.configure(state="disabled")
        self._set_sum("✅ 재생 완료", C_GREEN)
        try:
            if self._tmp_mp3 and os.path.exists(self._tmp_mp3):
                os.remove(self._tmp_mp3)
        except Exception:
            pass

    def _err_tts(self, msg):
        self._tts_play = False
        self.prog_sum.stop()
        self.btn_tts.configure(state="normal")
        self.btn_stop.configure(state="disabled")
        self._set_sum(f"오류: {msg}", C_RED)
        messagebox.showerror("TTS 오류", msg)

    def _tts_stop(self):
        self._tts_play = False
        try:
            pygame.mixer.music.stop()
        except Exception:
            pass
        self.prog_sum.stop()
        self.btn_tts.configure(state="normal")
        self.btn_stop.configure(state="disabled")
        self._set_sum("⏹ 중지됨", C_SLATE)

    # ════════════════════════════════════════════════════
    # 공통 조작
    # ════════════════════════════════════════════════════
    def _copy(self):
        text = self.tgt.get("1.0", "end-1c")
        self.clipboard_clear()
        self.clipboard_append(text)
        self._set_tr("📋 복사됨!", C_GREEN)

    def _save(self):
        default = "번역결과.txt"
        if self._cur_file:
            n, e = os.path.splitext(self._cur_file)
            default = f"{n}_번역{e}"
        path = filedialog.asksaveasfilename(
            title="저장", defaultextension=".txt", initialfile=default,
            filetypes=[("텍스트", "*.txt"), ("모든 파일", "*.*")])
        if not path:
            return
        with open(path, "w", encoding="utf-8") as f:
            f.write(self.tgt.get("1.0", "end-1c"))
        self._set_tr(f"💾 저장: {os.path.basename(path)}", C_GREEN)

    def _clear(self):
        self._tts_stop()
        self.src.delete("1.0", "end")
        self._write(self.tgt, "")
        self._write(self.sum, "")
        self.lbl_src_n.configure(text="원본  0 자")
        self.lbl_tgt_n.configure(text="번역결과  0 자")
        self.btn_copy.configure(state="disabled")
        self.btn_save.configure(state="disabled")
        self.btn_tts.configure(state="disabled")
        self.lbl_file.configure(text="파일 미선택", fg=C_GRAY)
        self._cur_file = None
        self._set_tr("", C_GRAY)
        self._set_sum("", C_GRAY)


if __name__ == "__main__":
    App().mainloop()
