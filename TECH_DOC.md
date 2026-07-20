# Media Transcriber — Technical Documentation

**Version 1.0 | July 2026 | Python 3.11+ / Streamlit | AssemblyAI STT**

---

## Table of Contents

- [Overview](#overview)
- [Tech Stack](#tech-stack)
- [Architecture](#architecture)
  - [Data Flow](#data-flow)
- [API Endpoints](#api-endpoints)
  - [POST /v2/upload](#post-v2upload)
  - [POST /v2/transcript](#post-v2transcript)
  - [GET /v2/transcript/{id}](#get-v2transcriptid)
  - [GET /v2/transcript/{id}/sentences](#get-v2transcriptidsentences)
  - [GET /v2/transcript (Key Verification)](#get-v2transcript-key-verification)
- [Data Model](#data-model)
  - [Session State](#session-state)
  - [Transcript Object](#transcript-object)
  - [Sentence Object](#sentence-object)
  - [Utterance Object](#utterance-object)
- [AI Models](#ai-models)
- [Security Assessment](#security-assessment)
  - [Current Posture](#current-posture)
  - [Threat Model](#threat-model)
  - [AssemblyAI Data Handling](#assemblyai-data-handling)
- [Enterprise Readiness](#enterprise-readiness)
- [Improvement Areas](#improvement-areas)
  - [High Priority](#high-priority)
  - [Medium Priority](#medium-priority)
  - [Nice to Have](#nice-to-have)

---

## Overview

Media Transcriber is a single-page web application that converts video and audio files into text transcripts. Users upload a local file or paste a public URL; the application handles chunked upload to AssemblyAI's speech-to-text service, polls for completion with real-time status feedback, and delivers the transcript as downloadable `.txt` and timestamped `.srt` files.

The app is intentionally stateless — no database, no user accounts, no server-side file retention. Every artifact is ephemeral: temporary files are deleted after upload, and transcripts live only in the browser session.

---

## Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| Frontend & Server | Streamlit 1.x | UI framework, widget rendering, session state, file uploader, WebSocket-driven reruns |
| AI / Speech-to-Text | AssemblyAI API v2 | Audio transcription, speaker diarization, sentence segmentation |
| SDK | assemblyai (Python) | Typed wrapper around the AssemblyAI REST API — handles auth, polling, model objects |
| HTTP Client | httpx | Chunked streaming upload with progress callbacks; API key verification |
| Runtime | Python 3.11+ | Walrus operator (`:=`) requires 3.8+; project targets 3.11 |
| Hosting | Streamlit Community Cloud | Free managed deployment from GitHub repo |

---

## Architecture

The system follows a three-tier flow: **Browser Client → Streamlit Server (Python process) → AssemblyAI Cloud**. The Streamlit server acts as a thin proxy — it receives the uploaded file, streams it to AssemblyAI, and relays status updates back to the browser over Streamlit's WebSocket channel.

```
┌─────────────────┐      ┌─────────────────────┐      ┌─────────────────────┐
│     CLIENT       │      │       SERVER         │      │      EXTERNAL       │
│                 │      │                     │      │                     │
│  ┌───────────┐  │ file │  ┌───────────────┐  │upload│  ┌───────────────┐  │
│  │  Browser   │──┼──────┼─▶│  Streamlit     │──┼──────┼─▶│  AssemblyAI   │  │
│  │  Widgets   │  │      │  │  Server        │  │ poll │  │  API v2       │  │
│  └───────────┘  │      │  │  (app.py)      │──┼──────┼─▶│               │  │
│                 │      │  └───────────────┘  │      │  └───────────────┘  │
│  ┌───────────┐  │      │  ┌───────────────┐  │      │  ┌───────────────┐  │
│  │  File      │  │      │  │  Chunked       │  │      │  │  Transcription│  │
│  │  Uploader  │  │      │  │  Upload        │  │      │  │  Conformer-2  │  │
│  │  200MB max │  │      │  │  5MB chunks    │  │      │  │  async proc   │  │
│  └───────────┘  │      │  └───────────────┘  │      │  └───────────────┘  │
│                 │      │                     │      │                     │
│  ┌───────────┐  │◀─────│  ┌───────────────┐  │◀─────│  ┌───────────────┐  │
│  │  Progress  │  │status│  │  Poll Loop     │  │result│  │  Status API   │  │
│  │  UI        │  │      │  │  3s interval   │  │      │  │  queued →     │  │
│  └───────────┘  │      │  └───────────────┘  │      │  │  processing → │  │
│                 │      │                     │      │  │  done          │  │
│  ┌───────────┐  │      │                     │      │  └───────────────┘  │
│  │ Download   │  │      │                     │      │                     │
│  │ .txt/.srt  │  │      │                     │      │                     │
│  └───────────┘  │      │                     │      │                     │
└─────────────────┘      └─────────────────────┘      └─────────────────────┘
```

### Data Flow

1. **API key validation** — an HTTP GET to `/v2/transcript?limit=1` confirms the key before any upload. The result is cached in `st.session_state` to avoid re-checking on every Streamlit rerun.

2. **File intake** — uploaded files are written to a `tempfile.NamedTemporaryFile` on the server. URL inputs bypass this step entirely.

3. **Chunked upload** — for local files, `httpx.post` streams the file in 5 MB chunks to `/v2/upload`, yielding progress callbacks that update the Streamlit UI in real time. Returns an `upload_url`.

4. **Transcription submit** — `transcriber.submit(source)` posts to `/v2/transcript` and returns immediately with a transcript ID (no blocking wait).

5. **Status polling** — a `while True` loop calls `Transcript.get_by_id()` every 3 seconds. The UI updates through four states: queued → processing → completed → error.

6. **Output** — on completion, the text is displayed in a `st.text_area`. Two download buttons offer `.txt` (plain text or speaker-labeled) and `.srt` (timestamped subtitles built from `get_sentences()`).

7. **Cleanup** — temporary files are deleted with `Path.unlink()` regardless of success or failure.

---

## API Endpoints

All requests go to `https://api.assemblyai.com/v2` with the header `Authorization: {api_key}`.

### POST /v2/upload

| Field | Detail |
|-------|--------|
| Purpose | Upload local audio/video file for transcription |
| Method | `POST` with streaming binary body |
| Content-Type | `application/octet-stream` |
| Timeout | 300s (custom, via httpx) |
| Response | `{"upload_url": "https://cdn.assemblyai.com/..."}` |
| Used in | `upload_with_progress()` |

### POST /v2/transcript

| Field | Detail |
|-------|--------|
| Purpose | Submit a transcription job |
| Body | `{"audio_url": "...", "speaker_labels": true\|false}` |
| Response | Transcript object with `id`, `status: "queued"` |
| Used in | `transcriber.submit(source)` |

### GET /v2/transcript/{id}

| Field | Detail |
|-------|--------|
| Purpose | Poll transcription status and retrieve result |
| Status values | `queued` → `processing` → `completed` \| `error` |
| Poll interval | 3 seconds |
| Response (done) | Full transcript object with `text`, `utterances`, `words` |
| Used in | `Transcript.get_by_id(transcript.id)` |

### GET /v2/transcript/{id}/sentences

| Field | Detail |
|-------|--------|
| Purpose | Retrieve sentence-level segments with timestamps |
| Response | Array of `{text, start, end, confidence, words}` |
| Used for | Building the `.srt` subtitle file |
| Used in | `transcript.get_sentences()` |

### GET /v2/transcript (Key Verification)

| Field | Detail |
|-------|--------|
| Purpose | Validate API key by listing transcripts |
| Params | `?limit=1` |
| Logic | HTTP 200 = valid key; any other status = invalid |
| Used in | `verify_api_key()` |

---

## Data Model

The application is stateless — there is no database. All state is ephemeral, held in Streamlit's `session_state` dictionary for the duration of a browser session.

### Session State

| Key | Type | Lifetime | Purpose |
|-----|------|----------|---------|
| `api_key_valid` | bool | Session | Cached result of API key verification |
| `last_key` | str | Session | Last verified key (avoids re-checking on rerun) |

### Transcript Object

From AssemblyAI SDK:

| Field | Type | Description |
|-------|------|-------------|
| `id` | str | Unique transcript identifier |
| `status` | enum | queued \| processing \| completed \| error |
| `text` | str | Full transcript text |
| `utterances` | list | Speaker-labeled segments (when diarization enabled) |
| `error` | str \| null | Error message if transcription failed |

### Sentence Object

| Field | Type | Description |
|-------|------|-------------|
| `text` | str | Sentence text |
| `start` | int | Start timestamp in milliseconds |
| `end` | int | End timestamp in milliseconds |
| `confidence` | float | Model confidence score (0–1) |

### Utterance Object

Returned when speaker diarization is enabled:

| Field | Type | Description |
|-------|------|-------------|
| `speaker` | str | Speaker label (A, B, C…) |
| `text` | str | Text spoken by this speaker in this segment |
| `start` | int | Start timestamp (ms) |
| `end` | int | End timestamp (ms) |

---

## AI Models

| Model | Provider | Task | Details |
|-------|----------|------|---------|
| Conformer-2 | AssemblyAI | Speech-to-Text | Default transcription model. Trained on 12.5M+ hours of multilingual audio data. Supports 99+ languages with automatic language detection. |
| Speaker Diarization | AssemblyAI | Speaker identification | Neural speaker embedding model that clusters voice segments by speaker identity. Activated via `speaker_labels=True`. |
| Sentence Segmentation | AssemblyAI | Text structuring | NLP model that splits the raw word stream into semantically coherent sentences with per-sentence timestamps. |

> **Note:** The application uses AssemblyAI's **Best** tier by default. The model selection is handled server-side by AssemblyAI — there is no model parameter in the current code. AssemblyAI also offers a Nano tier for lower latency at reduced accuracy, configurable via `TranscriptionConfig(speech_model="nano")`.

---

## Security Assessment

### Current Posture

| Area | Status | Detail |
|------|--------|--------|
| API key handling | ✅ Good | Key entered via `type="password"` input, never written to disk or logs. Sent only in HTTP headers to AssemblyAI. |
| File handling | ✅ Good | Temp files created with `NamedTemporaryFile`, deleted in cleanup regardless of success/failure. |
| Transport security | ✅ Good | All AssemblyAI communication over HTTPS/TLS. No plaintext API calls. |
| Input validation | ⚠️ Limited | File type restricted by extension via Streamlit's uploader. No content-type sniffing or malware scanning. |
| Data at rest | ✅ Good | No database, no persistent storage. Transcripts exist only in browser session memory. |
| Authentication | 🔴 None | No user authentication. Anyone with access to the URL can use it. API key is the only gate. |
| Rate limiting | 🔴 None | No application-level rate limiting. Relies entirely on AssemblyAI's account-level limits. |
| CORS / XSS | ✅ Good | Streamlit handles CSP headers and sandboxes widget rendering. |

### Threat Model

> **Key Risk:** The API key is entered client-side and transmitted through the Streamlit server. In a shared deployment, the server operator can observe the key in process memory. For enterprise use, the key should be injected via environment variable or a secrets manager, never through the UI.

### AssemblyAI Data Handling

- Uploaded audio is stored temporarily on AssemblyAI's infrastructure for processing
- AssemblyAI is SOC 2 Type II certified and GDPR compliant
- Audio files are deleted after transcription by default
- Transcripts are retained for retrieval via API until explicitly deleted

---

## Enterprise Readiness

**Current State: Prototype**

The application is functional for individual use but lacks the infrastructure expected in an enterprise deployment.

| Capability | Status | Gap |
|-----------|--------|-----|
| User authentication | 🔴 Missing | No login, SSO, or RBAC. Any visitor can use the app. |
| Secrets management | 🔴 Missing | API key entered by user in the UI. Should use env vars or vault. |
| Audit logging | 🔴 Missing | No record of who transcribed what, or when. |
| Multi-tenancy | 🔴 Missing | Single API key, no org/team isolation. |
| File size limits | ⚠️ Partial | Streamlit's 200 MB upload limit. No server-side enforcement or resumable upload. |
| Error recovery | ⚠️ Partial | Upload failures handled; network interruptions during polling are not (page refresh loses state). |
| Scalability | ⚠️ Limited | Single Streamlit process. Blocking poll loop holds a thread per transcription. |
| Monitoring | 🔴 Missing | No health checks, metrics, alerting, or dashboards. |
| CI/CD | ⚠️ Partial | GitHub repo exists. No automated tests, linting, or deployment pipeline. |
| Data residency | ⚠️ Depends | Audio processed in AssemblyAI's US/EU regions. No control over routing from this app. |

---

## Improvement Areas

### High Priority

1. **Server-side API key via environment variable**
   Move the API key to `st.secrets` or an environment variable. Remove the UI input field in production. This eliminates the key-in-transit risk and simplifies the user experience.

2. **User authentication**
   Add Streamlit's built-in auth, or proxy behind an identity-aware reverse proxy (e.g. Cloudflare Access, AWS ALB + Cognito). Gate access before any AssemblyAI calls.

3. **Audit logging**
   Log every transcription request: timestamp, user identity, file name/URL, transcript ID, duration, status. Ship to a structured log sink (CloudWatch, Datadog, etc.).

4. **Error handling & retry**
   Wrap the polling loop with exponential backoff. Handle network interruptions gracefully. Persist transcript IDs to session state so a page refresh can resume polling.

### Medium Priority

1. **Transcript history**
   Store completed transcript IDs in session state or a lightweight database (SQLite, Redis). Let users revisit past transcripts without re-uploading.

2. **Additional export formats**
   Add VTT (WebVTT) subtitles, DOCX with speaker labels, and JSON with full word-level timestamps and confidence scores.

3. **Language selection**
   Expose AssemblyAI's `language_code` parameter. Allow users to override auto-detection for better accuracy on known-language content.

4. **Webhook-based completion**
   Replace the polling loop with AssemblyAI's `webhook_url` callback. Requires a publicly reachable endpoint but eliminates the 3-second poll overhead.

5. **Batch processing**
   Support multiple file uploads with a queue. Use `transcribe_group()` to submit all files and track progress in a unified dashboard.

### Nice to Have

1. **Content intelligence features**
   Enable AssemblyAI's summarization, sentiment analysis, entity detection, and topic detection via `TranscriptionConfig`.

2. **Video player with synced transcript**
   Embed a video player alongside the transcript with click-to-seek on any sentence, using word-level timestamps for highlighting.

3. **Containerization**
   Add a `Dockerfile` for consistent deployment across environments. Publish to a container registry for Kubernetes/ECS deployment.

4. **Testing**
   Unit tests for `ms_to_srt()`, `build_srt()`, `verify_api_key()`. Integration tests with mocked AssemblyAI responses. CI pipeline via GitHub Actions.
