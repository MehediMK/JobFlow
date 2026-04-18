from django.conf import settings
from django.contrib.auth.models import User
from django.core.validators import FileExtensionValidator, MaxValueValidator, MinValueValidator
from django.db import models
from django.urls import reverse
from django.utils import timezone


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Profile(TimeStampedModel):
    THEME_CHOICES = [
        ('system', 'System'),
        ('light', 'Light'),
        ('dark', 'Dark'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE)
    full_name = models.CharField(max_length=180, blank=True)
    phone = models.CharField(max_length=30, blank=True)
    headline = models.CharField(max_length=180, blank=True)
    location = models.CharField(max_length=120, blank=True)
    bio = models.TextField(blank=True)
    theme_preference = models.CharField(max_length=20, choices=THEME_CHOICES, default='system')
    notify_email = models.BooleanField(default=True)
    email_verified = models.BooleanField(default=False)
    two_factor_enabled = models.BooleanField(default=False)
    two_factor_secret = models.CharField(max_length=64, blank=True)

    def __str__(self):
        return self.user.username


class Tag(TimeStampedModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='tags')
    name = models.CharField(max_length=60)

    class Meta:
        unique_together = ('user', 'name')
        ordering = ['name']

    def __str__(self):
        return self.name


class Application(TimeStampedModel):
    STATUS_DRAFT = 'draft'
    STATUS_PLANNING = 'planning'
    STATUS_APPLIED = 'applied'
    STATUS_UNDER_REVIEW = 'under_review'
    STATUS_TEST = 'assessment'
    STATUS_INTERVIEW = 'interview'
    STATUS_FINAL = 'final_interview'
    STATUS_OFFERED = 'offered'
    STATUS_REJECTED = 'rejected'
    STATUS_WITHDRAWN = 'withdrawn'
    STATUS_CHOICES = [
        (STATUS_DRAFT, 'Draft'),
        (STATUS_PLANNING, 'Planning to Apply'),
        (STATUS_APPLIED, 'Applied'),
        (STATUS_UNDER_REVIEW, 'Under Review'),
        (STATUS_TEST, 'Assessment/Test'),
        (STATUS_INTERVIEW, 'Interview Scheduled'),
        (STATUS_FINAL, 'Final Interview'),
        (STATUS_OFFERED, 'Offered'),
        (STATUS_REJECTED, 'Rejected'),
        (STATUS_WITHDRAWN, 'Withdrawn'),
    ]
    PRIORITY_CHOICES = [('low', 'Low'), ('medium', 'Medium'), ('high', 'High'), ('urgent', 'Urgent')]
    EMPLOYMENT_CHOICES = [
        ('full_time', 'Full Time'),
        ('part_time', 'Part Time'),
        ('contract', 'Contract'),
        ('internship', 'Internship'),
        ('remote', 'Remote'),
        ('hybrid', 'Hybrid'),
        ('onsite', 'Onsite'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='applications')
    company_name = models.CharField(max_length=180)
    job_title = models.CharField(max_length=180)
    portal_name = models.CharField(max_length=120, blank=True)
    application_url = models.URLField(blank=True)
    job_location = models.CharField(max_length=180, blank=True)
    employment_type = models.CharField(max_length=20, choices=EMPLOYMENT_CHOICES, blank=True)
    salary = models.CharField(max_length=120, blank=True)
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='medium')
    notes = models.TextField(blank=True)
    bookmarked = models.BooleanField(default=False)
    referral_name = models.CharField(max_length=120, blank=True)
    referral_contact = models.CharField(max_length=120, blank=True)
    company_rating = models.PositiveSmallIntegerField(default=0, validators=[MinValueValidator(0), MaxValueValidator(5)])
    match_score = models.PositiveSmallIntegerField(default=0, validators=[MinValueValidator(0), MaxValueValidator(100)])
    follow_up_email_draft = models.TextField(blank=True)
    application_start_date = models.DateField(null=True, blank=True)
    submitted_date = models.DateField(null=True, blank=True)
    test_date = models.DateField(null=True, blank=True)
    interview_date = models.DateField(null=True, blank=True)
    follow_up_date = models.DateField(null=True, blank=True)
    deadline_date = models.DateField(null=True, blank=True)
    tags = models.ManyToManyField(Tag, blank=True, related_name='applications')

    class Meta:
        ordering = ['deadline_date', '-updated_at']

    def __str__(self):
        return f'{self.company_name} - {self.job_title}'

    def get_absolute_url(self):
        return reverse('application_detail', args=[self.pk])

    @property
    def is_active(self):
        return self.status not in {self.STATUS_OFFERED, self.STATUS_REJECTED, self.STATUS_WITHDRAWN}


class PortalCredential(TimeStampedModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='credentials')
    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name='credentials', null=True, blank=True)
    portal_name = models.CharField(max_length=120)
    portal_email = models.EmailField(blank=True)
    portal_user_id = models.CharField(max_length=120, blank=True)
    login_url = models.URLField(blank=True)
    encrypted_password = models.TextField(blank=True)
    security_notes = models.TextField(blank=True)

    class Meta:
        ordering = ['portal_name']

    def __str__(self):
        return f'{self.portal_name} credentials'


