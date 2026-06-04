"""
Security middleware and settings.
Add to settings.py MIDDLEWARE list.
"""


class SessionTimeoutMiddleware:
    """Auto-logout after 30 minutes of inactivity."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            # Set session expiry to 30 minutes
            request.session.set_expiry(1800)
        return self.get_response(request)