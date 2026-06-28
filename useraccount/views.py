

from django.utils import timezone
from django.core.mail import send_mail
from django.conf import settings
from django.shortcuts import get_object_or_404, render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.views import (
    PasswordResetView, 
    PasswordResetDoneView, 
    PasswordResetConfirmView,
    PasswordResetCompleteView
)
from django.contrib import messages
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.contrib.auth.decorators import login_required
from django.views.decorators.cache import never_cache
from django.views.decorators.debug import sensitive_post_parameters
from .forms import *
from .models import *
from .utils import send_otp
import pyotp
from app.views import get_base_context



class CustomPasswordResetView(PasswordResetView):
    form_class = CustomPasswordResetForm
    template_name = 'useraccount/password_reset_form.html'
    email_template_name = 'useraccount/password_reset_email.txt'  # Plain text primary
    html_email_template_name = 'useraccount/password_reset_email.html'  # HTML fallback
    subject_template_name = 'useraccount/password_reset_subject.txt'
    success_url = reverse_lazy('password_reset_done')
    
    def form_valid(self, form):
        messages.success(
            self.request, 
            'Password reset email has been sent to your email address.'
        )
        return super().form_valid(form)

class CustomPasswordResetDoneView(PasswordResetDoneView):
    template_name = 'useraccount/password_reset_done.html'

@method_decorator(sensitive_post_parameters(), name='dispatch')
@method_decorator(never_cache, name='dispatch')
class CustomPasswordResetConfirmView(PasswordResetConfirmView):
    form_class = CustomSetPasswordForm
    template_name = 'useraccount/password_reset_confirm.html'
    success_url = reverse_lazy('password_reset_complete')
    
    def form_valid(self, form):
        messages.success(
            self.request, 
            'Your password has been reset successfully!'
        )
        return super().form_valid(form)

class CustomPasswordResetCompleteView(PasswordResetCompleteView):
    template_name = 'useraccount/password_reset_complete.html'



# ==========================================================================
def staff_profile(request, staff_id):
    """Page 2: Staff Profile - Shows editable details for one staff member"""
    staff = get_object_or_404(CustomUser, id=staff_id)
    roles = Role.objects.all()
    context = {
        'staff': staff,
        'roles':roles
    }
    return render(request, 'useraccount/staff_profile.html', context)

def signup(request):
    """Page 3: Add Staff - Create new staff member"""
    if request.method == 'POST':
        firstname = request.POST.get('firstname', '').strip()
        lastname = request.POST.get('lastname', '').strip()
        middlename = request.POST.get('middlename', '').strip()
        email = request.POST.get('email', '').strip()
        phone = request.POST.get('phone', '').strip()
        role = request.POST.get('role', None)
        office_allocation = request.POST.get('office_allocation')
        username = request.POST.get('username', '').strip()
        nssf_no = request.POST.get('nssf_no', '').strip()
        bank_account_name = request.POST.get('bank_account_name', '').strip()
        bank_account_number = request.POST.get('bank_account_number', '').strip()
        join_date = request.POST.get('join_date', None)

        # Default password
        password = 'Masco@1234'

        # Validation
        if not all([firstname, lastname, email, phone, role, office_allocation, username]):
            messages.error(request, 'Please fill in all required fields.')
            return redirect('staff_list')

        # Check if email already exists
        if CustomUser.objects.filter(email=email).exists():
            messages.error(request, 'An account with this email already exists.')
            return redirect('staff_list')

        # Check if username already exists
        if CustomUser.objects.filter(username=username).exists():
            messages.error(request, 'This username is already taken.')
            return redirect('staff_list')

        try:
            # Create user
            staff = CustomUser.objects.create_user(
                username=username,
                email=email,
                password=password,
                first_name=firstname,
                last_name=lastname,
                phone=phone,
                role_id=role,
                office_allocation_id=office_allocation,
                join_date=join_date if join_date else None,
                is_active=True
            )

            # Set additional fields if they exist
            if hasattr(staff, 'middlename'):
                staff.middlename = middlename
            if hasattr(staff, 'nssf_no'):
                staff.nssf_no = nssf_no
            if hasattr(staff, 'bank_account_name'):
                staff.bank_account_name = bank_account_name
            if hasattr(staff, 'bank_account_number'):
                staff.bank_account_number = bank_account_number

            staff.save()

            messages.success(request, f'Staff member {firstname} {lastname} created successfully!')
            return redirect('staff_list')

        except Exception as e:
            messages.error(request, f'Error creating staff: {str(e)}')
            return redirect('staff_list')

    return redirect('staff_list')


