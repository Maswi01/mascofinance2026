"""
Masco Microfinance - REST API Views
Provides JSON endpoints for the React Native mobile app.
"""
from django.utils import timezone
from django.db.models import Sum, Count, Q
from rest_framework import generics, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate
from datetime import date

from app.models import (
    Client, LoanApplication, LoanRepayment, Office,
    Expense, ExpenseCategory, Nyongeza
)
from app.serializers import (
    ClientSerializer, LoanApplicationSerializer, LoanRepaymentSerializer,
    OfficeSerializer, ExpenseSerializer, ExpenseCategorySerializer,
    DashboardStatsSerializer
)


# ─────────────────────────────────────────────────────────────────────────────
#  AUTH
# ─────────────────────────────────────────────────────────────────────────────

@api_view(['POST'])
def api_login(request):
    """
    POST /api/auth/login/
    Body: { "username": "...", "password": "..." }
    Returns: { "access": "...", "refresh": "...", "user": {...} }
    """
    username = request.data.get('username')
    password = request.data.get('password')

    user = authenticate(username=username, password=password)
    if not user:
        return Response(
            {'detail': 'Invalid credentials'},
            status=status.HTTP_401_UNAUTHORIZED
        )

    if not user.is_active:
        return Response(
            {'detail': 'Account is disabled'},
            status=status.HTTP_401_UNAUTHORIZED
        )

    refresh = RefreshToken.for_user(user)
    return Response({
        'access': str(refresh.access_token),
        'refresh': str(refresh),
        'user': {
            'id': user.id,
            'username': user.username,
            'full_name': user.get_full_name(),
            'email': user.email,
            'is_superuser': user.is_superuser,
        }
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_logout(request):
    try:
        refresh_token = request.data.get('refresh')
        token = RefreshToken(refresh_token)
        token.blacklist()
    except Exception:
        pass
    return Response({'detail': 'Logged out successfully'})


# ─────────────────────────────────────────────────────────────────────────────
#  DASHBOARD
# ─────────────────────────────────────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_dashboard(request):
    """
    GET /api/dashboard/
    Returns summary stats for the mobile dashboard.
    """
    today = date.today()
    month_start = today.replace(day=1)

    total_clients = Client.objects.count()
    total_active_loans = LoanApplication.objects.filter(
        repayment_amount_remaining__gt=0
    ).count()
    loan_agg = LoanApplication.objects.aggregate(
        total_issued=Sum('loan_amount'),
        total_outstanding=Sum('repayment_amount_remaining'),
    )
    total_repaid_agg = LoanRepayment.objects.aggregate(total=Sum('repayment_amount'))

    new_clients = Client.objects.filter(registered_date__gte=month_start).count()
    loans_month = LoanApplication.objects.filter(
        application_date__gte=month_start
    ).count()
    expenses_month = Expense.objects.filter(
        expense_date__gte=month_start
    ).aggregate(total=Sum('amount'))

    data = {
        'total_clients': total_clients,
        'total_active_loans': total_active_loans,
        'total_loan_amount': loan_agg.get('total_issued') or 0,
        'total_outstanding': loan_agg.get('total_outstanding') or 0,
        'total_repaid': total_repaid_agg.get('total') or 0,
        'new_clients_this_month': new_clients,
        'loans_this_month': loans_month,
        'expenses_this_month': expenses_month.get('total') or 0,
    }
    return Response(data)


# ─────────────────────────────────────────────────────────────────────────────
#  CLIENTS
# ─────────────────────────────────────────────────────────────────────────────

class ClientListAPI(generics.ListAPIView):
    """GET /api/clients/  — list all clients (supports ?search=)"""
    serializer_class = ClientSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = Client.objects.all().order_by('-registered_date')
        search = self.request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(
                Q(firstname__icontains=search) |
                Q(middlename__icontains=search) |
                Q(lastname__icontains=search) |
                Q(phonenumber__icontains=search) |
                Q(employmentcardno__icontains=search)
            )
        return qs


class ClientDetailAPI(generics.RetrieveAPIView):
    """GET /api/clients/<pk>/"""
    serializer_class = ClientSerializer
    permission_classes = [IsAuthenticated]
    queryset = Client.objects.all()


# ─────────────────────────────────────────────────────────────────────────────
#  LOANS
# ─────────────────────────────────────────────────────────────────────────────

class LoanListAPI(generics.ListAPIView):
    """GET /api/loans/  — supports ?status=active|completed&search=&office="""
    serializer_class = LoanApplicationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = LoanApplication.objects.select_related('client').prefetch_related(
            'repayments'
        ).order_by('-created_at')

        loan_status = self.request.query_params.get('status', '').strip()
        if loan_status == 'active':
            qs = qs.filter(repayment_amount_remaining__gt=0)
        elif loan_status == 'completed':
            qs = qs.filter(repayment_amount_remaining__lte=0)

        search = self.request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(
                Q(client__firstname__icontains=search) |
                Q(client__lastname__icontains=search) |
                Q(client__phonenumber__icontains=search)
            )

        office = self.request.query_params.get('office', '').strip()
        if office:
            qs = qs.filter(office__icontains=office)

        return qs


class LoanDetailAPI(generics.RetrieveAPIView):
    """GET /api/loans/<pk>/"""
    serializer_class = LoanApplicationSerializer
    permission_classes = [IsAuthenticated]
    queryset = LoanApplication.objects.select_related('client').prefetch_related('repayments')


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def client_loans(request, client_id):
    """GET /api/clients/<client_id>/loans/"""
    loans = LoanApplication.objects.filter(
        client_id=client_id
    ).prefetch_related('repayments').order_by('-created_at')
    serializer = LoanApplicationSerializer(loans, many=True)
    return Response(serializer.data)


# ─────────────────────────────────────────────────────────────────────────────
#  REPAYMENTS
# ─────────────────────────────────────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def loan_repayments(request, loan_id):
    """GET /api/loans/<loan_id>/repayments/"""
    repayments = LoanRepayment.objects.filter(
        loan_application_id=loan_id
    ).order_by('-repayment_date')
    serializer = LoanRepaymentSerializer(repayments, many=True)
    return Response(serializer.data)


# ─────────────────────────────────────────────────────────────────────────────
#  OFFICES
# ─────────────────────────────────────────────────────────────────────────────

class OfficeListAPI(generics.ListAPIView):
    """GET /api/offices/"""
    serializer_class = OfficeSerializer
    permission_classes = [IsAuthenticated]
    queryset = Office.objects.all().order_by('name')


# ─────────────────────────────────────────────────────────────────────────────
#  EXPENSES
# ─────────────────────────────────────────────────────────────────────────────

class ExpenseListAPI(generics.ListAPIView):
    """GET /api/expenses/  — supports ?office=&from=&to="""
    serializer_class = ExpenseSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = Expense.objects.select_related('transaction_type').order_by('-expense_date')
        office = self.request.query_params.get('office', '').strip()
        if office:
            qs = qs.filter(office__icontains=office)
        date_from = self.request.query_params.get('from', '')
        date_to   = self.request.query_params.get('to', '')
        if date_from:
            qs = qs.filter(expense_date__gte=date_from)
        if date_to:
            qs = qs.filter(expense_date__lte=date_to)
        return qs


class ExpenseCategoryListAPI(generics.ListAPIView):
    """GET /api/expense-categories/"""
    serializer_class = ExpenseCategorySerializer
    permission_classes = [IsAuthenticated]
    queryset = ExpenseCategory.objects.all().order_by('name')


# ─────────────────────────────────────────────────────────────────────────────
#  RECENT ACTIVITY
# ─────────────────────────────────────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def recent_activity(request):
    """
    GET /api/recent-activity/
    Returns last 10 repayments + last 5 new clients combined as a feed.
    """
    repayments = LoanRepayment.objects.select_related(
        'loan_application__client', 'processed_by'
    ).order_by('-created_at')[:10]

    new_clients = Client.objects.order_by('-registered_date')[:5]

    activities = []

    for r in repayments:
        activities.append({
            'type': 'repayment',
            'id': r.id,
            'title': f"Repayment Received",
            'subtitle': f"{r.loan_application.client.firstname} {r.loan_application.client.lastname}",
            'amount': str(r.repayment_amount),
            'date': str(r.repayment_date or r.created_at),
            'icon': 'cash',
        })

    for c in new_clients:
        activities.append({
            'type': 'new_client',
            'id': c.id,
            'title': 'New Client Registered',
            'subtitle': f"{c.firstname} {c.middlename} {c.lastname}",
            'amount': None,
            'date': str(c.registered_date),
            'icon': 'person-add',
        })

    activities.sort(key=lambda x: x['date'], reverse=True)
    return Response(activities[:15])
