"""Presentation helpers using Django's already permission-filtered app list.

Never query records or construct model links here: links and capabilities come
from AdminSite.get_app_list(), including custom ModelAdmin permission checks.
"""
from django import template

register = template.Library()

SECTIONS = {
    "content": ("Content & website", "Publish stories and shape the website.", "01"),
    "league": ("Editing league", "Manage weekly entries, monthly results and scoring.", "02"),
    "community": ("Members & community", "Review editor applications and manage member access.", "03"),
    "shop": ("Shop & payments", "Products, Amazon imports and customer orders.", "04"),
    "communications": ("Notifications & email", "Announcements, campaigns and delivery history.", "05"),
    "events": ("Events & support", "Community events, applications and contact messages.", "06"),
    "history": ("Records & advanced tools", "Supporting records, legacy history and integrations.", "07"),
}

MODEL_SECTIONS = {
    "edithub.editorapplication": "community",
    "edithub.editortitle": "community",
    "edithub.usertitleunlock": "community",
    "edithub.tournament": "history",
    "edithub.tournamentmatchvote": "history",
    "edithub.weekwinner": "history",
    "edithub.editsubmission": "history",
    "edithub.editupvote": "history",
    "edithub.editreport": "history",
    "edithub.seasonaward": "history",
    "edithub.leaguehistorysync": "history",
}

APP_SECTIONS = {
    "platform_api": "content", "core": "content", "shop": "shop",
    "accounts": "community", "auth": "community", "edithub": "league",
    "announcements": "communications", "notifications": "communications",
    "events": "events", "contact": "events",
}

QUICK_ACTIONS = (
    ("platform_api.blogpost", "add_url", "Write a blog post", "Create a new story"),
    ("platform_api.youtubeblogvideo", "admin_url", "YouTube → Blog", "Prepare videos and import drafts"),
    ("edithub.editorapplication", "admin_url", "Editor applications", "Review channel submissions"),
    ("edithub.competitionweek", "admin_url", "Weekly competitions", "Entries and frozen results"),
    ("shop.product", "admin_url", "Manage products", "Update your storefront"),
    ("notifications.notification", "add_url", "Create a notification", "Reach your members"),
    ("platform_api.sitesettings", "admin_url", "Website appearance", "Colors, hero and navigation"),
)


@register.simple_tag
def admin_workspace(app_list):
    """Group only visible modules; never turn a view permission into an add link."""
    grouped = {key: [] for key in SECTIONS}
    available = {}
    for app in app_list or []:
        for model in app.get("models", []):
            key = f"{app['app_label']}.{model['object_name'].lower()}"
            item = {**model, "app_name": app["name"], "key": key}
            section = MODEL_SECTIONS.get(key, APP_SECTIONS.get(app["app_label"], "history"))
            grouped[section].append(item)
            available[key] = item
    groups = [
        {"key": key, "title": title, "description": description, "number": number, "models": grouped[key]}
        for key, (title, description, number) in SECTIONS.items() if grouped[key]
    ]
    actions = []
    for key, capability, title, description in QUICK_ACTIONS:
        model = available.get(key)
        if model and model.get(capability):
            actions.append({"title": title, "description": description, "url": model[capability]})
    return {"groups": groups, "actions": actions, "module_count": len(available)}
