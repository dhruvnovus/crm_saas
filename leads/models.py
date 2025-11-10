from django.db import models
import uuid

from user.models import Tenant, TimestampedModel, CustomUser
from customer.models import Customer


class LeadStatus(models.TextChoices):
    NEW = 'new', 'New'
    CONTACTED = 'contacted', 'Contacted'
    OPEN = 'open', 'Open'
    INTERESTED = 'interested', 'Interested'
    NOT_INTERESTED = 'not_interested', 'Not Interested'
    FOLLOW_UP = 'follow_up', 'Follow Up'


class Lead(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='leads')
    customer = models.ForeignKey(Customer, on_delete=models.SET_NULL, null=True, blank=True, related_name='leads')
    name = models.CharField(max_length=255)
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=50, blank=True, null=True)
    status = models.CharField(max_length=20, choices=LeadStatus.choices, default=LeadStatus.NEW)
    source = models.CharField(max_length=120, blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    created_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_leads')
    is_active = models.BooleanField(default=True)

    class Meta:
        indexes = [
            models.Index(fields=['tenant', 'name']),
            models.Index(fields=['tenant', 'email']),
            models.Index(fields=['tenant', 'status']),
        ]

    def __str__(self):
        return f"{self.name}"


class CallOutcome(models.TextChoices):
    SCHEDULED_MEETING = 'scheduled_meeting', 'Scheduled Meeting'
    SENT_INFO = 'sent_info', 'Sent Info'
    ENDED_CALL = 'ended_call', 'Ended Call'
    THANKED_ENDED = 'thanked_ended', 'Thanked and Ended'
    FOLLOW_UP = 'follow_up', 'Follow Up'
    NOT_CONTACTED = 'not_contacted', 'Not Contacted'


class LeadCallSummary(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='lead_call_summaries')
    lead = models.ForeignKey('Lead', on_delete=models.CASCADE, related_name='call_summaries')
    summary = models.TextField(blank=True, null=True, help_text="Additional detailed call summary or notes")
    call_time = models.DateTimeField(blank=True, null=True)
    created_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_lead_call_summaries')
    is_active = models.BooleanField(default=True)
    
    # Q1: "Are you currently preparing for USMLE or applying for U.S. residency?"
    q1_preparing_usmle_residency = models.BooleanField(
        null=True, 
        blank=True,
        help_text="Q1: Are you currently preparing for USMLE or applying for U.S. residency?"
    )
    # Q1 Follow-up: Only asked if q1_preparing_usmle_residency is False
    q1_interested_future = models.BooleanField(
        null=True,
        blank=True,
        help_text="Q1 Follow-up: Are you interested in U.S. residency in the future? (Only if Q1 was NO)"
    )
    
    # Q2: "Are you looking for U.S. clinical experience or research opportunities?"
    q2_clinical_research_opportunities = models.BooleanField(
        null=True,
        blank=True,
        help_text="Q2: Are you looking for U.S. clinical experience or research opportunities?"
    )
    # Q2 Follow-up: Only asked if q2_clinical_research_opportunities is False
    q2_want_to_learn_more = models.BooleanField(
        null=True,
        blank=True,
        help_text="Q2 Follow-up: These really strengthen residency applications. Want to learn more? (Only if Q2 was NO)"
    )
    
    # Q3: "Would you like detailed info sent to you, or prefer a free 1-on-1 call with Dr. Urvish Patel for personalized guidance?"
    Q3_PREFERENCE_CHOICES = [
        ('call', 'Free 1-on-1 Call'),
        ('info', 'Detailed Info Only'),
        ('both', 'Both Call and Info'),
        ('none', 'No to Both'),
    ]
    q3_preference = models.CharField(
        max_length=10,
        choices=Q3_PREFERENCE_CHOICES,
        null=True,
        blank=True,
        help_text="Q3: Would you like detailed info sent to you, or prefer a free 1-on-1 call?"
    )
    # Q3 Follow-up: Only asked if q3_preference is 'info'
    q3_want_call_after_info = models.BooleanField(
        null=True,
        blank=True,
        help_text="Q3 Follow-up: Great! Info coming your way. Sure you don't want the free call too? (Only if Q3 was 'info')"
    )
    
    # Final call outcome
    call_outcome = models.CharField(
        max_length=20,
        choices=CallOutcome.choices,
        null=True,
        blank=True,
        help_text="Final outcome of the call"
    )

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['tenant', 'lead', 'created_at']),
            models.Index(fields=['tenant', 'created_at']),
            models.Index(fields=['call_outcome']),
        ]

    def __str__(self):
        return f"CallSummary({self.lead_id}) @ {self.created_at}"

class LeadHistory(TimestampedModel):
    """Model to track all changes and updates to Lead records"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name='history')
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='lead_history')
    changed_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='lead_changes')
    
    ACTION_CHOICES = [
        ('created', 'Created'),
        ('updated', 'Updated'),
        ('status_changed', 'Status Changed'),
        ('deleted', 'Deleted'),
    ]
    
    action = models.CharField(max_length=20, choices=ACTION_CHOICES, help_text="Type of action performed")
    
    # Store field changes
    field_name = models.CharField(max_length=100, blank=True, null=True, help_text="Field that was changed")
    old_value = models.TextField(blank=True, null=True, help_text="Previous value")
    new_value = models.TextField(blank=True, null=True, help_text="New value")
    
    # Store complete snapshot of changes for this update
    changes = models.JSONField(default=dict, blank=True, help_text="Complete snapshot of all field changes")
    
    # Additional metadata
    notes = models.TextField(blank=True, null=True, help_text="Additional notes about the change")

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['lead', 'created_at']),
            models.Index(fields=['tenant', 'created_at']),
            models.Index(fields=['action', 'created_at']),
        ]
        verbose_name = 'Lead History'
        verbose_name_plural = 'Lead Histories'

    def __str__(self):
        return f"{self.lead.name} - {self.action} ({self.created_at})"


