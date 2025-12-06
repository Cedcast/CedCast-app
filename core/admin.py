from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import School, User, Parent, Message

@admin.register(School)
class SchoolAdmin(admin.ModelAdmin):
	list_display = ("name", "primary_color", "secondary_color", "created_at")

@admin.register(User)
class CustomUserAdmin(UserAdmin):
	list_display = ("username", "role", "school", "is_superuser", "is_staff")
	fieldsets = UserAdmin.fieldsets + (
		("Role & School", {"fields": ("role", "school")}),
	)

@admin.register(Parent)
class ParentAdmin(admin.ModelAdmin):
	list_display = ("name", "phone_number", "school", "created_at")

@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
	list_display = ("school", "scheduled_time", "sent", "created_at")
