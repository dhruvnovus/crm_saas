import json

from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver

from .models import Branch, BranchHistory


def get_field_value(obj, field_name):
    """Safely get field value, handling ForeignKeys and special fields"""
    try:
        field = obj._meta.get_field(field_name)
        if field.many_to_one:  # ForeignKey
            value = getattr(obj, field_name)
            return str(value.id) if value else None
        if field.many_to_many:
            return [str(item.id) for item in getattr(obj, field_name).all()]
        value = getattr(obj, field_name)
        if value is None:
            return None
        if isinstance(value, (dict, list)):
            return json.dumps(value)
        return str(value)
    except Exception:
        return None


@receiver(pre_save, sender=Branch)
def branch_pre_save(sender, instance, **kwargs):
    """Store the old instance before save to compare changes"""
    if instance.pk:
        try:
            instance._old_instance = Branch.objects.get(pk=instance.pk)
        except Branch.DoesNotExist:
            instance._old_instance = None
    else:
        instance._old_instance = None


@receiver(post_save, sender=Branch)
def branch_post_save(sender, instance, created, **kwargs):
    """Track changes to Branch model"""
    changed_by = None
    if hasattr(instance, "_changed_by"):
        changed_by = instance._changed_by
    elif hasattr(instance, "created_by") and created:
        changed_by = instance.created_by

    tenant = instance.tenant

    from django.db import connections

    if hasattr(connections["default"], "tenant"):
        connections["default"].tenant = tenant

    if created:
        BranchHistory.objects.create(
            branch=instance,
            tenant=tenant,
            changed_by=changed_by,
            action="created",
            changes={"all_fields": "Branch created"},
            notes="Branch was created",
        )
        return

    old_instance = getattr(instance, "_old_instance", None)
    if not old_instance:
        return

    tracked_fields = [
        "name",
        "code",
        "address",
        "city",
        "state",
        "country",
        "zip_code",
        "phone",
        "email",
        "manager_name",
        "manager_email",
        "manager_phone",
        "is_active",
        "notes",
    ]
    changes = {}
    for field_name in tracked_fields:
        old_value = get_field_value(old_instance, field_name)
        new_value = get_field_value(instance, field_name)
        if old_value != new_value:
            changes[field_name] = {"old": old_value, "new": new_value}

    if not changes:
        return

    # Soft delete
    if "is_active" in changes and changes["is_active"]["new"] == "False":
        BranchHistory.objects.create(
            branch=instance,
            tenant=tenant,
            changed_by=changed_by,
            action="deleted",
            field_name="is_active",
            old_value=changes["is_active"]["old"],
            new_value=changes["is_active"]["new"],
            changes=changes,
            notes="Branch was soft-deleted",
        )
        changes.pop("is_active", None)

    if changes:
        changed_fields = list(changes.keys())
        BranchHistory.objects.create(
            branch=instance,
            tenant=tenant,
            changed_by=changed_by,
            action="updated",
            field_name=", ".join(changed_fields) if len(changed_fields) <= 3 else f"{len(changed_fields)} fields",
            changes=changes,
            notes=f"Updated fields: {', '.join(changed_fields)}",
        )


