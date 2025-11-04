from django.db import models
import uuid

from user.models import Tenant, TimestampedModel, CustomUser
from customer.models import Customer


class LeadStatus(models.TextChoices):
    NEW = 'new', 'New'
    CONTACTED = 'contacted', 'Contacted'
    QUALIFIED = 'qualified', 'Qualified'
    WON = 'won', 'Won'
    LOST = 'lost', 'Lost'


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


