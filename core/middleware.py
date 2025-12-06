from django.utils.deprecation import MiddlewareMixin
from core.models import School


class CurrentSchoolMiddleware(MiddlewareMixin):
    """Attach current school to request based on URL kwarg 'school_slug' if present."""

    def process_view(self, request, view_func, view_args, view_kwargs):
        school_slug = view_kwargs.get('school_slug')
        request.current_school = None
        if school_slug:
            try:
                request.current_school = School.objects.filter(slug=school_slug).first()
            except Exception:
                request.current_school = None
        return None
