import re

from django import forms
from django.contrib.auth import authenticate, get_user_model
from django.core.validators import URLValidator
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.core.exceptions import ValidationError
from django.utils import timezone

from .models import (
    Application,
    ApplicationDocument,
    ApplicationTemplate,
    ChecklistItem,
    InterviewNote,
    PortalCredential,
    Profile,
    Reminder,
)
from .utils import verify_totp

User = get_user_model()


class DateInput(forms.DateInput):
    input_type = 'date'


class DateTimeInput(forms.DateTimeInput):
    input_type = 'datetime-local'


def apply_placeholders(form):
    placeholder_map = {
        'full_name': 'Enter full name',
        'username': 'Enter username',
        'email': 'Enter email address',
        'phone': 'Enter phone number',
        'headline': 'Enter professional headline',
        'location': 'Enter location',
        'bio': 'Write a short bio',
        'company_name': 'Enter company name',
        'job_title': 'Enter job title',
        'portal_name': 'Enter portal name',
        'application_url': 'Paste application URL',
        'job_location': 'Enter job location',
        'salary': 'Enter salary details',
        'notes': 'Add notes',
        'referral_name': 'Enter referral name',
        'referral_contact': 'Enter referral contact',
        'follow_up_email_draft': 'Write follow-up email draft',
        'tags_input': 'Backend, Remote, Fintech',
        'portal_email': 'Enter portal email',
        'portal_user_id': 'Enter portal user ID',
        'login_url': 'Paste login URL',
        'password': 'Enter password',
        'security_notes': 'Add security notes',
        'title': 'Enter title',
        'version_label': 'Enter version label',
        'target_role': 'Enter target role',
        'content': 'Write content',
        'remind_at': 'Select reminder date and time',
        'company_rating': '0 to 5',
        'match_score': '0 to 100',
        'otp_code': 'Enter 6-digit code',
    }
    skip_widgets = (forms.CheckboxInput, forms.Select, forms.SelectMultiple, forms.ClearableFileInput)
    for name, field in form.fields.items():
        if isinstance(field.widget, skip_widgets):
            continue
        fallback_label = (field.label or name.replace('_', ' ')).lower()
        field.widget.attrs.setdefault('placeholder', placeholder_map.get(name, f'Enter {fallback_label}'))


class RegisterForm(UserCreationForm):
    email = forms.EmailField()
    full_name = forms.CharField(max_length=180)

    class Meta:
        model = User
        fields = ('username', 'full_name', 'email', 'password1', 'password2')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_placeholders(self)

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        user.first_name = self.cleaned_data['full_name']
        if commit:
            user.save()
            profile = user.profile
            profile.full_name = self.cleaned_data['full_name']
            profile.save()
        return user


class LoginWithOTPForm(AuthenticationForm):
    otp_code = forms.CharField(max_length=6, required=False, label='2FA Code')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_placeholders(self)

    def clean(self):
        username = self.cleaned_data.get('username')
        password = self.cleaned_data.get('password')
        otp_code = self.cleaned_data.get('otp_code', '').strip()
        if username and password:
            self.user_cache = authenticate(self.request, username=username, password=password)
            if self.user_cache is None:
                raise self.get_invalid_login_error()
            profile = self.user_cache.profile
            if profile.two_factor_enabled:
                if not otp_code:
                    raise ValidationError('Two-factor code is required for this account.')
                if not verify_totp(profile.two_factor_secret, otp_code):
                    raise ValidationError('Invalid two-factor code.')
            self.confirm_login_allowed(self.user_cache)
        return self.cleaned_data


class ProfileForm(forms.ModelForm):
    email = forms.EmailField()

    class Meta:
        model = Profile
        fields = ('full_name', 'phone', 'headline', 'location', 'bio', 'theme_preference', 'notify_email')
        widgets = {'bio': forms.Textarea(attrs={'rows': 4})}

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user')
        super().__init__(*args, **kwargs)
        self.fields['email'].initial = self.user.email
        apply_placeholders(self)

    def save(self, commit=True):
        profile = super().save(commit=False)
        self.user.email = self.cleaned_data['email']
        self.user.first_name = self.cleaned_data.get('full_name', '')
        if commit:
            self.user.save()
            profile.save()
        return profile


