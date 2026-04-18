# JobFlow Pro

JobFlow Pro is a Django 5.2 job application tracking system for candidates who want to organize applications, documents, reminders, credentials, and interview preparation in one place.

## Features

- User registration, login, password reset, email verification, and optional TOTP-based 2FA
- Job application management with status, priority, portal, deadline, follow-up, salary, rating, referral, and tags
- Dashboard with pipeline metrics, reminders, follow-up visibility, and interview preparation analytics
- Kanban and calendar views for managing application flow
- Encrypted portal credential storage using `cryptography`
- Document management for resumes, cover letters, certificates, portfolios, and other attachments
- Reusable resume and cover letter templates
- Interview notes, practice tracking, and interview preparation pages
- Reminder system for deadlines, interviews, follow-ups, and document expiry
- CSV, Excel, and PDF export for application data

## Tech Stack

- Python 3.13
- Django 5.2
- SQLite
- `cryptography`
- `openpyxl`
- `reportlab`

## Project Structure

```text
job_application/
|-- config/         # Django project settings and root URL config
|-- tracker/        # Main application logic, models, views, forms, utils
|-- templates/      # Shared and app templates
|-- static/         # Static CSS/JS/assets
|-- manage.py
|-- requirements.txt
`-- db.sqlite3      # Local development database
```

## Setup

### 1. Create and activate a virtual environment

Windows PowerShell:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

### 2. Install dependencies

```powershell
pip install -r requirements.txt
```

### 3. Apply migrations

```powershell
python manage.py migrate
```

### 4. Create a superuser

```powershell
python manage.py createsuperuser
```

### 5. Run the development server

```powershell
python manage.py runserver
```

Open `http://127.0.0.1:8000/`.

## Development Notes

- Default database: SQLite
- Time zone: `Asia/Dhaka`
- Email backend in development: Django console backend
- Uploaded files are stored in the local `media/` directory
- Reminder emails can be triggered manually through a management command

## Reminder Command

Run due reminders manually:

```powershell
python manage.py send_due_reminders
```

## Running Tests

```powershell
python manage.py test
```

## Key App Modules

- [tracker/models.py](D:\Mehedi\Django\job_application\tracker\models.py:1): data models for applications, reminders, documents, templates, credentials, interview notes, and activity logs
- [tracker/views.py](D:\Mehedi\Django\job_application\tracker\views.py:1): dashboard, CRUD views, exports, reminders, and interview features
- [tracker/forms.py](D:\Mehedi\Django\job_application\tracker\forms.py:1): forms for applications, reminders, profile, templates, credentials, and interview notes
- [tracker/utils.py](D:\Mehedi\Django\job_application\tracker\utils.py:1): encryption helpers, exports, activity logging, reminder syncing, and TOTP utilities

## Security Notes

- Portal passwords are stored encrypted, not plain text
- `SECRET_KEY` is currently hardcoded in development settings and should be moved to environment variables before production use
- `DEBUG` is enabled in the current local setup and must be disabled in production
- Production deployments should use a proper email backend, media/static setup, and a stronger database than local SQLite if needed

## Future Improvements

- Job URL import and job description parsing
- Resume-to-job match analysis
- Advanced funnel analytics
- Offer comparison tools
- Better interview preparation workflows

## License

This project currently does not define a license. Add one before public distribution.
