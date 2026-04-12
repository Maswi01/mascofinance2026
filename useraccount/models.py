import secrets
from django.db import models
from django.contrib.auth.models import AbstractUser


# ──────────────────────────────────────────────────────────────────────────────
# Permission catalogue
# ──────────────────────────────────────────────────────────────────────────────

# Every action in the system is listed here.
# codename  → used in templates/views: {% has_perm request.user 'loans-create' %}
# name      → human-readable label shown in the Edit Role page
# group     → card heading in the Edit Role page

ALL_PERMISSIONS = [
    # ── Users ──────────────────────────────────────────────────────────────
    ("user-list",        "View Users",        "Users"),
    ("user-create",      "Create new Users",  "Users"),
    ("user-show",        "Show Users",        "Users"),
    ("user-edit",        "Edit Users",        "Users"),
    ("user-delete",      "Delete Users",      "Users"),

    # ── Branches / Offices ─────────────────────────────────────────────────
    ("branch-list",      "View branches",     "Branches"),
    ("branch-create",    "Create branch",     "Branches"),
    ("branch-edit",      "Edit branch",       "Branches"),
    ("branch-show",      "Show branch",       "Branches"),
    ("branch-delete",    "Delete branch",     "Branches"),

    # ── Loans ──────────────────────────────────────────────────────────────
    ("loans-list",       "View loans",        "Loans"),
    ("loans-create",     "Create loans",      "Loans"),
    ("loans-show",       "Show loans",        "Loans"),
    ("loans-edit",       "Edit loans",        "Loans"),
    ("loans-delete",     "Delete loans",      "Loans"),
    ("loans-approve",    "Approve loans",     "Loans"),
    ("loans-topup",      "Topup loans",       "Loans"),
    ("loans-repay",      "Record repayment",  "Loans"),
    ("loans-repay-edit", "Edit repayment",    "Loans"),
    ("loans-repay-delete","Delete repayment", "Loans"),

    # ── Clients ────────────────────────────────────────────────────────────
    ("clients-list",     "Show clients",      "Clients"),
    ("clients-create",   "Create clients",    "Clients"),
    ("clients-edit",     "Edit clients",      "Clients"),
    ("clients-delete",   "Delete clients",    "Clients"),

    # ── Savings / Nyongeza ─────────────────────────────────────────────────
    ("savings-list",     "View savings",      "Savings"),
    ("savings-create",   "Create savings",    "Savings"),
    ("savings-edit",     "Edit savings",      "Savings"),
    ("savings-delete",   "Delete savings",    "Savings"),

    # ── Expenses ───────────────────────────────────────────────────────────
    ("expenses-list",    "View expenses",     "Expenses"),
    ("expenses-create",  "Create expenses",   "Expenses"),
    ("expenses-edit",    "Edit expenses",     "Expenses"),
    ("expenses-delete",  "Delete expenses",   "Expenses"),

    # ── Transactions ───────────────────────────────────────────────────────
    ("transactions-list",   "View transactions",   "Transactions"),
    ("transactions-create", "Create transactions", "Transactions"),
    ("transactions-edit",   "Edit transactions",   "Transactions"),
    ("transactions-delete", "Delete transactions", "Transactions"),

    # ── Salary ─────────────────────────────────────────────────────────────
    ("salary-list",      "View salary",       "Salary"),
    ("salary-create",    "Create salary",     "Salary"),
    ("salary-edit",      "Edit salary",       "Salary"),
    ("salary-delete",    "Delete salary",     "Salary"),
    ("salary-pay",       "Process payroll",   "Salary"),

    # ── Reports ────────────────────────────────────────────────────────────
    ("reports-loans-issued",      "Loans Issued Report",      "Reports"),
    ("reports-loans-owed",        "Loans Owed Report",        "Reports"),
    ("reports-repayment-schedule","Repayment Schedule",       "Reports"),
    ("reports-financial",         "Financial Statement",      "Reports"),
    ("reports-expenses",          "Expenses Statement",       "Reports"),
    ("reports-salary-slip",       "Salary Slip",              "Reports"),
]


class Permission(models.Model):
    codename = models.CharField(max_length=100, unique=True)
    name     = models.CharField(max_length=150)
    group    = models.CharField(max_length=100)

    class Meta:
        ordering = ['group', 'name']

    def __str__(self):
        return f"{self.group} › {self.name}"

    @classmethod
    def sync(cls):
        """
        Call once (e.g. in a management command or post_migrate signal) to
        make sure every entry in ALL_PERMISSIONS exists in the database.
        """
        for codename, name, group in ALL_PERMISSIONS:
            cls.objects.get_or_create(codename=codename, defaults={'name': name, 'group': group})


