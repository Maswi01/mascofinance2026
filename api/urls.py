"""
Masco Microfinance - API URLs - KAMILI (inayolingana na web urls.py)
Badilisha: api/urls.py
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
    # web: views.index
    path('dashboard/', views.api_dashboard, name='api_dashboard'),

    # ── CLIENTS ───────────────────────────────────────────────────────────────
    # web: views.clients, client_add, client_edit
    path('clients/',                       views.ClientListAPI.as_view(),  name='api_client_list'),
    path('clients/<int:pk>/',              views.ClientDetailAPI.as_view(),name='api_client_detail'),
    path('clients/<int:client_id>/loans/', views.client_loans,             name='api_client_loans'),

    # ── LOANS ─────────────────────────────────────────────────────────────────
    # web: views.loans
    path('loans/',                          views.LoanListAPI.as_view(),   name='api_loan_list'),
    path('loans/<int:pk>/',                 views.LoanDetailAPI.as_view(), name='api_loan_detail'),
    path('loans/<int:loan_id>/repayments/', views.loan_repayments,         name='api_loan_repayments'),
    # web: views.loan_repayment_schedule
    path('loans/<int:loan_id>/schedule/',   views.api_loan_repayment_schedule, name='api_loan_schedule'),

    # ── LOAN REPORT (Active loans with balance) ────────────────────────────────
    # web: views.loan_report
    path('loan-report/', views.api_loan_report, name='api_loan_report'),

    # ── COMPLETED LOANS ────────────────────────────────────────────────────────
    # web: views.completed_loans
    path('completed-loans/', views.api_completed_loans, name='api_completed_loans'),

    # ── EXPIRED LOANS ─────────────────────────────────────────────────────────
    # web: views.expired_loans
    path('expired-loans/', views.api_expired_loans, name='api_expired_loans'),

    # ── LOANS OWED ────────────────────────────────────────────────────────────
    # web: views.loans_owed_summary
    path('loans-owed/',        views.loans_owed_summary, name='api_loans_owed_summary'),
    # web: views.loans_owed_report
    path('loans-owed/report/', views.loans_owed_report,  name='api_loans_owed_report'),

    # ── LOAN OUTSTANDING (per client) ─────────────────────────────────────────
    # web: views.loan_outstanding_select + loan_outstanding_report
    path('loan-outstanding/', views.api_loan_outstanding, name='api_loan_outstanding'),

    # ── CUSTOMER STATEMENT ────────────────────────────────────────────────────
    # web: views.customer_statement
    path('customer-statement/', views.api_customer_statement, name='api_customer_statement'),

    # ── OFFICES ───────────────────────────────────────────────────────────────
    # web: views.office
    path('offices/', views.OfficeListAPI.as_view(), name='api_office_list'),

    # ── OFFICE TRANSACTIONS ───────────────────────────────────────────────────
    # web: views.office_transaction_list
    path('office-transactions/', views.api_office_transactions, name='api_office_transactions'),

    # ── EXPENSES ──────────────────────────────────────────────────────────────
    # web: views.expense
    path('expenses/',            views.ExpenseListAPI.as_view(),         name='api_expense_list'),
    path('expense-categories/',  views.ExpenseCategoryListAPI.as_view(), name='api_expense_category_list'),
    path('expense-categories/<int:pk>/', views.api_expense_category_detail, name='api_expense_category_detail'),

    # ── RECENT ACTIVITY ───────────────────────────────────────────────────────
    path('recent-activity/', views.recent_activity, name='api_recent_activity'),

    # ── STAFF & BRANCHES ──────────────────────────────────────────────────────
    # web: views.staff_list
    path('staff/',         views.api_staff,      name='api_staff'),
    path('my-branches/',   views.my_branches,    name='api_my_branches'),
    path('switch-branch/', views.switch_branch,  name='api_switch_branch'),

    # ── NO LOAN CUSTOMERS ─────────────────────────────────────────────────────
    # web: views.no_loan_customers
    path('no-loan-customers/', views.api_no_loan_customers, name='api_no_loan_customers'),

    # ── NYONGEZA ──────────────────────────────────────────────────────────────
    # web: views.nyongeza
    path('nyongeza/', views.api_nyongeza, name='api_nyongeza'),

    # ── SALARIES ──────────────────────────────────────────────────────────────
    # web: views.salary, salary_slip_list
    path('salaries/',        views.api_salaries,        name='api_salaries'),
    path('salary-advances/', views.api_salary_advances, name='api_salary_advances'),
    path('salary/slip/',     views.api_salary_slip,     name='api_salary_slip'),

    # ── BRANCH TRANSACTIONS ───────────────────────────────────────────────────
    # web: views.branch_transaction_statement_report
    path('branch-transactions/', views.api_branch_transactions, name='api_branch_transactions'),

    # ── LOAN COLLECTION STATEMENT ─────────────────────────────────────────────
    # web: views.loan_collection_statement_report
    path('loan-collection/', views.api_loan_collection, name='api_loan_collection'),

    # ── FINANCIAL STATEMENT ───────────────────────────────────────────────────
    # web: views.financial_statement
    path('financial-statement/',        views.api_financial_statement,    name='api_financial_statement'),
    # web: views.branch_financial_summary
    path('reports/branch-financial/',   views.api_branch_financial_summary, name='api_branch_financial'),

    # ── MONTHLY REPAYMENT REPORT ──────────────────────────────────────────────
    # web: views.monthly_repayment_report
    path('monthly-repayment/', views.api_monthly_repayment, name='api_monthly_repayment'),

    # ── MONTHLY OUTSTANDING ───────────────────────────────────────────────────
    # web: views.monthly_outstanding_report
    path('monthly-outstanding/', views.api_monthly_outstanding, name='api_monthly_outstanding'),

    # ── REPORTS ───────────────────────────────────────────────────────────────
    # web: views.loan_issued_report
    path('reports/loans-issued/',                  views.report_loans_issued,           name='api_rpt_loans_issued'),
    # web: views.loan_report (outstanding)
    path('reports/loans-outstanding/',             views.report_loans_outstanding,       name='api_rpt_outstanding'),
    # web: views.expired_loans_report
    path('reports/overdue-loans/',                 views.report_overdue_loans,           name='api_rpt_overdue'),
    # web: views.expenses_report
    path('reports/expenses/',                      views.report_expenses,                name='api_rpt_expenses'),
    # web: views.financial_statement_report
    path('reports/financial/',                     views.report_financial,               name='api_rpt_financial'),
    # web: views.loans_issued_report_result
    path('reports/loans-issued-summary/',          views.api_loans_issued_summary,       name='api_rpt_loans_issued_summary'),
    # web: views.monthly_outstanding_result_summary
    path('reports/monthly-outstanding-summary/',   views.api_monthly_outstanding_summary,name='api_rpt_monthly_outstanding_summary'),
    # web: views.expired_loans_report_summary
    path('reports/expired-loans-summary/',         views.api_expired_loans_summary,      name='api_rpt_expired_loans_summary'),
    # web: views.expenses_statement_result
    path('reports/expenses-statement/',            views.api_expenses_statement,          name='api_rpt_expenses_statement'),
]