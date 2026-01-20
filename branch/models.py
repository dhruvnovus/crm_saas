import uuid

from django.db import models

from user.models import CustomUser, Tenant, TimestampedModel


class Branch(TimestampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="branches")

    name = models.CharField(max_length=255)
    code = models.CharField(max_length=50, blank=True, null=True, help_text="Branch code or identifier")

    address = models.TextField(blank=True, null=True)
    city = models.CharField(max_length=120, blank=True, null=True)
    state = models.CharField(max_length=120, blank=True, null=True)
    country = models.CharField(max_length=120, blank=True, null=True)
    zip_code = models.CharField(max_length=20, blank=True, null=True)

    phone = models.CharField(max_length=50, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)

    manager_name = models.CharField(max_length=255, blank=True, null=True)
    manager_email = models.EmailField(blank=True, null=True)
    manager_phone = models.CharField(max_length=50, blank=True, null=True)

    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_branches",
    )
    notes = models.TextField(blank=True, null=True, help_text="Additional notes about the branch")

    class Meta:
        indexes = [
            models.Index(fields=["tenant", "name"]),
            models.Index(fields=["tenant", "code"]),
            models.Index(fields=["tenant", "city"]),
            models.Index(fields=["tenant", "is_active"]),
        ]
        unique_together = [("tenant", "code")]

    def __str__(self):
        return f"{self.name} ({self.code or 'No Code'})"


class BranchHistory(TimestampedModel):
    """Model to track all changes and updates to Branch records"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    branch = models.ForeignKey(Branch, on_delete=models.CASCADE, related_name="history")
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="branch_history")
    changed_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="branch_changes",
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
            models.Index(fields=["branch", "created_at"]),
            models.Index(fields=["tenant", "created_at"]),
            models.Index(fields=["action", "created_at"]),
        ]
        verbose_name = "Branch History"
        verbose_name_plural = "Branch Histories"

    def __str__(self):
        return f"{self.branch.name} - {self.action} ({self.created_at})"


