from .models import SiteLogo


def site_logo_context(request):
    """Make site_logo available to all templates."""
    return {
        'site_logo': SiteLogo.get_active_logo(),
    }

