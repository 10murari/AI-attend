from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    list_display = ('username', 'full_name', 'role', 'department', 'roll_no', 'semester', 'is_active')
    list_filter = ('role', 'department', 'semester', 'is_active')
    search_fields = ('username', 'full_name', 'roll_no', 'email')
    ordering = ('role', 'full_name')

    fieldsets = UserAdmin.fieldsets + (
        ('Role & Department', {
            'fields': ('role', 'full_name', 'department', 'roll_no', 'semester', 'phone'),
        }),
    )

    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Role & Department', {
            'fields': ('role', 'full_name', 'department', 'roll_no', 'semester', 'phone'),
        }),
    )