class ApplicationDocument(TimeStampedModel):
    DOC_TYPES = [
        ('resume', 'CV/Resume'),
        ('cover_letter', 'Cover Letter'),
        ('certificate', 'Certificate'),
        ('portfolio', 'Portfolio PDF'),
        ('offer_letter', 'Offer Letter'),
        ('interview', 'Interview Document'),
        ('other', 'Other Attachment'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='documents')
    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name='documents')
    document_type = models.CharField(max_length=20, choices=DOC_TYPES)
    title = models.CharField(max_length=180)
    version_label = models.CharField(max_length=80, blank=True)
    file = models.FileField(
        upload_to='documents/%Y/%m/',
        validators=[FileExtensionValidator(['pdf', 'doc', 'docx', 'png', 'jpg', 'jpeg', 'webp'])],
    )
    expiry_date = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title


class Reminder(TimeStampedModel):
    TYPE_CHOICES = [
        ('deadline', 'Deadline'),
        ('follow_up', 'Follow-up'),
        ('interview', 'Interview'),
        ('document_expiry', 'Document Expiry'),
        ('custom', 'Custom'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reminders')
    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name='reminders', null=True, blank=True)
    title = models.CharField(max_length=180)
    reminder_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='custom')
    remind_at = models.DateTimeField()
    notes = models.TextField(blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    is_completed = models.BooleanField(default=False)

    class Meta:
        ordering = ['remind_at']

    def __str__(self):
        return self.title

    @property
    def is_due(self):
        return not self.is_completed and self.remind_at <= timezone.now()


class ApplicationTemplate(TimeStampedModel):
    TEMPLATE_TYPES = [('resume', 'Resume Version'), ('cover_letter', 'Cover Letter Template')]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='templates')
    template_type = models.CharField(max_length=20, choices=TEMPLATE_TYPES)
    title = models.CharField(max_length=180)
    target_role = models.CharField(max_length=120, blank=True)
    content = models.TextField(blank=True)
    attachment = models.FileField(
        upload_to='templates/%Y/%m/',
        blank=True,
        validators=[FileExtensionValidator(['pdf', 'doc', 'docx'])],
    )

    class Meta:
        ordering = ['template_type', 'title']

    def __str__(self):
        return self.title


class ChecklistItem(TimeStampedModel):
    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name='checklist_items')
    title = models.CharField(max_length=180)
    is_done = models.BooleanField(default=False)

    class Meta:
        ordering = ['is_done', 'created_at']

    def __str__(self):
        return self.title


class InterviewNote(TimeStampedModel):
    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name='interview_notes')
    title = models.CharField(max_length=180)
    content = models.TextField()
    # New fields for interview preparation
    QUESTION_TYPES = [
        ('behavioral', 'Behavioral'),
        ('technical', 'Technical'),
        ('situational', 'Situational'),
        ('company_specific', 'Company Specific'),
        ('role_specific', 'Role Specific'),
        ('other', 'Other'),
    ]
    question_type = models.CharField(max_length=20, choices=QUESTION_TYPES, default='other')
    difficulty = models.CharField(
        max_length=10,
        choices=[('easy', 'Easy'), ('medium', 'Medium'), ('hard', 'Hard')],
        default='medium'
    )
    is_practiced = models.BooleanField(default=False)
    practice_count = models.PositiveIntegerField(default=0)
    last_practiced = models.DateTimeField(null=True, blank=True)
    user_rating = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        help_text="User's self-rating of answer quality (1-5)"
    )

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['application', 'question_type']),
            models.Index(fields=['is_practiced']),
        ]

    def __str__(self):
        return self.title

    @property
    def is_recently_practiced(self):
        """Check if practiced in the last 3 days"""
        if not self.last_practiced:
            return False
        return (timezone.now() - self.last_practiced).days <= 3


class ActivityLog(TimeStampedModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='activities')
    application = models.ForeignKey(Application, on_delete=models.CASCADE, related_name='activities', null=True, blank=True)
    action = models.CharField(max_length=120)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.action
