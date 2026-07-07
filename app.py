import tempfile
import time
from pathlib import Path

import assemblyai as aai
import httpx
import streamlit as st


def ms_to_srt(ms: int) -> str:
    s, ms = divmod(ms, 1000)
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def build_srt(sentences) -> str:
    lines = []
    for i, s in enumerate(sentences, 1):
        start = ms_to_srt(s.start)
        end = ms_to_srt(s.end)
        lines.append(f"{i}\n{start} --> {end}\n{s.text}\n")
    return "\n".join(lines)


def verify_api_key(key: str) -> bool:
    try:
        resp = httpx.get(
            "https://api.assemblyai.com/v2/transcript",
            headers={"Authorization": key},
            params={"limit": 1},
            timeout=10,
        )
        return resp.status_code == 200
    except httpx.HTTPError:
        return False


def upload_with_progress(file_path: str, api_key: str, status_box, progress_bar):
    file_size = Path(file_path).stat().st_size
    uploaded = 0
    chunk_size = 5 * 1024 * 1024

    def file_chunks():
        nonlocal uploaded
        with open(file_path, "rb") as f:
            while chunk := f.read(chunk_size):
                uploaded += len(chunk)
                pct = min(int(20 + (uploaded / file_size) * 30), 50)
                mb_done = uploaded / (1024 * 1024)
                mb_total = file_size / (1024 * 1024)
                progress_bar.progress(pct, text=f"Uploading… {mb_done:.1f} / {mb_total:.1f} MB")
                status_box.info(f"📤 **Uploading** — {mb_done:.1f} / {mb_total:.1f} MB sent")
                yield chunk

    resp = httpx.post(
        "https://api.assemblyai.com/v2/upload",
        headers={"Authorization": api_key},
        content=file_chunks(),
        timeout=httpx.Timeout(timeout=300.0),
    )
    resp.raise_for_status()
    return resp.json()["upload_url"]


st.set_page_config(page_title="Video to Transcript", page_icon="🎬")
st.title("Video to Text Transcript")
st.write("Upload a video/audio file or paste a URL to generate a transcript.")

api_key = st.text_input("AssemblyAI API Key", type="password")

if api_key:
    if "api_key_valid" not in st.session_state or st.session_state.get("last_key") != api_key:
        with st.spinner("Verifying API key…"):
            valid = verify_api_key(api_key)
        st.session_state.api_key_valid = valid
        st.session_state.last_key = api_key

    if st.session_state.api_key_valid:
        st.success("API key verified")
    else:
        st.error("Invalid API key — check your key at assemblyai.com/dashboard")

input_method = st.radio("Input method", ["Upload File", "Paste URL"], horizontal=True)

video_url = None
uploaded_file = None

if input_method == "Upload File":
    uploaded_file = st.file_uploader(
        "Choose a video or audio file",
        type=["mp4", "mov", "avi", "mkv", "webm", "mp3", "wav", "m4a", "flac", "ogg"],
    )
else:
    video_url = st.text_input("Video / Audio URL")

speaker_labels = st.checkbox("Enable speaker diarization")

has_input = (input_method == "Upload File" and uploaded_file) or (
    input_method == "Paste URL" and video_url
)
key_ok = api_key and st.session_state.get("api_key_valid", False)

if st.button("Generate Transcript", disabled=not key_ok or not has_input):
    aai.settings.api_key = api_key
    aai.settings.http_timeout = 300.0
    config = aai.TranscriptionConfig(speaker_labels=speaker_labels)
    transcriber = aai.Transcriber(config=config)

    status_box = st.empty()
    progress_bar = st.progress(0, text="Starting…")

    source = video_url
    tmp_path = None

    if input_method == "Upload File":
        status_box.info("📁 **Saving** — preparing uploaded file…")
        progress_bar.progress(5, text="Saving uploaded file…")
        suffix = Path(uploaded_file.name).suffix
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(uploaded_file.read())
            tmp_path = tmp.name

        try:
            upload_url = upload_with_progress(tmp_path, api_key, status_box, progress_bar)
            source = upload_url
        except httpx.HTTPError as e:
            status_box.error(f"❌ **Upload failed** — {e}")
            progress_bar.empty()
            Path(tmp_path).unlink(missing_ok=True)
            st.stop()
    else:
        status_box.info("📤 **Submitting** — sending URL to AssemblyAI…")
        progress_bar.progress(20, text="Submitting URL…")

    status_box.info("🚀 **Submitted** — starting transcription…")
    progress_bar.progress(55, text="Submitted for transcription…")

    transcript = transcriber.submit(source)

    while True:
        transcript = aai.Transcript.get_by_id(transcript.id)
        status = transcript.status

        if status == aai.TranscriptStatus.queued:
            status_box.info("⏳ **Queued** — waiting in AssemblyAI queue…")
            progress_bar.progress(60, text="Queued…")
        elif status == aai.TranscriptStatus.processing:
            status_box.warning("⚙️ **Processing** — transcription in progress…")
            progress_bar.progress(80, text="Transcribing audio…")
        elif status == aai.TranscriptStatus.completed:
            status_box.success("✅ **Completed** — transcript ready!")
            progress_bar.progress(100, text="Done!")
            break
        elif status == aai.TranscriptStatus.error:
            status_box.error(f"❌ **Error** — {transcript.error}")
            progress_bar.empty()
            if tmp_path:
                Path(tmp_path).unlink(missing_ok=True)
            st.stop()

        time.sleep(3)

    if tmp_path:
        Path(tmp_path).unlink(missing_ok=True)

    if speaker_labels and transcript.utterances:
        display = "\n\n".join(
            f"Speaker {u.speaker}: {u.text}" for u in transcript.utterances
        )
    else:
        display = transcript.text

    st.text_area("Transcript", display, height=400)

    col1, col2 = st.columns(2)
    with col1:
        st.download_button(
            label="Download .txt",
            data=display,
            file_name="transcript.txt",
            mime="text/plain",
        )
    with col2:
        sentences = transcript.get_sentences()
        if sentences:
            srt = build_srt(sentences)
            st.download_button(
                label="Download .srt",
                data=srt,
                file_name="transcript.srt",
                mime="text/plain",
            )
