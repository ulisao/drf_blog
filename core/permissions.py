from rest_framework import permissions
from django.conf import settings

class HasValidAPIKey(permissions.BasePermission):
    """
    Custom permission to check if the request has a valid API key.
    The API key is expected to be provided in the 'Authorization' header.
    """

    def has_permission(self, request, view):
        api_key = request.headers.get('API-Key')
        return api_key in getattr(settings, 'VALID_API_KEYS', [])