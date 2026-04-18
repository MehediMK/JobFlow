import json
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q, Avg
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import (
    ApplicationDocumentForm,
    ApplicationForm,
    ChecklistItemForm,
    InterviewNoteForm,
    PortalCredentialForm,
    ProfileForm,
    RegisterForm,
    ReminderForm,
    TemplateForm,
)
from .models import (
    Application,
    ApplicationDocument,
    ApplicationTemplate,
    InterviewNote,
    PortalCredential,
    Reminder,
)
from .utils import (
    build_email_verification_token,
    decrypt_password,
    export_applications_csv,
    export_applications_excel,
    export_applications_pdf,
    generate_totp_secret,
    log_activity,
    sync_application_reminders,
    verify_email_verification_token,
)


def landing(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    return render(request, 'tracker/landing.html')


def register(request):
    form = RegisterForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        login(request, user)
        log_activity(user, 'Account created', description='New account registration completed.')
        messages.success(request, 'Account created successfully.')
        return redirect('dashboard')
    return render(request, 'registration/register.html', {'form': form})


@login_required
def dashboard(request):
    applications = request.user.applications.all()
    now = timezone.localdate()
    week_end = now + timedelta(days=7)
    interviews = applications.filter(interview_date__range=[now, week_end])
    upcoming_deadlines = applications.filter(deadline_date__range=[now, week_end]).order_by('deadline_date')[:5]
    needs_followup = applications.filter(follow_up_date__isnull=False, follow_up_date__lte=week_end, status__in=[
        Application.STATUS_APPLIED, Application.STATUS_UNDER_REVIEW, Application.STATUS_TEST, Application.STATUS_INTERVIEW, Application.STATUS_FINAL
    ])
    recent_activity = request.user.activities.select_related('application')[:8]
    status_breakdown = list(applications.values('status').annotate(total=Count('id')).order_by())
    portal_breakdown = list(applications.exclude(portal_name='').values('portal_name').annotate(total=Count('id')).order_by('-total')[:5])

    # Calculate interview ready applications (those with interview notes)
    interview_ready_count = applications.filter(interview_notes__isnull=False).distinct().count()

    # Interview preparation stats
    interview_notes = InterviewNote.objects.filter(application__user=request.user)
    total_interview_questions = interview_notes.count()
    practiced_questions = interview_notes.filter(is_practiced=True).count()
    practice_percentage = round((practiced_questions / total_interview_questions * 100) if total_interview_questions > 0 else 0)
    avg_practice_rating = interview_notes.filter(user_rating__isnull=False).aggregate(
        avg_rating=Avg('user_rating')
    )['avg_rating'] or 0

    # Funnel analytics
    applied_count = applications.count()
    interviewed_count = applications.exclude(interview_date__isnull=True).count()
    offered_count = applications.filter(status=Application.STATUS_OFFERED).count()

    funnel_conversion_rate = round((interviewed_count / applied_count * 100) if applied_count > 0 else 0)
    offer_rate = round((offered_count / interviewed_count * 100) if interviewed_count > 0 else 0)

    # Funnel data for chart
    funnel_data = [
        {'status': 'Applied', 'count': applied_count},
        {'status': 'Interview', 'count': interviewed_count},
        {'status': 'Offered', 'count': offered_count}
    ]

    context = {
        'total_applications': applications.count(),
        'active_applications': applications.exclude(status__in=[Application.STATUS_REJECTED, Application.STATUS_OFFERED, Application.STATUS_WITHDRAWN]).count(),
        'offered_count': applications.filter(status=Application.STATUS_OFFERED).count(),
        'rejected_count': applications.filter(status=Application.STATUS_REJECTED).count(),
        'interviews_this_week': interviews.count(),
        'interview_ready_count': interview_ready_count,
        'upcoming_deadlines': upcoming_deadlines,
        'needs_followup': needs_followup[:5],
        'recent_activity': recent_activity,
        'urgent_reminders': request.user.reminders.filter(is_completed=False, remind_at__lte=timezone.now() + timedelta(days=3)).order_by('remind_at')[:6],
        'status_chart': json.dumps(status_breakdown),
        'portal_chart': json.dumps(portal_breakdown),
        'bookmarked_jobs': applications.filter(bookmarked=True)[:5],
        # New analytics data
        'funnel_data': json.dumps(funnel_data),
        'funnel_conversion_rate': funnel_conversion_rate,
        'offer_rate': offer_rate,
        'total_interview_questions': total_interview_questions,
        'practiced_questions': practiced_questions,
        'practice_percentage': practice_percentage,
        'avg_practice_rating': round(avg_practice_rating, 1),
    }
    return render(request, 'tracker/dashboard.html', context)


@login_required
def profile_view(request):
    form = ProfileForm(request.POST or None, instance=request.user.profile, user=request.user)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Profile updated.')
        return redirect('profile')
    return render(request, 'tracker/profile.html', {'form': form})


@login_required
def send_verification_email(request):
    token = build_email_verification_token(request.user)
    verification_link = request.build_absolute_uri(f'/verify-email/{token}/')
    request.user.email_user(
        'Verify your email',
        f'Open this link to verify your email address: {verification_link}',
    )
    messages.info(request, 'Verification email sent to the configured email address.')
    return redirect('profile')


def verify_email(request, token):
    user_id = verify_email_verification_token(token)
    if not user_id:
        raise Http404('Invalid or expired verification link.')
    from django.contrib.auth import get_user_model
    user = get_user_model().objects.filter(pk=user_id).first()
    if not user:
        raise Http404('Verification link does not match a valid user.')
    user.profile.email_verified = True
    user.profile.save(update_fields=['email_verified'])
    messages.success(request, 'Email verified successfully.')
    return redirect('login')


@login_required
def two_factor_setup(request):
    profile = request.user.profile
    if not profile.two_factor_secret:
        profile.two_factor_secret = generate_totp_secret()
        profile.save(update_fields=['two_factor_secret'])
    if request.method == 'POST':
        entered_code = request.POST.get('otp_code', '').strip()
        from .utils import verify_totp
        if verify_totp(profile.two_factor_secret, entered_code):
            profile.two_factor_enabled = True
            profile.save(update_fields=['two_factor_enabled'])
            messages.success(request, 'Two-factor authentication enabled.')
            return redirect('profile')
        messages.error(request, 'The code did not match. Try again.')
    return render(request, 'tracker/two_factor_setup.html', {'secret': profile.two_factor_secret})


@login_required
def disable_two_factor(request):
    profile = request.user.profile
    profile.two_factor_enabled = False
    profile.two_factor_secret = ''
    profile.save(update_fields=['two_factor_enabled', 'two_factor_secret'])
    messages.success(request, 'Two-factor authentication disabled.')
    return redirect('profile')


@login_required
def application_list(request):
    queryset = request.user.applications.all()
    search = request.GET.get('q', '').strip()
    status = request.GET.get('status', '').strip()
    priority = request.GET.get('priority', '').strip()
    tag = request.GET.get('tag', '').strip()
    if search:
        queryset = queryset.filter(
            Q(company_name__icontains=search)
            | Q(job_title__icontains=search)
            | Q(portal_name__icontains=search)
            | Q(job_location__icontains=search)
        )
    if status:
        queryset = queryset.filter(status=status)
    if priority:
        queryset = queryset.filter(priority=priority)
    if tag:
        queryset = queryset.filter(tags__name__iexact=tag)
    context = {
        'applications': queryset.distinct(),
        'status_choices': Application.STATUS_CHOICES,
        'priority_choices': Application.PRIORITY_CHOICES,
    }
    return render(request, 'tracker/application_list.html', context)


@login_required
def application_calendar(request):
    applications = request.user.applications.exclude(
        Q(deadline_date__isnull=True) & Q(interview_date__isnull=True) & Q(follow_up_date__isnull=True)
    )
    return render(request, 'tracker/application_calendar.html', {'applications': applications})


@login_required
def application_kanban(request):
    columns = [
        {
            'value': value,
            'label': label,
            'applications': request.user.applications.filter(status=value),
        }
        for value, label in Application.STATUS_CHOICES
    ]
    return render(request, 'tracker/application_kanban.html', {'columns': columns})


@login_required
def application_detail(request, pk):
    application = get_object_or_404(request.user.applications.prefetch_related('documents', 'credentials', 'reminders', 'checklist_items', 'interview_notes', 'tags'), pk=pk)
    credential_values = [(credential, decrypt_password(credential.encrypted_password)) for credential in application.credentials.all()]
    return render(request, 'tracker/application_detail.html', {'application': application, 'credential_values': credential_values})


@login_required
def application_create(request):
    form = ApplicationForm(request.POST or None, user=request.user)
    if request.method == 'POST' and form.is_valid():
        application = form.save()
        sync_application_reminders(application)
        log_activity(request.user, 'Application created', application, f'{application.company_name} / {application.job_title}')
        messages.success(request, 'Application saved.')
        return redirect(application)
    return render(request, 'tracker/application_form.html', {'form': form, 'title': 'Add Application'})


@login_required
def application_update(request, pk):
    application = get_object_or_404(request.user.applications, pk=pk)
    form = ApplicationForm(request.POST or None, instance=application, user=request.user)
    if request.method == 'POST' and form.is_valid():
        application = form.save()
        sync_application_reminders(application)
        log_activity(request.user, 'Application updated', application, f'Status: {application.get_status_display()}')
        messages.success(request, 'Application updated.')
        return redirect(application)
    return render(request, 'tracker/application_form.html', {'form': form, 'title': 'Edit Application'})


@login_required
def application_delete(request, pk):
    application = get_object_or_404(request.user.applications, pk=pk)
    if request.method == 'POST':
        log_activity(request.user, 'Application deleted', description=f'{application.company_name} / {application.job_title}')
        application.delete()
        messages.success(request, 'Application deleted.')
        return redirect('application_list')
    return render(request, 'tracker/confirm_delete.html', {'object': application, 'title': 'Delete application'})


@login_required
def application_duplicate(request, pk):
    source = get_object_or_404(request.user.applications, pk=pk)
    source_tags = list(source.tags.all())
    source.pk = None
    source.status = Application.STATUS_DRAFT
    source.submitted_date = None
    source.test_date = None
    source.interview_date = None
    source.follow_up_date = None
    source.deadline_date = None
    source.save()
    source.tags.set(source_tags)
    log_activity(request.user, 'Application duplicated', source, 'Created from existing application template.')
    messages.success(request, 'Application duplicated as a fresh draft.')
    return redirect(source)


def _filtered_applications(request):
    return request.user.applications.all().distinct()


@login_required
def export_csv(request):
    return export_applications_csv(_filtered_applications(request))


@login_required
def export_excel(request):
    return export_applications_excel(_filtered_applications(request))


@login_required
def export_pdf(request):
    return export_applications_pdf(_filtered_applications(request))


@login_required
def credential_list(request):
    credentials = request.user.credentials.select_related('application')
    credential_values = [(credential, decrypt_password(credential.encrypted_password)) for credential in credentials]
    return render(request, 'tracker/credential_list.html', {'credential_values': credential_values})


@login_required
def credential_create(request):
    form = PortalCredentialForm(request.POST or None, user=request.user)
    if request.method == 'POST' and form.is_valid():
        credential = form.save()
        log_activity(request.user, 'Portal credential saved', credential.application, credential.portal_name)
        messages.success(request, 'Credential saved with encryption.')
        return redirect('credential_list')
    return render(request, 'tracker/generic_form.html', {'form': form, 'title': 'Add Credential'})


@login_required
def credential_update(request, pk):
    credential = get_object_or_404(request.user.credentials, pk=pk)
    form = PortalCredentialForm(request.POST or None, instance=credential, user=request.user)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Credential updated.')
        return redirect('credential_list')
    return render(request, 'tracker/generic_form.html', {'form': form, 'title': 'Edit Credential'})


@login_required
def document_list(request):
    documents = request.user.documents.select_related('application')
    return render(request, 'tracker/document_list.html', {'documents': documents})


@login_required
def document_create(request):
    form = ApplicationDocumentForm(request.POST or None, request.FILES or None, user=request.user)
    if request.method == 'POST' and form.is_valid():
        document = form.save()
        if document.expiry_date:
            from datetime import datetime, time
            remind_at = timezone.make_aware(datetime.combine(document.expiry_date - timedelta(days=7), time(9, 0)))
            Reminder.objects.get_or_create(
                user=request.user,
                application=document.application,
                title=f'Document expiry check: {document.title}',
                reminder_type='document_expiry',
                remind_at=remind_at,
            )
        log_activity(request.user, 'Document uploaded', document.application, document.title)
        messages.success(request, 'Document uploaded.')
        return redirect('document_list')
    return render(request, 'tracker/generic_form.html', {'form': form, 'title': 'Upload Document'})


@login_required
def document_update(request, pk):
    document = get_object_or_404(request.user.documents, pk=pk)
    form = ApplicationDocumentForm(request.POST or None, request.FILES or None, instance=document, user=request.user)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Document updated.')
        return redirect('document_list')
    return render(request, 'tracker/generic_form.html', {'form': form, 'title': 'Edit Document'})


@login_required
def template_list(request):
    templates = request.user.templates.all()
    return render(request, 'tracker/template_list.html', {'templates': templates})


@login_required
def template_create(request):
    form = TemplateForm(request.POST or None, request.FILES or None, user=request.user)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Reusable template saved.')
        return redirect('template_list')
    return render(request, 'tracker/generic_form.html', {'form': form, 'title': 'Create Template'})


@login_required
def template_update(request, pk):
    template = get_object_or_404(request.user.templates, pk=pk)
    form = TemplateForm(request.POST or None, request.FILES or None, instance=template, user=request.user)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Template updated.')
        return redirect('template_list')
    return render(request, 'tracker/generic_form.html', {'form': form, 'title': 'Edit Template'})


@login_required
def reminder_list(request):
    reminders = request.user.reminders.select_related('application')
    return render(request, 'tracker/reminder_list.html', {'reminders': reminders})


@login_required
def reminder_create(request):
    form = ReminderForm(request.POST or None, user=request.user)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Reminder created.')
        return redirect('reminder_list')
    return render(request, 'tracker/generic_form.html', {'form': form, 'title': 'Create Reminder'})


@login_required
def reminder_update(request, pk):
    reminder = get_object_or_404(request.user.reminders, pk=pk)
    form = ReminderForm(request.POST or None, instance=reminder, user=request.user)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Reminder updated.')
        return redirect('reminder_list')
    return render(request, 'tracker/generic_form.html', {'form': form, 'title': 'Edit Reminder'})


@login_required
def reminder_toggle(request, pk):
    reminder = get_object_or_404(request.user.reminders, pk=pk)
    reminder.is_completed = not reminder.is_completed
    reminder.save(update_fields=['is_completed'])
    return redirect('reminder_list')


@login_required
def interview_list(request):
    interview_notes = InterviewNote.objects.filter(
        application__user=request.user
    ).select_related('application').order_by('-updated_at')
    return render(request, 'tracker/interview_list.html', {'interview_notes': interview_notes})


@login_required
def add_checklist_item(request, pk):
    application = get_object_or_404(request.user.applications, pk=pk)
    form = ChecklistItemForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        item = form.save(commit=False)
        item.application = application
        item.save()
        return redirect(application)
    return render(request, 'tracker/generic_form.html', {'form': form, 'title': 'Add Checklist Item'})


@login_required
def add_interview_note(request, pk):
    application = get_object_or_404(request.user.applications, pk=pk)
    form = InterviewNoteForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        note = form.save(commit=False)
        note.application = application
        note.save()
        messages.success(request, 'Interview note added.')
        return redirect(application)
    return render(request, 'tracker/generic_form.html', {'form': form, 'title': 'Add Interview Note'})


@login_required
def interview_note_edit(request, pk, note_pk):
    note = get_object_or_404(InterviewNote, pk=note_pk, application__pk=pk, application__user=request.user)
    form = InterviewNoteForm(request.POST or None, instance=note)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Interview note updated.')
        return redirect(note.application)
    return render(request, 'tracker/generic_form.html', {'form': form, 'title': 'Edit Interview Note'})


@login_required
def interview_note_delete(request, pk, note_pk):
    note = get_object_or_404(InterviewNote, pk=note_pk, application__pk=pk, application__user=request.user)
    application = note.application
    if request.method == 'POST':
        note.delete()
        messages.success(request, 'Interview note deleted.')
        return redirect(application)
    return render(request, 'tracker/confirm_delete.html', {'object': note, 'title': 'Delete interview note'})


@login_required
def interview_dashboard(request, pk):
    application = get_object_or_404(Application, pk=pk, user=request.user)
    interview_notes = application.interview_notes.all()

    # Stats
    total_questions = interview_notes.count()
    practiced_questions = interview_notes.filter(is_practiced=True).count()
    avg_rating = interview_notes.filter(user_rating__isnull=False).aggregate(
        avg_rating=Avg('user_rating')
    )['avg_rating'] or 0

    # Questions by type
    question_type_breakdown = list(interview_notes.values('question_type').annotate(
        count=Count('id')
    ).order_by('question_type'))
    for item in question_type_breakdown:
        item['percentage'] = round((item['count'] / total_questions * 100), 1) if total_questions > 0 else 0

    context = {
        'application': application,
        'interview_notes': interview_notes,
        'total_questions': total_questions,
        'practiced_questions': practiced_questions,
        'practice_percentage': round((practiced_questions / total_questions * 100) if total_questions > 0 else 0),
        'avg_rating': round(avg_rating, 1),
        'question_type_breakdown': question_type_breakdown,
    }
    return render(request, 'tracker/interview_dashboard.html', context)


@login_required
def interview_practice(request, pk, note_pk):
    note = get_object_or_404(InterviewNote, pk=note_pk, application__pk=pk, application__user=request.user)
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'mark_practiced':
            note.is_practiced = True
            note.practice_count += 1
            note.last_practiced = timezone.now()
            rating = request.POST.get('rating')
            if rating:
                note.user_rating = int(rating)
            note.save()
            messages.success(request, 'Practice logged.')
            return redirect('interview_practice', pk=pk, note_pk=note_pk)
        elif action == 'reset_practice':
            note.is_practiced = False
            note.practice_count = 0
            note.last_practiced = None
            note.user_rating = None
            note.save()
            messages.success(request, 'Practice status reset.')
            return redirect('interview_practice', pk=pk, note_pk=note_pk)
    context = {
        'note': note,
        'application': note.application,
    }
    return render(request, 'tracker/interview_practice.html', context)
