from rest_framework import status, generics, filters
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from django.utils.decorators import method_decorator
 

from .models import Lead, LeadHistory, LeadCallSummary
from customer.models import Customer
from .serializers import LeadSerializer, LeadStatusUpdateSerializer, LeadCallSummarySerializer
from .history_serializers import LeadHistorySerializer
from user.models import CustomUser
from .importer import detect_and_parse_tabular, normalize_lead_row


@method_decorator(
    name='get',
    decorator=swagger_auto_schema(
        tags=['Leads'],
        responses={
            200: openapi.Response(
                description='List leads',
                examples={
                    'application/json': {
                        'count': 1,
                        'next': None,
                        'previous': None,
                        'results': [
                            {
                                'id': 'uuid-here',
                                'name': 'Website Inquiry',
                                'status': 'new',
                                'customer': 'uuid-of-customer',
                                'is_active': True,
                            }
                        ],
                    }
                },
            )
        },
    ),
)
@method_decorator(
    name='post',
    decorator=swagger_auto_schema(
        tags=['Leads'],
        operation_description='Create a lead (link customer by ID or email)',
        responses={
            201: openapi.Response(
                description='Lead created',
                examples={
                    'application/json': {
                        'id': 'uuid-here',
                        'name': 'Website Inquiry',
                        'status': 'new',
                        'customer': 'uuid-of-customer',
                        'is_active': True,
                    }
                },
            ),
            400: openapi.Response(description='Validation error'),
            401: openapi.Response(description='Authentication required'),
        },
    ),
)
class LeadListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = LeadSerializer
    filter_backends = [filters.SearchFilter]
    search_fields = ['name', 'email', 'phone', 'status', 'customer__name', 'customer__email']

    def get_queryset(self):
        # Scope to current tenant
        if not hasattr(self.request.user, 'tenant') or not self.request.user.tenant:
            return Lead.objects.none()
        from django.db import connections
        connections['default'].tenant = self.request.user.tenant
        # Default ordering: newest first
        return (
            Lead.objects.filter(tenant=self.request.user.tenant, is_active=True)
            .select_related('customer')
            .order_by('-created_at')
        )

    
    def create(self, request, *args, **kwargs):
        if not request.user or not request.user.is_authenticated:
            return Response({'detail': 'Authentication required'}, status=status.HTTP_401_UNAUTHORIZED)
        if not hasattr(request.user, 'tenant') or not request.user.tenant:
            return Response({'detail': 'No tenant associated'}, status=status.HTTP_400_BAD_REQUEST)
        from django.db import connections
        connections['default'].tenant = request.user.tenant

        # Resolve a user that actually exists inside the current tenant DB.
        # If the authenticated user hasn't been copied into the tenant DB yet,
        # fall back to None to avoid FK errors.
        tenant_user = CustomUser.objects.filter(id=request.user.id).first()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated = dict(serializer.validated_data)

        # Link or create customer if customer id not explicitly provided
        customer = validated.pop('customer', None)
        customer_email = validated.pop('customer_email', None)
        customer_name = validated.pop('customer_name', None)

        # Validate customer if provided by ID
        if customer:
            # Ensure customer belongs to the same tenant
            if customer.tenant != request.user.tenant:
                return Response(
                    {'detail': 'Customer does not belong to the current tenant'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            if not customer.is_active:
                return Response(
                    {'detail': 'Customer is inactive'},
                    status=status.HTTP_400_BAD_REQUEST
                )

        if not customer and customer_email:
            # Ensure we operate in the tenant database
            try:
                customer = Customer.objects.get(tenant=request.user.tenant, email=customer_email, is_active=True)
            except Customer.DoesNotExist:
                customer = Customer.objects.create(
                    tenant=request.user.tenant,
                    created_by=tenant_user,
                    name=customer_name or validated.get('name') or customer_email.split('@')[0],
                    email=customer_email,
                    is_active=True,
                )
            except Customer.MultipleObjectsReturned:
                # Handle duplicate emails (shouldn't happen due to unique constraint, but handle gracefully)
                customer = Customer.objects.filter(tenant=request.user.tenant, email=customer_email, is_active=True).first()

        lead = Lead(
            tenant=request.user.tenant,
            created_by=tenant_user,  # may be None if user isn't present in tenant DB
            customer=customer,
            **validated,
        )
        # Attach user for history tracking
        lead._changed_by = tenant_user
        lead.save()
        return Response(LeadSerializer(lead, context={'request': request}).data, status=status.HTTP_201_CREATED)


@method_decorator(
    name='get',
    decorator=swagger_auto_schema(
        tags=['Leads'],
        responses={
            200: openapi.Response(
                description='Retrieve lead',
                examples={
                    'application/json': {
                        'id': 'uuid-here',
                        'name': 'Website Inquiry',
                        'status': 'new',
                        'customer': 'uuid-of-customer',
                        'is_active': True,
                    }
                },
            ),
            404: openapi.Response(description='Not found'),
        },
    ),
)
@method_decorator(
    name='patch',
    decorator=swagger_auto_schema(
        tags=['Leads'],
        responses={
            200: openapi.Response(
                description='Lead updated',
                examples={
                    'application/json': {
                        'id': 'uuid-here',
                        'name': 'Website Inquiry',
                        'status': 'contacted',
                        'customer': 'uuid-of-customer',
                        'is_active': True,
                    }
                },
            ),
            400: openapi.Response(description='Validation error'),
        },
    ),
)
@method_decorator(
    name='delete',
    decorator=swagger_auto_schema(
        tags=['Leads'],
        responses={
            200: openapi.Response(
                description='Soft delete confirmation',
                examples={'application/json': {'message': 'Lead soft-deleted'}},
            ),
        },
    ),
)
class LeadDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = LeadSerializer
    lookup_field = 'pk'
    http_method_names = ['get', 'patch', 'delete']  # Exclude PUT

    def get_queryset(self):
        if not hasattr(self.request.user, 'tenant') or not self.request.user.tenant:
            return Lead.objects.none()
        from django.db import connections
        connections['default'].tenant = self.request.user.tenant
        return Lead.objects.filter(tenant=self.request.user.tenant, is_active=True).select_related('customer')

    def perform_update(self, serializer):
        if not hasattr(self.request.user, 'tenant') or not self.request.user.tenant:
            from rest_framework.exceptions import ValidationError
            raise ValidationError({'detail': 'No tenant associated with user'})
        from django.db import connections
        connections['default'].tenant = self.request.user.tenant
        # Get tenant user for history tracking
        tenant_user = CustomUser.objects.filter(id=self.request.user.id).first()
        instance = serializer.instance
        instance._changed_by = tenant_user
        serializer.save()

    def delete(self, request, *args, **kwargs):
        if not hasattr(request.user, 'tenant') or not request.user.tenant:
            return Response({'detail': 'No tenant associated with user'}, status=status.HTTP_400_BAD_REQUEST)
        instance = self.get_object()
        from django.db import connections
        connections['default'].tenant = request.user.tenant
        # Get tenant user for history tracking
        tenant_user = CustomUser.objects.filter(id=request.user.id).first()
        instance.is_active = False
        instance._changed_by = tenant_user
        instance.save(update_fields=['is_active', 'updated_at'])
        # History will be tracked by the signal
        return Response({'message': 'Lead soft-deleted'}, status=status.HTTP_200_OK)


@method_decorator(
    name='patch',
    decorator=swagger_auto_schema(
        tags=['Leads'],
        operation_description='Update lead status',
        responses={
            200: openapi.Response(
                description='Lead status updated',
                examples={
                    'application/json': {
                        'id': 'uuid-here',
                        'name': 'Website Inquiry',
                        'status': 'interested',
                        'customer': 'uuid-of-customer',
                        'is_active': True,
                    }
                },
            ),
            400: openapi.Response(description='Validation error'),
        },
    ),
)
class LeadStatusUpdateView(generics.UpdateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = LeadStatusUpdateSerializer
    lookup_field = 'pk'
    http_method_names = ['patch']
    # Ensure tag grouping in Swagger under "Leads" (not auto path-based "leads")
    swagger_schema_fields = {"tags": ["Leads"]}

    def get_queryset(self):
        if not hasattr(self.request.user, 'tenant') or not self.request.user.tenant:
            return Lead.objects.none()
        from django.db import connections
        connections['default'].tenant = self.request.user.tenant
        return Lead.objects.filter(tenant=self.request.user.tenant, is_active=True)

    def patch(self, request, *args, **kwargs):
        if not hasattr(request.user, 'tenant') or not request.user.tenant:
            return Response({'detail': 'No tenant associated with user'}, status=status.HTTP_400_BAD_REQUEST)
        from django.db import connections
        connections['default'].tenant = request.user.tenant
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        # Get tenant user for history tracking
        tenant_user = CustomUser.objects.filter(id=request.user.id).first()
        instance._changed_by = tenant_user
        serializer.save()
        return Response(LeadSerializer(instance, context={'request': request}).data, status=status.HTTP_200_OK)


@method_decorator(
    name='post',
    decorator=swagger_auto_schema(
        tags=['Leads'],
        operation_description='Import leads via CSV or Excel (.xlsx). By default links existing customer by email or auto-creates if missing. Disable creation with ?auto_create_customer=false',
        manual_parameters=[
            openapi.Parameter(
                'file', openapi.IN_FORM, description='CSV or XLSX file', type=openapi.TYPE_FILE, required=True
            ),
            openapi.Parameter(
                'auto_create_customer', openapi.IN_QUERY, description='If true (default), create customer when not found by email', type=openapi.TYPE_BOOLEAN, required=False
            ),
        ],
        responses={
            200: openapi.Response(
                description='Import summary',
                examples={
                    'application/json': {
                        'processed': 10,
                        'created': 8,
                        'updated': 0,
                        'skipped': 2,
                        'errors': [
                            {'row': 3, 'error': 'name is required'}
                        ],
                    }
                },
            )
        },
    ),
)
class LeadImportView(APIView):
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, *args, **kwargs):
        if not request.user or not request.user.is_authenticated:
            return Response({'detail': 'Authentication required'}, status=status.HTTP_401_UNAUTHORIZED)
        if not getattr(request.user, 'tenant', None):
            return Response({'detail': 'No tenant associated'}, status=status.HTTP_400_BAD_REQUEST)

        file_obj = request.FILES.get('file')
        if not file_obj:
            return Response({'detail': 'file is required'}, status=status.HTTP_400_BAD_REQUEST)

        from django.db import connections
        connections['default'].tenant = request.user.tenant

        tenant_user = CustomUser.objects.filter(id=request.user.id).first()
        if not tenant_user:
            tenant_user = CustomUser.objects.create(
                id=request.user.id,
                username=request.user.username,
                email=request.user.email,
                first_name=request.user.first_name,
                last_name=request.user.last_name,
                is_active=request.user.is_active,
                is_staff=request.user.is_staff,
                is_superuser=request.user.is_superuser,
                password=request.user.password,
                tenant=request.user.tenant,
            )

        try:
            rows, _fmt = detect_and_parse_tabular(file_obj, file_obj.name)
        except Exception as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        auto_create_param = str(request.query_params.get('auto_create_customer', 'true')).strip().lower()
        auto_create_customer = auto_create_param not in ('false', '0', 'no')

        processed = created = updated = skipped = 0
        errors = []
        for idx, raw in enumerate(rows, start=2):
            processed += 1
            data = normalize_lead_row(raw)
            name = (data.get('name') or '') if data else ''
            if not name:
                skipped += 1
                errors.append({'row': idx, 'error': 'name is required'})
                continue
            try:
                # Optional link/create customer by email
                customer = None
                cust_email = (data.get('customer_email') or '').strip() if data.get('customer_email') else ''
                cust_name = (data.get('customer_name') or '').strip() if data.get('customer_name') else ''
                if cust_email:
                    try:
                        # Try to link any existing customer by email (regardless of active flag)
                        customer = Customer.objects.get(
                            tenant=request.user.tenant, email=cust_email
                        )
                        # Optionally re-activate if auto-create is on and record is inactive
                        if auto_create_customer and customer.is_active is False:
                            customer.is_active = True
                            customer.save(update_fields=['is_active'])
                    except Customer.DoesNotExist:
                        if auto_create_customer:
                            # Auto-create minimal customer when enabled
                            customer = Customer.objects.create(
                                tenant=request.user.tenant,
                                created_by=tenant_user,
                                name=(cust_name or cust_email.split('@')[0]),
                                email=cust_email,
                                is_active=True,
                            )
                        else:
                            customer = None

                lead = Lead(
                    tenant=request.user.tenant,
                    created_by=tenant_user,
                    customer=customer,
                    name=name,
                    email=data.get('email'),
                    phone=data.get('phone'),
                    status=data.get('status') or 'new',
                    source=data.get('source'),
                    notes=data.get('notes'),
                    is_active=data.get('is_active', True),
                )
                # Attach user for history tracking
                lead._changed_by = tenant_user
                lead.save()
                created += 1
            except Exception as exc:
                skipped += 1
                errors.append({'row': idx, 'error': str(exc)})

        return Response(
            {
                'processed': processed,
                'created': created,
                'updated': updated,
                'skipped': skipped,
                'errors': errors,
            },
            status=status.HTTP_200_OK,
        )


@method_decorator(
    name='get',
    decorator=swagger_auto_schema(
        tags=['Leads'],
        operation_description='Get history of all changes for a specific lead by ID',
        responses={
            200: openapi.Response(
                description='Lead history retrieved successfully',
                examples={
                    'application/json': {
                        'count': 2,
                        'next': None,
                        'previous': None,
                        'results': [
                            {
                                'id': 'uuid-here',
                                'action': 'created',
                                'field_name': None,
                                'old_value': None,
                                'new_value': None,
                                'changes': {'all_fields': 'Lead created'},
                                'notes': 'Lead was created',
                                'changed_by_username': 'john.doe',
                                'changed_by_email': 'john@example.com',
                                'created_at': '2024-01-01T12:00:00Z',
                            },
                            {
                                'id': 'uuid-here',
                                'action': 'status_changed',
                                'field_name': 'status',
                                'old_value': 'new',
                                'new_value': 'open',
                                'changes': {'status': {'old': 'new', 'new': 'open'}},
                                'notes': 'Status changed from new to open',
                                'changed_by_username': 'john.doe',
                                'changed_by_email': 'john@example.com',
                                'created_at': '2024-01-02T12:00:00Z',
                            },
                        ],
                    }
                },
            ),
            404: openapi.Response(description='Lead not found'),
        },
    ),
)
class LeadHistoryView(generics.ListAPIView):
    """API endpoint to retrieve history of changes for a specific lead"""
    permission_classes = [IsAuthenticated]
    serializer_class = LeadHistorySerializer
    lookup_field = 'pk'

    def get_queryset(self):
        if not hasattr(self.request.user, 'tenant') or not self.request.user.tenant:
            return LeadHistory.objects.none()
        
        from django.db import connections
        connections['default'].tenant = self.request.user.tenant
        
        lead_id = self.kwargs.get('pk')
        
        # Verify lead exists and belongs to tenant
        try:
            lead = Lead.objects.get(id=lead_id, tenant=self.request.user.tenant)
        except Lead.DoesNotExist:
            return LeadHistory.objects.none()
        
        return LeadHistory.objects.filter(
            lead=lead,
            tenant=self.request.user.tenant
        ).select_related('changed_by').order_by('-created_at')


@method_decorator(
    name='get',
    decorator=swagger_auto_schema(
        tags=['Leads'],
        operation_description='List call summaries for a lead',
    ),
)
@method_decorator(
    name='post',
    decorator=swagger_auto_schema(
        tags=['Leads'],
        operation_description='Create a call summary for a lead',
    ),
)
class LeadCallSummaryListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = LeadCallSummarySerializer

    def get_queryset(self):
        if not hasattr(self.request.user, 'tenant') or not self.request.user.tenant:
            return LeadCallSummary.objects.none()
        from django.db import connections
        connections['default'].tenant = self.request.user.tenant
        lead_id = self.kwargs.get('pk')
        return LeadCallSummary.objects.filter(
            tenant=self.request.user.tenant,
            lead_id=lead_id,
            is_active=True,
        ).order_by('-created_at')

    def perform_create(self, serializer):
        if not hasattr(self.request.user, 'tenant') or not self.request.user.tenant:
            from rest_framework.exceptions import ValidationError
            raise ValidationError({'detail': 'No tenant associated with user'})
        from django.db import connections
        connections['default'].tenant = self.request.user.tenant
        lead_id = self.kwargs.get('pk')
        try:
            lead = Lead.objects.get(id=lead_id, tenant=self.request.user.tenant, is_active=True)
        except Lead.DoesNotExist:
            from rest_framework.exceptions import NotFound
            raise NotFound('Lead not found')
        tenant_user = CustomUser.objects.filter(id=self.request.user.id).first()
        # Save instance - signal will use created_by for history tracking on create
        serializer.save(tenant=self.request.user.tenant, lead=lead, created_by=tenant_user)


@method_decorator(
    name='get',
    decorator=swagger_auto_schema(
        tags=['Leads'],
        operation_description='Retrieve a call summary',
    ),
)
@method_decorator(
    name='patch',
    decorator=swagger_auto_schema(
        tags=['Leads'],
        operation_description='Update a call summary',
    ),
)
@method_decorator(
    name='delete',
    decorator=swagger_auto_schema(
        tags=['Leads'],
        operation_description='Soft delete a call summary',
    ),
)
class LeadCallSummaryDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = LeadCallSummarySerializer
    lookup_field = 'summary_id'
    http_method_names = ['get', 'patch', 'delete']

    def get_queryset(self):
        if not hasattr(self.request.user, 'tenant') or not self.request.user.tenant:
            return LeadCallSummary.objects.none()
        from django.db import connections
        connections['default'].tenant = self.request.user.tenant
        lead_id = self.kwargs.get('pk')
        return LeadCallSummary.objects.filter(
            tenant=self.request.user.tenant,
            lead_id=lead_id,
            is_active=True,
        )

    def get_object(self):
        queryset = self.get_queryset()
        obj = queryset.filter(id=self.kwargs.get('summary_id')).first()
        if not obj:
            from rest_framework.exceptions import NotFound
            raise NotFound('Call summary not found')
        return obj

    def perform_update(self, serializer):
        if not hasattr(self.request.user, 'tenant') or not self.request.user.tenant:
            from rest_framework.exceptions import ValidationError
            raise ValidationError({'detail': 'No tenant associated with user'})
        from django.db import connections
        connections['default'].tenant = self.request.user.tenant
        # Get tenant user for history tracking
        tenant_user = CustomUser.objects.filter(id=self.request.user.id).first()
        instance = serializer.instance
        instance._changed_by = tenant_user
        serializer.save()

    def perform_destroy(self, instance):
        if not hasattr(self.request.user, 'tenant') or not self.request.user.tenant:
            from rest_framework.exceptions import ValidationError
            raise ValidationError({'detail': 'No tenant associated with user'})
        from django.db import connections
        connections['default'].tenant = self.request.user.tenant
        # Get tenant user for history tracking
        tenant_user = CustomUser.objects.filter(id=self.request.user.id).first()
        instance._changed_by = tenant_user
        instance.is_active = False
        instance.save(update_fields=['is_active', 'updated_at'])


@method_decorator(
    name='post',
    decorator=swagger_auto_schema(
        tags=['Leads'],
        operation_description='Create a call summary for a customer by customer ID. Automatically finds or creates a lead for the customer.',
        request_body=LeadCallSummarySerializer,
        responses={
            201: openapi.Response(
                description='Call summary created successfully',
                schema=LeadCallSummarySerializer,
            ),
            400: openapi.Response(description='Validation error'),
            404: openapi.Response(description='Customer not found'),
        },
    ),
)
class CustomerCallSummaryCreateView(APIView):
    """Create a call summary for a customer by customer ID"""
    permission_classes = [IsAuthenticated]
    
    def post(self, request, customer_id):
        if not hasattr(request.user, 'tenant') or not request.user.tenant:
            return Response({'detail': 'No tenant associated with user'}, status=status.HTTP_400_BAD_REQUEST)
        
        from django.db import connections
        connections['default'].tenant = request.user.tenant
        
        # Get customer
        try:
            customer = Customer.objects.get(id=customer_id, tenant=request.user.tenant, is_active=True)
        except Customer.DoesNotExist:
            return Response({'detail': 'Customer not found'}, status=status.HTTP_404_NOT_FOUND)
        
        # Find existing lead for this customer (if exists, we'll update its status)
        # Only create a new lead if none exists
        lead = Lead.objects.filter(
            tenant=request.user.tenant,
            customer=customer,
            is_active=True
        ).order_by('-created_at').first()
        
        tenant_user = CustomUser.objects.filter(id=request.user.id).first()
        
        if not lead:
            # No existing lead found, create a new one for this customer
            lead = Lead.objects.create(
                tenant=request.user.tenant,
                customer=customer,
                name=customer.name,
                email=customer.email,
                phone=customer.phone,
                status='follow_up' if request.data.get('call_outcome') == 'follow_up' else 'new',
                source='Call Summary',
                created_by=tenant_user,
                is_active=True
            )
            lead._changed_by = tenant_user
            # History will be tracked by the lead_post_save signal
        # If lead already exists, we'll update its status after creating the call summary
        
        # Create call summary using the existing serializer logic
        serializer = LeadCallSummarySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        tenant_user = CustomUser.objects.filter(id=request.user.id).first()
        call_summary = serializer.save(
            tenant=request.user.tenant,
            lead=lead,
            created_by=tenant_user
        )
        
        # Update lead status based on call summary answers
        # If any question is answered "no" → not_interested
        # If all questions are "yes" → interested
        from .models import LeadStatus
        
        q1_is_yes = None
        q2_is_yes = None
        q3_is_yes = None
        
        # Check Q1: Yes if preparing OR (not preparing but interested in future)
        q1_preparing = call_summary.q1_preparing_usmle_residency
        q1_interested = call_summary.q1_interested_future
        
        if q1_preparing is not None:
            if q1_preparing is True:
                q1_is_yes = True
            elif q1_preparing is False:
                if q1_interested is True:
                    q1_is_yes = True
                elif q1_interested is False:
                    q1_is_yes = False  # No to both = No
        
        # Check Q2: Yes if looking for opportunities OR (not looking but wants to learn more)
        q2_clinical = call_summary.q2_clinical_research_opportunities
        q2_learn_more = call_summary.q2_want_to_learn_more
        
        if q2_clinical is not None:
            if q2_clinical is True:
                q2_is_yes = True
            elif q2_clinical is False:
                if q2_learn_more is True:
                    q2_is_yes = True
                elif q2_learn_more is False:
                    q2_is_yes = False  # No to both = No
        
        # Check Q3: Yes if wants call/both OR (wants info and also wants call)
        q3_preference = call_summary.q3_preference
        q3_want_call = call_summary.q3_want_call_after_info
        
        if q3_preference:
            if q3_preference in ['call', 'both']:
                q3_is_yes = True
            elif q3_preference == 'none':
                q3_is_yes = False
            elif q3_preference == 'info':
                if q3_want_call is True:
                    q3_is_yes = True
                elif q3_want_call is False:
                    q3_is_yes = False  # Info only, doesn't want call = No
        
        # Determine status: if any No → not_interested, if all Yes → interested
        answers = [q1_is_yes, q2_is_yes, q3_is_yes]
        answered_questions = [a for a in answers if a is not None]
        
        if not answered_questions:
            # No questions answered, keep current status
            new_status = lead.status
        elif any(a is False for a in answered_questions):
            # At least one "No" answer
            new_status = LeadStatus.NOT_INTERESTED
        elif all(a is True for a in answered_questions):
            # All answered questions are "Yes"
            new_status = LeadStatus.INTERESTED
        else:
            # Mixed or incomplete answers
            new_status = LeadStatus.CONTACTED
        
        # Update lead status if it changed
        if lead.status != new_status:
            lead.status = new_status
            lead._changed_by = tenant_user
            lead.save(update_fields=['status', 'updated_at'])
        
        return Response(LeadCallSummarySerializer(call_summary).data, status=status.HTTP_201_CREATED)