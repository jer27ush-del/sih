# AICTE FDR Management Portal

A web portal for managing Fixed Deposit Receipts (FDRs) submitted by institutions: registration,
document upload, scrutiny queries, verification, renewal, release requests, reports, audit logs,
and automated 90/60/30-day maturity reminder emails.

> **Status: SIH prototype.** This is not an officially approved AICTE system and it is not connected
> to any bank. Verification here means a recorded review by a portal user, not confirmation from a bank.

## Architecture

One Django service runs everything:

```
Browser
  └── Django web service (one folder, one deployment)
        ├── /api/...      JSON API used by the React screens
        ├── /            React web interface (built into frontend/dist)
        ├── /admin/      Django admin
        ├── PostgreSQL   all data (Render-managed in production; SQLite locally)
        └── private disk FDR documents, never publicly served

Daily cron job (Render) ──> python manage.py send_fdr_reminders ──> SMTP email provider
```

## Folder structure

```
aicte-fdr-portal/
├── manage.py               Django command-line entry point
├── build.sh                Build script (used by Render; bash)
├── render.yaml             Render Blueprint: web service, PostgreSQL, daily reminder cron job
├── requirements.txt        Python packages
├── .env.example            Template for local settings (copy to .env)
├── config/                 Settings, URL routes, WSGI entry, React app view
├── accounts/               Users, login, password rules, user management
├── institutions/           Institution records
├── fdrs/                   FDRs, documents, verification, queries, renewals, releases, CSV import
├── reminders/              Maturity reminder rules, email sending, delivery history
├── notifications/          In-portal notifications
├── audit/                  Append-only audit log
├── portal/                 Settings, dashboard, reports, demo-data command
├── common/                 Error format, permission matrix, pagination
└── frontend/               React + TypeScript web interface (Vite)
```

## Requirements

- Windows 10/11 with PowerShell
- Python 3.11 or newer (download from python.org; tick "Add python.exe to PATH")
- Node.js 20 or newer (for building the web interface)
- Git (for GitHub and Render)

## Run it locally on Windows (PowerShell)

Open PowerShell in the project folder (the folder that contains `manage.py`).

**1. Create and activate a virtual environment**

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If PowerShell says running scripts is disabled, run this once (it only affects your user account), then activate again:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

**2. Install Python packages**

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

**3. Create your local settings file**

```powershell
Copy-Item .env.example .env
```

Open `.env` in VS Code. For local use the defaults are fine. Do not put real passwords in `.env`, and never commit it.

**4. Create the database and an administrator account**

```powershell
python manage.py migrate
python manage.py createsuperuser
```

Optional demo data (fictional institutions, accounts with password `demo123`, sample FDRs):

```powershell
python manage.py seed_demo
```

**5. Build the web interface**

```powershell
cd frontend
npm install
npm run build
cd ..
```

**6. Start the portal**

```powershell
python manage.py runserver
```

Open http://localhost:8000 and sign in. The administrator account is the one you created in step 4.
Demo accounts (after `seed_demo`): `institution@demo.test`, `officer@demo.test`, `admin@demo.test`,
`auditor@demo.test`, all with password `demo123`.

**Developer mode (optional):** to edit the React screens with live reload, run the Django server in one
terminal (`python manage.py runserver`) and `npm run dev` in `frontend` in a second terminal, then open
http://localhost:5173.

### Common Windows problems

| Problem | Fix |
|---|---|
| `Activate.ps1 cannot be loaded` | Run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, then activate again |
| `'python' is not recognized` | Reinstall Python with "Add to PATH", or use `py` instead |
| `requirements.txt` not found | You are in the wrong folder; `cd` to the folder that contains `manage.py` |
| Web page says "interface has not been built" | Run step 5 (`npm install`, `npm run build`) |
| Port 8000 already in use | Stop the other program, or run `python manage.py runserver 8001` |

## Tests

```powershell
python manage.py test
python manage.py makemigrations --check --dry-run
python manage.py check
```

Tests use an in-memory email backend, so no real email is sent. The suite covers permissions,
institution isolation, the FDR workflow, document validation, the reminder rules (90/60/30 days,
leap years, idempotency, retries, dry-run) and the reminder history access rules.

Frontend checks (from the `frontend` folder): `npm run build`, `npx vitest run`.

## Maturity reminders (90 / 60 / 30 days)

