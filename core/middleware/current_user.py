"""Remember the request's user for the activity history signal handlers."""

from core.services import activity


class CurrentUserMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        activity.set_current_user(getattr(request, "user", None))

        try:
            return self.get_response(request)
        finally:
            activity.set_current_user(None)