from django.shortcuts import get_object_or_404
from .models import Role

def update_staff(request, staff_id):
    """Update staff profile information"""
    staff = get_object_or_404(CustomUser, id=staff_id)

    if request.method == 'POST':
        try:
            # Update basic fields
            staff.first_name = request.POST.get('first_name', '').strip()
            staff.last_name = request.POST.get('last_name', '').strip()
            staff.phone = request.POST.get('phone', '').strip()

            # ✅ FIX: Handle role properly
            role_id = request.POST.get('role')
            if role_id:
                staff.role = get_object_or_404(Role, id=role_id)
            else:
                staff.role = None

            # Optional fields
            if hasattr(staff, 'middlename'):
                staff.middlename = request.POST.get('middlename', '').strip()

            if hasattr(staff, 'nssf_no'):
                staff.nssf_no = request.POST.get('nssf_no', '').strip()

            if hasattr(staff, 'bank_account_name'):
                staff.bank_account_name = request.POST.get('bank_account_name', '').strip()

            if hasattr(staff, 'bank_account_number'):
                staff.bank_account_number = request.POST.get('bank_account_number', '').strip()

            staff.save()

            messages.success(request, 'Staff profile updated successfully!')
            return redirect('staff_profile', staff_id=staff.id)

        except Exception as e:
            messages.error(request, f'Error updating staff: {str(e)}')
            return redirect('staff_profile', staff_id=staff.id)

    return redirect('staff_list')


def verify_email(request, username):
    user = get_object_or_404(CustomUser, username=username)
    user_otp = OtpToken.objects.filter(user=user).last()
    if request.method == 'POST':
        if user_otp.otp_code == request.POST.get('otp_code'):
            if user_otp.otp_expires_at >= timezone.now():
                user.is_active = True
                user.save()
                messages.success(request, 'Your email has been verified successfully! You can now log in.')
                return redirect('signin')
            # expired token
            else:
                messages.warning(request, 'OTP has expired. Get a new OTP.')
                return redirect('verify-email', username=user.username)
        # invalid otp code
        else:
            messages.warning(request, 'Invalid OTP. Please enter a valid OTP.')
            return redirect('verify-email', username=user.username)
    context = {}
    return render(request, 'useraccount/verify_token.html', context)

def resend_otp(request):
    if request.method == 'POST':
        user_email = request.POST["otp_email"]

        if CustomUser.objects.filter(email=user_email).exists():
            user = get_object_or_404(CustomUser, email=user_email)
            otp = OtpToken.objects.create(user=user, otp_expires_at=timezone.now() + timezone.timedelta(minutes=2))
         
            # email
            subject = 'Email Verification - Your OTP Code'
            message = f"""
                            Dear {user.username},
                            Your OTP code is: {otp.otp_code}
                            This code will expire in 2 minutes. 
                            use the url below to verify your account:
                            http://127.0.0.1:8000/verify-email/{user.username}
                            If you did not request this, please ignore this email.
                        """
            sender = settings.EMAIL_HOST_USER
            receiver = [user.email]
            send_mail(
                subject, 
                message, 
                sender, 
                receiver, 
                fail_silently=False
            )
            messages.success(request, 'A new OTP has been sent to your email address.')
            return redirect('verify-email', username=user.username)
        else:
            messages.warning(request, 'Email address not found. Please enter a registered email.')
            return redirect('resend-otp')
    
    context = {}
    return render(request, 'useraccount/resend_otp.html', context)

def custom_logout_view(request):
    logout(request)
    return redirect('signin') 


# login without otp verification ===============

def signin(request):
    if request.method == 'POST':
        username = request.POST['username']
        password1 = request.POST['password1']

        # Check if username exists
        if not CustomUser.objects.filter(username=username).exists():
            messages.error(request, 'No account found with this username.')
            return redirect('signin')

        user = authenticate(username=username, password=password1)

        if user is not None:
            if user.is_active:
                login(request, user)
                return redirect('index')
            else:
                messages.warning(request, 'Your account is not verified yet. Please check your email for OTP verification.')
                return redirect('signin')
            
        else:
            messages.error(request, 'Incorrect password. Please try again.')
            return redirect('signin')

    return render(request, 'useraccount/signin.html')

# login with otp verification ===============
# def signin(request):
#     if request.method == 'POST':
#         username = request.POST['username']
#         password1 = request.POST['password1']

