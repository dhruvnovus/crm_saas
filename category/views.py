from django.utils.decorators import method_decorator
from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import filters, generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from user.models import CustomUser

from .history_serializers import CategoryHistorySerializer
from .models import Category, CategoryHistory
from .serializers import CategorySerializer


@method_decorator(
    name="get",
    decorator=swagger_auto_schema(
        tags=["Categories"],
        responses={
            200: openapi.Response(
                description="List categories",
                examples={
                    "application/json": {
                        "count": 1,
                        "next": None,
                        "previous": None,
                        "results": [
                            {
                                "id": "uuid-here",
                                "name": "Electronics",
                                "code": "CAT001",
                                "description": "Electronic products",
                                "parent": None,
                                "is_active": True,
                            }
                        ],
                    }
                },
            )
        },
    ),
)
@method_decorator(
    name="post",
    decorator=swagger_auto_schema(
        tags=["Categories"],
        operation_description="Create a category in the current tenant",
        responses={
            201: openapi.Response(description="Category created"),
            400: openapi.Response(description="Validation error"),
            401: openapi.Response(description="Authentication required"),
        },
    ),
)
class CategoryListCreateView(generics.ListCreateAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = CategorySerializer
    filter_backends = [filters.SearchFilter]
    search_fields = ["name", "code", "description"]

    def get_queryset(self):
        if not getattr(self.request.user, "tenant", None):
            return Category.objects.none()
        from django.db import connections

        connections["default"].tenant = self.request.user.tenant
        return Category.objects.filter(tenant=self.request.user.tenant).order_by("-created_at")

    def create(self, request, *args, **kwargs):
        if not request.user or not request.user.is_authenticated:
            return Response({"detail": "Authentication required"}, status=status.HTTP_401_UNAUTHORIZED)
        if not getattr(request.user, "tenant", None):
            return Response({"detail": "No tenant associated"}, status=status.HTTP_400_BAD_REQUEST)

        from django.db import connections

        connections["default"].tenant = request.user.tenant

        # Ensure user exists in tenant DB (avoid FK issues in tenant DB context)
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
                tenant=None,
            )

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        category = Category(
            tenant=request.user.tenant,
            created_by=tenant_user,
            **serializer.validated_data,
        )
        # Attach user for history tracking
        category._changed_by = tenant_user
        category.save()
        return Response(CategorySerializer(category).data, status=status.HTTP_201_CREATED)


@method_decorator(
    name="get",
    decorator=swagger_auto_schema(
        tags=["Categories"],
        responses={
            200: openapi.Response(
                description="Retrieve category",
                examples={
                    "application/json": {
                        "id": "uuid-here",
                        "name": "Electronics",
                        "code": "CAT001",
                        "description": "Electronic products",
                        "parent": None,
                        "is_active": True,
                    }
                },
            ),
            404: openapi.Response(description="Not found"),
        },
    ),
)
@method_decorator(
    name="patch",
    decorator=swagger_auto_schema(
        tags=["Categories"],
        responses={
            200: openapi.Response(description="Category updated"),
            400: openapi.Response(description="Validation error"),
        },
    ),
)
@method_decorator(
    name="delete",
    decorator=swagger_auto_schema(
        tags=["Categories"],
        responses={
            200: openapi.Response(
                description="Soft delete confirmation",
                examples={"application/json": {"message": "Category soft-deleted"}},
            ),
        },
    ),
)
class CategoryDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = CategorySerializer
    lookup_field = "pk"
    http_method_names = ["get", "patch", "delete"]  # Exclude PUT

    def get_queryset(self):
        if not getattr(self.request.user, "tenant", None):
            return Category.objects.none()
        from django.db import connections

        connections["default"].tenant = self.request.user.tenant
        return Category.objects.filter(tenant=self.request.user.tenant)

    def perform_update(self, serializer):
        from django.db import connections

        connections["default"].tenant = self.request.user.tenant
        # Get tenant user for history tracking
        tenant_user = CustomUser.objects.filter(id=self.request.user.id).first()
        instance = serializer.instance
        instance._changed_by = tenant_user if tenant_user else self.request.user
        serializer.save()

    def delete(self, request, *args, **kwargs):
        instance = self.get_object()
        from django.db import connections

        connections["default"].tenant = self.request.user.tenant
        # Get tenant user for history tracking
        tenant_user = CustomUser.objects.filter(id=request.user.id).first()
        instance.is_active = False
        instance._changed_by = tenant_user if tenant_user else request.user
        instance.save(update_fields=["is_active", "updated_at"])
        # History will be tracked by the signal
        return Response({"message": "Category soft-deleted"}, status=status.HTTP_200_OK)


@method_decorator(
    name="get",
    decorator=swagger_auto_schema(
        tags=["Categories"],
        operation_description="Get history of all changes for a specific category by ID",
        responses={
            200: openapi.Response(
                description="Category history retrieved successfully",
                examples={
                    "application/json": {
                        "count": 2,
                        "next": None,
                        "previous": None,
                        "results": [
                            {
                                "id": "uuid-here",
                                "action": "created",
                                "field_name": None,
                                "old_value": None,
                                "new_value": None,
                                "changes": {"all_fields": "Category created"},
                                "notes": "Category was created",
                                "changed_by_username": "john.doe",
                                "changed_by_email": "john@example.com",
                                "created_at": "2024-01-01T12:00:00Z",
                            },
                            {
                                "id": "uuid-here",
                                "action": "updated",
                                "field_name": "name, description",
                                "old_value": None,
                                "new_value": None,
                                "changes": {
                                    "name": {"old": "Old Name", "new": "New Name"},
                                    "description": {"old": "Old Desc", "new": "New Desc"}
                                },
                                "notes": "Updated fields: name, description",
                                "changed_by_username": "john.doe",
                                "changed_by_email": "john@example.com",
                                "created_at": "2024-01-02T12:00:00Z",
                            },
                        ],
                    }
                },
            ),
            404: openapi.Response(description="Category not found"),
        },
    ),
)
class CategoryHistoryView(generics.ListAPIView):
    """API endpoint to retrieve history of changes for a specific category"""
    permission_classes = [IsAuthenticated]
    serializer_class = CategoryHistorySerializer
    lookup_field = "pk"

    def get_queryset(self):
        if not getattr(self.request.user, "tenant", None):
            return CategoryHistory.objects.none()
        
        from django.db import connections
        connections["default"].tenant = self.request.user.tenant
        
        category_id = self.kwargs.get("pk")
        
        # Verify category exists and belongs to tenant
        try:
            category = Category.objects.get(id=category_id, tenant=self.request.user.tenant)
        except Category.DoesNotExist:
            return CategoryHistory.objects.none()
        
        return CategoryHistory.objects.filter(
            category=category,
            tenant=self.request.user.tenant
        ).select_related("changed_by").order_by("-created_at")


