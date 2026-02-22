# Security Management

A comprehensive security scanning platform that automatically detects vulnerabilities, generates AI-powered remediation, and integrates with GitHub Pull Requests.

## Prerequisites

- **Docker** and **Docker Compose** installed and running
- **GitHub Personal Access Token** (with `repo` scope) — for PR scanning

## Quick Start

### 1. Configure Environment
Edit `backend/.env` and set your tokens:
```env
GITHUB_TOKEN=ghp_your_token_here
GITHUB_WEBHOOK_SECRET=your-secret-here
GEMINI_API_KEY=your-gemini-key-here
```

### 2. Start the Stack
```bash
./start_all.sh
```

### 3. Access Points
| Service | URL |
|---|---|
| Frontend UI | [http://localhost:5173](http://localhost:5173) |
| Backend API | [http://localhost:8000](http://localhost:8000) |
| API Docs | [http://localhost:8000/docs](http://localhost:8000/docs) |

## Monitoring Logs
```bash
./view_logs.sh
```
Press `Ctrl+C` to stop.

## GitHub Webhook Setup (PR Scanning)

When a Pull Request is opened or updated on a connected repo, the app automatically runs a full security scan and posts the results as a **commit status** on the PR.

### Setup Steps

1. **Expose your backend** using [ngrok](https://ngrok.com/):
   ```bash
   ngrok http 8000
   ```
   Copy the `https://` URL (e.g., `https://abc123.ngrok.io`).

2. **Register the webhook** in your GitHub repo:
   - Go to **Settings → Webhooks → Add webhook**
   - **Payload URL**: `https://abc123.ngrok.io/webhook/github`
   - **Content type**: `application/json`
   - **Secret**: Same value as `GITHUB_WEBHOOK_SECRET` in `.env`
   - **Events**: Select **Pull requests**
   - Click **Add webhook**

3. **Open a PR** on that repo — the scan will trigger automatically.

4. **Check results**:
   - View logs: `./view_logs.sh`
   - Check the PR's commit status on GitHub
   - View scan results: `http://localhost:8000/scans`

## Manual Scan
Trigger a scan for any repo URL via the API:
```bash
curl -X POST "http://localhost:8000/scan?repo_url=https://github.com/owner/repo"
```

## Troubleshooting

**Backend won't start?** Run components individually:
```bash
cd backend && ./start_manual_stack.sh   # Backend
cd frontend && docker-compose up -d --build  # Frontend
```

**Webhook not triggering?** Check:
- ngrok is running and URL matches webhook config
- `GITHUB_WEBHOOK_SECRET` matches in both `.env` and GitHub
- Worker logs: `./view_logs.sh`
