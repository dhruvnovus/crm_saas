from django.db import models
from user.models import Tenant, TimestampedModel, CustomUser
import uuid


class Customer(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='customers')
    name = models.CharField(max_length=255)
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=50, blank=True, null=True)
    company = models.CharField(max_length=255, blank=True, null=True)
    created_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_customers')
    address = models.TextField(blank=True, null=True)
    city = models.CharField(max_length=120, blank=True, null=True)
    state = models.CharField(max_length=120, blank=True, null=True)
    country = models.CharField(max_length=120, blank=True, null=True)
    zip_code = models.CharField(max_length=20, blank=True, null=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        indexes = [
            models.Index(fields=['tenant', 'name']),
            models.Index(fields=['tenant', 'email']),
        ]
        unique_together = [('tenant', 'email')]

    def __str__(self):
        return f"{self.name}"


class CustomerHistory(TimestampedModel):
    """Model to track all changes and updates to Customer records"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='history')
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name='customer_history')
    changed_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True, blank=True, related_name='customer_changes')
    
    ACTION_CHOICES = [
        ('created', 'Created'),
        ('updated', 'Updated'),
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
            models.Index(fields=['customer', 'created_at']),
            models.Index(fields=['tenant', 'created_at']),
            models.Index(fields=['action', 'created_at']),
        ]
        verbose_name = 'Customer History'
        verbose_name_plural = 'Customer Histories'

    def __str__(self):
        return f"{self.customer.name} - {self.action} ({self.created_at})"
