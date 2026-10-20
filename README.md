# Fund Tracker: Backend

REST API for the Fund Management & Monthly Payment Tracker. Members submit monthly payment records, the admin approves or rejects them, and the group fund is always calculated from approved payments.

This API only records contributions. It does not move money or connect to any payment gateway.

## Tech stack

- Python 3.11 or 3.12, FastAPI
- SQLAlchemy 2 with SQLite
- Pydantic v2 for validation
- JWT authentication (PyJWT) and Argon2 password hashing
- pytest for tests

## Features

- Login with email or username and password
- Two roles: **admin** and **member**. There is no public sign-up, and the admin creates all member accounts
- Members submit one payment per month and year (bKash, Bank Transfer or In Person)
- Admin approves or rejects submissions, with an optional rejection reason
- Fund balance, dashboards and monthly reports calculated from approved payments
- Admin can change the monthly contribution (default ৳3,000)

## Setup (Windows PowerShell)

```powershell
cd backend

python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

Copy-Item .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

If PowerShell blocks the activate script, run this once and try again:

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

Open `.env` and paste the printed value after `SECRET_KEY=`.

### Environment variables

| Variable | Default | Description |
|---|---|---|
| `SECRET_KEY` | required, 32+ characters | Signs login tokens. Keep it private |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `60` | How long a login lasts |
| `FRONTEND_ORIGIN` | `http://localhost:5173` | The only origin allowed by CORS. Must match the frontend URL exactly, with no trailing slash |
| `DEFAULT_MONTHLY_CONTRIBUTION` | `3000` | Starting amount in BDT. Change it later in Fund Settings |
| `DATABASE_URL` | `fund_tracker.db` in this folder | SQLite database location |

## Create the admin account

The admin can only be created from the command line:

```powershell
python -m scripts.create_admin
```

It asks for a name, username, email and password (at least 8 characters).

## Run

```powershell
python -m uvicorn app.main:app --reload
```

- API: http://127.0.0.1:8000
- Interactive docs: http://127.0.0.1:8000/docs
- Health check: http://127.0.0.1:8000/api/health

Always run this from the `backend` folder. The app is `app.main:app`, not `main:app`.

## API

All routes are under `/api`. Everything except `login` and `health` needs the header `Authorization: Bearer <token>`.

| Method | Route | Who | Purpose |
|---|---|---|---|
| GET | `/health` | public | Server check |
| POST | `/auth/login` | public | `{identifier, password}` returns token and user |
| GET | `/auth/me` | any user | Current user |
| POST | `/auth/change-password` | any user | `{current_password, new_password}` |
| GET | `/member/dashboard` | member | Contribution, totals, fund balance, recent payments |
| POST | `/member/payments` | member | `{month, year, payment_method}` |
| GET | `/member/payments` | member | Own payment history only |
| GET | `/member/monthly-status?year=` | member | Paid, pending and unpaid months |
| GET | `/admin/members` | admin | List members with totals |
| POST | `/admin/members` | admin | `{name, username, email, password}` |
| DELETE | `/admin/members/{id}` | admin | Permanently delete a member and their payments |
| GET | `/admin/payments` | admin | Filters: `user_id`, `month`, `year`, `status`, `q` |
| POST | `/admin/payments/{id}/approve` | admin | Pending to approved |
| POST | `/admin/payments/{id}/reject` | admin | `{reason?}` pending to rejected |
| GET | `/admin/dashboard?month=&year=` | admin | Fund and monthly statistics |
| GET | `/admin/monthly-report?month=&year=` | admin | Status of every member for a month |
| GET | `/admin/fund-settings` | admin | Current monthly contribution |
| PUT | `/admin/fund-settings` | admin | `{monthly_contribution_amount}` (greater than 0) |

Status codes: 401 not logged in, 403 wrong role, 404 not found, 409 duplicate or already reviewed, 422 invalid input.

## Business rules

- **One active payment per member per month and year.** A pending or approved payment blocks another one. A rejected payment does not, so the member can submit again. This is enforced by the backend and by a SQLite partial unique index.
- **The amount is set by the server** from Fund Settings and frozen on each payment. Changing the setting never changes existing payments. Requests that include `amount` or `status` are rejected.
- **Fund balance** is the sum of approved payments, calculated on demand and never stored as a number.
- **Approve and reject are atomic.** A single `UPDATE ... WHERE status = 'pending'` means a payment can be reviewed only once, even if two admins click at the same time.
- **Deleting a member is permanent.** The member and all of their payments are removed, so the fund total drops by their approved amount.
- An admin cannot delete their own account, and the delete route only works on member accounts.
- **Monthly report:** Paid means an approved payment exists, Pending means a pending payment exists, and Unpaid means neither. Rejected history is shown beside Unpaid.
- Amounts are whole taka (integers).

## Tests

```powershell
python -m pytest -q
```

The 23 tests use a temporary SQLite file and never touch your real database. They cover login, role separation, privacy between members, amount tampering, duplicate prevention, approval, rejection and resubmission, fund totals, settings changes, monthly reports and member deletion.

## Security notes

- Passwords are hashed with Argon2id. Plaintext passwords are never stored.
- Tokens expire (default 60 minutes). The role and active status are re-read from the database on every request.
- Admin routes need the admin role. Member routes always filter by the logged-in user's id.
- Login errors are generic and take similar time whether or not the user exists.
- CORS allows only `FRONTEND_ORIGIN`. Secrets come from environment variables, and `.env` and `*.db` should stay out of Git.
- Not included: login rate limiting and password reset by email. Use HTTPS in production and consider rate limiting at the reverse proxy.

## Deployment notes

- Set `SECRET_KEY` and `FRONTEND_ORIGIN` in the host's environment settings.
- SQLite is a single file, so the host needs a persistent disk or volume. Otherwise data is lost on every deploy.
- Start command: `uvicorn app.main:app --host 0.0.0.0 --port 8000`
- Deploy the backend first, deploy the frontend with the backend URL, then set `FRONTEND_ORIGIN` and restart the backend.

## Project structure

```text
backend/
├── app/
│   ├── main.py            # app, CORS, routers
│   ├── config.py          # environment settings
│   ├── database.py        # engine, sessions, SQLite settings, seeding
│   ├── models.py          # User, Payment, FundSettings
│   ├── schemas.py         # request and response models
│   ├── security.py        # password hashing, JWT
│   ├── dependencies.py    # current user, require_admin / require_member
│   ├── routers/           # auth.py, member.py, admin.py
│   └── services/          # payments.py (rules), reports.py (summaries)
├── scripts/create_admin.py
├── tests/
├── requirements.txt
└── .env.example
```
