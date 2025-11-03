from rest_framework.pagination import PageNumberPagination


class CustomPageNumberPagination(PageNumberPagination):
    """
    Custom pagination class that allows clients to control page size.
    Default page size: 20
    Max page size: 100 (to prevent abuse)
    """
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100

