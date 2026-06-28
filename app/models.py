
from django.db import models, transaction
from django.core.exceptions import ValidationError
from django.contrib.auth.models import AbstractUser

from useraccount.models import CustomUser
from decimal import Decimal

# Create your models here.


class Office(models.Model):
    name = models.CharField(max_length=255)
    region = models.CharField(max_length=255, blank=True, null=True)
    district = models.CharField(max_length=255, blank=True, null=True)
    ward = models.CharField(max_length=255, blank=True, null=True)
    street = models.CharField(max_length=255, blank=True, null=True)
    founded_date = models.DateField(blank=True, null=True)
    head_officer = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, blank=True, null=True, related_name='headed_offices')

    def __str__(self):
        return self.name
    
    
class UserOfficeAssignment(models.Model):
    user   = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='office_assignments')
    office = models.ForeignKey(Office, on_delete=models.CASCADE, related_name='user_assignments')
    assigned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'office')
        ordering = ['id']
    
class Client(models.Model):
    firstname = models.CharField(max_length=255)
    middlename = models.CharField(max_length=255)
    lastname = models.CharField(max_length=255)
    phonenumber = models.CharField(max_length=20, blank=True, null=True)
    date_of_birth = models.DateField(blank=True, null=True)
    marital_status = models.CharField(max_length=50, blank=True, null=True)
    employername = models.CharField(max_length=255, blank=True, null=True)
    idara = models.CharField(max_length=255, blank=True, null=True)
    kaziyako = models.CharField(max_length=255, blank=True, null=True)
    employmentcardno = models.CharField(max_length=255, blank=True, null=True)
    tareheya_kuajiriwa = models.DateField(blank=True, null=True)
    umri_kazini = models.IntegerField(blank=True, null=True)
    tarehe_ya_kustaafu = models.DateField(blank=True, null=True)
    region = models.CharField(max_length=255, blank=True, null=True)
    district = models.CharField(max_length=255, blank=True, null=True)
    street = models.CharField(max_length=255, blank=True, null=True)
    checkno = models.CharField(max_length=255, blank=True, null=True)
    mkoa = models.CharField(max_length=255, blank=True, null=True)
    wilaya = models.CharField(max_length=255, blank=True, null=True)
    tarafa = models.CharField(max_length=255, blank=True, null=True)
    kata = models.CharField(max_length=255, blank=True, null=True)
    mtaa = models.CharField(max_length=255, blank=True, null=True)
    wategemezi_wako = models.CharField(max_length=255, blank=True, null=True)
    bank_name = models.CharField(max_length=255, blank=True, null=True)
    bank_branch = models.CharField(max_length=255, blank=True, null=True)
    bank_account_number = models.CharField(max_length=255, blank=True, null=True)
    account_name = models.CharField(max_length=255, blank=True, null=True)
    account_type = models.CharField(max_length=100, blank=True, null=True)

    # ── Taarifa za Mdhamini (Guarantor) ──────────────────────────────────────
    mdhamini_jina_kamili = models.CharField(max_length=255, blank=True, null=True)
    mdhamini_checkno = models.CharField(max_length=255, blank=True, null=True)
    mdhamini_kitambulisho_kazi = models.CharField(max_length=255, blank=True, null=True)
    mdhamini_kazi = models.CharField(max_length=255, blank=True, null=True)
    mdhamini_kituo_kazi = models.CharField(max_length=255, blank=True, null=True)
    mdhamini_kata = models.CharField(max_length=255, blank=True, null=True)
    mdhamini_tarafa = models.CharField(max_length=255, blank=True, null=True)
    mdhamini_wilaya = models.CharField(max_length=255, blank=True, null=True)
    mdhamini_mkoa = models.CharField(max_length=255, blank=True, null=True)
    mdhamini_simu = models.CharField(max_length=20, blank=True, null=True)

    registered_date = models.DateField(auto_now_add=True)
    registered_by = models.ForeignKey(CustomUser, on_delete=models.CASCADE, blank=True, null=True, related_name='registered_clients')
    registered_office = models.ForeignKey(Office, on_delete=models.CASCADE, null=True, blank=True, related_name='office_registered')

    def __str__(self):
        return f"{self.firstname} {self.lastname}"

