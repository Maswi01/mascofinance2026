from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from . import views

urlpatterns = [
    # Auth
    path('auth/login/',   views.api_login,   name='api_login'),
    path('auth/logout/',  views.api_logout,  name='api_logout'),
    path('auth/refresh/', TokenRefreshView.as_view(), name='token_refresh'),

    # Dashboard
    path('dashboard/', views.api_dashboard, name='api_dashboard'),

    # Clients
    path('clients/',          views.ClientListAPI.as_view(),   name='api_client_list'),
    path('clients/<int:pk>/', views.ClientDetailAPI.as_view(), name='api_client_detail'),
    path('clients/<int:client_id>/loans/', views.client_loans, name='api_client_loans'),

    # Loans
    path('loans/',          views.LoanListAPI.as_view(),   name='api_loan_list'),
    path('loans/<int:pk>/', views.LoanDetailAPI.as_view(), name='api_loan_detail'),
    path('loans/<int:loan_id>/repayments/', views.loan_repayments, name='api_loan_repayments'),

    # Offices
    path('offices/', views.OfficeListAPI.as_view(), name='api_office_list'),

    # Expenses
    path('expenses/',           views.ExpenseListAPI.as_view(),         name='api_expense_list'),
    path('expense-categories/', views.ExpenseCategoryListAPI.as_view(), name='api_expense_category_list'),

    # Activity feed
    path('recent-activity/', views.recent_activity, name='api_recent_activity'),
]
