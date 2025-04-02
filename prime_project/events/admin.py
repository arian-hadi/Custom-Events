from django.contrib import admin
from .models import Event, EventField, EventApplication

@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ('title', 'created_by', 'date', 'deadline', 'is_active', 'posted_date')
    list_filter = ('is_active', 'date', 'deadline', 'created_by')
    search_fields = ('title', 'description', 'created_by__username')
    ordering = ('-posted_date',)
    date_hierarchy = 'date'

    fieldsets = (
        (None, {
            'fields': ('title', 'description', 'created_by')
        }),
        ('Timing & Status', {
            'fields': ('date', 'deadline', 'is_active')
        }),
    )

    readonly_fields = ('posted_date',)


@admin.register(EventField)
class EventFieldAdmin(admin.ModelAdmin):
    list_display = ('name', 'event', 'field_type')
    list_filter = ('field_type', 'event')
    search_fields = ('name', 'event__title')


@admin.register(EventApplication)
class EventApplicationAdmin(admin.ModelAdmin):
    list_display = ('event', 'applicant', 'status', 'applied_date', 'updated_date')
    list_filter = ('status', 'applied_date', 'event')
    search_fields = ('event__title', 'applicant__username')
    readonly_fields = ('applied_date', 'updated_date')

    fieldsets = (
        (None, {
            'fields': ('event', 'applicant', 'cover_letter', 'status')
        }),
        ('Timestamps', {
            'fields': ('applied_date', 'updated_date')
        }),
    )
