import streamlit as st
import os, re, io

# Streamlit Secrets에서 API 키 로드 (Advanced Settings > Secrets)
# 로컬에서는 .streamlit/secrets.toml 파일에 설정
GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY", "")

# ── 외부 패키지 ───────────────────────────────────────
from deep_translator import GoogleTranslator

try:
    from google import genai
    _genai_client = genai.Client(api_key=GEMINI_API_KEY) if GEMINI_API_KEY else None
except Exception:
    _genai_client = None

try:
    from gtts import gTTS
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
LANG_NAMES = list(LANGUAGES.keys())
LANG_NOTGT = [k for k in LANG_NAMES if k != "자동 감지"]
CHUNK = 4500


# ── 텍스트 분할 ──────────────────────────────────────
def split_text(text: str, size: int) -> list[str]:
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


# ── 파일에서 텍스트 추출 ──────────────────────────────
def extract_text(uploaded_file) -> str:
    name = uploaded_file.name.lower()

    if name.endswith(".pdf"):
        if not PDF_OK:
            st.error("pdfplumber 패키지가 필요합니다: pip install pdfplumber")
            return ""
        with pdfplumber.open(uploaded_file) as pdf:
            pages = [
                f"[{i+1}페이지]\n{p.extract_text()}"
                for i, p in enumerate(pdf.pages)
                if p.extract_text()
            ]
        text = "\n\n".join(pages)
        if not text.strip():
            st.warning("텍스트를 추출할 수 없습니다. (이미지 PDF는 지원 안 됨)")
        return text

    raw = uploaded_file.read()
    for enc in ("utf-8", "cp949", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


# ── 번역 ─────────────────────────────────────────────
def translate(text: str, src: str, tgt: str) -> str:
    chunks = split_text(text, CHUNK)
    results = []
    bar = st.progress(0, text="번역 중...")
    for i, chunk in enumerate(chunks):
        results.append(GoogleTranslator(source=src, target=tgt).translate(chunk) or "")
        bar.progress((i + 1) / len(chunks), text=f"번역 중... ({i+1}/{len(chunks)})")
    bar.empty()
    return "\n".join(results)


# ── AI 요약 ──────────────────────────────────────────
def summarize(text: str) -> str:
    if not _genai_client:
        st.error(".env 파일에 GEMINI_API_KEY가 없습니다.")
        return ""
    prompt = (
        "다음 문서를 읽고 핵심 내용을 한국어로 정확히 3줄로 요약해줘. "
        "각 줄은 '1. ', '2. ', '3. '으로 시작하고 간결하게 작성해.\n\n"
        f"[문서]\n{text[:15000]}"
    )
    resp = _genai_client.models.generate_content(
        model="gemini-2.5-flash", contents=prompt)
    return resp.text.strip()


# ── TTS MP3 생성 ─────────────────────────────────────
def make_tts_mp3(text: str, lang: str) -> bytes:
    buf = io.BytesIO()
    gTTS(text=text, lang=lang, slow=False).write_to_fp(buf)
    return buf.getvalue()


# ════════════════════════════════════════════════════
# 페이지 설정
# ════════════════════════════════════════════════════
st.set_page_config(
    page_title="문서 번역기",
    page_icon="📄",
    layout="wide",
)

# ── 커스텀 CSS ────────────────────────────────────────
st.markdown("""
<style>
/* 헤더 */
.app-header {
    background: linear-gradient(135deg, #6366f1 0%, #4f46e5 100%);
    color: white;
    padding: 20px 28px;
    border-radius: 12px;
    margin-bottom: 20px;
}
.app-header h1 { margin: 0; font-size: 1.7rem; }
.app-header p  { margin: 4px 0 0; opacity: .8; font-size: .9rem; }

/* 섹션 카드 */
.section-card {
    background: white;
    border: 1px solid #e2e8f0;
    border-radius: 10px;
    padding: 16px 20px;
    margin-bottom: 16px;
}
.section-title {
    font-weight: 700;
    color: #475569;
    font-size: .85rem;
    text-transform: uppercase;
    letter-spacing: .05em;
    margin-bottom: 8px;
}

/* 요약 박스 */
.summary-box {
    background: #faf5ff;
    border: 1px solid #ddd6fe;
    border-radius: 10px;
    padding: 16px 18px;
    font-size: 1rem;
    line-height: 1.8;
    color: #1e293b;
    white-space: pre-wrap;
}

/* 번역결과 박스 */
.result-box {
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 10px;
    padding: 14px 16px;
    font-size: .95rem;
    line-height: 1.7;
    color: #1e293b;
    white-space: pre-wrap;
    max-height: 380px;
    overflow-y: auto;
}

/* API 뱃지 */
.badge-ok  { background:#dcfce7; color:#166534; padding:3px 10px;
             border-radius:99px; font-size:.78rem; font-weight:600; }
.badge-err { background:#fef3c7; color:#92400e; padding:3px 10px;
             border-radius:99px; font-size:.78rem; font-weight:600; }

/* Streamlit 버튼 색 오버라이드 */
div[data-testid="stButton"] > button {
    border-radius: 8px !important;
    font-weight: 600 !important;
}
</style>
""", unsafe_allow_html=True)

# ── 세션 초기화 ───────────────────────────────────────
for key, default in [
    ("src_text", ""),
    ("tgt_text", ""),
    ("summary",  ""),
    ("tts_mp3",  None),
    ("filename", ""),
]:
    if key not in st.session_state:
        st.session_state[key] = default

# ════════════════════════════════════════════════════
# 헤더
# ════════════════════════════════════════════════════
api_badge = (
    '<span class="badge-ok">✅ Gemini 연결됨</span>'
    if _genai_client else
    '<span class="badge-err">⚠ GEMINI_API_KEY 없음</span>'
)
st.markdown(f"""
<div class="app-header">
  <h1>📄 문서 번역기</h1>
  <p>파일 업로드 또는 텍스트 입력 → 번역 · AI 요약 · TTS &nbsp;&nbsp;{api_badge}</p>
</div>
""", unsafe_allow_html=True)

# ════════════════════════════════════════════════════
# 사이드바 — 설정
# ════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("## ⚙️ 설정")

    src_lang_name = st.selectbox("원본 언어", LANG_NAMES, index=0)
    tgt_lang_name = st.selectbox("번역 언어", LANG_NOTGT, index=1)

    st.divider()

    uploaded = st.file_uploader(
        "📂 파일 업로드",
        type=["txt", "md", "csv", "json", "html", "py", "js", "ts", "pdf"],
        help=".txt .md .csv .json .html .py .js .ts .pdf 지원"
    )
    if uploaded:
        if uploaded.name != st.session_state.filename:
            with st.spinner(f"파일 읽는 중: {uploaded.name}"):
                content = extract_text(uploaded)
            if content:
                st.session_state.src_text = content
                st.session_state.filename = uploaded.name
                st.session_state.tgt_text = ""
                st.session_state.summary  = ""
                st.session_state.tts_mp3  = None
                st.success(f"✅ {uploaded.name} 불러옴")

    st.divider()

    tts_lang_name = st.selectbox("🔊 TTS 언어", LANG_NOTGT, index=0)

    st.divider()
    st.markdown("**단축 안내**")
    st.caption("① 텍스트 입력 또는 파일 업로드\n② 번역하기\n③ AI 요약 생성\n④ TTS 재생")


# ════════════════════════════════════════════════════
# 메인 — 번역 에디터
# ════════════════════════════════════════════════════
col_src, col_tgt = st.columns(2, gap="medium")

with col_src:
    st.markdown('<div class="section-title">원본 텍스트</div>', unsafe_allow_html=True)
    src_input = st.text_area(
        label="원본",
        value=st.session_state.src_text,
        height=320,
        placeholder="번역할 텍스트를 여기에 입력하거나, 사이드바에서 파일을 올려주세요...",
        label_visibility="collapsed",
    )
    st.session_state.src_text = src_input
    st.caption(f"{len(src_input):,} 자")

with col_tgt:
    st.markdown('<div class="section-title">번역 결과</div>', unsafe_allow_html=True)
    if st.session_state.tgt_text:
        st.markdown(
            f'<div class="result-box">{st.session_state.tgt_text}</div>',
            unsafe_allow_html=True,
        )
        st.caption(f"{len(st.session_state.tgt_text):,} 자")
    else:
        st.text_area(
            label="번역결과",
            value="",
            height=320,
            placeholder="번역 결과가 여기에 표시됩니다...",
            disabled=True,
            label_visibility="collapsed",
        )

# ── 번역 버튼 행 ──────────────────────────────────────
b1, b2, b3, b4, _ = st.columns([1.4, 1, 1, 1, 3])

with b1:
    do_translate = st.button("🌐 번역하기", type="primary", use_container_width=True)
with b2:
    do_clear = st.button("🗑 초기화", use_container_width=True)
with b3:
    if st.session_state.tgt_text:
        st.download_button(
            "💾 저장",
            data=st.session_state.tgt_text.encode("utf-8"),
            file_name=(
                os.path.splitext(st.session_state.filename)[0] + "_번역.txt"
                if st.session_state.filename else "번역결과.txt"
            ),
            mime="text/plain",
            use_container_width=True,
        )
with b4:
    if st.session_state.tgt_text:
        st.button(
            "📋 복사",
            on_click=lambda: st.write(
                "<script>navigator.clipboard.writeText("
                + repr(st.session_state.tgt_text) + ")</script>",
                unsafe_allow_html=True,
            ),
            use_container_width=True,
        )

# 초기화
if do_clear:
    for k in ("src_text", "tgt_text", "summary", "tts_mp3", "filename"):
        st.session_state[k] = "" if k != "tts_mp3" else None
    st.rerun()

# 번역 실행
if do_translate:
    src = st.session_state.src_text.strip()
    if not src:
        st.warning("번역할 텍스트를 입력하세요.")
    else:
        sl = LANGUAGES[src_lang_name]
        tl = LANGUAGES[tgt_lang_name]
        try:
            with st.spinner("번역 중..."):
                result = translate(src, sl, tl)
            st.session_state.tgt_text = result
            st.session_state.summary  = ""
            st.session_state.tts_mp3  = None
            st.rerun()
        except Exception as e:
            st.error(f"번역 오류: {e}")

st.divider()

# ════════════════════════════════════════════════════
# AI 3줄 요약 + TTS
# ════════════════════════════════════════════════════
st.markdown("### ✨ AI 3줄 요약 + 🔊 TTS")

sum_b1, sum_b2, _ = st.columns([1.5, 1.2, 4])

with sum_b1:
    do_summary = st.button(
        "✨ 3줄 요약 생성",
        disabled=not bool(st.session_state.src_text.strip()),
        use_container_width=True,
    )
with sum_b2:
    do_tts = st.button(
        "🔊 TTS 재생",
        disabled=not bool(st.session_state.summary),
        use_container_width=True,
    )

# 요약 실행
if do_summary:
    src = st.session_state.src_text.strip()
    if not src:
        st.warning("요약할 텍스트를 입력하세요.")
    elif not _genai_client:
        st.error(".env 파일에 GEMINI_API_KEY를 설정하세요.")
    else:
        with st.spinner("Gemini 2.5 Flash로 요약 중..."):
            try:
                st.session_state.summary  = summarize(src)
                st.session_state.tts_mp3  = None
                st.rerun()
            except Exception as e:
                st.error(f"요약 오류: {e}")

# TTS 실행
if do_tts:
    text = st.session_state.summary
    if not TTS_OK:
        st.error("pip install gtts 실행 필요")
    elif text:
        lang = LANGUAGES.get(tts_lang_name, "ko")
        with st.spinner("음성 생성 중..."):
            try:
                st.session_state.tts_mp3 = make_tts_mp3(text, lang)
            except Exception as e:
                st.error(f"TTS 오류: {e}")

# 요약 결과 표시
if st.session_state.summary:
    st.markdown(
        f'<div class="summary-box">{st.session_state.summary}</div>',
        unsafe_allow_html=True,
    )

    # TTS 오디오 플레이어
    if st.session_state.tts_mp3:
        st.audio(st.session_state.tts_mp3, format="audio/mp3", autoplay=True)
        st.caption("🔊 요약 내용을 음성으로 재생합니다.")
else:
    st.info("원본 텍스트를 입력한 뒤 **✨ 3줄 요약 생성** 버튼을 누르세요.", icon="💡")
