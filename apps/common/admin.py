from django.contrib import admin
from django.contrib.admin.sites import NotRegistered
from django.contrib.auth.admin import GroupAdmin as BaseGroupAdmin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import Group, User
from unfold.admin import ModelAdmin
from unfold.forms import AdminPasswordChangeForm, UserChangeForm, UserCreationForm


for model in (User, Group):
    try:
        admin.site.unregister(model)
    except NotRegistered:
        pass


@admin.register(User)
class UserAdmin(BaseUserAdmin, ModelAdmin):
    form = UserChangeForm
    add_form = UserCreationForm
    change_password_form = AdminPasswordChangeForm
    list_fullwidth = True
    list_filter_submit = True
    compressed_fields = True


@admin.register(Group)
class GroupAdmin(BaseGroupAdmin, ModelAdmin):
    list_fullwidth = True
    compressed_fields = True
