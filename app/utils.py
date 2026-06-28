# app/utils.py
from decimal import Decimal
from django.db.models import Sum
from app.models import (
    LoanRepayment,
    LoanApplication,
    Nyongeza,
    Expense,
    OfficeTransaction,
    BankCharge,
    BankCashTransaction,
)


def get_office_balances(office=None):
    from decimal import Decimal
    from django.db.models import Sum

    def rep_qs():
        qs = LoanRepayment.objects.all()
        if office:
            qs = qs.filter(loan_application__office__iexact=office.name)
        return qs

    def loan_qs():
        qs = LoanApplication.objects.all()
        if office:
            qs = qs.filter(office__iexact=office.name)
        return qs

    def nyo_qs():
        qs = Nyongeza.objects.all()
        if office:
            qs = qs.filter(Office=office)
        return qs

    def exp_qs():
        qs = Expense.objects.all()
        if office:
            qs = qs.filter(office__iexact=office.name)
        return qs

    def transfer_in_qs():
        qs = OfficeTransaction.objects.all()
        if office:
            qs = qs.filter(office_to=office)
        return qs

    def transfer_out_non_hq_qs():
        qs = OfficeTransaction.objects.all()
        if office:
            qs = qs.filter(office_from=office)
        return qs.exclude(office_to__name__iexact='HQ')

    def transfer_out_hq_qs():
        qs = OfficeTransaction.objects.all()
        if office:
            qs = qs.filter(office_from=office)
        return qs.filter(office_to__name__iexact='HQ')

    def transfer_out_qs():
        qs = OfficeTransaction.objects.all()
        if office:
            qs = qs.filter(office_from=office)
        return qs

    def bank_charge_qs():
        qs = BankCharge.objects.all()
        if office:
            qs = qs.filter(office__iexact=office.name)
        return qs

    def bank_cash_txn_qs():
        qs = BankCashTransaction.objects.all()
        if office:
            qs = qs.filter(office_from=office)
        return qs

    D = Decimal('0')

    # ── Internal transfers ────────────────────────────────────────────────────
    cash_to_bank = bank_cash_txn_qs().filter(
        source__iexact='cash', destination__iexact='bank'
    ).aggregate(t=Sum('amount'))['t'] or D

    bank_to_cash = bank_cash_txn_qs().filter(
        source__iexact='bank', destination__iexact='cash'
    ).aggregate(t=Sum('amount'))['t'] or D

    # ═════════════════════════════════════════════════════════════════════════
    # CASH IN OFFICE
    # Mirrors: opening_cash + period cash_in_office
    #
    # opening_cash IN:  cash_rep_b + cash_hazina_b + cash_nyo_b + bank_to_cash_b
    # opening_cash OUT: cash_exp_b + cash_loan_b + cash_charge_b + cash_to_bank_b
    #
    # period cash_in_office:
    #   + cash_rep_period (hazina excluded)
    #   + bank_to_cash_period
    #   + cash_nyo_period
    #   - loan_cash_amount
    #   - cash_exp_period
    #   - cash_charge_period
    #   - cash_to_bank_period
    #
    # Combined all-time = opening terms + period terms.
    # Hazina cash appears in opening IN but NOT in period — so it must be included.
    # ═════════════════════════════════════════════════════════════════════════

    cash_rep = rep_qs().exclude(
        loan_application__loan_type__iexact='Hazina'
    ).filter(transaction_method__iexact='cash').aggregate(t=Sum('repayment_amount'))['t'] or D

    cash_hazina = rep_qs().filter(
        loan_application__loan_type__iexact='Hazina',
        transaction_method__iexact='cash',
    ).aggregate(t=Sum('repayment_amount'))['t'] or D

    cash_nyo = nyo_qs().filter(
        deposit_method__iexact='cash'
    ).aggregate(t=Sum('amount'))['t'] or D

    cash_loans = loan_qs().filter(
        transaction_method__iexact='cash'
    ).aggregate(t=Sum('loan_amount'))['t'] or D

    cash_exp = exp_qs().filter(
        payment_method__iexact='cash'
    ).aggregate(t=Sum('amount'))['t'] or D

    cash_charge = bank_charge_qs().filter(
        payment_method__iexact='cash'
    ).aggregate(t=Sum('amount'))['t'] or D

    cash_in_office = (
        cash_rep + cash_hazina + cash_nyo + bank_to_cash
    ) - (
        cash_loans + cash_exp + cash_charge + cash_to_bank
    )

    # ═════════════════════════════════════════════════════════════════════════
    # CASH IN BANK
    # Mirrors: opening_bank + period cash_in_bank
    #
    # opening_bank IN:  bank_rep_b + bank_hazina_b + bank_nyo_b + bank_transfer_in_b + cash_to_bank_b
    # opening_bank OUT: bank_exp_b + bank_loan_b + bank_transfer_out_b + bank_charge_b + bank_to_cash_b
    #
    # period cash_in_bank:
    #   + bank_rep_period (hazina excluded)
    #   + bank_nyo_period
    #   + bank_transfer_in_period
    #   + cash_to_bank_period
    #   - loan_bank_amount
    #   - bank_exp_period
    #   - bank_transfer_out_period  (= kituo + mkurugenzi)
    #   - bank_charge_period
    #   - bank_to_cash_period
    #
    # Hazina bank appears in opening IN but NOT in period — so it must be included.
    # bank_transfer_out_period uses transfer_out_qs (all), same as opening.
    # ═════════════════════════════════════════════════════════════════════════

    bank_rep = rep_qs().exclude(
        loan_application__loan_type__iexact='Hazina'
    ).filter(transaction_method__iexact='bank').aggregate(t=Sum('repayment_amount'))['t'] or D

    bank_hazina = rep_qs().filter(
        loan_application__loan_type__iexact='Hazina',
        transaction_method__iexact='bank',
    ).aggregate(t=Sum('repayment_amount'))['t'] or D

    bank_nyo = nyo_qs().filter(
        deposit_method__iexact='bank'
    ).aggregate(t=Sum('amount'))['t'] or D

    bank_transfer_in = transfer_in_qs().aggregate(t=Sum('amount'))['t'] or D

    bank_loans = loan_qs().filter(
        transaction_method__iexact='bank'
    ).aggregate(t=Sum('loan_amount'))['t'] or D

    bank_exp = exp_qs().filter(
        payment_method__iexact='bank'
    ).aggregate(t=Sum('amount'))['t'] or D

    bank_transfer_out = transfer_out_qs().aggregate(t=Sum('amount'))['t'] or D

    bank_charge = bank_charge_qs().filter(
        payment_method__iexact='bank'
    ).aggregate(t=Sum('amount'))['t'] or D

    cash_in_bank = (
        bank_rep + bank_hazina + bank_nyo + bank_transfer_in + cash_to_bank
    ) - (
        bank_loans + bank_exp + bank_transfer_out + bank_charge + bank_to_cash
    )

    return cash_in_office, cash_in_bank