# This model is for recording transactions between offices, not between bank and cash accounts. The office_from and office_to fields indicate which offices are involved in the transaction, while the transaction_type field indicates the nature of the transaction (e.g., fund transfer, resource allocation).   
class OfficeTransaction(models.Model):
    office_from        = models.ForeignKey(Office, on_delete=models.CASCADE, related_name='transactions')
    office_to          = models.ForeignKey(Office, on_delete=models.CASCADE, related_name='received_transactions')
    transaction_type   = models.CharField(max_length=100)
    transaction_method = models.CharField(max_length=100, null=True, blank=True)
    amount             = models.DecimalField(max_digits=50, decimal_places=2)
    transaction_date   = models.DateField(auto_now_add=True)
    attachment         = models.FileField(upload_to='office_transaction_attachments/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    processed_by       = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='processed_transactions')
 
    def __str__(self):
        return f"{self.transaction_type} - {self.amount} at {self.office_to.name}"


    
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from dateutil.relativedelta import relativedelta


class LoanApplication(models.Model):
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='loan_applications')

    loan_amount   = models.DecimalField(max_digits=10, decimal_places=2)
    loan_purpose  = models.TextField(null=True, blank=True)
    loan_type     = models.CharField(max_length=100)

    interest_rate         = models.DecimalField(max_digits=5, decimal_places=2)
    payment_period_months = models.IntegerField()

    # ✅ default=date.today instead of auto_now_add=True
    # auto_now_add sets the date in the DB but does NOT update self.application_date
    # in memory after super().save(), so self.application_date.day → AttributeError
    application_date = models.DateField(default=date.today)

    status = models.CharField(max_length=50, default='Approved')

    monthly_installment    = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    interest_amount        = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    total_interest_amount  = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    total_repayment_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    first_repayment_date   = models.DateField(null=True, blank=True)

    repayment_amount_remaining = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)

    processed_by       = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='processed_loans')
    office             = models.CharField(max_length=255, blank=True, null=True)
    transaction_method = models.CharField(max_length=100, null=True, blank=True)

    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)
    is_approved = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        super().save(*args, **kwargs)

        if is_new:
            # self.application_date is always a real date object (default=date.today)
            if not self.first_repayment_date:
                if self.application_date.day <= 18:
                    self.first_repayment_date = self.application_date.replace(day=28)
                else:
                    self.first_repayment_date = (
                        self.application_date + relativedelta(months=1)
                    ).replace(day=28)

            P = Decimal(str(self.loan_amount))
            I = Decimal(str(self.interest_rate))
            N = Decimal(str(self.payment_period_months))

            total_interest  = (I / Decimal('100')) * P
            total_repayment = P + total_interest
            monthly         = total_repayment / N

            self.interest_amount        = total_interest.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            self.total_interest_amount  = self.interest_amount
            self.total_repayment_amount = total_repayment.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            self.monthly_installment    = monthly.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            self.repayment_amount_remaining = self.total_repayment_amount

            super().save(update_fields=[
                'first_repayment_date',
                'interest_amount',
                'total_interest_amount',
                'total_repayment_amount',
                'monthly_installment',
                'repayment_amount_remaining',
            ])

    def __str__(self):
        return f"Loan Application for {self.client.firstname} {self.client.lastname} - {self.status}"

  
       
class LoanRepayment(models.Model):
    loan_application   = models.ForeignKey(LoanApplication, on_delete=models.CASCADE, related_name='repayments')
    repayment_amount   = models.DecimalField(max_digits=10, decimal_places=2)
    repayment_date     = models.DateField(null=True, blank=True)
    transaction_method = models.CharField(max_length=100, null=True, blank=True)
    payment_month      = models.DateField(null=True, blank=True)
    processed_by       = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='processed_repayments')
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        super().save(*args, **kwargs)

        if is_new:
            # Decrement the remaining balance on the parent loan
            LoanApplication.objects.filter(pk=self.loan_application_id).update(
                repayment_amount_remaining=models.F('repayment_amount_remaining') - self.repayment_amount
            )

    def delete(self, *args, **kwargs):
        # Restore balance if repayment is deleted
        LoanApplication.objects.filter(pk=self.loan_application_id).update(
            repayment_amount_remaining=models.F('repayment_amount_remaining') + self.repayment_amount
        )
        super().delete(*args, **kwargs)

    def __str__(self):
        return f"Repayment of {self.repayment_amount} for {self.loan_application.client.firstname} {self.loan_application.client.lastname}"
    
    
