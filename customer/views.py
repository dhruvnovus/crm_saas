from rest_framework import status, generics, filters
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from django.utils.decorators import method_decorator
from django.db import models
from django.conf import settings
import requests
import logging
from .models import Customer, CustomerHistory
from user.models import CustomUser
from .serializers import CustomerSerializer, CustomerLeadStatusSerializer
from .history_serializers import CustomerHistorySerializer
from .importer import detect_and_parse_tabular, normalize_customer_row
from leads.models import Lead, LeadStatus

logger = logging.getLogger(__name__)


@method_decorator(
    name='get',
    decorator=swagger_auto_schema(
        tags=['Customers'],
        responses={
            200: openapi.Response(
                description='List customers',
                examples={
                    'application/json': {
                        'count': 1,
                        'next': None,
                        'previous': None,
                        'results': [
                            {
                                'id': 'uuid-here',
                                'name': 'Acme Contact',
                                'email': 'contact@acme.com',
                                'phone': '+1-202-555-0114',
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
        tags=['Customers'],
        operation_description='Create a customer in the current tenant',
        responses={
            201: openapi.Response(
                description='Customer created',
                examples={
                    'application/json': {
                        'id': 'uuid-here',
                        'name': 'Acme Contact',
                        'email': 'contact@acme.com',
                        'phone': '+1-202-555-0114',
                        'is_active': True,
                    }
                },
            ),
            400: openapi.Response(description='Validation error'),
        },
    ),
)
class CustomerListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = CustomerSerializer
    filter_backends = [filters.SearchFilter]
    search_fields = ['name', 'email', 'phone', 'company', 'city', 'state', 'country']

    def get_queryset(self):
        # Scope to current tenant
        if hasattr(self.request.user, 'tenant') and self.request.user.tenant:
            from django.db import connections
            connections['default'].tenant = self.request.user.tenant
            # Default ordering: newest first
            return Customer.objects.filter(tenant=self.request.user.tenant).order_by('-created_at')
        return Customer.objects.none()

    def create(self, request, *args, **kwargs):
        if not request.user or not request.user.is_authenticated:
            return Response({'detail': 'Authentication required'}, status=status.HTTP_401_UNAUTHORIZED)
        if not request.user.tenant:
            return Response({'detail': 'No tenant associated'}, status=status.HTTP_400_BAD_REQUEST)
        from django.db import connections
        connections['default'].tenant = request.user.tenant
        # Ensure the acting user exists in the tenant database so FK constraints pass
        # Some flows authenticate against the main DB; we mirror the user into the
        # tenant DB on-demand using the same primary key.
        try:
            # Check presence in the tenant DB context
            CustomUser.objects.get(id=request.user.id)
        except CustomUser.DoesNotExist:
            # Create a lightweight clone in the tenant DB with the same ID
            # Password hash and flags are copied to preserve auth semantics if used.
            CustomUser.objects.create(
                id=request.user.id,
                username=request.user.username,
                email=request.user.email,
                first_name=request.user.first_name,
                last_name=request.user.last_name,
                is_active=request.user.is_active,
                is_staff=request.user.is_staff,
                is_superuser=request.user.is_superuser,
                password=request.user.password,
                # IMPORTANT: Do not set tenant FK inside tenant DB to avoid
                # cross-database FK constraint issues. Leave it NULL here.
                tenant=None,
            )
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        customer = Customer(
            tenant=request.user.tenant,
            created_by=request.user,
            **serializer.validated_data,
        )
        # Attach user for history tracking
        customer._changed_by = request.user
        customer.save()
        return Response(CustomerSerializer(customer).data, status=status.HTTP_201_CREATED)


@method_decorator(
    name='get',
    decorator=swagger_auto_schema(
        tags=['Customers'],
        responses={
            200: openapi.Response(
                description='Retrieve customer',
                examples={
                    'application/json': {
                        'id': 'uuid-here',
                        'name': 'Acme Contact',
                        'email': 'contact@acme.com',
                        'phone': '+1-202-555-0114',
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
        tags=['Customers'],
        responses={
            200: openapi.Response(
                description='Customer updated',
                examples={
                    'application/json': {
                        'id': 'uuid-here',
                        'name': 'Acme Contact Updated',
                        'email': 'contact@acme.com',
                        'phone': '+1-202-555-0114',
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
        tags=['Customers'],
        responses={
            200: openapi.Response(
                description='Soft delete confirmation',
                examples={'application/json': {'message': 'Customer soft-deleted'}},
            ),
        },
    ),
)
class CustomerDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = CustomerSerializer
    lookup_field = 'pk'
    http_method_names = ['get', 'patch', 'delete']  # Exclude PUT

    def get_queryset(self):
        if hasattr(self.request.user, 'tenant') and self.request.user.tenant:
            from django.db import connections
            connections['default'].tenant = self.request.user.tenant
            return Customer.objects.filter(tenant=self.request.user.tenant)
        return Customer.objects.none()

    def perform_update(self, serializer):
        from django.db import connections
        connections['default'].tenant = self.request.user.tenant
        # Get tenant user for history tracking
        tenant_user = CustomUser.objects.filter(id=self.request.user.id).first()
        instance = serializer.instance
        instance._changed_by = tenant_user if tenant_user else self.request.user
        serializer.save()

    def delete(self, request, *args, **kwargs):
        instance = self.get_object()
        from django.db import connections
        connections['default'].tenant = self.request.user.tenant
        # Get tenant user for history tracking
        tenant_user = CustomUser.objects.filter(id=request.user.id).first()
        instance.is_active = False
        instance._changed_by = tenant_user if tenant_user else request.user
        instance.save(update_fields=['is_active', 'updated_at'])
        # History will be tracked by the signal
        return Response({'message': 'Customer soft-deleted'}, status=status.HTTP_200_OK)


@method_decorator(
    name='post',
    decorator=swagger_auto_schema(
        tags=['Customers'],
        operation_description='Import customers via CSV or Excel (.xlsx)',
        manual_parameters=[
            openapi.Parameter(
                'file', openapi.IN_FORM, description='CSV or XLSX file', type=openapi.TYPE_FILE, required=True
            )
        ],
        responses={
            200: openapi.Response(
                description='Import summary',
                examples={
                    'application/json': {
                        'processed': 10,
                        'created': 7,
                        'updated': 2,
                        'skipped': 1,
                        'errors': [
                            {'row': 5, 'error': 'Email is required'}
                        ],
                    }
                },
            )
        },
    ),
)
class CustomerImportView(APIView):
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

        # Ensure user exists inside tenant DB context
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
                # IMPORTANT: Prevent FK error by keeping tenant NULL inside tenant DB
                tenant=None,
            )

        try:
            rows, _fmt = detect_and_parse_tabular(file_obj, file_obj.name)
        except Exception as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        processed = created = updated = skipped = 0
        errors = []
        for idx, raw in enumerate(rows, start=2):  # assuming row 1 is header
            processed += 1
            data = normalize_customer_row(raw)
            email = (data.get('email') or '') if data else ''
            name = (data.get('name') or '') if data else ''
            if not email:
                skipped += 1
                errors.append({'row': idx, 'error': 'Email is required'})
                continue
            try:
                if not name:
                    name = email.split('@')[0]
                defaults = {
                    'name': name,
                    'phone': data.get('phone'),
                    'company': data.get('company'),
                    'address': data.get('address'),
                    'city': data.get('city'),
                    'state': data.get('state'),
                    'country': data.get('country'),
                    'zip_code': data.get('zip_code'),
                    'is_active': data.get('is_active', True),
                    'created_by': tenant_user,
                }
                obj, created_flag = Customer.objects.update_or_create(
                    tenant=request.user.tenant,
                    email=email,
                    defaults=defaults,
                )
                # Attach user for history tracking
                obj._changed_by = tenant_user
                if created_flag:
                    created += 1
                else:
                    updated += 1
                obj.save()
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
        tags=['Customers'],
        operation_description='Get history of all changes for a specific customer by ID',
        responses={
            200: openapi.Response(
                description='Customer history retrieved successfully',
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
                                'changes': {'all_fields': 'Customer created'},
                                'notes': 'Customer was created',
                                'changed_by_username': 'john.doe',
                                'changed_by_email': 'john@example.com',
                                'created_at': '2024-01-01T12:00:00Z',
                            },
                            {
                                'id': 'uuid-here',
                                'action': 'updated',
                                'field_name': 'name, phone',
                                'old_value': None,
                                'new_value': None,
                                'changes': {
                                    'name': {'old': 'Old Name', 'new': 'New Name'},
                                    'phone': {'old': '123', 'new': '456'}
                                },
                                'notes': 'Updated fields: name, phone',
                                'changed_by_username': 'john.doe',
                                'changed_by_email': 'john@example.com',
                                'created_at': '2024-01-02T12:00:00Z',
                            },
                        ],
                    }
                },
            ),
            404: openapi.Response(description='Customer not found'),
        },
    ),
)
class CustomerHistoryView(generics.ListAPIView):
    """API endpoint to retrieve history of changes for a specific customer"""
    permission_classes = [IsAuthenticated]
    serializer_class = CustomerHistorySerializer
    lookup_field = 'pk'

    def get_queryset(self):
        if not hasattr(self.request.user, 'tenant') or not self.request.user.tenant:
            return CustomerHistory.objects.none()
        
        from django.db import connections
        connections['default'].tenant = self.request.user.tenant
        
        customer_id = self.kwargs.get('pk')
        
        # Verify customer exists and belongs to tenant
        try:
            customer = Customer.objects.get(id=customer_id, tenant=self.request.user.tenant)
        except Customer.DoesNotExist:
            return CustomerHistory.objects.none()
        
        return CustomerHistory.objects.filter(
            customer=customer,
            tenant=self.request.user.tenant
        ).select_related('changed_by').order_by('-created_at')


@method_decorator(
    name='get',
    decorator=swagger_auto_schema(
        tags=['Customers'],
        operation_description='Get customers that match any of: no leads, follow-up leads, new status leads, or interested status leads (no pagination). Returns HubSpot-like format.',
        responses={
            200: openapi.Response(
                description='List of customers in HubSpot format',
                examples={
                    'application/json': [
                        {
                            'id': '161292840091',
                            'properties': {
                                'phone': '+918490981272',
                                'firstname': 'olivia',
                                'lastname': 'thompson',
                                'email': 'olivia.thompson@yopmail.com',
                                'hs_lead_status': 'ATTEMPTED_TO_CONTACT',
                            },
                            'company': {
                                'name': 'Medical Center Inc',
                            },
                        },
                        {
                            'id': '161292840092',
                            'properties': {
                                'phone': '+918490981273',
                                'firstname': 'john',
                                'lastname': 'doe',
                                'email': 'john.doe@example.com',
                                'hs_lead_status': 'INTERESTED',
                            },
                        }
                    ],
                },
            )
        },
    ),
)
class CustomersByLeadStatusView(generics.ListAPIView):
    """API endpoint to retrieve customers that have no leads, follow-up leads, new status leads, or interested status leads"""
    permission_classes = [IsAuthenticated]
    serializer_class = CustomerLeadStatusSerializer
    filter_backends = [filters.SearchFilter]
    search_fields = ['name', 'email', 'phone', 'company', 'city', 'state', 'country']
    pagination_class = None  # Disable pagination

    def get_queryset(self):
        if not hasattr(self.request.user, 'tenant') or not self.request.user.tenant:
            return Customer.objects.none()
        
        from django.db import connections
        from django.db.models import Q, Exists, OuterRef, Case, When, Value, CharField, Subquery
        connections['default'].tenant = self.request.user.tenant
        
        # Base queryset for active customers
        base_queryset = Customer.objects.filter(
            tenant=self.request.user.tenant,
            is_active=True
        )
        
        # Build conditions using subqueries for better performance
        # 1. Customers with no leads at all
        has_any_lead = Lead.objects.filter(
            tenant=self.request.user.tenant,
            customer_id=OuterRef('pk')
        )
        
        # 2. Customers with follow-up leads
        has_follow_up_lead = Lead.objects.filter(
            tenant=self.request.user.tenant,
            customer_id=OuterRef('pk'),
            status=LeadStatus.FOLLOW_UP,
            is_active=True
        )
        
        # 3. Customers with new status leads
        has_new_lead = Lead.objects.filter(
            tenant=self.request.user.tenant,
            customer_id=OuterRef('pk'),
            status=LeadStatus.NEW,
            is_active=True
        )
        
        # 4. Customers with interested status leads
        has_interested_lead = Lead.objects.filter(
            tenant=self.request.user.tenant,
            customer_id=OuterRef('pk'),
            status=LeadStatus.INTERESTED,
            is_active=True
        )
        
        # Check if customer has phone or has a lead with phone
        has_customer_phone = Q(phone__isnull=False) & ~Q(phone='')
        has_lead_with_phone = Exists(
            Lead.objects.filter(
                tenant=self.request.user.tenant,
                customer_id=OuterRef('pk'),
                phone__isnull=False
            ).exclude(phone='')
        )
        
        # Filter: customer must have phone OR have a lead with phone
        base_queryset = base_queryset.filter(has_customer_phone | has_lead_with_phone)
        
        # Annotate with lead phone for serializer (use lead phone if customer phone is missing)
        lead_phone_subquery = Lead.objects.filter(
            tenant=self.request.user.tenant,
            customer_id=OuterRef('pk'),
            phone__isnull=False
        ).exclude(phone='').order_by('-created_at').values('phone')[:1]
        
        base_queryset = base_queryset.annotate(
            lead_phone=Subquery(lead_phone_subquery)
        )
        
        # Annotate with lead status for serializer context
        # Priority: follow_up > interested > new > no_leads
        base_queryset = base_queryset.annotate(
            lead_status_annotation=Case(
                When(Exists(has_follow_up_lead), then=Value('ATTEMPTED_TO_CONTACT')),
                When(Exists(has_interested_lead), then=Value('INTERESTED')),
                When(Exists(has_new_lead), then=Value('NEW')),
                When(~Exists(has_any_lead), then=Value('NOT_CONTACTED')),
                default=Value(None),
                output_field=CharField()
            )
        )
        
        # Combine conditions: (no leads) OR (follow-up leads) OR (new status leads) OR (interested status leads)
        return base_queryset.filter(
            ~Exists(has_any_lead) | Exists(has_follow_up_lead) | Exists(has_new_lead) | Exists(has_interested_lead)
        ).distinct().order_by('-created_at')

    def list(self, request, *args, **kwargs):
        """
        Override list method to:
        1. Get customers (limited to 10)
        2. Serialize the response
        3. Call external POST API with the serialized data and token
        4. Return the external API response
        """
        # Get queryset and limit to 10 customers
        queryset = self.filter_queryset(self.get_queryset())[:10]
        
        # Serialize the data
        serializer = self.get_serializer(queryset, many=True)
        customers_data = serializer.data
        
        # Extract token from request.auth
        # In DRF TokenAuthentication, request.auth is the Token object
        token = None
        if request.auth and hasattr(request.auth, 'key'):
            token = request.auth.key
        
        # Prepare payload with customers data and token
        payload = {
            'customers': customers_data,
        }
        if token:
            payload['token'] = token
        
        # Call external POST API with the serialized data
        external_api_url = settings.CAMPAIGN_API_URL
        
        try:
            # Make POST request to external API
            # Note: ngrok-free.app may require bypass header to avoid interstitial page
            headers = {
                'Content-Type': 'application/json',
                'ngrok-skip-browser-warning': 'true'  # Bypass ngrok warning page
            }
            response = requests.post(
                external_api_url,
                json=payload,
                headers=headers,
                timeout=30  # 30 seconds timeout
            )
            
            # Log the response for debugging
            logger.info(f"External API call to {external_api_url} returned status {response.status_code}")
            
            # Return the external API response
            try:
                response_data = response.json()
            except ValueError:
                # If response is not JSON, return text
                response_data = {'message': response.text, 'status_code': response.status_code}
            
            return Response(response_data, status=response.status_code)
            
        except requests.exceptions.RequestException as e:
            # Handle any request exceptions (timeout, connection error, etc.)
            logger.error(f"Error calling external API {external_api_url}: {str(e)}")
            return Response(
                {
                    'error': 'Failed to call external API',
                    'detail': str(e),
                    'payload': payload  # Return the original payload in case of error
                },
                status=status.HTTP_502_BAD_GATEWAY
            )
