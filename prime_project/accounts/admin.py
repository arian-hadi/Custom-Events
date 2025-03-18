from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import CustomUser

class CustomUserAdmin(UserAdmin):
    list_display = ("email", "username", "role", "is_verified", "is_active", "is_staff")  
    list_filter = ("role", "is_verified", "is_active")

    fieldsets = (
        (None, {"fields": ("email", "username", "password")}),
        ("Permissions", {"fields": ("role", "is_verified", "is_active", "is_staff", "is_superuser")}),
        ("Important Dates", {"fields": ("last_login", "date_joined")}),  # ✅ Keep `date_joined` here
    )

    readonly_fields = ("date_joined",)  # ✅ Make `date_joined` non-editable

    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("email", "username", "password1", "password2", "role"),
        }),
    )

    search_fields = ("email", "username")
    ordering = ("email",)

admin.site.register(CustomUser, CustomUserAdmin)