#         # Check if username exists
#         if not CustomUser.objects.filter(email=username).exists():
#             messages.error(request, 'No account found with this email.')
#             return redirect('signin')

#         # Authenticate user
#         user = authenticate(username=username, password=password1)

#         if user is not None:
#             if user.is_active:
#                 pass
#             else:
#                 messages.warning(request, 'Your account is not verified yet. Please check your email for OTP verification.')
#                 return redirect('signin')

#             # ✅ send otp tied to user
#             send_otp(user)

#             request.session['username'] = username
#             request.session['backend'] = user.backend  # keep backend

#             return redirect('otp')
#         else:
#             messages.error(request, 'Incorrect password. Please try again.')
#             return redirect('signin')

#     return render(request, 'useraccount/signin.html')


def otp_view(request):
    if request.method == 'POST':
        otp = request.POST['otp']
        username = request.session.get('username')

        try:
            user = CustomUser.objects.get(email=username)
        except CustomUser.DoesNotExist:
            messages.error(request, 'User not found. Please log in again.')
            return redirect('signin')

        if user.otp_secret_key and user.otp_valid_date:
            if user.otp_valid_date > timezone.now():
                totp = pyotp.TOTP(user.otp_secret_key, interval=120)
                if totp.verify(otp):
                    backend = request.session.get('backend', 'django.contrib.auth.backends.ModelBackend')
                    login(request, user, backend=backend)

                    # clean up OTP fields
                    user.otp_secret_key = None
                    user.otp_valid_date = None
                    user.save(update_fields=['otp_secret_key', 'otp_valid_date'])

                    # clean session
                    request.session.pop('backend', None)
                    request.session.pop('username', None)

                    return redirect('index')
                else:
                    messages.error(request, 'Invalid OTP. Please try again.')
                    return redirect('otp')
            else:
                messages.error(request, 'OTP has expired. Please log in again.')
                return redirect('signin')
        else:
            messages.error(request, 'No OTP found. Please log in again.')
            return redirect('signin')

    return render(request, 'useraccount/otp.html')


# ==========================================================================
def home(request):
    return render(request, 'useraccount/home.html')

def dashboard(request):
    return render(request, 'useraccount/dashboard.html')

def profile(request):
    profile, created = Profile.objects.get_or_create(user=request.user)
    context = {'profile': profile}
    return render(request, 'useraccount/profile.html', context)

@login_required
def profile_edit(request):
    profile, created = Profile.objects.get_or_create(user=request.user)

    if request.method == 'POST':
        user_form = UserEditForm(request.POST, request.FILES, instance=request.user)
        profile_form = ProfileEditForm(request.POST, request.FILES, instance=profile)

        if user_form.is_valid() and profile_form.is_valid():
            user_form.save()
            profile_form.save()
            messages.success(request, 'Your profile has been updated successfully!')
            return redirect('profile')
    else:
        user_form = UserEditForm(instance=request.user)
        profile_form = ProfileEditForm(instance=profile)

    return render(request, 'useraccount/profile_edit.html', {
        'user_form': user_form,
        'profile_form': profile_form,
    })

@login_required
def delete_account(request):
    if request.method == 'POST':
        user = request.user
        logout(request)  # log out the user first
        user.delete()    # delete the user and related profile (if on_delete=CASCADE)
        messages.success(request, 'Your account has been deleted successfully.')
        return redirect('home')  # redirect to home page or landing page

    return render(request, 'useraccount/delete_account.html')

# ==============================================================================
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from .forms import CustomPasswordChangeForm

@login_required
def change_password(request):
    if request.method == 'POST':
        form = CustomPasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            user = form.save()
            # Update session to prevent logout
            update_session_auth_hash(request, user)
            messages.success(request, 'Your password was successfully updated!')
            return redirect('password_change_done')
        else:
            messages.error(request, 'Please correct the error below.')
    else:
        form = CustomPasswordChangeForm(request.user)
    
    return render(request, 'useraccount/change_password.html', {'form': form})


def password_change_done(request):
    return render(request,'useraccount/password_change_done.html')

# ===================================================================================






"""
useraccount/views_roles.py
Role & Permission management views.
Add these URLs to useraccount/urls.py (see snippet at bottom of file).
"""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from itertools import groupby

from .models import Role, Permission, RolePermission


# ─────────────────────────────────────────────────────────────────────────────
# helpers
# ─────────────────────────────────────────────────────────────────────────────

