from rest_framework import serializers
from django.db.models import Sum
from .models import (
    Client, LoanApplication, LoanRepayment, LoanTopup,
    Office, Expense, ExpenseCategory, Salary, Nyongeza,
    BankCashTransaction, OfficeTransaction
)


class OfficeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Office
        fields = ['id', 'name', 'region', 'district', 'ward', 'street', 'founded_date']


class ClientSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    registered_office_name = serializers.SerializerMethodField()

    class Meta:
        model = Client
        fields = [
            'id', 'full_name', 'firstname', 'middlename', 'lastname',
            'phonenumber', 'date_of_birth', 'marital_status',
            'employername', 'idara', 'kaziyako', 'employmentcardno',
            'region', 'district', 'street',
            'bank_name', 'bank_branch', 'bank_account_number', 'account_name',
            'registered_date', 'registered_office_name',
        ]

    def get_full_name(self, obj):
        return f"{obj.firstname} {obj.middlename} {obj.lastname}".strip()

    def get_registered_office_name(self, obj):
        return obj.registered_office.name if obj.registered_office else None


class LoanRepaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = LoanRepayment
        fields = [
            'id', 'repayment_amount', 'repayment_date',
            'transaction_method', 'payment_month', 'created_at'
        ]


class LoanApplicationSerializer(serializers.ModelSerializer):
    client_name = serializers.SerializerMethodField()
    client_phone = serializers.SerializerMethodField()
    repayments = LoanRepaymentSerializer(many=True, read_only=True)
    repayment_count = serializers.SerializerMethodField()
    amount_paid = serializers.SerializerMethodField()

    class Meta:
        model = LoanApplication
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

    def get_client_name(self, obj):
        return f"{obj.client.firstname} {obj.client.lastname}"

    def get_client_phone(self, obj):
        return obj.client.phonenumber

    def get_repayment_count(self, obj):
        return obj.repayments.count()

    def get_amount_paid(self, obj):
        result = obj.repayments.aggregate(total=Sum('repayment_amount'))
        return result['total'] or 0


class ExpenseCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ExpenseCategory
        fields = ['id', 'name', 'created_at']


class ExpenseSerializer(serializers.ModelSerializer):
    category_name = serializers.SerializerMethodField()

    class Meta:
        model = Expense
        fields = [
            'id', 'description', 'amount', 'expense_date',
            'office', 'category_name', 'expense_account',
            'payment_method', 'transaction_date', 'created_at'
        ]

    def get_category_name(self, obj):
        return obj.transaction_type.name if obj.transaction_type else None


class DashboardStatsSerializer(serializers.Serializer):
    total_clients = serializers.IntegerField()
    total_active_loans = serializers.IntegerField()
    total_loan_amount = serializers.DecimalField(max_digits=20, decimal_places=2)
    total_outstanding = serializers.DecimalField(max_digits=20, decimal_places=2)
    total_repaid = serializers.DecimalField(max_digits=20, decimal_places=2)
    new_clients_this_month = serializers.IntegerField()
    loans_this_month = serializers.IntegerField()
    expenses_this_month = serializers.DecimalField(max_digits=20, decimal_places=2)
