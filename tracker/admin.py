from django.contrib import admin

from .models import (
    ActivityLog,
    Application,
    ApplicationDocument,
    ApplicationTemplate,
    ChecklistItem,
    InterviewNote,
    PortalCredential,
    Profile,
    Reminder,
    Tag,
)


@admin.register(Application)
class ApplicationAdmin(admin.ModelAdmin):
    list_display = ('company_name', 'job_title', 'status', 'priority', 'deadline_date', 'user')
    list_filter = ('status', 'priority', 'employment_type')
    search_fields = ('company_name', 'job_title', 'portal_name', 'job_location')


admin.site.register([Profile, Tag, PortalCredential, ApplicationDocument, Reminder, ApplicationTemplate, ChecklistItem, InterviewNote, ActivityLog])
