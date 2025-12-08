from django.conf import settings


def tenant_branding(request):
    """Expose tenant (organization/school) branding to all templates.

    Provides:
      - tenant: the tenant object (Organization or School) or None
      - tenant_name
      - tenant_logo_url
      - tenant_primary_color
      - tenant_secondary_color
      - is_tenant_admin: True if the user is authenticated and linked to a tenant
    """
    tenant = getattr(request, 'current_tenant', None)
    # Fallback to user's organization/school
    if tenant is None and getattr(request, 'user', None) and request.user.is_authenticated:
        tenant = getattr(request.user, 'organization', None) or getattr(request.user, 'school', None)

    tenant_name = None
    tenant_logo_url = None
    tenant_primary_color = None
    tenant_secondary_color = None
    is_tenant_admin = False

    if tenant:
        tenant_name = getattr(tenant, 'name', None)
        # logo may be a FileField; guard access
        try:
            logo = getattr(tenant, 'logo', None)
            if logo:
                # Some tenants may not have uploaded a logo yet
                tenant_logo_url = getattr(logo, 'url', None)
        except Exception:
            tenant_logo_url = None
        tenant_primary_color = getattr(tenant, 'primary_color', None)
        tenant_secondary_color = getattr(tenant, 'secondary_color', None)
        # determine if current user is a tenant admin
        is_tenant_admin = getattr(request.user, 'is_authenticated', False) and (
            getattr(request.user, 'organization', None) is not None or getattr(request.user, 'school', None) is not None
        )

    # Provide sane defaults when not set
    tenant_primary_color = tenant_primary_color or getattr(settings, 'DEFAULT_PRIMARY_COLOR', '#0d6efd')
    tenant_secondary_color = tenant_secondary_color or getattr(settings, 'DEFAULT_SECONDARY_COLOR', '#6c757d')

    return {
        'tenant': tenant,
        'tenant_name': tenant_name,
        'tenant_logo_url': tenant_logo_url,
        'tenant_primary_color': tenant_primary_color,
        'tenant_secondary_color': tenant_secondary_color,
        'is_tenant_admin': is_tenant_admin,
    }