class ApplicationForm(forms.ModelForm):
    tags_input = forms.CharField(required=False, help_text='Comma separated tags like Backend, Remote, Fintech')
    application_url = forms.CharField(required=False)

    class Meta:
        model = Application
        exclude = ('user', 'tags')
        widgets = {
            'notes': forms.Textarea(attrs={'rows': 4}),
            'follow_up_email_draft': forms.Textarea(attrs={'rows': 4}),
            'application_start_date': DateInput(),
            'submitted_date': DateInput(),
            'test_date': DateInput(),
            'interview_date': DateInput(),
            'follow_up_date': DateInput(),
            'deadline_date': DateInput(),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user')
        super().__init__(*args, **kwargs)
        self.fields['company_rating'].required = False
        self.fields['match_score'].required = False
        self.fields['application_url'].help_text = 'Use a full URL like https://company.com/jobs/123. If you omit the scheme, https:// will be added automatically.'
        if self.instance.pk:
            self.fields['tags_input'].initial = ', '.join(self.instance.tags.values_list('name', flat=True))
        apply_placeholders(self)

    def clean_application_url(self):
        url = (self.cleaned_data.get('application_url') or '').strip()
        if url and '://' not in url:
            url = f'https://{url}'
        if url:
            URLValidator()(url)
        return url

    def save(self, commit=True):
        application = super().save(commit=False)
        application.user = self.user
        if commit:
            application.save()
            tags = []
            for raw_tag in re.split(r',\s*', self.cleaned_data.get('tags_input', '').strip()):
                if raw_tag:
                    tag, _ = self.user.tags.get_or_create(name=raw_tag)
                    tags.append(tag)
            application.tags.set(tags)
        return application


class PortalCredentialForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput(render_value=True), required=False)

    class Meta:
        model = PortalCredential
        fields = ('application', 'portal_name', 'portal_email', 'portal_user_id', 'login_url', 'password', 'security_notes')
        widgets = {'security_notes': forms.Textarea(attrs={'rows': 4})}

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user')
        super().__init__(*args, **kwargs)
        self.fields['application'].queryset = self.user.applications.all()
        if self.instance.pk:
            self.fields['password'].initial = ''
        apply_placeholders(self)

    def save(self, commit=True):
        credential = super().save(commit=False)
        credential.user = self.user
        if commit:
            credential.save()
            password = self.cleaned_data.get('password')
            if password:
                from .utils import encrypt_password
                credential.encrypted_password = encrypt_password(password)
                credential.save(update_fields=['encrypted_password'])
        return credential


class ApplicationDocumentForm(forms.ModelForm):
    class Meta:
        model = ApplicationDocument
        fields = ('application', 'document_type', 'title', 'version_label', 'file', 'expiry_date')
        widgets = {'expiry_date': DateInput()}

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user')
        super().__init__(*args, **kwargs)
        self.fields['application'].queryset = self.user.applications.all()
        apply_placeholders(self)

    def save(self, commit=True):
        document = super().save(commit=False)
        document.user = self.user
        if commit:
            document.save()
        return document


class ReminderForm(forms.ModelForm):
    class Meta:
        model = Reminder
        fields = ('application', 'title', 'reminder_type', 'remind_at', 'notes', 'is_completed')
        widgets = {'remind_at': DateTimeInput(), 'notes': forms.Textarea(attrs={'rows': 3})}

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user')
        super().__init__(*args, **kwargs)
        self.fields['application'].queryset = self.user.applications.all()
        self.fields['remind_at'].initial = timezone.now().replace(second=0, microsecond=0)
        apply_placeholders(self)

    def save(self, commit=True):
        reminder = super().save(commit=False)
        reminder.user = self.user
        if commit:
            reminder.save()
        return reminder


class TemplateForm(forms.ModelForm):
    class Meta:
        model = ApplicationTemplate
        fields = ('template_type', 'title', 'target_role', 'content', 'attachment')
        widgets = {'content': forms.Textarea(attrs={'rows': 6})}

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user')
        super().__init__(*args, **kwargs)
        apply_placeholders(self)

    def save(self, commit=True):
        template = super().save(commit=False)
        template.user = self.user
        if commit:
            template.save()
        return template


class ChecklistItemForm(forms.ModelForm):
    class Meta:
        model = ChecklistItem
        fields = ('title', 'is_done')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_placeholders(self)


class InterviewNoteForm(forms.ModelForm):
    class Meta:
        model = InterviewNote
        fields = ('title', 'content', 'question_type', 'difficulty')
        widgets = {
            'content': forms.Textarea(attrs={'rows': 4}),
            'question_type': forms.Select(attrs={'class': 'form-select'}),
            'difficulty': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        apply_placeholders(self)
