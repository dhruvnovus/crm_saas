from django.db.models.signals import post_save, pre_save, pre_delete
from django.dispatch import receiver
from .models import Lead, LeadHistory, LeadCallSummary
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


@receiver(pre_save, sender=Lead)
def lead_pre_save(sender, instance, **kwargs):
    """Store the old instance before save to compare changes"""
    if instance.pk:
        try:
            old_instance = Lead.objects.get(pk=instance.pk)
            instance._old_instance = old_instance
        except Lead.DoesNotExist:
            instance._old_instance = None
    else:
        instance._old_instance = None


@receiver(post_save, sender=Lead)
def lead_post_save(sender, instance, created, **kwargs):
    """Track changes to Lead model"""
    # Get the user from the request if available
    # This is a workaround since signals don't have direct access to request
    # We'll get the user from a thread-local or pass it through the save method
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
        LeadHistory.objects.create(
            lead=instance,
            tenant=tenant,
            changed_by=changed_by,
            action='created',
            changes={'all_fields': 'Lead created'},
            notes='Lead was created'
        )
    else:
        # Record updates
        old_instance = getattr(instance, '_old_instance', None)
        if old_instance:
            changes = {}
            tracked_fields = ['name', 'email', 'phone', 'status', 'source', 'notes', 'customer', 'is_active']
            
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
                    LeadHistory.objects.create(
                        lead=instance,
                        tenant=tenant,
                        changed_by=changed_by,
                        action='deleted',
                        field_name='is_active',
                        old_value=changes['is_active']['old'],
                        new_value=changes['is_active']['new'],
                        changes=changes,
                        notes='Lead was soft-deleted'
                    )
                    changes.pop('is_active', None)
                
                # Check if status was changed
                is_status_change = 'status' in changes
                
                # Create history entry for each field change or a single entry with all changes
                if is_status_change:
                    # Special handling for status changes
                    LeadHistory.objects.create(
                        lead=instance,
                        tenant=tenant,
                        changed_by=changed_by,
                        action='status_changed',
                        field_name='status',
                        old_value=changes['status']['old'],
                        new_value=changes['status']['new'],
                        changes=changes,
                        notes=f"Status changed from {changes['status']['old']} to {changes['status']['new']}"
                    )
                    # Remove status from changes if we want separate entries
                    changes.pop('status', None)
                
                # Record other changes if any
                if changes:
                    # Create a single entry for all other changes
                    changed_fields = list(changes.keys())
                    LeadHistory.objects.create(
                        lead=instance,
                        tenant=tenant,
                        changed_by=changed_by,
                        action='updated',
                        field_name=', '.join(changed_fields) if len(changed_fields) <= 3 else f"{len(changed_fields)} fields",
                        changes=changes,
                        notes=f"Updated fields: {', '.join(changed_fields)}"
                    )


@receiver(pre_save, sender=LeadCallSummary)
def lead_call_summary_pre_save(sender, instance, **kwargs):
    """Store the old instance before save to compare changes"""
    if instance.pk:
        try:
            old_instance = LeadCallSummary.objects.get(pk=instance.pk)
            instance._old_instance = old_instance
        except LeadCallSummary.DoesNotExist:
            instance._old_instance = None
    else:
        instance._old_instance = None


