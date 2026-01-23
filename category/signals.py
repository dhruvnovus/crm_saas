from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from .models import Category, CategoryHistory
import json


def get_field_value(obj, field_name):
    """Safely get field value, handling ForeignKeys and special fields"""
    try:
        field = obj._meta.get_field(field_name)
        if field.many_to_one:  # ForeignKey
            value = getattr(obj, field_name)
            return str(value.id) if value else None
        elif field.many_to_many:
            return [str(item.id) for item in getattr(obj, field_name).all()]
        else:
            value = getattr(obj, field_name)
            # Convert to string for storage, handling None
            if value is None:
                return None
            if isinstance(value, (dict, list)):
                return json.dumps(value)
            return str(value)
    except Exception:
        return None


@receiver(pre_save, sender=Category)
def category_pre_save(sender, instance, **kwargs):
    """Store the old instance before save to compare changes"""
    if instance.pk:
        try:
            old_instance = Category.objects.get(pk=instance.pk)
            instance._old_instance = old_instance
        except Category.DoesNotExist:
            instance._old_instance = None
    else:
        instance._old_instance = None


@receiver(post_save, sender=Category)
def category_post_save(sender, instance, created, **kwargs):
    """Track changes to Category model"""
    # Get the user from the request if available
    changed_by = None
    if hasattr(instance, '_changed_by'):
        changed_by = instance._changed_by
    elif hasattr(instance, 'created_by') and created:
        changed_by = instance.created_by
    
    tenant = instance.tenant
    
    # Ensure we're in the tenant database context
    from django.db import connections
    if hasattr(connections['default'], 'tenant'):
        connections['default'].tenant = tenant
    
    if created:
        # Record creation
        CategoryHistory.objects.create(
            category=instance,
            tenant=tenant,
            changed_by=changed_by,
            action='created',
            changes={'all_fields': 'Category created'},
            notes='Category was created'
        )
    else:
        # Record updates
        old_instance = getattr(instance, '_old_instance', None)
        if old_instance:
            changes = {}
            tracked_fields = [
                'name', 'code', 'description', 'parent', 'is_active', 'notes'
            ]
            
            for field_name in tracked_fields:
                old_value = get_field_value(old_instance, field_name)
                new_value = get_field_value(instance, field_name)
                
                if old_value != new_value:
                    changes[field_name] = {
                        'old': old_value,
                        'new': new_value
                    }
            
            if changes:
                # Check if this is a soft delete (is_active changed to False)
                if 'is_active' in changes and changes['is_active']['new'] == 'False':
                    CategoryHistory.objects.create(
                        category=instance,
                        tenant=tenant,
                        changed_by=changed_by,
                        action='deleted',
                        field_name='is_active',
                        old_value=changes['is_active']['old'],
                        new_value=changes['is_active']['new'],
                        changes=changes,
                        notes='Category was soft-deleted'
                    )
                    changes.pop('is_active', None)
                
                # Record other changes if any
                if changes:
                    changed_fields = list(changes.keys())
                    CategoryHistory.objects.create(
                        category=instance,
                        tenant=tenant,
                        changed_by=changed_by,
                        action='updated',
                        field_name=', '.join(changed_fields) if len(changed_fields) <= 3 else f"{len(changed_fields)} fields",
                        changes=changes,
                        notes=f"Updated fields: {', '.join(changed_fields)}"
                    )


