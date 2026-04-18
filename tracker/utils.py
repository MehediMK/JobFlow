import base64
import csv
import hashlib
import hmac
import io
import secrets
import struct
from datetime import datetime, time, timedelta

from cryptography.fernet import Fernet
from django.conf import settings
from django.core.mail import send_mail
from django.core.signing import BadSignature, SignatureExpired, TimestampSigner
from django.http import HttpResponse
from django.template.loader import render_to_string
from django.utils import timezone
from openpyxl import Workbook
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from .models import ActivityLog, Reminder


def get_cipher():
    return Fernet(settings.ENCRYPTION_KEY)


def encrypt_password(raw_password):
    return get_cipher().encrypt(raw_password.encode()).decode()


def decrypt_password(encrypted_password):
    if not encrypted_password:
        return ''
    return get_cipher().decrypt(encrypted_password.encode()).decode()


def generate_totp_secret():
    return base64.b32encode(secrets.token_bytes(10)).decode().rstrip('=')


def _totp_token(secret, for_time=None, interval=30):
    if not secret:
        return ''
    if for_time is None:
        for_time = timezone.now().timestamp()
    padded = secret + '=' * (-len(secret) % 8)
    key = base64.b32decode(padded, casefold=True)
    counter = int(for_time // interval)
    digest = hmac.new(key, struct.pack('>Q', counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = (struct.unpack('>I', digest[offset:offset + 4])[0] & 0x7FFFFFFF) % 1000000
    return f'{code:06d}'


def verify_totp(secret, code):
    now = timezone.now().timestamp()
    return any(code == _totp_token(secret, now + offset) for offset in (-30, 0, 30))


def build_email_verification_token(user):
    return TimestampSigner().sign(str(user.pk))


def verify_email_verification_token(token, max_age=60 * 60 * 24):
    try:
        user_id = TimestampSigner().unsign(token, max_age=max_age)
        return int(user_id)
    except (BadSignature, SignatureExpired, ValueError):
        return None


def log_activity(user, action, application=None, description=''):
    ActivityLog.objects.create(user=user, application=application, action=action, description=description)


def sync_application_reminders(application):
    lead_days = getattr(settings, 'REMINDER_LEAD_DAYS', 3)
    reminder_specs = []
    if application.deadline_date:
        reminder_specs.append(
            ('deadline', f'Deadline approaching for {application.company_name}', datetime.combine(application.deadline_date - timedelta(days=lead_days), time(9, 0)))
        )
    if application.follow_up_date:
        reminder_specs.append(
            ('follow_up', f'Follow up with {application.company_name}', datetime.combine(application.follow_up_date, time(10, 0)))
        )
    if application.interview_date:
        reminder_specs.append(
            ('interview', f'Interview preparation for {application.company_name}', datetime.combine(application.interview_date, time(8, 30)))
        )

    existing = {rem.reminder_type: rem for rem in application.reminders.filter(reminder_type__in=['deadline', 'follow_up', 'interview'])}
    seen = set()
    for reminder_type, title, dt in reminder_specs:
        aware_dt = timezone.make_aware(dt, timezone.get_current_timezone()) if timezone.is_naive(dt) else dt
        reminder = existing.get(reminder_type)
        if reminder:
            reminder.title = title
            reminder.remind_at = aware_dt
            reminder.save(update_fields=['title', 'remind_at', 'updated_at'])
        else:
            Reminder.objects.create(
                user=application.user,
                application=application,
                title=title,
                reminder_type=reminder_type,
                remind_at=aware_dt,
            )
        seen.add(reminder_type)
    for reminder_type, reminder in existing.items():
        if reminder_type not in seen:
            reminder.delete()


def send_due_reminders():
    pending = Reminder.objects.select_related('user', 'application').filter(
        is_completed=False,
        sent_at__isnull=True,
        remind_at__lte=timezone.now(),
        user__profile__notify_email=True,
    )
    sent_count = 0
    for reminder in pending:
        context = {'reminder': reminder}
        message = render_to_string('emails/reminder_email.txt', context)
        send_mail(
            subject=f'Reminder: {reminder.title}',
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[reminder.user.email],
            fail_silently=True,
        )
        reminder.sent_at = timezone.now()
        reminder.save(update_fields=['sent_at'])
        sent_count += 1
    return sent_count


def export_applications_csv(queryset):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="applications.csv"'
    writer = csv.writer(response)
    writer.writerow(['Company', 'Job Title', 'Status', 'Priority', 'Location', 'Portal', 'Deadline', 'Follow Up'])
    for application in queryset:
        writer.writerow([
            application.company_name,
            application.job_title,
            application.get_status_display(),
            application.get_priority_display(),
            application.job_location,
            application.portal_name,
            application.deadline_date,
            application.follow_up_date,
        ])
    return response


def export_applications_excel(queryset):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = 'Applications'
    sheet.append(['Company', 'Job Title', 'Status', 'Priority', 'Portal', 'Location', 'Salary', 'Deadline', 'Notes'])
    for application in queryset:
        sheet.append([
            application.company_name,
            application.job_title,
            application.get_status_display(),
            application.get_priority_display(),
            application.portal_name,
            application.job_location,
            application.salary,
            application.deadline_date.isoformat() if application.deadline_date else '',
            application.notes,
        ])
    output = io.BytesIO()
    workbook.save(output)
    response = HttpResponse(
        output.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = 'attachment; filename="applications.xlsx"'
    return response


def export_applications_pdf(queryset):
    output = io.BytesIO()
    pdf = canvas.Canvas(output, pagesize=A4)
    width, height = A4
    y = height - 50
    pdf.setTitle('Applications Report')
    pdf.setFont('Helvetica-Bold', 16)
    pdf.drawString(40, y, 'Job Applications Report')
    y -= 30
    pdf.setFont('Helvetica', 10)
    for application in queryset:
        lines = [
            f'{application.company_name} - {application.job_title}',
            f'Status: {application.get_status_display()} | Priority: {application.get_priority_display()} | Deadline: {application.deadline_date or "N/A"}',
            f'Portal: {application.portal_name or "N/A"} | Location: {application.job_location or "N/A"}',
        ]
        for line in lines:
            pdf.drawString(40, y, line[:110])
            y -= 16
            if y < 60:
                pdf.showPage()
                pdf.setFont('Helvetica', 10)
                y = height - 50
        y -= 8
    pdf.save()
    response = HttpResponse(output.getvalue(), content_type='application/pdf')
    response['Content-Disposition'] = 'attachment; filename="applications.pdf"'
    return response
