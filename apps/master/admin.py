from django.contrib import admin
from django.contrib.auth.admin import GroupAdmin as DjangoGroupAdmin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.contrib.auth.models import Group as DjangoGroup

from .models import Group, User


class UserAdmin(DjangoUserAdmin):
    readonly_fields = (
        "last_login",
        "date_joined",
    )


class GroupAdmin(DjangoGroupAdmin):
    pass


admin.site.unregister(DjangoGroup)

admin.site.register(User, UserAdmin)
admin.site.register(Group, GroupAdmin)