Command:

```powershell
python manage.py send_fdr_reminders                                  # today (Asia/Kolkata)
python manage.py send_fdr_reminders --date 2026-10-17 --dry-run      # test a date; sends nothing
python manage.py send_fdr_reminders --date 2026-10-17                # live run for that date
```

**Testing without sending email:** always use `--dry-run` first. It prints what would be sent and records nothing.
Use `--date` to test a chosen day. For example, with the demo data, DEMO-FDR-1001 matures on 15 Jan 2027,
so `--date 2026-10-17` is exactly 90 days before maturity.

**Rules**

- A reminder is due on the exact day an FDR is 90, 60 or 30 calendar days from its maturity date.
- Only FDRs with status *Active* or *Nearing Maturity* are reminded. Others (for example Matured, Under Verification, Released) are not.
- The recipient is the institution's contact email. Missing or invalid addresses are recorded as *skipped*; they are retried after the address is fixed.
- Each reminder is recorded once per FDR, interval and maturity date. Running the command repeatedly never sends a successful reminder again.
- Failed sends are recorded with a short, password-free error message and retried on later runs, up to 5 attempts.
- *Accepted by mail server* means the mail server accepted the message. It does not prove the institution received or read it.
- Reminder history is visible to administrators and auditors at `/api/reminders/`.

**Schedule:** `render.yaml` defines a cron job that runs every day at 03:30 UTC (09:00 India time).

## Email configuration

Set these in `.env` (local) or in the Render dashboard (production):

| Variable | Example | Notes |
|---|---|---|
| `EMAIL_BACKEND` | `django.core.mail.backends.smtp.EmailBackend` | Console backend locally (prints emails) |
| `EMAIL_HOST` | `smtp.example.com` | Your SMTP provider |
| `EMAIL_PORT` | `587` | 587 with TLS, or 465 with SSL |
| `EMAIL_HOST_USER` | `portal@example.com` | SMTP login |
| `EMAIL_HOST_PASSWORD` | (secret) | Use the provider's app password, not your normal login |
| `EMAIL_USE_TLS` | `True` | Set `True` only for port 587 |
| `EMAIL_USE_SSL` | `False` | Set `True` only for port 465. Never enable TLS and SSL together |
| `DEFAULT_FROM_EMAIL` | `AICTE FDR Portal <no-reply@example.com>` | Sender shown to recipients |
| `PORTAL_BASE_URL` | `https://aicte-fdr-portal.onrender.com` | Link used inside emails |

Troubleshooting: *authentication failed* usually means the wrong password or an account that requires an app
password; *connection refused/timeout* usually means the wrong host or port, or a blocked port;
emails landing in spam are controlled by your domain's SPF, DKIM and DMARC settings with your provider.

## Deploy on Render (step by step)

**A. Put the project on GitHub**

```powershell
cd aicte-fdr-portal
git init
git add .
git commit -m "AICTE FDR portal"
```

Check first that secrets are not included: `git status --short --ignored` should not list `.env` as staged.
Then create an empty repository on github.com (no README), and run the two lines GitHub shows you, for example:

```powershell
git branch -M main
git remote add origin https://github.com/YOUR-USER/aicte-fdr-portal.git
git push -u origin main
```

**B. Create the services from the Blueprint**

1. Create a Render account at render.com and connect your GitHub account.
2. Click **New +** → **Blueprint**, choose your repository, and click **Apply** (or *Connect*).
3. Render creates the web service, the PostgreSQL database, the disk and the cron job from `render.yaml`.
4. Fill in the values Render asks for (variables marked `sync: false`): `PORTAL_BASE_URL` (you can enter a placeholder first), and the SMTP settings (`EMAIL_HOST`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `DEFAULT_FROM_EMAIL`). Set the same values on the cron job.
5. Wait for the first build to finish (it takes several minutes; it builds the React app and collects static files).

**C. After the first deploy**

1. Copy the service URL (for example `https://aicte-fdr-portal.onrender.com`).
2. Set `PORTAL_BASE_URL` to that URL on both the web service and the cron job, then redeploy.
3. Create an administrator. In the web service, open **Shell** and run `python manage.py createsuperuser`.
   Create the administrator account for real use with `createsuperuser`; it is the account you sign in with.
   Use the portal's user management to create institution and officer accounts.
