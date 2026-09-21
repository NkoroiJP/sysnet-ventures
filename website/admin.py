from django.contrib import admin

from billing.models import ServicePage, ServiceEnquiry, Project, Testimonial


@admin.register(ServicePage)
class ServicePageAdmin(admin.ModelAdmin):
    list_display = ('title', 'slug', 'sort_order', 'is_active')
    prepopulated_fields = {'slug': ('title',)}


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ('title', 'category', 'is_public', 'completed_on')
    prepopulated_fields = {'slug': ('title',)}


@admin.register(Testimonial)
class TestimonialAdmin(admin.ModelAdmin):
    list_display = ('client_name', 'client_role', 'is_public', 'created_at')


@admin.register(ServiceEnquiry)
class ServiceEnquiryAdmin(admin.ModelAdmin):
    list_display = ('name', 'email', 'status', 'created_at')
    list_filter = ('status',)