@receiver(post_save, sender=LeadCallSummary)
def lead_call_summary_post_save(sender, instance, created, **kwargs):
    """Track call summary changes in LeadHistory"""
    # Get the user from the instance
    changed_by = None
    if hasattr(instance, '_changed_by'):
        changed_by = instance._changed_by
    elif hasattr(instance, 'created_by') and created:
        changed_by = instance.created_by
    
    lead = instance.lead
    tenant = instance.tenant
    
    # Ensure we're in the tenant database context
    from django.db import connections
    if hasattr(connections['default'], 'tenant'):
        connections['default'].tenant = tenant
    
    if created:
        # Record call summary creation
        summary_text = instance.summary or ""
        summary_preview = summary_text[:200] if len(summary_text) > 200 else summary_text
        summary_display = f"{summary_text[:100]}..." if len(summary_text) > 100 else summary_text or "No summary"
        
        LeadHistory.objects.create(
            lead=lead,
            tenant=tenant,
            changed_by=changed_by,
            action='updated',
            field_name='call_summary',
            old_value=None,
            new_value=f"Call summary added: {summary_display}",
            changes={
                'call_summary_id': str(instance.id),
                'action': 'added',
                'summary_preview': summary_preview,
                'call_time': str(instance.call_time) if instance.call_time else None,
                'q1_preparing_usmle_residency': instance.q1_preparing_usmle_residency,
                'q1_interested_future': instance.q1_interested_future,
                'q2_clinical_research_opportunities': instance.q2_clinical_research_opportunities,
                'q2_want_to_learn_more': instance.q2_want_to_learn_more,
                'q3_preference': instance.q3_preference,
                'q3_want_call_after_info': instance.q3_want_call_after_info,
                'call_outcome': instance.call_outcome,
            },
            notes=f"Call summary added for lead. Summary: {summary_display}"
        )
    else:
        # Record call summary updates
        old_instance = getattr(instance, '_old_instance', None)
        if old_instance:
            changes = {}
            tracked_fields = [
                'summary', 'call_time', 'is_active',
                'q1_preparing_usmle_residency', 'q1_interested_future',
                'q2_clinical_research_opportunities', 'q2_want_to_learn_more',
                'q3_preference', 'q3_want_call_after_info', 'call_outcome'
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
                    old_summary = old_instance.summary or ""
                    summary_display = f"{old_summary[:100]}..." if len(old_summary) > 100 else old_summary or "No summary"
                    LeadHistory.objects.create(
                        lead=lead,
                        tenant=tenant,
                        changed_by=changed_by,
                        action='deleted',
                        field_name='call_summary',
                        old_value=f"Call summary: {summary_display}",
                        new_value='Deleted',
                        changes={
                            'call_summary_id': str(instance.id),
                            'action': 'deleted',
                            **changes
                        },
                        notes=f"Call summary deleted for lead. Summary was: {summary_display}"
                    )
                    changes.pop('is_active', None)
                
                # Record other call summary changes if any
                if changes:
                    changed_fields = list(changes.keys())
                    LeadHistory.objects.create(
                        lead=lead,
                        tenant=tenant,
                        changed_by=changed_by,
                        action='updated',
                        field_name='call_summary',
                        old_value=f"Call summary (ID: {instance.id})",
                        new_value=f"Call summary (ID: {instance.id}) - Updated",
                        changes={
                            'call_summary_id': str(instance.id),
                            'action': 'updated',
                            **changes
                        },
                        notes=f"Call summary updated for lead. Changed fields: {', '.join(changed_fields)}"
                    )


@receiver(pre_delete, sender=LeadCallSummary)
def lead_call_summary_pre_delete(sender, instance, **kwargs):
    """Track call summary deletion in LeadHistory before the object is deleted"""
    lead = instance.lead
    tenant = instance.tenant
    
    # Ensure we're in the tenant database context
    from django.db import connections
    if hasattr(connections['default'], 'tenant'):
        connections['default'].tenant = tenant
    
    # Get the user - try to get from instance if available
    changed_by = None
    if hasattr(instance, '_changed_by'):
        changed_by = instance._changed_by
    elif hasattr(instance, 'created_by'):
        changed_by = instance.created_by
    
    # Record hard delete (if is_active is True, meaning it wasn't soft-deleted)
    if instance.is_active:
        summary_text = instance.summary or ""
        summary_preview = summary_text[:200] if len(summary_text) > 200 else summary_text
        summary_display = f"{summary_text[:100]}..." if len(summary_text) > 100 else summary_text or "No summary"
        
        LeadHistory.objects.create(
            lead=lead,
            tenant=tenant,
            changed_by=changed_by,
            action='deleted',
            field_name='call_summary',
            old_value=f"Call summary: {summary_display}",
            new_value='Hard deleted',
            changes={
                'call_summary_id': str(instance.id),
                'action': 'hard_deleted',
                'summary_preview': summary_preview,
                'call_time': str(instance.call_time) if instance.call_time else None,
                'q1_preparing_usmle_residency': instance.q1_preparing_usmle_residency,
                'q1_interested_future': instance.q1_interested_future,
                'q2_clinical_research_opportunities': instance.q2_clinical_research_opportunities,
                'q2_want_to_learn_more': instance.q2_want_to_learn_more,
                'q3_preference': instance.q3_preference,
                'q3_want_call_after_info': instance.q3_want_call_after_info,
                'call_outcome': instance.call_outcome,
            },
            notes=f"Call summary hard deleted for lead. Summary was: {summary_display}"
        )

