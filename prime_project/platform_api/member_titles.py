"""Read existing title selections/grants without recalculating legacy rankings."""
from edithub.utils import is_title_unlocked_for_user


def selected_editor_title(user, application=None):
    if not (application and application.status == 'accepted' and application.channel_verified
            and not application.removal_requested):
        return None
    for title in (user.selected_title, application.selected_title):
        if title and title.is_active and title.category != 'comment' and is_title_unlocked_for_user(user, title):
            return title
    return None


def title_data(user, application=None):
    title = selected_editor_title(user, application)
    return {'editor_title': title.name if title else '', 'editor_title_rarity': title.rarity if title else None}
