# Meeting Notes

Local Windows sidecar plus Oracle ARM backend for recording video meeting audio and turning it into rolling transcripts, notes, and action items.

This repo is intentionally independent from any existing project in `C:\home\dev`.

Before using it in real meetings, make sure recording and transcription are allowed by the meeting participants, your company policy, and the jurisdictions involved.

## What v1 Does

- Captures default Windows speaker output through WASAPI loopback.
- Captures the default microphone as a separate track.
- Sends JSON metadata as WebSocket text frames and raw PCM16 audio as WebSocket binary frames.
- Runs `faster-whisper` on the backend, with CPU `int8` defaults suitable for an Oracle ARM server.
- Maintains a rolling transcript and rule-based notes/action items.

## What v1 Does Not Do Yet

- It records device-level loopback, not process-specific Teams/Zoom/Chrome audio.
- Speaker separation is only `system` versus `mic`.
- It transcribes buffered windows, not a full diarized meeting timeline.

Process-specific loopback belongs in v2. The Windows application/process loopback API is the right path for that, but the device-level loopback version is much faster to get running.

## Repo Layout

```text
meeting-notes/
  sidecar/
    app.py
    audio_capture.py
    config.py
    ws_client.py
    requirements.txt

  backend/
    app.py
    notes.py
    schemas.py
    session.py
    transcriber.py
    requirements.txt

  docs/
    protocol.md
```

## Backend: Oracle ARM

```powershell
cd C:\home\dev\meeting-notes\backend
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt

$env:MN_MODEL_SIZE = "small"
$env:MN_COMPUTE_TYPE = "int8"
$env:MN_DEVICE = "cpu"
$env:MN_TRANSCRIBE_WINDOW_MS = "5000"

.\.venv\Scripts\python -m uvicorn app:app --host 0.0.0.0 --port 8000
```

On Linux/Oracle, use the same commands with `python3` and `source .venv/bin/activate`.

Useful environment variables:

| Variable | Default | Meaning |
| --- | --- | --- |
| `MN_MODEL_SIZE` | `small` | faster-whisper model name or local model path |
| `MN_DEVICE` | `cpu` | faster-whisper device |
| `MN_COMPUTE_TYPE` | `int8` | CTranslate2 compute type |
| `MN_LANGUAGE` | `en` | Language hint; set empty for auto-detect |
| `MN_TRANSCRIBE_WINDOW_MS` | `5000` | Buffered audio duration before transcription |
| `MN_OUTPUT_DIR` | `outputs` | Directory for exported session files |
| `MN_EXPORT_RETENTION_DAYS` | `365` | Delete exported session folders older than this many days; `0` disables age pruning |
| `MN_EXPORT_MAX_SESSIONS` | `200` | Keep at most this many exported session folders; `0` disables count pruning |
| `MN_BACKEND_HOST_PORT` | `18000` | Host localhost port used by Docker so nginx can reverse proxy without exposing the backend publicly |

Health check:

```text
GET http://ORACLE_IP:8000/health
```

### Backend: Oracle Ubuntu Docker

The repo includes [backend/Dockerfile](C:/home/dev/meeting-notes/backend/Dockerfile) and [docker-compose.yml](C:/home/dev/meeting-notes/docker-compose.yml) for a CPU-only `faster-whisper` deployment on Oracle ARM.

Preferred path on the Oracle server:

```bash
cd /path/to/meeting-notes
cp .env.example .env
# edit .env for your server
docker compose up -d --build
```

Check:

```bash
docker compose ps
curl http://127.0.0.1:18000/health
```

Override defaults by exporting environment variables before `docker compose up`:

```bash
export MN_MODEL_SIZE=small
export MN_DEVICE=cpu
export MN_COMPUTE_TYPE=int8
export MN_LANGUAGE=en
export MN_TRANSCRIBE_WINDOW_MS=5000
export MN_EXPORT_RETENTION_DAYS=365
export MN_EXPORT_MAX_SESSIONS=200
export OMP_NUM_THREADS=8
export MN_EXPORTS_HOST_DIR=/srv/meeting-notes/outputs
export MN_BACKEND_HOST_PORT=18000
```

The compose file uses:

- a named Docker volume for model cache
- a host bind mount for exports so you can inspect files directly on the Oracle host

```text
meeting-notes-models:/models-cache
${MN_EXPORTS_HOST_DIR:-./outputs}:/outputs
```

This means exported notes live on the host filesystem instead of an opaque Docker volume. On Oracle, a typical choice is:

```text
/srv/meeting-notes/outputs
```

The backend no longer needs to occupy public host port `8000`. With the current compose file it binds only to:

```text
127.0.0.1:${MN_BACKEND_HOST_PORT:-18000} -> container:8000
```

That keeps it reachable by host `nginx` while avoiding clashes with other public-facing services.

Example `nginx` reverse proxy with TLS:

