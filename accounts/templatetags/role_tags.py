from django import template

register = template.Library()


@register.filter
def role_badge(user):
    """CSS class for the role chip in the dashboard/portal header."""
    return {
        'super_admin': 'bg-purple-100 text-purple-800',
        'finance': 'bg-emerald-100 text-emerald-800',
        'sales': 'bg-sky-100 text-sky-800',
        'client': 'bg-blue-100 text-blue-800',
    }.get(getattr(user, 'role', ''), 'bg-gray-100 text-gray-800')
