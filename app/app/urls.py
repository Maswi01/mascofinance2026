
from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('base/', views.base, name='base'),
    path('office_transactions/', views.office_transactions, name='office_transactions'),
    # path('staff/', views.staff, name='staff'),
    path('office/', views.office, name='office'),
    path('office/add/', views.office_add, name='office_add'),
    path('office/update/<int:office_id>/', views.office_update, name='office_update'),
    
    path('customer_plan_calculator/', views.customer_plan_calculator, name='customer_plan_calculator'),
    path('loan_calculator/', views.loan_calculator, name='loan_calculator'),
    path('clients/', views.clients, name='clients'),
    path('clients/add/', views.client_add, name='client_add'),
    path('clients/<int:pk>/edit/', views.client_edit, name='client_edit'),
    path('clients/<int:client_id>/delete/', views.client_delete, name='client_delete'),
    
    path('office_transaction/', views.office_transaction, name='office_transaction'),
    path('office_transaction/add/', views.office_transaction_add, name='office_transaction_add'),
    path('loans/', views.loans, name='loans'),
    # path('loans/apply/', views.loan_application, name='loan_application'),
    path('loan-receipt/<int:loan_id>/', views.loan_application_receipt, name='loan_receipt'),
    # path('loans/repay/<int:loan_id>/', views.loan_repayment, name='loan_repayment'),
    path('salary/', views.salary, name='salary'),
    path('salary/add/', views.salary_add, name='salary_add'),
    # path('loan-report/', views.loan_report, name='loan_report'),
    path('expenses/', views.expense, name='expense'),
    path('expense/add/', views.expense_add, name='expense_add'),
    path('expense-report/', views.expense_report, name='expense_report'),
    
    path('receipt/<int:repayment_id>/', views.view_receipt, name='view_receipt'),
    # path('customer-statement/', views.customer_statement, name='customer_statement'),
    
    path('loan-history/', views.loan_history, name='loan_history'),
    path('loan-schedule/<int:loan_id>/', views.get_repayment_schedule_ajax, name='loan_schedule'),
    
    path('transaction-statement/', views.transaction_statement, name='transaction_statement'),
    # path('transaction-details/<str:date>/', views.get_transaction_details, name='transaction_details'),
    
    # path('loan-collection-statement/', views.loan_collection_statement, name='loan_collection_statement'),
    
    # path('bank-cash-transaction/', views.bank_cash_transaction, name='bank_cash_transaction'),
    # path('bank-cash-transaction/add/', views.bank_cash_transaction_add, name='bank_cash_transaction_add'),
    path('bank-cash-transaction-statement/', views.bank_cash_transaction_statement, name='bank_cash_transaction_statement'),
    
    path('branches-loan-report/', views.branches_loan_report, name='branches_loan_report'),
    path('expired-loans-report/', views.expired_loans_report, name='expired_loans_report'),
    
    # path('loans-owed-report/', views.loans_owed_report, name='loans_owed_report'),
    
    path('transfer-staff/', views.transfer_staff, name='transfer_staff'),
    path('process-transfer-staff/', views.process_transfer_staff, name='process_transfer_staff'),
    
    path('block-user/', views.block_user, name='block_user'),
    path('process-block-user/', views.process_block_user, name='process_block_user'),
    path('blocked-staff/', views.blocked_staff_list, name='blocked_staff_list'),
    
    path('loans-issued/', views.loans_issued, name='loans_issued'),
    
    path('completed-loans/', views.completed_loans, name='completed_loans'),
    
    path('nyongeza/', views.nyongeza, name='nyongeza'),
    path('nyongeza/add/', views.nyongeza_add, name='nyongeza_add'),
    
    path('financial-statement/', views.financial_statement, name='financial_statement'),
    path('hq-financial-statement/', views.hq_financial_statement, name='hq_financial_statement'),
    
    path('fomu-mkopo/', views.fomu_mkopo, name='fomu_mkopo'),
    path('mkopo-wa-dharula/', views.fomu_mkopo_wa_dharula, name='fomu_mkopo_wa_dharula'),
    
    path('fomu-mkopo/', views.fomu_mkopo_new, name='fomu_mkopo_new'),
    path('fomu-mkopo/<int:loan_id>/', views.fomu_mkopo, name='fomu_mkopo'),
    path('mkopo-dharura/<int:loan_id>/', views.fomu_mkopo_wa_dharula, name='fomu_mkopo_wa_dharula'),
    
    # Add this line for topup eligibility check
    path('api/check-topup-eligibility/<int:loan_id>/', views.check_topup_eligibility, name='check_topup_eligibility'),
    
    # Add this line for topup submission
    path('loan-topup/<int:loan_id>/', views.loan_topup, name='loan_topup'),
    
    # path('bank_transfer_expenses/', views.bank_transfer_expenses, name='bank_transfer_expenses'),
    
    path('switch-branch/', views.switch_branch, name='switch_branch'),
    
    # path('branch-financial-summary/', views.branch_financial_summary, name='branch_financial_summary'),
    
    path('office_transaction_page/', views.office_transaction_page, name='office_transaction_page'),
    
    path('bank_charges/', views.bank_charges, name='bank_charges'),
    path('bank_charge_add/', views.bank_charge_add, name='bank_charge_add'),
    
    path('process-loan/<int:pk>/',       views.process_loan,      name='process_loan'),
    path('process-loan/<int:pk>/partb/', views.process_loan_partb, name='process_loan_partb'),
    path('loan-application/',            views.loan_application,   name='loan_application'),
    
    path('loan-payment/',                views.loan_payment_page,  name='loan_payment_page'),
    path('loan-payment/select/',         views.loan_payment_select, name='loan_payment_select'),
    path('loan-repayment/<int:loan_id>/', views.loan_repayment,      name='loan_repayment'),
    
    path('bank-cash-transaction/',    views.bank_cash_transaction_add, name='bank_cash_transaction'),
    path('branches-transaction/add/', views.branches_transaction_add,  name='branches_transaction_add'),
    
    path('loan-receipt/',                  views.loan_receipt_select,   name='loan_receipt_select'),
    path('loan-receipt/list/',             views.loan_receipt_list,     name='loan_receipt_list'),
    path('loan-receipt/receipt/<int:pk>/', views.loan_repayment_receipt, name='loan_repayment_receipt'),
    path('repayment/<int:repayment_id>/delete/', views.delete_repayment, name='delete_repayment'),
    
    path('loan-outstanding/',                        views.loan_outstanding_select, name='loan_outstanding_select'),
    path('loan-outstanding/report/',                 views.loan_outstanding_report, name='loan_outstanding_report'),
    path('loan-outstanding/schedule/<int:loan_id>/', views.loan_repayment_schedule, name='loan_repayment_schedule'),
    path('loan/<int:loan_id>/delete/', views.delete_loan, name='delete_loan'),
    path('loan/<int:loan_id>/toggle-approve/', views.toggle_loan_approve, name='toggle_loan_approve'),

    path('customer-statement/',        views.customer_statement_select, name='customer_statement_select'),
    path('customer-statement/report/', views.customer_statement,        name='customer_statement'),
    # 
    path('repayment/edit/<int:repayment_id>/',views.edit_repayment_2,{'record_type': 'repayment'},name='edit_repayment'),
    path('topup/edit/<int:repayment_id>/',views.edit_repayment_2,{'record_type': 'topup'},name='edit_topup'),
    # 
    path('branch-transaction-statement/', views.branch_transaction_statement, name='branch_transaction_statement'),
    path('branch-transaction-statement/report/', views.branch_transaction_statement_report, name='branch_transaction_statement_report'),
    # 
    # Add this to your urlpatterns in urls.py:
    path(
        'transaction/delete/<str:record_type>/<int:record_id>/',
        views.delete_transaction,
        name='delete_transaction',
    ),
    
    path('loan-collection-statement/', views.loan_collection_statement, name='loan_collection_statement'),
    path('loan-collection-statement/report/', views.loan_collection_statement_report, name='loan_collection_statement_report'),
    
    path('bank-transfer-expenses/', views.bank_transfer_expenses, name='bank_transfer_expenses'),
    path('bank-transfer-expenses/report/', views.bank_transfer_expenses_report, name='bank_transfer_expenses_report'),
    path('office-transaction/delete/<int:txn_id>/', views.delete_office_transaction, name='delete_office_transaction'),
    
    path('bank-cash-transfer/', views.bank_cash_transfer, name='bank_cash_transfer'),
    path('bank-cash-transfer/report/', views.bank_cash_transfer_report,name='bank_cash_transfer_report'),
    path('bank-cash-transaction/delete/<int:txn_id>/', views.delete_bank_cash_transaction, name='delete_bank_cash_transaction'),
    
    path('loan-issued-report/',         views.loan_issued_filter, name='loan_issued_filter'),
    path('loan-issued-report/report/',  views.loan_issued_report, name='loan_issued_report'),
    path('loans/edit/<int:loan_id>/', views.loan_issued_report_edit, name='loan_issued_report_edit'),
    
    path('loan-report/', views.loan_report, name='loan_report'),
    
    path('no-loan-customers/', views.no_loan_customers, name='no_loan_customers'),
    
    path('expired-loans/', views.expired_loans, name='expired_loans'),
    
    path('monthly-outstanding/',         views.monthly_outstanding_filter, name='monthly_outstanding_filter'),
    path('monthly-outstanding/report/',  views.monthly_outstanding_report, name='monthly_outstanding_report'),
    
    path('expenses-statement/',         views.expenses_filter, name='expenses_filter'),
    path('expenses-statement/report/',  views.expenses_report, name='expenses_report'),
    
    path('financial-statement-office/',         views.financial_statement_filter, name='financial_statement_filter'),
    path('financial-statement/report/',  views.financial_statement_report, name='financial_statement_report'),
    
    path('monthly-wise-repayment/',         views.monthly_repayment_filter, name='monthly_repayment_filter'),
    path('monthly-wise-repayment/report/',  views.monthly_repayment_report, name='monthly_repayment_report'),

    path('staff/', views.staff_list, name='staff_list'),
    
    path('expense-category/', views.expense_category_list,name='expense_category_list'),
    path('expense-category/add/', views.expense_category_add, name='expense_category_add'),
    path('expense-category/<int:pk>/update/', views.expense_category_update, name='expense_category_update'),
    path('expense-category/<int:pk>/delete/', views.expense_category_delete,name='expense_category_delete'),
    path('expense-category/<int:pk>/detail/', views.expense_category_detail,name='expense_category_detail'),
    
     # List view: shows all staff with salary & deduction columns (read-only)
    path('staff/salary/',views.staff_salary_list,name='staff_salary_list'),
    # Setting page: editable table for entering/updating salary & deduction
    path('staff/salary/setting/',views.staff_salary_setting,name='staff_salary_setting'),
    # POST endpoint: bulk-update salaries (handles both AJAX & form submit)
    path('staff/salary/update/',views.staff_salary_update,name='staff_salary_update'),
    # Optional: JSON detail for a single staff member
    path('staff/salary/<int:pk>/detail/',views.staff_salary_detail_json,name='staff_salary_detail_json'),
    
    # List all salary advances
    path('salary-advance/',views.salary_advance_list,name='salary_advance_list'),
    # Create form page
    path('salary-advance/create/',views.salary_advance_create,name='salary_advance_create'),
    # Handle form POST submission
    path('salary-advance/store/',views.salary_advance_store,name='salary_advance_store'),
    # AJAX: preview installment schedule
    path('salary-advance/preview/',views.salary_advance_preview,name='salary_advance_preview'),
    # AJAX: get employee info (role/designation)
    path('salary-advance/employee-info/',views.get_employee_info, name='salary_advance_employee_info'),
    
     # Page 1: Date range filter form
    path('reports/loans-issued/',views.loans_issued_report_filter,name='loans_issued_report_filter'),
    # Page 2: Report result table (receives date_from & date_to via GET)
    path('reports/loans-issued/result/',views.loans_issued_report_result,name='loans_issued_report_result' ),
    
    # Page 1: Month picker
    path('reports/monthly-outstanding/',views.monthly_outstanding_filter_summary,name='monthly_outstanding_filter_summary'),
    # Page 2: Result table (receives ?month=YYYY-MM-DD via GET)
    path('reports/monthly-outstanding/result/', views.monthly_outstanding_result_summary,name='monthly_outstanding_result_summary'),
    
    path('reports/expired-loans/', views.expired_loans_report_summary,name='expired_loans_report_summary'),
    
    # Page 1: Date range filter
    path('reports/bank-transfer-expenses/',views.bank_transfer_expenses_filter,name='bank_transfer_expenses_filter'),
    # Page 2: Result summary table (receives date_from & date_to via GET)
    path('reports/bank-transfer-expenses/result/',views.bank_transfer_expenses_result,name='bank_transfer_expenses_result'),
    
    path('branch-to-hq/filter/',  views.branch_to_hq_expenses_filter, name='branch_to_hq_expenses_filter'),
    path('branch-to-hq/result/',  views.branch_to_hq_expenses_result, name='branch_to_hq_expenses_result'),
    
    # Page 1: Date range filter
    path('reports/expenses-statement/',views.expenses_statement_filter,name='expenses_statement_filter'),
    # Page 2: Result table (receives date_from & date_to via GET)
    path('reports/expenses-statement/result/',views.expenses_statement_result,name='expenses_statement_result'),
    
    # Page 1: Date filter form
    path('reports/financial-statement/',views.general_financial_statement_filter,name='general_financial_statement_filter'),
    # Page 2: Report (POST receives date_from & date_to)
    path('reports/financial-statement/result/',views.general_financial_statement_report,name='general_financial_statement_report'),
    
    # Page 1 — filter form
    path('reports/financial-transaction/',views.branch_financial_summary_filter,name='branch_financial_summary_filter'),
    # Page 2 — columnar report (GET: ?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD)
    path('reports/financial-transaction/result/', views.branch_financial_summary,name='branch_financial_summary'),
    
    # Page 1 — month picker
    path('salary/slip/', views.salary_slip_filter, name='salary_slip_filter'),
    # Page 2 — payroll list (GET ?month=YYYY-MM)
    path('salary/slip/list/',views.salary_slip_list,name='salary_slip_list'),
    # Action — mark all as paid
    path('salary/slip/pay-all/',views.salary_slip_pay_all,name='salary_slip_pay_all'),
    
    path('manage-admin-branches/',              views.manage_admin_branches,             name='manage_admin_branches'),
    path('manage-admin-branches/add/',          views.manage_admin_branches_add,         name='manage_admin_branches_add'),
    path('manage-admin-branches/set-current/',  views.manage_admin_branches_set_current, name='manage_admin_branches_set_current'),
    path('manage-admin-branches/remove/',       views.manage_admin_branches_remove,      name='manage_admin_branches_remove'),
    
    
    path('payroll/',views.payroll_filter,name='payroll_filter'),
    path('payroll/report/',views.payroll_report, name='payroll_report'),
    path('payroll/submit/',views.payroll_submit,name='payroll_submit'),
    
    path('office-transactions/',                 views.office_transaction_list,   name='office_transaction_list'),
    path('office-transactions/delete/<int:pk>/', views.office_transaction_delete, name='office_transaction_delete'),

    path('loans-owed/',          views.loans_owed_summary, name='loans_owed_summary'),
    path('loans-owed/report/',   views.loans_owed_report,  name='loans_owed_report'),
    path('loans-owed/approve/',  views.loans_owed_approve, name='loans_owed_approve'),
    
    path('check-checkno/', views.check_checkno, name='check_checkno'),
    
    # path('report/hq/', views.hq_financial_statement_report, name='hq_financial_statement_report'),
    
    path('loan/<int:loan_id>/edit/', views.loan_edit, name='loan_edit'),
    
    
    # Monthly repayment report (existing POST handler)
    path('reports/monthly-repayment/', views.monthly_repayment_report, name='monthly_repayment_report'),
    
    path('repayment/edit/<str:repayment_type>/<int:repayment_id>/', views.edit_repayment, name='edit_repayment'),
    path('repayment/bulk-update-month/', views.bulk_update_payment_month, name='bulk_update_payment_month'),

    # Excel import
    path('clients/import-excel/', views.client_import_excel, name='client_import_excel'),
    path('clients/import-excel/sample/', views.client_excel_sample, name='client_excel_sample'),
    path('clients/export-excel/', views.client_export_excel, name='client_export_excel'),
]