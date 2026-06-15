from rest_framework.permissions import BasePermission


class IsClient(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and getattr(request.user, "role", None) == "client")


class IsMaster(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and getattr(request.user, "role", None) == "master")


class IsStaffOrAdminUser(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and getattr(request.user, "is_staff", False))
