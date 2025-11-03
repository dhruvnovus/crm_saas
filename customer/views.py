from rest_framework import status, generics, filters
from rest_framework.views import APIView
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi
from django.utils.decorators import method_decorator
from .models import Customer
from user.models import CustomUser
from .serializers import CustomerSerializer
from .importer import detect_and_parse_tabular, normalize_customer_row


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
                tenant=request.user.tenant,
            )
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        customer = Customer(
            tenant=request.user.tenant,
            created_by=request.user,
            **serializer.validated_data,
        )
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
        serializer.save()

    def delete(self, request, *args, **kwargs):
        instance = self.get_object()
        from django.db import connections
        connections['default'].tenant = self.request.user.tenant
        instance.is_active = False
        instance.save(update_fields=['is_active', 'updated_at'])
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
                tenant=request.user.tenant,
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
                if created_flag:
                    created += 1
                else:
                    updated += 1
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
