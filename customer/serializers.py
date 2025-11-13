from rest_framework import serializers
from .models import Customer


class CustomerSerializer(serializers.ModelSerializer):
    is_lead_created = serializers.SerializerMethodField()
    last_call_time = serializers.SerializerMethodField()
    lead_status = serializers.SerializerMethodField()
    
    class Meta:
        model = Customer
        fields = [
            'id', 'name', 'email', 'phone', 'company',
            'address', 'city', 'state', 'country', 'zip_code', 'is_active',
            'created_at', 'updated_at', 'is_lead_created', 'last_call_time', 'lead_status'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'is_lead_created', 'last_call_time', 'lead_status']
        extra_kwargs = {
            'email': {'required': True, 'allow_null': False, 'allow_blank': False},
            'phone': {'required': True, 'allow_null': False, 'allow_blank': False},
            # Align with model: company is optional and can be null/blank
            'company': {'required': False, 'allow_null': True, 'allow_blank': True},
            'is_active': {'required': True},
        }
    
    def get_is_lead_created(self, obj):
        """Check if any lead has been created for this customer"""
        # Check if annotation exists (from queryset)
        if hasattr(obj, 'is_lead_created_annotation'):
            return obj.is_lead_created_annotation
        # Fallback: check directly if not annotated
        from leads.models import Lead
        if hasattr(obj, 'tenant') and obj.tenant:
            return Lead.objects.filter(
                tenant=obj.tenant,
                customer_id=obj.id
            ).exists()
        return False
    
    def get_last_call_time(self, obj):
        """Get the most recent call_time from call summaries for this customer's leads"""
        from django.utils.dateparse import parse_datetime
        from datetime import datetime
        
        # Check if annotation exists (from queryset)
        last_call_time = None
        if hasattr(obj, 'last_call_time_annotation'):
            last_call_time = obj.last_call_time_annotation
        else:
            # Fallback: check directly if not annotated
            from leads.models import Lead, LeadCallSummary
            from django.db.models import Max
            if hasattr(obj, 'tenant') and obj.tenant:
                # Get all leads for this customer
                customer_leads = Lead.objects.filter(
                    tenant=obj.tenant,
                    customer_id=obj.id
                ).values_list('id', flat=True)
                
                if not customer_leads:
                    return None
                
                # Get the most recent call_time from call summaries
                # Use call_time if available, otherwise use created_at
                latest_call = LeadCallSummary.objects.filter(
                    tenant=obj.tenant,
                    lead_id__in=customer_leads,
                    is_active=True
                ).aggregate(
                    latest_call_time=Max('call_time'),
                    latest_created_at=Max('created_at')
                )
                
                # Return call_time if available, otherwise created_at
                last_call_time = latest_call['latest_call_time'] or latest_call['latest_created_at']
        
        # Convert datetime to ISO format string if it's a datetime object
        if last_call_time:
            if isinstance(last_call_time, datetime):
                return last_call_time.isoformat()
            elif isinstance(last_call_time, str):
                # If it's already a string, try to parse and reformat to ensure ISO format
                try:
                    dt = parse_datetime(last_call_time)
                    if dt:
                        return dt.isoformat()
                except (ValueError, TypeError):
                    pass
                return last_call_time
        return None
    
    def get_lead_status(self, obj):
        """Get the lead status for this customer"""
        # Check if annotation exists (from queryset)
        if hasattr(obj, 'lead_status_annotation'):
            return obj.lead_status_annotation
        # Fallback: calculate directly if not annotated
        from leads.models import Lead
        if hasattr(obj, 'tenant') and obj.tenant:
            # Check for leads with different statuses (priority: follow_up > interested > new > no_leads)
            has_follow_up_lead = Lead.objects.filter(
                tenant=obj.tenant,
                customer_id=obj.id,
                status='follow_up',
                is_active=True
            ).exists()
            
            if has_follow_up_lead:
                return 'ATTEMPTED_TO_CONTACT'
            
            has_interested_lead = Lead.objects.filter(
                tenant=obj.tenant,
                customer_id=obj.id,
                status='interested',
                is_active=True
            ).exists()
            
            if has_interested_lead:
                return 'INTERESTED'
            
            has_new_lead = Lead.objects.filter(
                tenant=obj.tenant,
                customer_id=obj.id,
                status='new',
                is_active=True
            ).exists()
            
            if has_new_lead:
                return 'NEW'
            
            # Check if customer has any leads at all
            has_any_lead = Lead.objects.filter(
                tenant=obj.tenant,
                customer_id=obj.id
            ).exists()
            
            if not has_any_lead:
                return 'NOT_CONTACTED'
        
        return None


