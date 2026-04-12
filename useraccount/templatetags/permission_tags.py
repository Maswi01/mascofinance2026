from django import template

register = template.Library()


@register.simple_tag
def user_has_perm(user, codename):
    """
    Usage in templates:
        {% load permission_tags %}
        {% user_has_perm request.user 'loans-delete' as can_delete %}
        {% if can_delete %}
            <button>Delete</button>
        {% endif %}
    """
    if not user or not user.is_authenticated:
        return False
    return user.has_system_perm(codename)


@register.inclusion_tag('useraccount/permission_button.html')
def perm_button(user, codename, label, url='#', btn_class='btn-primary', icon=''):
    """
    Renders a button only if the user has the given permission.
    Usage:
        {% perm_button request.user 'loans-delete' 'Delete' url=delete_url btn_class='btn-danger' icon='fa-trash' %}
    """
    has_perm = user.has_system_perm(codename) if user and user.is_authenticated else False
    return {
        'has_perm': has_perm,
        'label': label,
        'url': url,
        'btn_class': btn_class,
        'icon': icon,
    }