class LoanTopup(models.Model):
    loan_application = models.ForeignKey(LoanApplication, on_delete=models.CASCADE, related_name='topups')
    topup_amount = models.DecimalField(max_digits=10, decimal_places=2)
    interest_rate = models.DecimalField(max_digits=5, decimal_places=2)  # annual %
    transaction_method = models.CharField(max_length=100, null=True, blank=True) #cash or bank
    topup_date = models.DateField(auto_now_add=True)
    old_balance_cleared = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    payment_month = models.DateField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    
    processed_by = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='processed_topups')

    def __str__(self):
        return f"Top-up of {self.topup_amount} for {self.loan_application.client.firstname} {self.loan_application.client.lastname}"
   
class Salary(models.Model):
    employee = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='salaries')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    salary_for_month = models.DateField()
    transaction_method = models.CharField(max_length=100, default='bank', null=True, blank=True)
    fund_source = models.ForeignKey(Office, on_delete=models.CASCADE, null=True,blank=True)
    payment_date = models.DateField(auto_now_add=True)
    processed_by = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='processed_salaries')
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)

    def __str__(self):
        return f"Salary of {self.amount} for {self.employee.get_full_name()}"

class SalaryAdvance(models.Model):
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]

    employee = models.ForeignKey(CustomUser,on_delete=models.CASCADE,related_name='salary_advances' )
    account = models.CharField(max_length=255,default='Salary Advance',help_text='Type of deduction account e.g. Salary Advance, Loan, etc.')
    amount = models.DecimalField(max_digits=15,decimal_places=2,help_text='Total loan/advance amount')
    payment_period = models.PositiveIntegerField( help_text='Number of months to repay')
    starting_payment_month = models.DateField(help_text='First month deduction begins (stored as 1st of that month)')
    ending_payment_month = models.DateField(help_text='Last month of deduction (auto-calculated)',blank=True, null=True)
    monthly_installment = models.DecimalField(max_digits=15, decimal_places=2,blank=True,null=True,help_text='Auto-calculated: amount / payment_period')
    status = models.CharField(max_length=20,choices=STATUS_CHOICES,default='active')
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Salary Advance'
        verbose_name_plural = 'Salary Advances'

    def save(self, *args, **kwargs):
        """Auto-calculate monthly installment and ending month on save."""
        from dateutil.relativedelta import relativedelta

        if self.amount and self.payment_period and self.payment_period > 0:
            self.monthly_installment = round(self.amount / self.payment_period, 2)

        if self.starting_payment_month and self.payment_period:
            self.ending_payment_month = (
                self.starting_payment_month
                + relativedelta(months=self.payment_period - 1)
            )

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.employee.get_full_name()} - {self.account} ({self.amount})"

    def get_installment_schedule(self):
        """Return list of (month_label, installment_amount) tuples."""
        from dateutil.relativedelta import relativedelta
        schedule = []
        if not self.starting_payment_month or not self.payment_period:
            return schedule
        for i in range(self.payment_period):
            month_date = self.starting_payment_month + relativedelta(months=i)
            schedule.append({
                'month': month_date.strftime('%m-%Y'),
                'amount': self.monthly_installment or 0,
            })
        return schedule


# expenses category == transaction type
class ExpenseCategory(models.Model):
    name = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name
      
class Expense(models.Model):
    description = models.TextField()
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    expense_date = models.DateField(auto_now_add=True)
    recorded_by = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='recorded_expenses')
    office = models.CharField(max_length=255, blank=True, null=True)
    
    transaction_type = models.ForeignKey(ExpenseCategory, on_delete=models.CASCADE, related_name='expenses')
    expense_account = models.CharField(max_length=255, blank=True, null=True)
    attachment = models.FileField(upload_to='expense_attachments/', blank=True, null=True)
    payment_method = models.CharField(max_length=100, blank=True, null=True) #bank or cash
    transaction_date = models.DateField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)

    def __str__(self):
        return f"Expense: {self.description} - {self.amount}"


