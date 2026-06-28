# useraccount/permission_registry.py
# Central definition of every permissionable action in the system.
# 'codename' must match the URL name= in urls.py exactly.
# Add / remove entries here as your URL structure grows.

PERMISSION_REGISTRY = [

    # ── Users ────────────────────────────────────────────────────────────────
    {"category": "Users",   "codename": "staff_list",           "label": "View Users"},
    {"category": "Users",   "codename": "signup",               "label": "Create new Users"},
    {"category": "Users",   "codename": "staff_profile",        "label": "Show User profile"},
    {"category": "Users",   "codename": "update_staff",         "label": "Edit Users"},

    # ── Branches / Offices ───────────────────────────────────────────────────
    {"category": "Branches","codename": "office",               "label": "View Branches"},
    {"category": "Branches","codename": "office_add",           "label": "Create Branch"},
    {"category": "Branches","codename": "office_update",        "label": "Edit Branch"},
    {"category": "Branches","codename": "switch_branch",        "label": "Switch Branch"},
    {"category": "Branches","codename": "manage_admin_branches","label": "Manage Admin Branches"},

    # ── Loans ────────────────────────────────────────────────────────────────
    {"category": "Loans",   "codename": "loans",                "label": "View Loans"},
    {"category": "Loans",   "codename": "loan_application",     "label": "Create Loan"},
    {"category": "Loans",   "codename": "process_loan",         "label": "Process Loan (Part A)"},
    {"category": "Loans",   "codename": "process_loan_partb",   "label": "Process Loan (Part B)"},
    {"category": "Loans",   "codename": "loan_edit",            "label": "Edit Loan"},
    {"category": "Loans",   "codename": "delete_loan",          "label": "Delete Loan"},
    {"category": "Loans",   "codename": "toggle_loan_approve",  "label": "Approve / Reject Loan"},
    {"category": "Loans",   "codename": "loan_topup",           "label": "Loan Top-Up"},
    {"category": "Loans",   "codename": "loan_payment_page",    "label": "Loan Payment"},
    {"category": "Loans",   "codename": "loan_repayment",       "label": "Record Repayment"},
    {"category": "Loans",   "codename": "delete_repayment",     "label": "Delete Repayment"},
    {"category": "Loans",   "codename": "edit_repayment",       "label": "Edit Repayment"},
    {"category": "Loans",   "codename": "edit_topup",           "label": "Edit Top-Up Payment"},
    {"category": "Loans",   "codename": "completed_loans",      "label": "View Completed Loans"},
    {"category": "Loans",   "codename": "expired_loans",        "label": "View Expired Loans"},
    {"category": "Loans",   "codename": "loans_issued",         "label": "View Loans Issued"},

    # ── Clients ──────────────────────────────────────────────────────────────
    {"category": "Clients", "codename": "clients",              "label": "Show Clients"},
    {"category": "Clients", "codename": "client_add",           "label": "Create Clients"},
    {"category": "Clients", "codename": "client_edit",          "label": "Edit Clients"},
    {"category": "Clients", "codename": "client_delete",        "label": "Delete Clients"},

    # ── Savings / Transactions ───────────────────────────────────────────────
    {"category": "Savings", "codename": "office_transaction",      "label": "View Savings/Transactions"},
    {"category": "Savings", "codename": "office_transaction_add",  "label": "Add Office Transaction"},
    {"category": "Savings", "codename": "office_transaction_list", "label": "Office Transaction List"},
    {"category": "Savings", "codename": "delete_office_transaction","label": "Delete Office Transaction"},
    {"category": "Savings", "codename": "bank_cash_transaction",   "label": "Bank Cash Transaction"},
    {"category": "Savings", "codename": "delete_bank_cash_transaction","label":"Delete Bank Cash Transaction"},
    {"category": "Savings", "codename": "bank_cash_transfer",      "label": "Bank Cash Transfer"},
    {"category": "Savings", "codename": "delete_transaction",      "label": "Delete Transaction"},
    {"category": "Savings", "codename": "nyongeza",                "label": "View Nyongeza"},
    {"category": "Savings", "codename": "nyongeza_add",            "label": "Add Nyongeza"},

    # ── Expenses ─────────────────────────────────────────────────────────────
    {"category": "Expenses","codename": "expense",              "label": "View Expenses"},
    {"category": "Expenses","codename": "expense_add",          "label": "Create Expenses"},
    {"category": "Expenses","codename": "expense_category_list","label": "View Expense Categories"},
    {"category": "Expenses","codename": "expense_category_add", "label": "Add Expense Category"},
    {"category": "Expenses","codename": "expense_category_update","label":"Edit Expense Category"},
    {"category": "Expenses","codename": "expense_category_delete","label":"Delete Expense Category"},
    {"category": "Expenses","codename": "bank_transfer_expenses","label": "Bank Transfer Expenses"},

    # ── Salary ───────────────────────────────────────────────────────────────
    {"category": "Salary",  "codename": "salary",                  "label": "View Salary"},
    {"category": "Salary",  "codename": "salary_add",              "label": "Add Salary"},
    {"category": "Salary",  "codename": "staff_salary_list",       "label": "Staff Salary List"},
    {"category": "Salary",  "codename": "staff_salary_setting",    "label": "Staff Salary Settings"},
    {"category": "Salary",  "codename": "staff_salary_update",     "label": "Update Staff Salary"},
    {"category": "Salary",  "codename": "salary_advance_list",     "label": "Salary Advances"},
    {"category": "Salary",  "codename": "salary_advance_create",   "label": "Create Salary Advance"},
    {"category": "Salary",  "codename": "payroll_filter",          "label": "Payroll"},
    {"category": "Salary",  "codename": "salary_slip_filter",      "label": "Salary Slips"},

    # ── Reports ──────────────────────────────────────────────────────────────
    {"category": "Reports", "codename": "loan_report",             "label": "Loan Report"},
    {"category": "Reports", "codename": "expense_report",          "label": "Expense Report"},
    {"category": "Reports", "codename": "branches_loan_report",    "label": "Branches Loan Report"},
    {"category": "Reports", "codename": "financial_statement",     "label": "Financial Statement"},
    {"category": "Reports", "codename": "hq_financial_statement",  "label": "HQ Financial Statement"},
    {"category": "Reports", "codename": "transaction_statement",   "label": "Transaction Statement"},
    {"category": "Reports", "codename": "customer_statement",      "label": "Customer Statement"},
    {"category": "Reports", "codename": "loan_collection_statement","label":"Loan Collection Statement"},
    {"category": "Reports", "codename": "bank_cash_transfer_report","label":"Bank Cash Transfer Report"},
    {"category": "Reports", "codename": "loans_owed_summary",      "label": "Loans Owed"},
    {"category": "Reports", "codename": "monthly_repayment_report","label": "Monthly Repayment Report"},
    {"category": "Reports", "codename": "monthly_outstanding_filter","label":"Monthly Outstanding"},
    {"category": "Reports", "codename": "expired_loans_report",    "label": "Expired Loans Report"},
    {"category": "Reports", "codename": "loan_issued_filter",      "label": "Loans Issued Report"},
    {"category": "Reports", "codename": "loans_issued_report_filter","label":"Loans Issued (Summary)"},
    {"category": "Reports", "codename": "bank_cash_transaction_statement","label":"Bank Cash Stmt"},
    {"category": "Reports", "codename": "branch_transaction_statement","label":"Branch Txn Statement"},

    # ── Staff Management ─────────────────────────────────────────────────────
    {"category": "Staff Mgmt","codename": "transfer_staff",        "label": "Transfer Staff"},
    {"category": "Staff Mgmt","codename": "block_user",            "label": "Block User"},
    {"category": "Staff Mgmt","codename": "blocked_staff_list",    "label": "Blocked Staff List"},
    {"category": "Staff Mgmt","codename": "bank_charges",          "label": "Bank Charges"},
    {"category": "Staff Mgmt","codename": "bank_charge_add",       "label": "Add Bank Charge"},
]