class CustomerLeadStatusSerializer(serializers.Serializer):
    """Custom serializer for customers with lead status in HubSpot-like format"""
    id = serializers.SerializerMethodField()
    properties = serializers.SerializerMethodField()
    company = serializers.SerializerMethodField()
    is_lead_created = serializers.SerializerMethodField()
    last_call_time = serializers.SerializerMethodField()

    def get_id(self, obj):
        """Return customer ID as string"""
        return str(obj.id)

    def get_properties(self, obj):
        """Return properties object with phone, firstname, lastname, email, and hs_lead_status"""
        # Split name into firstname and lastname
        name_parts = (obj.name or '').strip().split(maxsplit=1)
        firstname = name_parts[0] if name_parts else ''
        lastname = name_parts[1] if len(name_parts) > 1 else ''

        # Get lead status from annotation (set in view queryset)
        hs_lead_status = None
        if hasattr(obj, 'lead_status_annotation'):
            hs_lead_status = obj.lead_status_annotation

        # Use customer phone if available, otherwise use lead phone (from annotation)
        customer_phone = obj.phone or ''
        lead_phone = getattr(obj, 'lead_phone', None) or ''
        phone = customer_phone if customer_phone else lead_phone
        
        # Remove '-' characters from phone number if present
        phone = phone.replace('-', '')

        properties = {
            'phone': phone,
        }

        # Add optional fields only if they have values
        if firstname:
            properties['firstname'] = firstname
        if lastname:
            properties['lastname'] = lastname
        if obj.email:
            properties['email'] = obj.email
        if hs_lead_status:
            properties['hs_lead_status'] = hs_lead_status

        return properties

    def get_company(self, obj):
        """Return company object if company name exists"""
        if obj.company:
            return {
                'name': obj.company
            }
        return None
    
    def get_is_lead_created(self, obj):
        """Check if any lead has been created for this customer"""
        # Check if annotation exists (from queryset)
        if hasattr(obj, 'is_lead_created_annotation'):
            return obj.is_lead_created_annotation
        # Fallback: check directly if not annotated
        from leads.models import Lead
        if hasattr(obj, 'tenant') and obj.tenant:
            return Lead.objects.filter(
                tenant=obj.tenant,
                customer_id=obj.id
            ).exists()
        return False
    
    def get_last_call_time(self, obj):
        """Get the most recent call_time from call summaries for this customer's leads"""
        from django.utils.dateparse import parse_datetime
        from datetime import datetime
        
        # Check if annotation exists (from queryset)
        last_call_time = None
        if hasattr(obj, 'last_call_time_annotation'):
            last_call_time = obj.last_call_time_annotation
        else:
            # Fallback: check directly if not annotated
            from leads.models import Lead, LeadCallSummary
            from django.db.models import Max
            if hasattr(obj, 'tenant') and obj.tenant:
                # Get all leads for this customer
                customer_leads = Lead.objects.filter(
                    tenant=obj.tenant,
                    customer_id=obj.id
                ).values_list('id', flat=True)
                
                if not customer_leads:
                    return None
                
                # Get the most recent call_time from call summaries
                # Use call_time if available, otherwise use created_at
                latest_call = LeadCallSummary.objects.filter(
                    tenant=obj.tenant,
                    lead_id__in=customer_leads,
                    is_active=True
                ).aggregate(
                    latest_call_time=Max('call_time'),
                    latest_created_at=Max('created_at')
                )
                
                # Return call_time if available, otherwise created_at
                last_call_time = latest_call['latest_call_time'] or latest_call['latest_created_at']
        
        # Convert datetime to ISO format string if it's a datetime object
        if last_call_time:
            if isinstance(last_call_time, datetime):
                return last_call_time.isoformat()
            elif isinstance(last_call_time, str):
                # If it's already a string, try to parse and reformat to ensure ISO format
                try:
                    dt = parse_datetime(last_call_time)
                    if dt:
                        return dt.isoformat()
                except (ValueError, TypeError):
                    pass
                return last_call_time
        return None
