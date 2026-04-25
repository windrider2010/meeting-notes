# Oracle Deployment Checklist

This checklist is for deploying the backend on an Oracle Ubuntu host with host `nginx` reverse proxying to the Docker container.

## 1. Host Preparation

- [ ] Confirm the Oracle VM is Ubuntu and reachable by SSH.
- [ ] Confirm Docker and Docker Compose are installed:

```bash
docker --version
docker compose version
```

- [ ] Confirm `nginx` is installed on the host:

```bash
nginx -v
```

- [ ] Pick a public DNS name for the backend, for example:

```text
notes-api.example.com
```

- [ ] Point that DNS record to the Oracle public IP.

## 2. Clone and Prepare the Repo

- [ ] Clone the repo:

```bash
cd /srv
git clone https://github.com/windrider2010/meeting-notes.git
cd meeting-notes
```

- [ ] Copy the runtime environment file:

```bash
cp .env.example .env
```

- [ ] Create the host export directory:

```bash
sudo mkdir -p /srv/meeting-notes/outputs
sudo chown -R $USER:$USER /srv/meeting-notes
```

## 3. Configure `.env`

- [ ] Set a real host export path:

```dotenv
MN_EXPORTS_HOST_DIR=/srv/meeting-notes/outputs
```

- [ ] Set the localhost host port used behind `nginx`:

```dotenv
MN_BACKEND_HOST_PORT=18000
```

- [ ] Keep or adjust model/runtime settings:

```dotenv
MN_MODEL_SIZE=small
MN_DEVICE=cpu
MN_COMPUTE_TYPE=int8
MN_LANGUAGE=en
MN_TRANSCRIBE_WINDOW_MS=5000
OMP_NUM_THREADS=8
```

- [ ] Keep or adjust retention settings:

```dotenv
MN_OUTPUT_DIR=/outputs
MN_EXPORT_RETENTION_DAYS=365
MN_EXPORT_MAX_SESSIONS=200
```

## 4. Start the Backend

- [ ] Build and start the container:

```bash
docker compose up -d --build
```

- [ ] Confirm the container is running:

```bash
docker compose ps
```

- [ ] Confirm the backend is healthy on localhost only:

```bash
curl http://127.0.0.1:18000/health
```

Expected result:

- HTTP 200
- JSON response with `ok: true`

## 5. Configure `nginx`

- [ ] Copy or adapt [nginx/meeting-notes.conf](C:/home/dev/meeting-notes/docs/nginx/meeting-notes.conf) into the host `nginx` config.
- [ ] Replace:
  - `notes-api.example.com`
  - certificate paths
  - `127.0.0.1:18000` if you changed `MN_BACKEND_HOST_PORT`

- [ ] Test the config:

```bash
sudo nginx -t
```

- [ ] Reload `nginx`:

```bash
sudo systemctl reload nginx
```

## 6. TLS Certificate

- [ ] Obtain a certificate for your domain.
- [ ] If using Certbot on Ubuntu:

```bash
sudo certbot --nginx -d notes-api.example.com
```

- [ ] Confirm HTTPS works:

```bash
curl -I https://notes-api.example.com/health
```

## 7. Backend Verification

- [ ] Confirm API access through `nginx`:

```bash
curl https://notes-api.example.com/health
curl https://notes-api.example.com/sessions
```

- [ ] Confirm WebSocket path is proxied:

```text
wss://notes-api.example.com/ws/audio
```

## 8. Windows Sidecar Verification

- [ ] On the Windows laptop, list devices:

```powershell
cd C:\home\dev\meeting-notes\sidecar
.\.venv\Scripts\python app.py --list-devices
```

- [ ] Start the sidecar against the Oracle backend:

```powershell
.\.venv\Scripts\python app.py `
  --ws-url wss://notes-api.example.com/ws/audio `
  --session-id demo-session-001 `
  --chunk-ms 1000
```

- [ ] Confirm the terminal shows:
  - transcript segments
  - rolling summary
  - recent action items

## 9. Export Verification

- [ ] Confirm export files appear on the Oracle host:

```bash
find /srv/meeting-notes/outputs -maxdepth 2 -type f
```

- [ ] Confirm the exports API works:

```bash
curl https://notes-api.example.com/sessions/demo-session-001/exports
curl -L https://notes-api.example.com/sessions/demo-session-001/exports/notes.json
curl -L https://notes-api.example.com/sessions/demo-session-001/exports/notes.md
```

- [ ] If downloading from Windows, use the examples in [download-examples.md](C:/home/dev/meeting-notes/docs/download-examples.md).

## 10. Disk and Retention Checks

- [ ] Check export directory size:

```bash
du -sh /srv/meeting-notes/outputs
```

- [ ] Check free disk space:

```bash
df -h
```

- [ ] Confirm retention settings are what you expect:

```bash
grep '^MN_EXPORT_' .env
```

Notes:

- The backend stores text outputs only.
- It does not persist raw audio.
- Cleanup runs automatically after each export write.

## 11. Operations

- [ ] View backend logs:

```bash
docker compose logs -f backend
```

- [ ] Restart after config changes:

```bash
docker compose up -d --build
```

- [ ] Stop the service:

```bash
docker compose down
```

## 12. Update and Rollback

- [ ] Pull updates:

```bash
git pull --ff-only
docker compose up -d --build
```

- [ ] If a deploy is bad, roll back to the last known good commit:

```bash
git log --oneline -n 5
git checkout <known-good-commit>
docker compose up -d --build
```

If you later want a safer rollback path, tag releases and deploy from tags instead of raw branch head.
