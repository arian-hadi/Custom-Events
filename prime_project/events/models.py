from django.db import models
from accounts.models import CustomUser

class Event(models.Model):
    title = models.CharField(max_length=200)
    created_by = models.ForeignKey(
        CustomUser, 
        on_delete=models.CASCADE, 
        related_name='events',
        limit_choices_to={'role': 'admin'}
    )
    description = models.TextField()
    deadline = models.DateTimeField()
    date = models.DateTimeField()
    is_active = models.BooleanField(default=True)
    posted_date = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-posted_date']

    def __str__(self):
        return self.title

class EventField(models.Model):
    FIELD_TYPES = [
        ('text', 'Text'),
        ('number', 'Number'),
        ('date', 'Date'),
        ('boolean', 'Yes/No'),
    ]

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="custom_fields")
    name = models.CharField(max_length=255)  # Field label
    field_type = models.CharField(max_length=10, choices=FIELD_TYPES)
    value_text = models.TextField(blank=True, null=True)
    value_number = models.FloatField(blank=True, null=True)
    value_date = models.DateField(blank=True, null=True)
    value_boolean = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.event.title} - {self.name}"

class EventApplication(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('reviewing', 'Reviewing'),
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected'),
    ]

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='applications')
    applicant = models.ForeignKey(
        CustomUser, 
        on_delete=models.CASCADE, 
        related_name='applications',
        limit_choices_to={'role': 'user'}  # Ensures only normal users can apply
    )
    cover_letter = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    applied_date = models.DateTimeField(auto_now_add=True)
    updated_date = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('event', 'applicant')

    def __str__(self):
        return f"{self.applicant.username} - {self.event.title}"
