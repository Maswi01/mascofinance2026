======================================================================================
19 May 2026
===========
1. Solve monthly wise repayment by changing the view: monthly_repayment_report
2. modify transaction statement not include bank to cash transfer within branch  by changing the view: branch_transaction_statement_report
3. Add kituo cha kazi at repayment schedule by replacing view and template: monthly_outstanding_report 
4. under office transaction change to keep default cash in transfer or uses , change its templates respectively: bank_cash_transaction_add , expense , bank_charges
5. DATA_UPLOAD_MAX_NUMBER_FIELDS = 10000 # added this to disable the limit entirely during approve loans in loans owed. this added to settings.py

=========================================================================================
22 May 2026
===========
1. loan collection statement report -  solving duplicate of topup
    modify only view function - loan_collection_statement_report(request)
2. adding new approve completed loan
    a. add 2 views = completed_loans_approval(request): and completed_loans_approve(request):
    b. add  2 urls in app = 
        path('loans/completed-approval/',         views.completed_loans_approval, name='completed_loans_approval'),
        path('loans/completed-approval/approve/', views.completed_loans_approve,  name='completed_loans_approve'),
    c. add app template = completed_loans_approval.html
=========================================================================================