# def get_office_balances(office=None):
#     """
#     Returns (cash_in_office, cash_in_bank) calculated from all transactions
#     ever recorded for the given office (no date filter).
#     Pass office=None for all branches combined.
#     Transfers are now split by transaction_method (cash/bank).
#     """
#     from decimal import Decimal
#     from django.db.models import Sum

#     def rep_qs():
#         qs = LoanRepayment.objects.all()
#         if office:
#             qs = qs.filter(loan_application__office__iexact=office.name)
#         return qs

#     def loan_qs():
#         qs = LoanApplication.objects.all()
#         if office:
#             qs = qs.filter(office__iexact=office.name)
#         return qs

#     def nyo_qs():
#         qs = Nyongeza.objects.all()
#         if office:
#             qs = qs.filter(Office=office)
#         return qs

#     def exp_qs():
#         qs = Expense.objects.all()
#         if office:
#             qs = qs.filter(office__iexact=office.name)
#         return qs

#     def transfer_in_qs():
#         qs = OfficeTransaction.objects.all()
#         if office:
#             qs = qs.filter(office_to=office)
#         return qs

#     def transfer_out_qs():
#         qs = OfficeTransaction.objects.all()
#         if office:
#             qs = qs.filter(office_from=office)
#         return qs

#     def bank_charge_qs():
#         qs = BankCharge.objects.all()
#         if office:
#             qs = qs.filter(office__iexact=office.name)
#         return qs

#     def bank_cash_txn_qs():
#         qs = BankCashTransaction.objects.all()
#         if office:
#             qs = qs.filter(office_from=office)
#         return qs

