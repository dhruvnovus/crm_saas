import uuid

from django.db import models

from user.models import CustomUser, Tenant, TimestampedModel


class Category(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="categories")
    
    name = models.CharField(max_length=255)
    code = models.CharField(max_length=50, blank=True, null=True, help_text="Category code or identifier")
    description = models.TextField(blank=True, null=True, help_text="Category description")
    parent = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='children',
        help_text="Parent category for hierarchical structure"
    )
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_categories",
    )
    notes = models.TextField(blank=True, null=True, help_text="Additional notes about the category")

    class Meta:
        indexes = [
            models.Index(fields=["tenant", "name"]),
            models.Index(fields=["tenant", "code"]),
            models.Index(fields=["tenant", "parent"]),
            models.Index(fields=["tenant", "is_active"]),
        ]
        unique_together = [("tenant", "code")]
        verbose_name = "Category"
        verbose_name_plural = "Categories"

    def __str__(self):
        return f"{self.name} ({self.code or 'No Code'})"


class CategoryHistory(TimestampedModel):
    """Model to track all changes and updates to Category records"""
    
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    category = models.ForeignKey(Category, on_delete=models.CASCADE, related_name="history")
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="category_history")
    changed_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="category_changes",
    )
    
    ACTION_CHOICES = [
        ("created", "Created"),
        ("updated", "Updated"),
        ("deleted", "Deleted"),
    ]
    action = models.CharField(max_length=20, choices=ACTION_CHOICES, help_text="Type of action performed")
    
    field_name = models.CharField(max_length=100, blank=True, null=True, help_text="Field that was changed")
    old_value = models.TextField(blank=True, null=True, help_text="Previous value")
    new_value = models.TextField(blank=True, null=True, help_text="New value")
    
    changes = models.JSONField(default=dict, blank=True, help_text="Complete snapshot of all field changes")
    notes = models.TextField(blank=True, null=True, help_text="Additional notes about the change")

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["category", "created_at"]),
            models.Index(fields=["tenant", "created_at"]),
            models.Index(fields=["action", "created_at"]),
        ]
        verbose_name = "Category History"
        verbose_name_plural = "Category Histories"

    def __str__(self):
        return f"{self.category.name} - {self.action} ({self.created_at})"


