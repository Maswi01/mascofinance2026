"""
MASCO Microfinance — Serializers (Mobile-Ready)
===============================================
Badilisha: app/serializers.py

Changes from original:
  - ClientSerializer     → added checkno, registered_date; writable for POST/PATCH
  - LoanApplicationSerializer → writable for POST (create loan)
  - LoanRepaymentSerializer   → writable for POST (add repayment)
  - ExpenseSerializer    → writable for POST; field names consistent with model
"""
from rest_framework import serializers
from django.db.models import Sum
from .models import (
    Client, LoanApplication, LoanRepayment, LoanTopup,
    Office, Expense, ExpenseCategory, Salary, Nyongeza,
    BankCashTransaction, OfficeTransaction,
)


class OfficeSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Office
        fields = ['id', 'name', 'region', 'district', 'ward', 'street', 'founded_date']


# =============================================================================
#  CLIENT
# =============================================================================

class ClientSerializer(serializers.ModelSerializer):
    full_name               = serializers.SerializerMethodField(read_only=True)
    registered_office_name  = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model  = Client
        fields = [
            'id', 'full_name',
            'firstname', 'middlename', 'lastname',
            'phonenumber', 'date_of_birth', 'marital_status',
            # Employment
            'employername', 'idara', 'kaziyako', 'employmentcardno',
            'checkno',
            # Address
            'region', 'district', 'street',
            # Bank
            'bank_name', 'bank_branch', 'bank_account_number', 'account_name',
            # Guarantor
            'mdhamini_name', 'mdhamini_phonenumber', 'mdhamini_checkno',
            'mdhamini_employername',
            # Meta
            'registered_date', 'registered_office', 'registered_office_name',
        ]
        # registered_office is writable (set by perform_create in the view)
        extra_kwargs = {
            'registered_office': {'required': False, 'allow_null': True},
            'middlename':        {'required': False, 'allow_blank': True, 'allow_null': True},
            'date_of_birth':     {'required': False, 'allow_null': True},
            'marital_status':    {'required': False, 'allow_blank': True, 'allow_null': True},
            'employername':      {'required': False, 'allow_blank': True, 'allow_null': True},
            'idara':             {'required': False, 'allow_blank': True, 'allow_null': True},
            'kaziyako':          {'required': False, 'allow_blank': True, 'allow_null': True},
            'employmentcardno':  {'required': False, 'allow_blank': True, 'allow_null': True},
            'checkno':           {'required': False, 'allow_blank': True, 'allow_null': True},
            'region':            {'required': False, 'allow_blank': True, 'allow_null': True},
            'district':          {'required': False, 'allow_blank': True, 'allow_null': True},
            'street':            {'required': False, 'allow_blank': True, 'allow_null': True},
            'bank_name':         {'required': False, 'allow_blank': True, 'allow_null': True},
            'bank_branch':       {'required': False, 'allow_blank': True, 'allow_null': True},
            'bank_account_number':{'required': False,'allow_blank': True, 'allow_null': True},
            'account_name':      {'required': False, 'allow_blank': True, 'allow_null': True},
            'mdhamini_name':         {'required': False, 'allow_blank': True, 'allow_null': True},
            'mdhamini_phonenumber':  {'required': False, 'allow_blank': True, 'allow_null': True},
            'mdhamini_checkno':      {'required': False, 'allow_blank': True, 'allow_null': True},
            'mdhamini_employername': {'required': False, 'allow_blank': True, 'allow_null': True},
        }

    def get_full_name(self, obj):
        parts = [obj.firstname, obj.middlename, obj.lastname]
        return ' '.join(p for p in parts if p).strip()

    def get_registered_office_name(self, obj):
        return obj.registered_office.name if obj.registered_office else None


# =============================================================================
#  LOAN REPAYMENT
# =============================================================================

class LoanRepaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model  = LoanRepayment
        fields = [
            'id', 'repayment_amount', 'repayment_date',
            'transaction_method', 'payment_month', 'created_at',
        ]
        extra_kwargs = {
            'repayment_date':     {'required': False},
            'transaction_method': {'required': False, 'allow_blank': True, 'allow_null': True},
            'payment_month':      {'required': False, 'allow_null': True},
        }


