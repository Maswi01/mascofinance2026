from django.contrib import admin
from app.models import *
# Register your models here.

admin.site.register(Office)
admin.site.register(Client)
admin.site.register(OfficeTransaction)
admin.site.register(LoanApplication)
admin.site.register(LoanRepayment)
admin.site.register(Salary)
admin.site.register(Expense)
admin.site.register(BankAmount)
admin.site.register(Nyongeza)
admin.site.register(ExpenseCategory)
admin.site.register(LoanTopup)
admin.site.register(BranchBalance)
admin.site.register(HQTransaction)
admin.site.register(BankCashTransaction)
admin.site.register(BankCharge)
admin.site.register(UserOfficeAssignment)