class BankCharge(models.Model):
    description = models.TextField()
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    expense_date = models.DateField(auto_now_add=True)
    recorded_by = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='bank_charge_admin')
    office = models.CharField(max_length=255, blank=True, null=True)
    
    attachment = models.FileField(upload_to='expense_attachments/', blank=True, null=True)
    payment_method = models.CharField(max_length=100, blank=True, null=True) #bank or cash
    transaction_date = models.DateField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)

    def __str__(self):
        return f"BankCharge: {self.description} - {self.amount}"
       
# 
# class BankTransaction(models.Model):
#     office = models.CharField(max_length=255, blank=True, null=True)
#     transaction_type = models.CharField(max_length=100)
#     amount = models.DecimalField(max_digits=10, decimal_places=2)
#     transaction_date = models.DateField(auto_now_add=True)
#     processed_by = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='processed_bank_transactions')

#     def __str__(self):
#         return f"{self.transaction_type} - {self.amount} at {self.office}"
    



    

class Nyongeza(models.Model):
    description = models.TextField()
    amount = models.DecimalField(max_digits=20, decimal_places=2)
    Office = models.ForeignKey(Office, on_delete=models.CASCADE, null=True, blank=True)
    deposit_method = models.CharField(max_length=100, null=True, blank=True)
    date = models.DateField(auto_now_add=True)
    created_at = models.DateTimeField(auto_now_add=True)
    recorded_by = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='recorded_nyongezas')

    def __str__(self):
        return f"Nyongeza: {self.description} - {self.amount}"
    
# ================= MAY BE REMOVED =====================================
class BankAmount(models.Model):
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    last_updated = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Bank Amount: {self.amount}"
#======================================================================
    
class BranchBalance(models.Model):
    """Track branch balances (office balance and bank balance)"""
    branch = models.ForeignKey('Office', on_delete=models.CASCADE, related_name='branch_balances')
    office_balance = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    bank_balance = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    last_updated = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_by = models.ForeignKey(CustomUser, on_delete=models.SET_NULL, null=True)
    
    class Meta:
        unique_together = ['branch', 'last_updated']
    
    def __str__(self):
        return f"{self.branch.name} - Office: {self.office_balance}, Bank: {self.bank_balance}"

class HQTransaction(models.Model):
    """Track HQ-level transactions that affect branch balances."""
    from_branch      = models.ForeignKey('Office', on_delete=models.CASCADE, related_name='hq_transactions_from', null=True, blank=True)
    to_branch        = models.ForeignKey('Office', on_delete=models.CASCADE, related_name='hq_transactions_to',   null=True, blank=True)
    amount           = models.DecimalField(max_digits=15, decimal_places=2)
    description      = models.TextField()
    transaction_date = models.DateField(null=True, blank=True)
    attachment       = models.FileField(upload_to='hq_transaction_attachments/', blank=True, null=True)
    processed_by     = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    processed_at     = models.DateTimeField(auto_now_add=True)
    created_at = models.DateTimeField(auto_now_add=True)
 
    def __str__(self):
        return f"{self.amount} on {self.transaction_date}"
    
    
# This model is for recording transactions WITHDRAW AND DEPOSIT between bank and cash accounts, not between offices. The office field indicates which office is involved in the transaction, but the source and destination fields indicate whether it's a bank or cash transaction.  
class BankCashTransaction(models.Model):
    office_from      = models.ForeignKey(Office, on_delete=models.CASCADE, related_name='transactions_bank_cash')
    source           = models.CharField(max_length=100)       # bank or cash
    destination      = models.CharField(max_length=100)       # bank or cash
    amount           = models.DecimalField(max_digits=10, decimal_places=2)
    transaction_date = models.DateField(auto_now_add=True)
    created_at = models.DateTimeField(auto_now_add=True)
    attachment       = models.FileField(upload_to='bank_cash_attachments/', blank=True, null=True)
 
    def __str__(self):
        return f"{self.source} to {self.destination} - {self.amount} at {self.office_from.name}"