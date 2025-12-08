from django.utils.deprecation import MiddlewareMixin

# Make the middleware tenant-aware: prefer Organization (org_slug) but
# fall back to School (school_slug) for backwards compatibility.
from core.models import Organization, School


class CurrentTenantMiddleware(MiddlewareMixin):
    """Attach the current tenant (Organization or School) to the request.

    Looks for URL kwargs 'org_slug' first (preferred), then 'school_slug'.
    Sets the following attributes on request for templates and views:
      - request.current_tenant: Organization or School instance (or None)
      - request.current_organization: Organization instance when available (or None)
      - request.current_school: School instance when available (or None)
    """

    def process_view(self, request, view_func, view_args, view_kwargs):
        org_slug = view_kwargs.get('org_slug') or view_kwargs.get('organization_slug')
        school_slug = view_kwargs.get('school_slug')

        request.current_tenant = None
        request.current_organization = None
        request.current_school = None

        # Prefer organization slug
        if org_slug:
            try:
                org = Organization.objects.filter(slug=org_slug).first()
                if org:
                    request.current_tenant = org
                    request.current_organization = org
            except Exception:
                request.current_tenant = None

        # Backwards compatibility: support school_slug
        if request.current_tenant is None and school_slug:
            try:
                sch = School.objects.filter(slug=school_slug).first()
                if sch:
                    request.current_tenant = sch
                    request.current_school = sch
            except Exception:
                request.current_tenant = None

        # Also attach tenant based on authenticated user's organization/school if still unset
        if request.current_tenant is None and getattr(request, 'user', None) and request.user.is_authenticated:
            try:
                if getattr(request.user, 'organization', None):
                    request.current_tenant = request.user.organization
                    request.current_organization = request.user.organization
                elif getattr(request.user, 'school', None):
                    request.current_tenant = request.user.school
                    request.current_school = request.user.school
            except Exception:
                pass

        return None
