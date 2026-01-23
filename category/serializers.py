from rest_framework import serializers
from .models import Category


class CategorySerializer(serializers.ModelSerializer):
    parent_name = serializers.CharField(source='parent.name', read_only=True)
    children_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Category
        fields = [
            'id', 'name', 'code', 'description', 'parent', 'parent_name',
            'is_active', 'notes', 'children_count', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'parent_name', 'children_count']
        extra_kwargs = {
            'name': {'required': True},
            'code': {'required': False, 'allow_null': True, 'allow_blank': True},
            'parent': {'required': False, 'allow_null': True},
            'is_active': {'required': False, 'default': True},
        }
    
    def get_children_count(self, obj):
        """Get the number of child categories"""
        if hasattr(obj, 'children'):
            return obj.children.filter(is_active=True).count()
        return 0


