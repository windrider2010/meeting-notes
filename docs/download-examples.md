# Download Examples

These examples assume:

- `nginx` is proxying the backend as `https://notes-api.example.com`
- the session id is `demo-session-001`

## curl

Get export metadata:

```bash
curl https://notes-api.example.com/sessions/demo-session-001/exports
```

Download `notes.json` to the current directory:

```bash
curl -L https://notes-api.example.com/sessions/demo-session-001/exports/notes.json -o notes.json
```

Download `notes.md`:

```bash
curl -L https://notes-api.example.com/sessions/demo-session-001/exports/notes.md -o notes.md
```

## PowerShell

Get export metadata:

```powershell
Invoke-RestMethod https://notes-api.example.com/sessions/demo-session-001/exports
```

Download `transcript.json`:

```powershell
Invoke-WebRequest `
  -Uri https://notes-api.example.com/sessions/demo-session-001/exports/transcript.json `
  -OutFile .\transcript.json
```

Download `notes.md`:

```powershell
Invoke-WebRequest `
  -Uri https://notes-api.example.com/sessions/demo-session-001/exports/notes.md `
  -OutFile .\notes.md
```
