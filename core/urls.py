from django.urls import path
from . import views

urlpatterns = [
    path('', views.home_view, name='home'),
    path('login/', views.login_redirect, name='login'),
    path('login/super/', views.login_super_view, name='login_super'),
    path('login/org/', views.login_org_view, name='login_org'),
    path('logout/', views.logout_view, name='logout'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('send-sms/', views.send_sms_view, name='send_sms'),
    # Multi-tenant (slug-prefixed) routes
    path('<slug:school_slug>/dashboard/', views.dashboard, name='school_dashboard'),
    path('<slug:school_slug>/send-sms/', views.send_sms_view, name='school_send_sms'),
    # Organization tenant routes
    path('<slug:org_slug>/org/dashboard/', views.org_dashboard, name='org_dashboard'),
    path('<slug:org_slug>/org/upload-contacts/', views.org_upload_contacts, name='org_upload_contacts'),
    path('<slug:org_slug>/org/templates/', views.org_templates, name='org_templates'),
    path('<slug:org_slug>/org/templates/<int:template_id>/edit/', views.org_template_edit, name='org_template_edit'),
    path('<slug:org_slug>/org/templates/<int:template_id>/delete/', views.org_template_delete, name='org_template_delete'),
    path('<slug:org_slug>/org/retry-failed/', views.org_retry_failed, name='org_retry_failed'),
    # Hubtel delivery receipt webhook
    path('webhooks/hubtel/', views.hubtel_webhook, name='hubtel_webhook'),
    path('health/', views.health, name='health'),
]