#     D = Decimal('0')

#     # ── Internal transfers between cash and bank ──────────────────────────────
#     cash_to_bank = bank_cash_txn_qs().filter(
#         source__iexact='cash', destination__iexact='bank'
#     ).aggregate(t=Sum('amount'))['t'] or D

#     bank_to_cash = bank_cash_txn_qs().filter(
#         source__iexact='bank', destination__iexact='cash'
#     ).aggregate(t=Sum('amount'))['t'] or D

#     # ── CASH IN ───────────────────────────────────────────────────────────────
#     cash_rep = rep_qs().exclude(
#         loan_application__loan_type__iexact='Hazina'
#     ).filter(transaction_method__iexact='cash').aggregate(t=Sum('repayment_amount'))['t'] or D

#     cash_hazina = rep_qs().filter(
#         loan_application__loan_type__iexact='Hazina',
#         transaction_method__iexact='cash'
#     ).aggregate(t=Sum('repayment_amount'))['t'] or D

#     cash_nyo = nyo_qs().filter(
#         deposit_method__iexact='cash'
#     ).aggregate(t=Sum('amount'))['t'] or D

#     cash_transfer_in = transfer_in_qs().filter(
#         transaction_method__iexact='cash'
#     ).aggregate(t=Sum('amount'))['t'] or D

#     # ── CASH OUT ──────────────────────────────────────────────────────────────
#     cash_loans = loan_qs().filter(
#         transaction_method__iexact='cash'
#     ).aggregate(t=Sum('loan_amount'))['t'] or D

#     cash_exp = exp_qs().filter(
#         payment_method__iexact='cash'
#     ).aggregate(t=Sum('amount'))['t'] or D

#     cash_charges = bank_charge_qs().filter(
#         payment_method__iexact='cash'
#     ).aggregate(t=Sum('amount'))['t'] or D

#     cash_transfer_out = transfer_out_qs().filter(
#         transaction_method__iexact='cash'
#     ).aggregate(t=Sum('amount'))['t'] or D

#     # cash_to_bank leaves cash, bank_to_cash enters cash
#     cash_in_office = (
#         cash_rep  + cash_nyo + bank_to_cash + cash_transfer_in
#     ) - (
#         cash_loans + cash_exp + cash_charges + cash_to_bank + cash_transfer_out
#     )

#     # ── BANK IN ───────────────────────────────────────────────────────────────
#     bank_rep = rep_qs().exclude(
#         loan_application__loan_type__iexact='Hazina'
#     ).filter(transaction_method__iexact='bank').aggregate(t=Sum('repayment_amount'))['t'] or D

#     bank_hazina = rep_qs().filter(
#         loan_application__loan_type__iexact='Hazina',
#         transaction_method__iexact='bank'
#     ).aggregate(t=Sum('repayment_amount'))['t'] or D

#     bank_nyo = nyo_qs().filter(
#         deposit_method__iexact='bank'
#     ).aggregate(t=Sum('amount'))['t'] or D

#     bank_transfer_in = transfer_in_qs().filter(
#         transaction_method__iexact='bank'
#     ).aggregate(t=Sum('amount'))['t'] or D

#     # ── BANK OUT ──────────────────────────────────────────────────────────────
#     bank_loans = loan_qs().filter(
#         transaction_method__iexact='bank'
#     ).aggregate(t=Sum('loan_amount'))['t'] or D

#     bank_exp = exp_qs().filter(
#         payment_method__iexact='bank'
#     ).aggregate(t=Sum('amount'))['t'] or D

#     bank_charges = bank_charge_qs().filter(
#         payment_method__iexact='bank'
#     ).aggregate(t=Sum('amount'))['t'] or D

#     bank_transfer_out = transfer_out_qs().filter(
#         transaction_method__iexact='bank'
#     ).aggregate(t=Sum('amount'))['t'] or D

#     # cash_to_bank enters bank, bank_to_cash leaves bank
#     cash_in_bank = (
#         bank_rep + bank_nyo + bank_transfer_in + cash_to_bank
#     ) - (
#         bank_loans + bank_exp + bank_charges + bank_transfer_out + bank_to_cash
#     )

#     return cash_in_office, cash_in_bank


