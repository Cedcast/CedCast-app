from django.urls import path
from . import views

urlpatterns = [
    path('', views.home_view, name='home'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('send-sms/', views.send_sms_view, name='send_sms'),
    # Multi-tenant (slug-prefixed) routes
    path('<slug:school_slug>/dashboard/', views.dashboard, name='school_dashboard'),
    path('<slug:school_slug>/send-sms/', views.send_sms_view, name='school_send_sms'),
    # Organization tenant routes
    path('<slug:org_slug>/org/dashboard/', views.org_dashboard, name='org_dashboard'),
    # Hubtel delivery receipt webhook
    path('webhooks/hubtel/', views.hubtel_webhook, name='hubtel_webhook'),
    path('health/', views.health, name='health'),
]