def _superuser_required(view_fn):
    """Simple decorator: only superusers can manage roles."""
    from functools import wraps
    @wraps(view_fn)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated or not request.user.is_superuser:
            messages.error(request, "You do not have permission to manage roles.")
            return redirect('index')
        return view_fn(request, *args, **kwargs)
    return wrapper


def _grouped_permissions():
    """
    Returns a list of dicts:
      [{'group': 'Loans', 'permissions': [<Permission>, ...]}, ...]
    """
    all_perms = list(Permission.objects.all().order_by('group', 'name'))
    groups = []
    for group_name, perms in groupby(all_perms, key=lambda p: p.group):
        groups.append({'group': group_name, 'permissions': list(perms)})
    return groups


# ─────────────────────────────────────────────────────────────────────────────
# List all roles
# ─────────────────────────────────────────────────────────────────────────────

@login_required
@_superuser_required
def roles_list(request):
    base_ctx      = get_base_context(request)
    roles = Role.objects.prefetch_related('role_permissions__permission').all()
    context = {
        **base_ctx,
        'roles': roles,
        'page_title': 'Role Management',
    }
    return render(request, 'useraccount/roles_list.html', context)


# ─────────────────────────────────────────────────────────────────────────────
# Create role
# ─────────────────────────────────────────────────────────────────────────────

@login_required
@_superuser_required
def role_create(request):
    # Make sure the Permission table is populated
    base_ctx      = get_base_context(request)
    Permission.sync()

    if request.method == 'POST':
        title       = request.POST.get('title', '').strip()
        description = request.POST.get('description', '').strip()
        codenames   = request.POST.getlist('permissions')  # list of codenames

        if not title:
            messages.error(request, "Role name is required.")
        else:
            role = Role.objects.create(title=title, description=description or None)
            perms = Permission.objects.filter(codename__in=codenames)
            RolePermission.objects.bulk_create(
                [RolePermission(role=role, permission=p) for p in perms]
            )
            messages.success(request, f'Role "{role.title}" created successfully.')
            return redirect('roles_list')

    context = {
        **base_ctx,
        'page_title':   'Create Role',
        'perm_groups':  _grouped_permissions(),
        'selected':     set(),
        'role':         None,
    }
    return render(request, 'useraccount/role_edit.html', context)


# ─────────────────────────────────────────────────────────────────────────────
# Edit role
# ─────────────────────────────────────────────────────────────────────────────

@login_required
@_superuser_required
def role_edit(request, role_id):
    base_ctx      = get_base_context(request)
    Permission.sync()
    role = get_object_or_404(Role, pk=role_id)

    if request.method == 'POST':
        title       = request.POST.get('title', '').strip()
        description = request.POST.get('description', '').strip()
        codenames   = set(request.POST.getlist('permissions'))

        if not title:
            messages.error(request, "Role name is required.")
        else:
            role.title       = title
            role.description = description or None
            role.save()

            # Replace all permissions with the submitted set
            role.role_permissions.all().delete()
            perms = Permission.objects.filter(codename__in=codenames)
            RolePermission.objects.bulk_create(
                [RolePermission(role=role, permission=p) for p in perms]
            )
            messages.success(request, f'Role "{role.title}" updated successfully.')
            return redirect('roles_list')

    context = {
        **base_ctx,
        'page_title':  f'Edit Role — {role.title}',
        'perm_groups': _grouped_permissions(),
        'selected':    role.get_permission_codenames(),
        'role':        role,
    }
    return render(request, 'useraccount/role_edit.html', context)


# ─────────────────────────────────────────────────────────────────────────────
# Delete role
# ─────────────────────────────────────────────────────────────────────────────

@login_required
@_superuser_required
def role_delete(request, role_id):
    role = get_object_or_404(Role, pk=role_id)
    if request.method == 'POST':
        name = role.title
        role.delete()
        messages.success(request, f'Role "{name}" deleted.')
    return redirect('roles_list')


# ─────────────────────────────────────────────────────────────────────────────
# URL SNIPPET  — paste into useraccount/urls.py
# ─────────────────────────────────────────────────────────────────────────────
"""
from .views_roles import roles_list, role_create, role_edit, role_delete

urlpatterns += [
    path('roles/',                    roles_list,   name='roles_list'),
    path('roles/create/',             role_create,  name='role_create'),
    path('roles/<int:role_id>/edit/', role_edit,    name='role_edit'),
    path('roles/<int:role_id>/delete/', role_delete, name='role_delete'),
]
"""