```nginx
server {
    listen 80;
    server_name notes-api.example.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name notes-api.example.com;

    ssl_certificate /etc/letsencrypt/live/notes-api.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/notes-api.example.com/privkey.pem;

    location /ws/audio {
        proxy_pass http://127.0.0.1:18000/ws/audio;
        proxy_http_version 1.1;
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }

    location / {
        proxy_pass http://127.0.0.1:18000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

A ready-to-edit copy also lives in [docs/nginx/meeting-notes.conf](C:/home/dev/meeting-notes/docs/nginx/meeting-notes.conf).

Then the Windows sidecar can point at:

```text
wss://notes-api.example.com/ws/audio
```

If you prefer plain `docker build` / `docker run`, use:

```bash
docker build -f backend/Dockerfile -t meeting-notes-backend:cpu .

docker run -d \
  --name meeting-notes-backend \
  --restart unless-stopped \
  -p 127.0.0.1:18000:8000 \
  -e MN_MODEL_SIZE=small \
  -e MN_DEVICE=cpu \
  -e MN_COMPUTE_TYPE=int8 \
  -e MN_TRANSCRIBE_WINDOW_MS=5000 \
  -e MN_OUTPUT_DIR=/outputs \
  -e MN_EXPORT_RETENTION_DAYS=365 \
  -e MN_EXPORT_MAX_SESSIONS=200 \
  -e OMP_NUM_THREADS=8 \
  -v meeting-notes-models:/models-cache \
  -v /srv/meeting-notes/outputs:/outputs \
  meeting-notes-backend:cpu
```

If you build from a non-ARM machine and then push the image to Oracle, build for `linux/arm64` explicitly:

```bash
docker buildx build --platform linux/arm64 -f backend/Dockerfile -t meeting-notes-backend:cpu .
```

## Sidecar: Windows

```powershell
cd C:\home\dev\meeting-notes\sidecar
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt

.\.venv\Scripts\python app.py --list-devices

.\.venv\Scripts\python app.py `
  --ws-url ws://ORACLE_IP:8000/ws/audio `
  --session-id demo-session-001 `
  --chunk-ms 1000
```

By default the sidecar uses:

- The default WASAPI loopback device for `system`.
- The default microphone input for `mic`.
- The device default sample rate/channel count.

You can force devices or audio format:

```powershell
.\.venv\Scripts\python app.py `
  --ws-url ws://ORACLE_IP:8000/ws/audio `
  --system-device-index 19 `
  --mic-device-index 2 `
  --sample-rate 16000 `
  --channels 1
```

Environment variables are also supported:

| Variable | Default | Meaning |
| --- | --- | --- |
| `MN_WS_URL` | `ws://YOUR_ORACLE_IP:8000/ws/audio` | Backend WebSocket URL |
| `MN_SESSION_ID` | timestamped session id | Session id |
| `MN_CHUNK_MS` | `1000` | Sidecar send chunk size |
| `MN_SAMPLE_RATE` | empty | Optional forced capture sample rate |
| `MN_CHANNELS` | empty | Optional forced channel count |
| `MN_SYSTEM_DEVICE_INDEX` | empty | Optional forced loopback device index |
| `MN_MIC_DEVICE_INDEX` | empty | Optional forced mic device index |

## Output

The sidecar prints partial transcript segments received from the backend. The backend also exposes:

```text
GET /sessions
GET /sessions/{session_id}/transcript
GET /sessions/{session_id}/notes
GET /sessions/{session_id}/exports
GET /sessions/{session_id}/exports/{export_name}
```

For each session, the backend also writes:

```text
{MN_OUTPUT_DIR}/{sanitized-session-id}/transcript.json
{MN_OUTPUT_DIR}/{sanitized-session-id}/notes.json
{MN_OUTPUT_DIR}/{sanitized-session-id}/notes.md
```

Example inside Docker:

```text
/outputs/demo-session-001/transcript.json
/outputs/demo-session-001/notes.json
/outputs/demo-session-001/notes.md
```

The sidecar terminal currently shows:

- partial transcript segments
- rolling summary
- recent action items

Download examples from your laptop once nginx is proxying the backend:

```text
https://notes-api.example.com/sessions/demo-session-001/exports
https://notes-api.example.com/sessions/demo-session-001/exports/notes.json
https://notes-api.example.com/sessions/demo-session-001/exports/notes.md
```

More copy-paste examples for `curl` and PowerShell are in [docs/download-examples.md](C:/home/dev/meeting-notes/docs/download-examples.md).

Disk usage behavior:

- The backend stores transcript and notes only. It does not persist raw audio.
- Export cleanup runs automatically after each export write.
- By default it deletes session folders older than 365 days.
- By default it also keeps only the most recent 200 session folders.
- Set `MN_EXPORT_RETENTION_DAYS=0` or `MN_EXPORT_MAX_SESSIONS=0` only if you explicitly want unbounded retention.

`docker compose` reads `.env` automatically. Start from [`.env.example`](C:/home/dev/meeting-notes/.env.example) and set `MN_EXPORTS_HOST_DIR` to a real host path on the Oracle server.

## v2 Direction

- Replace device-level loopback with process-specific loopback for Teams, Zoom, Chrome, and Edge.
- Add rolling windows with overlap and transcript de-duplication.
- Persist transcript and notes to Markdown/JSON.
- Add an optional local UI for session control and exports.
