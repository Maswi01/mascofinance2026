# ─── Add these lines to useraccount/urls.py ───────────────────────────────────
#
# 1. At the top, add this import:
#
#    from .views_roles import roles_list, role_create, role_edit, role_delete
#
# 2. Add these paths inside urlpatterns = [...]:
#
#    path('roles/',                      roles_list,   name='roles_list'),
#    path('roles/create/',               role_create,  name='role_create'),
#    path('roles/<int:role_id>/edit/',   role_edit,    name='role_edit'),
#    path('roles/<int:role_id>/delete/', role_delete,  name='role_delete'),
#
# ─── FULL updated urls.py (copy-paste ready) ──────────────────────────────────

from django.urls import path
from . import views
from .views import custom_logout_view
from .views import (
    CustomPasswordResetView,
    CustomPasswordResetDoneView,
    CustomPasswordResetConfirmView,
    CustomPasswordResetCompleteView,
)
from .views import roles_list, role_create, role_edit, role_delete


urlpatterns = [
    path('home/',      views.home,      name='home'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('profile/',   views.profile,   name='profile'),
    path('profile/edit/', views.profile_edit, name='profile_edit'),
    path('account/delete/', views.delete_account, name='delete_account'),

    path('logout/', custom_logout_view, name='logout'),
    path('',        views.signin,       name='signin'),
    path('verify-email/<str:username>/', views.verify_email, name='verify-email'),
    path('resend-otp/', views.resend_otp, name='resend-otp'),
    path('otp/', views.otp_view, name='otp'),

    # Password reset
    path('password-reset/',
         CustomPasswordResetView.as_view(), name='password_reset'),
    path('password-reset/done/',
         CustomPasswordResetDoneView.as_view(), name='password_reset_done'),
    path('reset/<uidb64>/<token>/',
         CustomPasswordResetConfirmView.as_view(), name='password_reset_confirm'),
    path('reset/done/',
         CustomPasswordResetCompleteView.as_view(), name='password_reset_complete'),

    # Change password
    path('change-password/',    views.change_password,     name='change_password'),
    path('password_change_done/', views.password_change_done, name='password_change_done'),

    # Staff
    path('staff/profile/<int:staff_id>/', views.staff_profile, name='staff_profile'),
    path('signup/', views.signup, name='signup'),
    path('staff/update/<int:staff_id>/', views.update_staff, name='update_staff'),

    # ── Role & Permission management ──────────────────────────────────────────
    path('roles/',                      roles_list,   name='roles_list'),
    path('roles/create/',               role_create,  name='role_create'),
    path('roles/<int:role_id>/edit/',   role_edit,    name='role_edit'),
    path('roles/<int:role_id>/delete/', role_delete,  name='role_delete'),
]