4. Optional demo data (not for real records): `python manage.py seed_demo --force` in the Shell.
5. Open the URL and sign in. Check http://YOUR-URL/api/health/ shows `{"status": "ok"}`.

**D. Check the reminder job**

Open the cron job in Render, use **Trigger Run** once, and read its logs. Use `--dry-run` in the job
command temporarily if you want a safe first check.

**Notes on Render (verify on render.com before relying on them)**

- Plans and prices change. `render.yaml` uses a paid web plan because persistent disks need one. Free PostgreSQL databases expire, so use a paid database plan for real use.
- The persistent disk stores FDR documents. A service with a disk runs one instance and can have short pauses during deploys. Back up both the disk and the database.
- Render Shell availability depends on your plan.
- Render cron schedules use UTC.

## Environment variables (summary)

| Variable | Required in production | Purpose |
|---|---|---|
| `DJANGO_DEBUG` | yes (`False`) | Turns off debug pages |
| `DJANGO_SECRET_KEY` | yes | Signing key; generated automatically by Render |
| `DATABASE_URL` | yes | PostgreSQL connection string (set from the Render database) |
| `DJANGO_ALLOWED_HOSTS` | optional | Extra hostnames; Render's own hostname is added automatically |
| `PORTAL_BASE_URL` | yes | Public URL, used in emails |
| `PRIVATE_UPLOAD_ROOT` | yes | Private document folder (`/var/data/private_uploads` on Render) |
| `EMAIL_*`, `DEFAULT_FROM_EMAIL` | yes for reminders | SMTP settings |
| `DJANGO_SECURE_SSL_REDIRECT` | optional | `True` to force HTTPS redirects inside Django (Render already redirects HTTP to HTTPS) |
| `REQUIRE_MALWARE_SCAN` | optional | `True` refuses uploads until a scanner is connected |

## Security notes and limitations

- **Documents:** uploads are checked against an allowlist (PDF, PNG, JPEG), checked by their content, size-limited, given random storage names, and stored outside the public web folders. Every download is permission-checked and audited.
- **Integrity:** each document version stores a SHA-256 digest. A matching digest shows the file has not changed since upload. It does not prove the FDR is genuine or that a bank issued it. NIST SP 800-107 concerns the approved use of hash functions; this project does not claim NIST compliance.
- **Malware scanning is not connected.** Set `REQUIRE_MALWARE_SCAN=True` once a scanner is integrated; the integration point is `fdrs/documents.py`.
- **Two-factor sign-in is not implemented.** Use strong, unique administrator passwords.
- **Demo accounts** (`seed_demo`) use a known password and must not be used in real deployments; remove them from the database before use.
- **PDF export is not implemented;** CSV export is.
- **Email:** an accepted message is not proof of delivery or receipt.
- **Retention and deletion:** not yet defined. The project owner must confirm how long documents and audit records are kept.
- **Secrets:** rotate `DJANGO_SECRET_KEY` and the SMTP password if they were ever shared or committed.
- **Deployment check:** `python manage.py check --deploy` reports three warnings by design: HSTS for subdomains and preload would apply to the whole `onrender.com` domain, and HTTPS redirects are handled by Render at its edge.

## Research references and how they were used

| Reference | Relevant guidance | Implemented here | Check / limitation |
|---|---|---|---|
| AICTE Approval Process Handbook 2022–23 | Institutional context only | Workflow based on the project specification | Historical document; no rules were invented from it |
| NIST SP 800-107 | Use of approved hash functions | SHA-256 digest per document version | Integrity check only; not proof of authenticity |
| Django security documentation (5.1) | Production settings, secrets, cookies, CSRF | `DEBUG` off, secrets from environment, secure cookies, HSTS, `check --deploy` | Warnings explained above |
| Django password documentation | Built-in hashing and validation | Argon2 hashing, password validators, reset-token mechanism | Reset screen is not yet in the React interface |
| OWASP File Upload Cheat Sheet | Allowlist, size limits, content checks, private storage, authorized downloads | `fdrs/documents.py`, download permission and audit | Malware scanning not connected |

## Known gaps (honest list)

- The password-reset API exists, but the web screen for it is not built.
- The reminder history is available through the API; a screen for it is not built.
- Excel export is not implemented.
- Retention policy needs the project owner's decision.
- No real bank integration.
