"""
MASCO Microfinance - Complete API URLs
File: api/urls.py
"""
from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from . import views

urlpatterns = [

    # ── AUTH ──────────────────────────────────────────────────────────────────
    path('auth/login/',   views.api_login,            name='api_login'),
    path('auth/logout/',  views.api_logout,           name='api_logout'),
    path('auth/refresh/', TokenRefreshView.as_view(), name='token_refresh'),

    # ── DASHBOARD ─────────────────────────────────────────────────────────────
    path('dashboard/', views.api_dashboard, name='api_dashboard'),
    path('reports/balance-sheet/', views.api_balance_sheet_report, name='api_balance_sheet_report'),
    path('reports/trial-balance/', views.api_trial_balance_report, name='api_trial_balance_report'),

    # ── OFFICES & BRANCHES ────────────────────────────────────────────────────
    path('offices/',       views.OfficeListAPI.as_view(), name='api_office_list'),
    path('offices/add/',   views.api_office_add,          name='api_office_add'),
    path('my-branches/',   views.my_branches,             name='api_my_branches'),
    path('switch-branch/', views.switch_branch,           name='api_switch_branch'),

    # ── CLIENTS ───────────────────────────────────────────────────────────────
    path('clients/',                       views.ClientListAPI.as_view(),   name='api_client_list'),
    path('clients/<int:pk>/',              views.ClientDetailAPI.as_view(), name='api_client_detail'),
    path('clients/<int:client_id>/loans/',        views.client_loans,              name='api_client_loans'),
    path('clients/<int:client_id>/active-loans/', views.api_client_active_loans,   name='api_client_active_loans'),
    path('loans/<int:loan_id>/topup/',             views.api_loan_topup,             name='api_loan_topup'),

    # ── LOANS ─────────────────────────────────────────────────────────────────
    path('loans/',                              views.LoanListAPI.as_view(),              name='api_loan_list'),
    path('loans/<int:pk>/',                     views.LoanDetailAPI.as_view(),            name='api_loan_detail'),
    path('loans/<int:loan_id>/repayments/',     views.loan_repayments,                    name='api_loan_repayments'),
    path('loans/<int:loan_id>/schedule/',       views.api_loan_repayment_schedule,        name='api_loan_schedule'),
    path('loans/completed-approval/',           views.api_completed_loans_approval,       name='api_completed_loans_approval'),
    path('loans/completed-approval/approve/',   views.api_completed_loans_approve,        name='api_completed_loans_approve'),
    path('loans/<int:loan_id>/toggle-approve/',  views.api_toggle_loan_approve,             name='api_toggle_loan_approve'),

    # ── EXPENSES ──────────────────────────────────────────────────────────────
    path('expenses/',                    views.ExpenseListAPI.as_view(),         name='api_expense_list'),
    path('expense-categories/',          views.ExpenseCategoryListAPI.as_view(), name='api_expense_category_list'),
    path('expense-categories/add/',      views.api_expense_category_add,         name='api_expense_category_add'),
    path('expense-categories/<int:pk>/', views.api_expense_category_edit,        name='api_expense_category_edit'),

    # ── SALARIES ──────────────────────────────────────────────────────────────
    path('salaries/',        views.SalaryListAPI.as_view(), name='api_salaries'),
    path('salary-advances/', views.api_salary_advances,     name='api_salary_advances'),
    path('salary/slip/',     views.api_salary_slip,         name='api_salary_slip'),

    # ── PAYROLL ───────────────────────────────────────────────────────────────
    path('payroll/report/', views.api_payroll_report, name='api_payroll_report'),
    path('payroll/submit/', views.api_payroll_submit, name='api_payroll_submit'),

    # ── STAFF ─────────────────────────────────────────────────────────────────
    path('staff/',          views.api_staff,          name='api_staff'),
    path('staff/add/',      views.api_staff_add,      name='api_staff_add'),
    path('staff/block/',    views.api_staff_block,    name='api_staff_block'),
    path('staff/transfer/', views.api_staff_transfer, name='api_staff_transfer'),

    # ── NYONGEZA (Capital) ────────────────────────────────────────────────────
    path('nyongeza/',     views.api_nyongeza,         name='api_nyongeza'),
    path('nyongeza/add/', views.api_nyongeza_add,     name='api_nyongeza_add'),

    # ── OFFICE TRANSACTIONS ───────────────────────────────────────────────────
    path('office-transactions/',     views.api_office_transactions,      name='api_office_transactions'),
    path('office-transactions/add/',     views.api_office_transaction_add,       name='api_office_transaction_add'),
    path('office-transactions/<int:txn_id>/delete/', views.api_delete_office_transaction, name='api_delete_office_txn'),

    # ── LOAN UTILITIES ────────────────────────────────────────────────────────
    path('loan-report/',      views.api_loan_report,      name='api_loan_report'),
    path('loan-outstanding/', views.api_loan_outstanding,  name='api_loan_outstanding'),
    path('loan-receipt/',     views.api_loan_receipt,      name='api_loan_receipt'),
    path('loan-collection/',          views.api_loan_collection,          name='api_loan_collection'),
    path('hq/loans-report/',           views.api_branches_loan_report,     name='api_branches_loan_report'),
    path('hq/expense-report/',         views.api_hq_expense_report,        name='api_hq_expense_report'),
    path('hq/loan-collection/',        views.api_loan_collection_report,   name='api_loan_collection_report'),
    path('hq/bank-transfer/',          views.api_hq_bank_transfer_report,  name='api_hq_bank_transfer_report'),
    path('completed-loans/',  views.api_completed_loans,   name='api_completed_loans'),
    path('expired-loans/',    views.api_expired_loans,     name='api_expired_loans'),

    # ── LOANS OWED ────────────────────────────────────────────────────────────
    path('loans-owed/',               views.loans_owed_summary,      name='api_loans_owed_summary'),
    path('loans-owed/report/',         views.loans_owed_report,       name='api_loans_owed_report'),
    path('loans-owed/approve/',        views.api_loans_owed_approve,  name='api_loans_owed_approve'),

    # ── CUSTOMER ──────────────────────────────────────────────────────────────
    path('customer-statement/', views.api_customer_statement, name='api_customer_statement'),
    path('customer-report',     views.api_customer_report,    name='api_customer_report'),
    path('customer-report/',    views.api_customer_report,    name='api_customer_report_slash'),
    path('no-loan-customers/',  views.api_no_loan_customers,  name='api_no_loan_customers'),

    # ── FINANCIAL STATEMENTS ──────────────────────────────────────────────────
    path('financial-statement/',              views.api_financial_statement,          name='api_financial_statement'),
    path('branch-transactions/',              views.api_branch_transactions,          name='api_branch_transactions'),
    path('bank-cash-transaction-statement/',  views.api_bank_cash_transaction_statement, name='api_bank_cash_stmt'),
    path('bank-charges/add/',                  views.api_bank_charge_add,                 name='api_bank_charge_add'),
    path('bank-cash-transaction/add/',         views.api_bank_cash_transaction_add,          name='api_bank_cash_txn_add'),
    path('bank-cash-transaction/<int:txn_id>/delete/', views.api_delete_bank_cash_transaction, name='api_bank_cash_txn_delete'),

    # ── MONTHLY REPORTS ───────────────────────────────────────────────────────
    path('monthly-repayment/',                          views.api_monthly_repayment_v2,         name='api_monthly_repayment'),
    path('monthly-repayment/bulk-update/',              views.api_bulk_update_payment_month,    name='api_bulk_update_payment_month'),
    path('repayment/<str:repayment_type>/<int:repayment_id>/edit/', views.api_edit_repayment,   name='api_edit_repayment'),
    path('monthly-outstanding/', views.api_monthly_outstanding_v2,  name='api_monthly_outstanding'),

    # ── RECENT ACTIVITY ───────────────────────────────────────────────────────
    path('recent-activity/', views.recent_activity, name='api_recent_activity'),

    # ── REPORTS ───────────────────────────────────────────────────────────────
    path('reports/monthly/',                      views.api_monthly_summary,             name='api_monthly_summary'),
    path('reports/loans-issued/',                 views.report_loans_issued,             name='api_rpt_loans_issued'),
    path('reports/loans-outstanding/',            views.report_loans_outstanding,        name='api_rpt_outstanding'),
    path('reports/overdue-loans/',                views.report_overdue_loans,            name='api_rpt_overdue'),
    path('reports/expenses/',                     views.report_expenses,                 name='api_rpt_expenses'),
    path('reports/financial/',                    views.report_financial,                name='api_rpt_financial'),
    path('reports/hq-financial/',                 views.api_hq_financial_statement,      name='api_hq_financial'),
    path('reports/bank-charges/',                 views.api_bank_charges,                name='api_bank_charges'),
    path('reports/branch-expenses/',              views.api_branch_expenses_report,      name='api_branch_expenses'),
    path('reports/bank-transfer-expenses/',       views.api_bank_transfer_expenses,      name='api_bank_transfer_expenses'),
    path('reports/branch-to-hq-expenses/',        views.api_branch_to_hq_expenses,       name='api_branch_to_hq_expenses'),
    path('reports/loans-issued-summary/',         views.api_loans_issued_summary,        name='api_rpt_loans_issued_summary'),
    path('reports/monthly-outstanding-summary/',  views.api_monthly_outstanding_summary, name='api_rpt_monthly_outstanding_summary'),
    path('reports/expired-loans-summary/',        views.api_expired_loans_summary,       name='api_rpt_expired_loans_summary'),
    path('reports/branch-financial/',             views.api_branch_financial_summary,    name='api_branch_financial'),

    # ── MANAGE ADMIN BRANCHES ─────────────────────────────────────────────────
    path('manage-admin-branches/add/',        views.manage_admin_branches_add,        name='manage_admin_branches_add'),
    path('manage-admin-branches/remove/',     views.manage_admin_branches_remove,     name='manage_admin_branches_remove'),
    path('manage-admin-branches/set-current/',views.manage_admin_branches_set_current,name='manage_admin_branches_set_current'),
]
