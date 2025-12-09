from django.urls import path
from . import views
from django.contrib.auth import views as auth_views
from django.urls import reverse_lazy

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
    path('<slug:org_slug>/org/send/', views.org_send_sms, name='org_send_sms'),
    path('<slug:org_slug>/org/groups/', views.org_groups_view, name='org_groups'),
    path('<slug:org_slug>/org/messages/scheduled/', views.org_scheduled_messages, name='org_scheduled_messages'),
    path('<slug:org_slug>/org/messages/sent/', views.org_sent_messages, name='org_sent_messages'),
    path('<slug:org_slug>/org/message-logs/', views.org_message_logs, name='org_message_logs'),
    path('<slug:org_slug>/org/users/', views.org_users_view, name='org_users'),
    path('<slug:org_slug>/org/settings/', views.org_settings_view, name='org_settings'),
    # Hubtel delivery receipt webhook
    path('webhooks/hubtel/', views.hubtel_webhook, name='hubtel_webhook'),
    path('health/', views.health, name='health'),
    # Super-admin pages (use 'super/' prefix to avoid colliding with Django admin)
    path('super/enroll/', views.enroll_tenant_view, name='enroll_tenant'),
    path('super/system-logs/', views.system_logs_view, name='system_logs'),
    path('super/global-templates/', views.global_templates_view, name='global_templates'),
    path('super/global-templates/create/', views.create_global_template_view, name='create_global_template'),
    path('super/global-templates/<int:template_id>/edit/', views.edit_global_template_view, name='edit_global_template'),
    path('super/onboarding/', views.onboarding_view, name='onboarding'),
    path('super/orgs/', views.onboarding_view, name='super_orgs'),
    path('super/orgs/<slug:org_slug>/edit/', views.super_edit_org_view, name='super_edit_org'),
    # Password reset (uses Django auth views with our templates)
    path('password_reset/', auth_views.PasswordResetView.as_view(
        template_name='registration/password_reset_form.html',
        email_template_name='registration/password_reset_email.html',
        success_url=reverse_lazy('password_reset_done')
    ), name='password_reset'),
    path('password_reset/done/', auth_views.PasswordResetDoneView.as_view(
        template_name='registration/password_reset_done.html'
    ), name='password_reset_done'),
    path('reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(
        template_name='registration/password_reset_confirm.html',
        success_url=reverse_lazy('password_reset_complete')
    ), name='password_reset_confirm'),
    path('reset/done/', auth_views.PasswordResetCompleteView.as_view(
        template_name='registration/password_reset_complete.html'
    ), name='password_reset_complete'),
]