# ──────────────────────────────────────────────────────────────────────────────
# Role
# ──────────────────────────────────────────────────────────────────────────────

class Role(models.Model):
    title       = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    created_at  = models.DateTimeField(auto_now_add=True, null=True, blank=True)

    def __str__(self):
        return self.title

    # ── helpers ──────────────────────────────────────────────────────────────

    def get_permission_codenames(self):
        """Return a set of codenames granted to this role."""
        return set(
            self.role_permissions.values_list('permission__codename', flat=True)
        )

    def has_perm(self, codename: str) -> bool:
        return self.role_permissions.filter(permission__codename=codename).exists()


class RolePermission(models.Model):
    role       = models.ForeignKey(Role, on_delete=models.CASCADE, related_name='role_permissions')
    permission = models.ForeignKey(Permission, on_delete=models.CASCADE, related_name='role_permissions')

    class Meta:
        unique_together = ('role', 'permission')

    def __str__(self):
        return f"{self.role} — {self.permission.codename}"



# ──────────────────────────────────────────────────────────────────────────────
# CustomUser (unchanged except role FK already points at Role above)
# ──────────────────────────────────────────────────────────────────────────────

class CustomUser(AbstractUser):
    middlename          = models.CharField(max_length=30, null=True, blank=True)
    nssf_no             = models.CharField(max_length=30, null=True, blank=True)
    bank_account_name   = models.CharField(max_length=30, null=True, blank=True)
    bank_account_number = models.CharField(max_length=30, null=True, blank=True)

    email     = models.EmailField(unique=True)
    phone     = models.CharField(max_length=15, null=True, blank=True, default="null")
    image     = models.ImageField(blank=True, null=True)
    role      = models.ForeignKey(Role, on_delete=models.CASCADE, null=True, blank=True)
    signature = models.ImageField(blank=True, null=True)

    employee_id     = models.CharField(max_length=50, unique=True, null=True, blank=True)
    join_date       = models.DateField(blank=True, null=True)
    salary          = models.DecimalField(max_digits=20, decimal_places=2, blank=True, null=True)
    deduction_amount = models.DecimalField(max_digits=20, decimal_places=2, blank=True, null=True)
    nssf_amount     = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True,
                                          help_text="Monthly NSSF deduction amount")

    office_allocation = models.ForeignKey(
        'app.Office', on_delete=models.SET_NULL, blank=True, null=True,
        related_name='allocated_users'
    )

    otp_secret_key = models.CharField(max_length=255, blank=True, null=True)
    otp_valid_date = models.DateTimeField(blank=True, null=True)

    def save(self, *args, **kwargs):
        if not self.employee_id:
            last_user = (
                CustomUser.objects
                .exclude(employee_id__isnull=True)
                .exclude(employee_id__exact="")
                .order_by('id')
                .last()
            )
            if last_user and last_user.employee_id:
                try:
                    last_id = int(last_user.employee_id.split('-')[-1])
                except ValueError:
                    last_id = 0
            else:
                last_id = 0
            self.employee_id = f"MASC0-{last_id + 1:03d}"
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.username} ({self.email})"

    # ── permission shortcut ───────────────────────────────────────────────────

    def has_system_perm(self, codename: str) -> bool:
        """
        Returns True if the user is superuser OR their role grants this codename.
        Usage in views:  request.user.has_system_perm('loans-delete')
        Usage in templates: via {% user_has_perm request.user 'loans-delete' %}
        """
        if self.is_superuser:
            return True
        if self.role_id is None:
            return False
        return self.role.has_perm(codename)


# ──────────────────────────────────────────────────────────────────────────────
# Unchanged models
# ──────────────────────────────────────────────────────────────────────────────

class Profile(models.Model):
    user       = models.OneToOneField(CustomUser, on_delete=models.CASCADE)
    bio        = models.TextField(blank=True, null=True)
    location   = models.CharField(max_length=100, blank=True, null=True)
    birth_date = models.DateField(blank=True, null=True)

    def __str__(self):
        return f"Profile of {self.user.username}"


def generate_otp():
    return str(secrets.randbelow(10**6)).zfill(6)


class OtpToken(models.Model):
    user           = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    otp_code       = models.CharField(max_length=6, default=generate_otp)
    otp_created_at = models.DateTimeField(auto_now_add=True)
    otp_expires_at = models.DateTimeField(blank=True, null=True)

    def __str__(self):
        return f"OTP for {self.user.email}: {self.otp_code}"