# =============================================================================
#  LOAN APPLICATION
# =============================================================================

class LoanApplicationSerializer(serializers.ModelSerializer):
    client_name     = serializers.SerializerMethodField(read_only=True)
    client_phone    = serializers.SerializerMethodField(read_only=True)
    repayments      = LoanRepaymentSerializer(many=True, read_only=True)
    repayment_count = serializers.SerializerMethodField(read_only=True)
    amount_paid     = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model  = LoanApplication
        fields = [
            'id', 'client', 'client_name', 'client_phone',
            'loan_amount', 'loan_purpose', 'loan_type',
            'interest_rate', 'payment_period_months',
            'application_date', 'status',
            'monthly_installment', 'interest_amount',
            'total_interest_amount', 'total_repayment_amount',
            'first_repayment_date', 'repayment_amount_remaining',
            'office', 'transaction_method', 'is_approved',
            'created_at', 'updated_at',
            'repayments', 'repayment_count', 'amount_paid',
        ]
        read_only_fields = [
            'monthly_installment', 'interest_amount',
            'total_interest_amount', 'total_repayment_amount',
            'repayment_amount_remaining', 'is_approved',
            'created_at', 'updated_at',
        ]
        extra_kwargs = {
            'loan_purpose':        {'required': False, 'allow_blank': True, 'allow_null': True},
            'first_repayment_date':{'required': False, 'allow_null': True},
            'transaction_method':  {'required': False, 'allow_blank': True, 'allow_null': True},
            'office':              {'required': False, 'allow_blank': True, 'allow_null': True},
            'status':              {'required': False},
        }

    def get_client_name(self, obj):
        return f"{obj.client.firstname} {obj.client.lastname}"

    def get_client_phone(self, obj):
        return obj.client.phonenumber

    def get_repayment_count(self, obj):
        return obj.repayments.count()

    def get_amount_paid(self, obj):
        result = obj.repayments.aggregate(total=Sum('repayment_amount'))
        return result['total'] or 0


# =============================================================================
#  EXPENSE CATEGORY
# =============================================================================

class ExpenseCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model  = ExpenseCategory
        fields = ['id', 'name', 'created_at']


# =============================================================================
#  EXPENSE
# =============================================================================

class ExpenseSerializer(serializers.ModelSerializer):
    category_name = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model  = Expense
        fields = [
            'id', 'description', 'amount',
            # expense_date is auto set (auto_now_add); transaction_date is manually set
            'expense_date', 'transaction_date',
            'office', 'transaction_type', 'category_name',
            'expense_account', 'payment_method',
            'attachment',
            'created_at',
        ]
        extra_kwargs = {
            # transaction_type is the FK to ExpenseCategory (required for create)
            'transaction_type':  {'required': True},
            'expense_date':      {'read_only': True},   # auto_now_add
            'transaction_date':  {'required': False, 'allow_null': True},
            'office':            {'required': False, 'allow_blank': True, 'allow_null': True},
            'expense_account':   {'required': False, 'allow_blank': True, 'allow_null': True},
            'payment_method':    {'required': False, 'allow_blank': True, 'allow_null': True},
            'attachment':        {'required': False, 'allow_null': True},
        }

    def get_category_name(self, obj):
        return obj.transaction_type.name if obj.transaction_type else None


# =============================================================================
#  DASHBOARD STATS (read-only — used internally)
# =============================================================================

class DashboardStatsSerializer(serializers.Serializer):
    total_clients       = serializers.IntegerField()
    total_active_loans  = serializers.IntegerField()
    total_loan_amount   = serializers.DecimalField(max_digits=20, decimal_places=2)
    total_outstanding   = serializers.DecimalField(max_digits=20, decimal_places=2)
    total_repaid        = serializers.DecimalField(max_digits=20, decimal_places=2)
    new_clients_this_month = serializers.IntegerField()
    loans_this_month    = serializers.IntegerField()
    expenses_this_month = serializers.DecimalField(max_digits=20, decimal_places=2)
