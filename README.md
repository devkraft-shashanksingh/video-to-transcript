# Media Transcriber

A Streamlit app that transcribes video and audio files to text using [AssemblyAI](https://www.assemblyai.com/).

## Features

- **File upload** — drag & drop or browse for video/audio files (MP4, MOV, AVI, MKV, WEBM, MP3, WAV, M4A, FLAC, OGG)
- **URL support** — paste a direct link to any public video/audio
- **API key validation** — verifies your AssemblyAI key before transcribing
- **Live progress** — real-time upload tracking (MB sent) and transcription status (queued → processing → done)
- **Speaker diarization** — optionally label speakers in the transcript
- **Download** — save transcript as `.txt` or timestamped `.srt` subtitle file

## Setup

1. Get a free API key from [assemblyai.com](https://www.assemblyai.com/dashboard/signup)

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Run the app:
   ```bash
   streamlit run app.py
   ```

4. Open http://localhost:8501, enter your API key, upload a file or paste a URL, and click **Generate Transcript**.

## Deploy

This app can be deployed for free on [Streamlit Community Cloud](https://share.streamlit.io/):

1. Push the repo to GitHub
2. Go to share.streamlit.io and sign in with GitHub
3. Select the repo, branch `master`, and file `app.py`
4. Click **Deploy**
