"""
Masco Microfinance - Full API Views
Mirrors web views.py exactly with office filtering.
Weka hii kama: api/views.py
"""
import datetime
from decimal import Decimal
from django.utils import timezone
from django.db.models import Sum, Count, Q
from django.db.models.functions import Coalesce
from rest_framework import generics, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate
from datetime import date

from app.models import (
    Client, LoanApplication, LoanRepayment, Office, BranchBalance,
    Expense, ExpenseCategory, Nyongeza, Salary, SalaryAdvance,
    BankCharge, UserOfficeAssignment, OfficeTransaction, HQTransaction,
)
from app.serializers import (
    ClientSerializer, LoanApplicationSerializer, LoanRepaymentSerializer,
    OfficeSerializer, ExpenseSerializer, ExpenseCategorySerializer,
    DashboardStatsSerializer,
)
from useraccount.models import CustomUser


def _d(val):
    try: return float(val or 0)
    except: return 0.0


def _str(val):
    return str(val) if val is not None else ''


def _parse_dates(request):
    from_str = request.GET.get('date_from', '')
    to_str   = request.GET.get('date_to', '')
    try:
        d_from = datetime.datetime.strptime(from_str, '%Y-%m-%d').date()
        d_to   = datetime.datetime.strptime(to_str,   '%Y-%m-%d').date()
        return d_from, d_to, None
    except ValueError:
        return None, None, 'Invalid date. Use YYYY-MM-DD'


# =============================================================================
#  OFFICE HELPERS — mirrors web views.py get_user_allowed_offices &
#                   get_selected_office exactly
# =============================================================================

def get_user_allowed_offices(user):
    assigned_qs = Office.objects.filter(
        user_assignments__user=user
    ).distinct().order_by('name')

    if user.is_superuser:
        if assigned_qs.exists():
            return assigned_qs
        return Office.objects.all().order_by('name')

    if assigned_qs.exists():
        return assigned_qs

    primary = getattr(user, 'office_allocation', None)
    if primary:
        return Office.objects.filter(pk=primary.pk)

    return Office.objects.none()


def get_selected_office_api(request):
    """
    Reads office_id from:
      - HTTP header  X-Office-Id: 3
      - Query param  ?office_id=3
    Falls back to user.office_allocation.
    """
    user = request.user
    allowed_qs = get_user_allowed_offices(user)

    office_id = (
        request.META.get('HTTP_X_OFFICE_ID') or
        request.GET.get('office_id') or
        request.data.get('office_id') if hasattr(request, 'data') else None
    )

    if user.is_superuser:
        if office_id:
            try:
                o = Office.objects.get(id=office_id)
                if allowed_qs.filter(pk=o.pk).exists():
                    return o
            except Office.DoesNotExist:
                pass
        primary = getattr(user, 'office_allocation', None)
        if primary and allowed_qs.filter(pk=primary.pk).exists():
            return primary
        return allowed_qs.first()

    if office_id:
        try:
            o = Office.objects.get(id=office_id)
            if allowed_qs.filter(pk=o.pk).exists():
                return o
        except Office.DoesNotExist:
            pass

    primary = getattr(user, 'office_allocation', None)
    if primary and allowed_qs.filter(pk=primary.pk).exists():
        return primary

    return allowed_qs.first()


def get_filter_office(request):
    """
    Returns None (all data) when HQ is selected, else the Office object.
    Mirrors web get_base_context() filter_office logic.
    """
    selected = get_selected_office_api(request)
    if selected and selected.name.strip().upper() == 'HQ':
        return None
    return selected


# =============================================================================
#  AUTH
# =============================================================================

@api_view(['POST'])
def api_login(request):
    """POST /api/auth/login/"""
    username = request.data.get('username')
    password = request.data.get('password')
    user = authenticate(username=username, password=password)
    if not user:
        return Response({'detail': 'Invalid credentials'}, status=401)
    if not user.is_active:
        return Response({'detail': 'Account is disabled'}, status=401)

    refresh = RefreshToken.for_user(user)
    office  = user.office_allocation
    return Response({
        'access':  str(refresh.access_token),
        'refresh': str(refresh),
        'user': {
            'id':           user.id,
            'username':     user.username,
            'full_name':    user.get_full_name(),
            'email':        user.email,
            'phone':        _str(user.phone),
            'employee_id':  _str(user.employee_id),
            'role':         str(user.role) if user.role else '',
            'is_superuser': user.is_superuser,
            'is_active':    user.is_active,
            'office':       office.name if office else '',
            'branch':       office.name if office else '',
            'office_id':    office.id   if office else None,
        }
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_logout(request):
    try:
        RefreshToken(request.data.get('refresh')).blacklist()
    except Exception:
        pass
    return Response({'detail': 'Logged out'})


# =============================================================================
#  BRANCH MANAGEMENT
# =============================================================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def my_branches(request):
    """GET /api/my-branches/ — mirrors web get_user_allowed_offices()"""
    offices  = get_user_allowed_offices(request.user)
    selected = get_selected_office_api(request)
    data = [{
        'id':       o.id,
        'name':     o.name,
        'region':   o.region   or '',
        'district': o.district or '',
        'selected': bool(selected and selected.id == o.id),
    } for o in offices]
    return Response(data)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def switch_branch(request):
    """POST /api/switch-branch/ — superuser switches active branch"""
    if not request.user.is_superuser:
        return Response({'detail': 'Not allowed'}, status=403)
    office_id = request.data.get('office_id')
    allowed   = get_user_allowed_offices(request.user)
    try:
        office = allowed.get(id=office_id)
        return Response({
            'office_id':   office.id,
            'office_name': office.name,
            'message':     f'Switched to {office.name}',
        })
    except Office.DoesNotExist:
        return Response({'detail': 'Office not found or not allowed'}, status=404)


# =============================================================================
#  DASHBOARD — mirrors web index() exactly
# =============================================================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_dashboard(request):
    """GET /api/dashboard/"""
    today         = date.today()
    month_start   = today.replace(day=1)
    filter_office = get_filter_office(request)
    selected      = get_selected_office_api(request)

    # Global querysets scoped to office — same as web index()
    loans_qs      = LoanApplication.objects.all()
    repayments_qs = LoanRepayment.objects.all()
    clients_qs    = Client.objects.all()
    expenses_qs   = Expense.objects.all()

    if filter_office:
        loans_qs      = loans_qs.filter(office=filter_office.name)
        repayments_qs = repayments_qs.filter(loan_application__office=filter_office.name)
        clients_qs    = clients_qs.filter(registered_office=filter_office)
        expenses_qs   = expenses_qs.filter(office=filter_office.name)

    total_clients      = clients_qs.count()
    total_active_loans = loans_qs.filter(repayment_amount_remaining__gt=0).count()
    loan_agg           = loans_qs.aggregate(
        total_issued=Sum('loan_amount'),
        total_outstanding=Sum('repayment_amount_remaining'),
    )
    total_repaid     = repayments_qs.aggregate(total=Sum('repayment_amount'))
    new_clients      = clients_qs.filter(registered_date__gte=month_start).count()
    loans_month      = loans_qs.filter(application_date__gte=month_start).count()
    exp_month        = expenses_qs.filter(expense_date__gte=month_start).aggregate(total=Sum('amount'))

    # Per-office today summary — mirrors web index() per-office loop
    user_primary = getattr(request.user, 'office_allocation', None)
    is_hq = (
        request.user.is_superuser or not user_primary or
        (user_primary and user_primary.name.strip().upper() == 'HQ')
    )

    if is_hq:
        target_offices = Office.objects.exclude(name__iexact='HQ').order_by('name')
    elif filter_office:
        target_offices = Office.objects.filter(pk=filter_office.pk)
    elif user_primary:
        target_offices = Office.objects.filter(pk=user_primary.pk)
    else:
        target_offices = Office.objects.exclude(name__iexact='HQ').order_by('name')

    loans_today      = []
    repayments_today = []
    expenses_today   = []

    for o in target_offices:
        r = LoanApplication.objects.filter(
            office=o.name, created_at__date=today
        ).aggregate(total=Sum('loan_amount'), count=Count('id'))
        loans_today.append({'office': o.name, 'amount': _d(r['total']), 'count': r['count'] or 0})

        r = LoanRepayment.objects.filter(
            loan_application__office__iexact=o.name, created_at__date=today
        ).aggregate(total=Sum('repayment_amount'), count=Count('id'))
        repayments_today.append({'office': o.name, 'amount': _d(r['total']), 'count': r['count'] or 0})

        r = Expense.objects.filter(
            office=o.name, expense_date=today
        ).aggregate(total=Sum('amount'), count=Count('id'))
        expenses_today.append({'office': o.name, 'amount': _d(r['total']), 'count': r['count'] or 0})

    # Recent activity
    recent = []
    for l in loans_qs.select_related('client').order_by('-created_at')[:5]:
        recent.append({
            'type':   'loan',
            'label':  f"Mkopo: {l.client.firstname} {l.client.lastname}",
            'amount': _d(l.loan_amount),
            'date':   _str(l.created_at.date()),
            'office': l.office or '',
        })
    for r in repayments_qs.select_related('loan_application__client').order_by('-created_at')[:5]:
        c = r.loan_application.client
        recent.append({
            'type':   'repayment',
            'label':  f"Malipo: {c.firstname} {c.lastname}",
            'amount': _d(r.repayment_amount),
            'date':   _str(r.created_at.date()) if r.created_at else '',
            'office': r.loan_application.office or '',
        })
    recent.sort(key=lambda x: x['date'], reverse=True)

    return Response({
        'selected_office':    selected.name if selected else 'HQ',
        'selected_office_id': selected.id   if selected else None,
        # Global stats
        'total_clients':          total_clients,
        'total_active_loans':     total_active_loans,
        'total_loan_amount':      _d(loan_agg.get('total_issued')),
        'total_outstanding':      _d(loan_agg.get('total_outstanding')),
        'total_repaid':           _d(total_repaid.get('total')),
        'new_clients_this_month': new_clients,
        'loans_this_month':       loans_month,
        'expenses_this_month':    _d(exp_month.get('total')),
        # Today per-office
        'loans_today':            loans_today,
        'repayments_today':       repayments_today,
        'expenses_today':         expenses_today,
        # Totals
        'loans_total_today':      sum(x['amount'] for x in loans_today),
        'repayments_total_today': sum(x['amount'] for x in repayments_today),
        'expenses_total_today':   sum(x['amount'] for x in expenses_today),
        'recent_activity':        recent[:10],
    })


# =============================================================================
#  CLIENTS — mirrors web clients() view
# =============================================================================

class ClientListAPI(generics.ListAPIView):
    """GET /api/clients/?search="""
    serializer_class   = ClientSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        filter_office = get_filter_office(self.request)
        qs = Client.objects.all().order_by('-registered_date')
        if filter_office:
            qs = qs.filter(registered_office=filter_office)
        s = self.request.query_params.get('search', '').strip()
        if s:
            qs = qs.filter(
                Q(firstname__icontains=s) | Q(middlename__icontains=s) |
                Q(lastname__icontains=s)  | Q(phonenumber__icontains=s) |
                Q(employmentcardno__icontains=s) | Q(checkno__icontains=s)
            )
        return qs


class ClientDetailAPI(generics.RetrieveAPIView):
    """GET /api/clients/<pk>/"""
    serializer_class   = ClientSerializer
    permission_classes = [IsAuthenticated]
    queryset           = Client.objects.all()


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def client_loans(request, client_id):
    """GET /api/clients/<client_id>/loans/"""
    loans = LoanApplication.objects.filter(
        client_id=client_id
    ).prefetch_related('repayments').order_by('-created_at')
    return Response(LoanApplicationSerializer(loans, many=True).data)


# =============================================================================
#  LOANS — mirrors web loans() view
# =============================================================================

class LoanListAPI(generics.ListAPIView):
    """GET /api/loans/?status=active|completed|overdue&search="""
    serializer_class   = LoanApplicationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        filter_office = get_filter_office(self.request)
        qs = LoanApplication.objects.select_related('client').prefetch_related('repayments').order_by('-created_at')
        if filter_office:
            qs = qs.filter(office=filter_office.name)

        loan_status = self.request.query_params.get('status', '').strip()
        if loan_status == 'active':
            qs = qs.filter(repayment_amount_remaining__gt=0, status='Approved')
        elif loan_status == 'completed':
            qs = qs.filter(repayment_amount_remaining__lte=0)
        elif loan_status == 'overdue':
            today = date.today()
            qs = qs.filter(repayment_amount_remaining__gt=0, first_repayment_date__lt=today)

        s = self.request.query_params.get('search', '').strip()
        if s:
            qs = qs.filter(
                Q(client__firstname__icontains=s) |
                Q(client__lastname__icontains=s)  |
                Q(client__phonenumber__icontains=s)
            )
        return qs


class LoanDetailAPI(generics.RetrieveAPIView):
    """GET /api/loans/<pk>/"""
    serializer_class   = LoanApplicationSerializer
    permission_classes = [IsAuthenticated]
    queryset           = LoanApplication.objects.prefetch_related('repayments').all()


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def loan_repayments(request, loan_id):
    """GET /api/loans/<loan_id>/repayments/"""
    reps = LoanRepayment.objects.filter(loan_application_id=loan_id).order_by('-created_at')
    return Response(LoanRepaymentSerializer(reps, many=True).data)


# =============================================================================
#  OFFICES
# =============================================================================

class OfficeListAPI(generics.ListAPIView):
    """GET /api/offices/"""
    serializer_class   = OfficeSerializer
    permission_classes = [IsAuthenticated]
    queryset           = Office.objects.all().order_by('name')


# =============================================================================
#  EXPENSES — mirrors web expense() view
# =============================================================================

class ExpenseListAPI(generics.ListAPIView):
    """GET /api/expenses/"""
    serializer_class   = ExpenseSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        filter_office = get_filter_office(self.request)
        qs = Expense.objects.select_related('transaction_type').all().order_by('-expense_date')
        if filter_office:
            qs = qs.filter(office=filter_office.name)
        return qs


class ExpenseCategoryListAPI(generics.ListAPIView):
    """GET /api/expense-categories/"""
    serializer_class   = ExpenseCategorySerializer
    permission_classes = [IsAuthenticated]
    queryset           = ExpenseCategory.objects.all()


# =============================================================================
#  RECENT ACTIVITY — mirrors web recent_activity
# =============================================================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def recent_activity(request):
    """GET /api/recent-activity/"""
    filter_office = get_filter_office(request)
    loans_qs = LoanApplication.objects.select_related('client').order_by('-created_at')
    repay_qs = LoanRepayment.objects.select_related('loan_application__client').order_by('-created_at')
    if filter_office:
        loans_qs = loans_qs.filter(office=filter_office.name)
        repay_qs = repay_qs.filter(loan_application__office=filter_office.name)

    items = []
    for l in loans_qs[:5]:
        items.append({
            'type':   'loan',
            'label':  f"Mkopo: {l.client.firstname} {l.client.lastname}",
            'amount': _d(l.loan_amount),
            'date':   _str(l.created_at.date()),
        })
    for r in repay_qs[:5]:
        c = r.loan_application.client
        items.append({
            'type':   'repayment',
            'label':  f"Malipo: {c.firstname} {c.lastname}",
            'amount': _d(r.repayment_amount),
            'date':   _str(r.created_at.date()) if r.created_at else '',
        })
    items.sort(key=lambda x: x['date'], reverse=True)
    return Response(items[:10])


# =============================================================================
#  STAFF — mirrors web staff_list() view
# =============================================================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_staff(request):
    """GET /api/staff/"""
    staff = CustomUser.objects.all().order_by('id')
    data  = []
    for u in staff:
        o = u.office_allocation
        data.append({
            'id':          u.id,
            'full_name':   u.get_full_name(),
            'username':    u.username,
            'email':       u.email,
            'phone':       _str(u.phone),
            'employee_id': _str(u.employee_id),
            'role':        str(u.role) if u.role else '',
            'salary':      _d(u.salary),
            'is_active':   u.is_active,
            'is_superuser':u.is_superuser,
            'office':      o.name if o else '',
            'office_id':   o.id   if o else None,
        })
    return Response(data)


# =============================================================================
#  NYONGEZA — mirrors web nyongeza() view exactly
# =============================================================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_nyongeza(request):
    """GET /api/nyongeza/ — mirrors web nyongeza() view"""
    filter_office = get_filter_office(request)
    qs = Nyongeza.objects.all().order_by('-id')
    if filter_office:
        qs = qs.filter(Office=filter_office)

    totals = qs.aggregate(
        total_bank=Sum('amount', filter=Q(deposit_method='bank')),
        total_cash=Sum('amount', filter=Q(deposit_method='cash')),
        total_all=Sum('amount'),
    )

    data = []
    for n in qs:
        data.append({
            'id':             n.id,
            'amount':         _d(n.amount),
            'deposit_method': n.deposit_method or '',
            'description':    n.description or '',
            'date':           _str(n.date),
            'office':         n.Office.name if n.Office else '',
            'recorded_by':    n.recorded_by.get_full_name() if n.recorded_by else '',
        })

    return Response({
        'total_bank': _d(totals['total_bank']),
        'total_cash': _d(totals['total_cash']),
        'total_all':  _d(totals['total_all']),
        'nyongeza':   data,
    })


# =============================================================================
#  SALARIES — mirrors web salary() view
# =============================================================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_salaries(request):
    """GET /api/salaries/?month=YYYY-MM"""
    qs = Salary.objects.select_related('employee', 'processed_by', 'fund_source').all().order_by('-id')

    month_str = request.GET.get('month', '')
    if month_str:
        try:
            parts = month_str.split('-')
            qs = qs.filter(
                salary_for_month__year=int(parts[0]),
                salary_for_month__month=int(parts[1]),
            )
        except Exception:
            pass

    now = datetime.datetime.now()
    monthly_total = Salary.objects.filter(
        salary_for_month__year=now.year,
        salary_for_month__month=now.month,
    ).aggregate(total=Sum('amount'))['total'] or 0

    total_all = Salary.objects.aggregate(total=Sum('amount'))['total'] or 0

    data = []
    for s in qs:
        emp = s.employee
        data.append({
            'id':               s.id,
            'employee_name':    emp.get_full_name() if emp else '',
            'employee_id':      _str(emp.employee_id) if emp else '',
            'amount':           _d(s.amount),
            'salary_for_month': _str(s.salary_for_month),
            'transaction_method': s.transaction_method or '',
            'payment_date':     _str(s.payment_date) if hasattr(s, 'payment_date') else '',
            'fund_source':      s.fund_source.name if s.fund_source else '',
            'processed_by':     s.processed_by.get_full_name() if s.processed_by else '',
        })

    return Response({
        'total_this_month': _d(monthly_total),
        'total_all':        _d(total_all),
        'count':            len(data),
        'salaries':         data,
    })


# =============================================================================
#  SALARY ADVANCES — mirrors web salary_advance_list() view
# =============================================================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_salary_advances(request):
    """GET /api/salary-advances/"""
    qs = SalaryAdvance.objects.select_related('employee').all().order_by('-created_at')
    data = []
    for s in qs:
        emp = s.employee
        data.append({
            'id':                    s.id,
            'employee_name':         emp.get_full_name() if emp else '',
            'account':               s.account or '',
            'amount':                _d(s.amount),
            'payment_period':        s.payment_period,
            'monthly_installment':   _d(s.monthly_installment),
            'starting_payment_month': _str(s.starting_payment_month),
            'ending_payment_month':   _str(s.ending_payment_month),
            'status':                s.status or '',
        })
    return Response(data)


# =============================================================================
#  OFFICE TRANSACTIONS — mirrors web office_transaction() view
# =============================================================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_office_transactions(request):
    """GET /api/office-transactions/"""
    filter_office = get_filter_office(request)
    qs = OfficeTransaction.objects.select_related(
        'office_from', 'office_to', 'processed_by'
    ).order_by('-transaction_date', '-id')

    if filter_office:
        qs = qs.filter(
            Q(office_from=filter_office) | Q(office_to=filter_office)
        )

    data = []
    for t in qs[:100]:
        data.append({
            'id':                t.id,
            'office_from':       t.office_from.name if t.office_from else '',
            'office_to':         t.office_to.name   if t.office_to   else '',
            'transaction_type':  t.transaction_type or '',
            'transaction_method':t.transaction_method or '',
            'amount':            _d(t.amount),
            'transaction_date':  _str(t.transaction_date),
            'processed_by':      t.processed_by.get_full_name() if t.processed_by else '',
        })
    return Response(data)


# =============================================================================
#  COMPLETED LOANS — mirrors web completed_loans() view
# =============================================================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_completed_loans(request):
    """GET /api/completed-loans/"""
    filter_office = get_filter_office(request)
    qs = LoanApplication.objects.filter(
        repayment_amount_remaining__lte=0
    ).select_related('client', 'processed_by').order_by('-updated_at')

    if filter_office:
        qs = qs.filter(office=filter_office.name)

    agg = qs.aggregate(
        total=Sum('total_repayment_amount'),
        interest=Sum('total_interest_amount'),
    )

    data = []
    for l in qs[:100]:
        data.append({
            'id':           l.id,
            'client_name':  f"{l.client.firstname} {l.client.lastname}",
            'loan_amount':  _d(l.loan_amount),
            'total_paid':   _d(l.total_repayment_amount),
            'office':       l.office or '',
            'date':         _str(l.application_date),
            'loan_type':    l.loan_type or '',
        })

    return Response({
        'count':                len(data),
        'total_amount_repaid':  _d(agg['total']),
        'total_interest_earned':_d(agg['interest']),
        'loans':                data,
    })


# =============================================================================
#  LOAN REPORT (outstanding, not approved) — mirrors web loan_report() view
# =============================================================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_loan_report(request):
    """GET /api/loan-report/ — active loans not yet approved"""
    filter_office = get_filter_office(request)
    qs = LoanApplication.objects.filter(
        is_approved=False,
        repayment_amount_remaining__gt=0,
    ).select_related('client').prefetch_related('repayments').order_by(
        'client__lastname', 'client__firstname', 'id'
    )

    if filter_office:
        qs = qs.filter(office=filter_office.name)

    rows = []
    grand_loan = grand_interest = grand_total = grand_paid = grand_balance = Decimal('0')

    for l in qs:
        paid        = sum(r.repayment_amount for r in l.repayments.all())
        loan_amt    = l.loan_amount            or Decimal('0')
        interest    = l.total_interest_amount  or Decimal('0')
        total       = l.total_repayment_amount or Decimal('0')
        balance     = max(l.repayment_amount_remaining or Decimal('0'), Decimal('0'))

        rows.append({
            'name':            f"{l.client.firstname} {l.client.middlename or ''} {l.client.lastname}".strip(),
            'check_no':        l.client.checkno or l.client.employmentcardno or '',
            'mobile':          l.client.phonenumber or '',
            'loan_type':       l.loan_type or '',
            'loan_amount':     _d(loan_amt),
            'interest_amount': _d(interest),
            'total_amount':    _d(total),
            'paid_amount':     _d(paid) if paid > 0 else None,
            'balance':         _d(balance),
        })

        grand_loan    += loan_amt
        grand_interest+= interest
        grand_total   += total
        grand_paid    += paid
        grand_balance += balance

    return Response({
        'rows':                  rows,
        'grand_loan_amount':     _d(grand_loan),
        'grand_interest_amount': _d(grand_interest),
        'grand_total_amount':    _d(grand_total),
        'grand_paid_amount':     _d(grand_paid),
        'grand_balance':         _d(grand_balance),
    })


# =============================================================================
#  EXPIRED LOANS — mirrors web expired_loans() view
# =============================================================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_expired_loans(request):
    """GET /api/expired-loans/"""
    from dateutil.relativedelta import relativedelta

    filter_office = get_filter_office(request)
    today = date.today()

    qs = LoanApplication.objects.filter(
        repayment_amount_remaining__gt=0,
    ).select_related('client').prefetch_related('repayments').order_by('application_date', 'id')

    if filter_office:
        qs = qs.filter(office=filter_office.name)

    MONTH_NAMES = {1:'Jan',2:'Feb',3:'Mar',4:'Apr',5:'May',6:'Jun',
                   7:'Jul',8:'Aug',9:'Sep',10:'Oct',11:'Nov',12:'Dec'}

    def month_label(d):
        return f"{MONTH_NAMES[d.month]}/{d.year}"

    def classify(expired_days):
        if expired_days <= 30:  return 'Substandard'
        elif expired_days <= 90: return 'Doubtful'
        else:                   return 'Loss'

    rows = []
    total_loaned = total_paid = total_outstanding = Decimal('0')

    for l in qs:
        if not l.first_repayment_date or not l.payment_period_months:
            continue
        from dateutil.relativedelta import relativedelta
        end_date = l.first_repayment_date + relativedelta(months=l.payment_period_months - 1)
        if end_date >= today:
            continue
        expired_days = (today - end_date).days
        if expired_days <= 0:
            continue

        paid_amt    = sum(r.repayment_amount for r in l.repayments.all())
        outstanding = l.repayment_amount_remaining or Decimal('0')
        client      = l.client

        rows.append({
            'loan_id':       l.id,
            'name':          f"{client.firstname} {client.middlename or ''} {client.lastname}".strip(),
            'check_no':      client.checkno or client.employmentcardno or '',
            'contact':       client.phonenumber or '',
            'loan_type':     l.loan_type or '',
            'loaned_amount': _d(l.loan_amount),
            'paid_amount':   _d(paid_amt),
            'outstanding':   _d(outstanding),
            'expired_days':  expired_days,
            'status':        classify(expired_days),
            'start_month':   month_label(l.first_repayment_date),
            'end_month':     month_label(end_date),
            'office':        l.office or '',
        })

        total_loaned      += l.loan_amount or Decimal('0')
        total_paid        += paid_amt
        total_outstanding += outstanding

    return Response({
        'count':            len(rows),
        'total_loaned':     _d(total_loaned),
        'total_paid':       _d(total_paid),
        'total_outstanding':_d(total_outstanding),
        'loans':            rows,
    })


# =============================================================================
#  FINANCIAL STATEMENT — mirrors web financial_statement_report() view
# =============================================================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_financial_statement(request):
    """GET /api/financial-statement/?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD"""
    d_from, d_to, err = _parse_dates(request)
    if err:
        return Response({'error': err}, status=400)

    filter_office = get_filter_office(request)
    selected      = get_selected_office_api(request)

    start_dt = datetime.datetime.combine(d_from, datetime.time.min)
    end_dt   = datetime.datetime.combine(d_to,   datetime.time.max)

    # ── Opening Balance (before d_from, same office) ──────────────────
    def _sum(qs, field='amount'):
        return qs.aggregate(t=Sum(field))['t'] or Decimal('0')

    rep_b  = _sum(LoanRepayment.objects.filter(
        loan_application__office=filter_office.name if filter_office else None,
        repayment_date__lt=d_from,
    ) if filter_office else LoanRepayment.objects.filter(repayment_date__lt=d_from),
    'repayment_amount')

    nyo_b  = _sum((Nyongeza.objects.filter(Office=filter_office, date__lt=d_from)
                   if filter_office else Nyongeza.objects.filter(date__lt=d_from)))

    exp_b  = _sum((Expense.objects.filter(office=filter_office.name, expense_date__lt=d_from)
                   if filter_office else Expense.objects.filter(expense_date__lt=d_from)))

    loan_b = _sum((LoanApplication.objects.filter(office=filter_office.name, application_date__lt=d_from)
                   if filter_office else LoanApplication.objects.filter(application_date__lt=d_from)),
                  'loan_amount')

    opening_balance = (rep_b + nyo_b) - (exp_b + loan_b)

    # ── Current period ────────────────────────────────────────────────
    pq = Q(created_at__gte=start_dt, created_at__lte=end_dt)

    rep_qs = LoanRepayment.objects.filter(pq)
    nyo_qs = Nyongeza.objects.filter(pq)
    exp_qs = Expense.objects.filter(pq)
    loan_qs= LoanApplication.objects.filter(pq)
    sal_qs = Salary.objects.filter(pq)

    if filter_office:
        rep_qs  = rep_qs.filter(loan_application__office__iexact=filter_office.name)
        nyo_qs  = nyo_qs.filter(Office=filter_office)
        exp_qs  = exp_qs.filter(office__iexact=filter_office.name)
        loan_qs = loan_qs.filter(office__iexact=filter_office.name)
        sal_qs  = sal_qs.filter(fund_source=filter_office)

    total_mapato   = _sum(rep_qs, 'repayment_amount')
    total_nyongeza = _sum(nyo_qs)
    total_income   = opening_balance + total_mapato + total_nyongeza

    total_loans    = _sum(loan_qs, 'loan_amount')
    total_expenses = _sum(exp_qs)
    total_salaries = _sum(sal_qs)
    total_outflow  = total_loans + total_expenses + total_salaries

    # Live balances
    if filter_office:
        latest = BranchBalance.objects.filter(branch=filter_office).order_by('-last_updated').first()
        cash_in_office = _d(latest.office_balance) if latest else 0
        cash_in_bank   = _d(latest.bank_balance)   if latest else 0
    else:
        cash_in_office = cash_in_bank = 0
        for o in Office.objects.all():
            lb = BranchBalance.objects.filter(branch=o).order_by('-last_updated').first()
            if lb:
                cash_in_office += _d(lb.office_balance)
                cash_in_bank   += _d(lb.bank_balance)

    return Response({
        'date_from':         _str(d_from),
        'date_to':           _str(d_to),
        'selected_office':   filter_office.name if filter_office else 'All',
        'opening_balance':   _d(opening_balance),
        'total_mapato':      _d(total_mapato),
        'total_nyongeza':    _d(total_nyongeza),
        'total_income':      _d(total_income),
        'total_loans':       _d(total_loans),
        'total_expenses':    _d(total_expenses),
        'total_salaries':    _d(total_salaries),
        'total_outflow':     _d(total_outflow),
        'closing_balance':   _d(total_income - total_outflow),
        'cash_in_office':    cash_in_office,
        'cash_in_bank':      cash_in_bank,
        'total_cash':        cash_in_office + cash_in_bank,
    })


# =============================================================================
#  BRANCH TRANSACTION STATEMENT — mirrors web branch_transaction_statement_report()
# =============================================================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_branch_transactions(request):
    """GET /api/branch-transactions/?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD"""
    d_from, d_to, err = _parse_dates(request)
    if err:
        return Response({'error': err}, status=400)

    filter_office = get_filter_office(request)
    office_name   = filter_office.name if filter_office else None

    start_dt = datetime.datetime.combine(d_from, datetime.time.min)
    end_dt   = datetime.datetime.combine(d_to,   datetime.time.max)

    rows = []

    # Repayments (CREDIT)
    rep_qs = LoanRepayment.objects.filter(
        created_at__range=(start_dt, end_dt)
    ).select_related('loan_application__client', 'processed_by').order_by('created_at', 'id')
    if office_name:
        rep_qs = rep_qs.filter(loan_application__office=office_name)

    for r in rep_qs:
        c = r.loan_application.client
        rows.append({
            'date':        _str(r.created_at.date()),
            'type':        'repayment',
            'receipt_no':  str(r.id).zfill(6),
            'name':        f"{c.firstname} {c.middlename or ''} {c.lastname}".strip(),
            'description': 'Loan payment',
            'credit':      _d(r.repayment_amount),
            'debit':       None,
            'processed_by':r.processed_by.get_full_name() if r.processed_by else '',
        })

    # Loan disbursements (DEBIT)
    loan_qs = LoanApplication.objects.filter(
        created_at__date__range=(d_from, d_to)
    ).select_related('client', 'processed_by').order_by('created_at', 'id')
    if office_name:
        loan_qs = loan_qs.filter(office=office_name)

    for l in loan_qs:
        rows.append({
            'date':        _str(l.application_date),
            'type':        'loan',
            'receipt_no':  str(l.id).zfill(6),
            'name':        f"{l.client.firstname} {l.client.lastname}",
            'description': 'Loan disbursed',
            'credit':      None,
            'debit':       _d(l.loan_amount),
            'processed_by':l.processed_by.get_full_name() if l.processed_by else '',
        })

    # Expenses (DEBIT)
    exp_qs = Expense.objects.filter(
        created_at__range=(start_dt, end_dt)
    ).select_related('recorded_by', 'transaction_type').order_by('created_at', 'id')
    if office_name:
        exp_qs = exp_qs.filter(office=office_name)

    for e in exp_qs:
        cat = e.transaction_type.name if e.transaction_type else 'Expense'
        rows.append({
            'date':        _str(e.created_at.date()) if e.created_at else '',
            'type':        'expense',
            'receipt_no':  str(e.id).zfill(6),
            'name':        e.recorded_by.get_full_name() if e.recorded_by else '',
            'description': f"{cat}: {e.description or ''}",
            'credit':      None,
            'debit':       _d(e.amount),
            'processed_by':e.recorded_by.get_full_name() if e.recorded_by else '',
        })

    rows.sort(key=lambda x: x['date'], reverse=False)

    grand_credit = sum(r['credit'] or 0 for r in rows)
    grand_debit  = sum(r['debit']  or 0 for r in rows)

    return Response({
        'date_from':    _str(d_from),
        'date_to':      _str(d_to),
        'branch_name':  office_name or 'All Branches',
        'grand_credit': grand_credit,
        'grand_debit':  grand_debit,
        'rows':         rows,
    })


# =============================================================================
#  REPORTS — mirrors all web report views
# =============================================================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def report_loans_issued(request):
    """GET /api/reports/loans-issued/?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD"""
    d_from, d_to, err = _parse_dates(request)
    if err:
        return Response({'error': err}, status=400)

    filter_office = get_filter_office(request)
    qs = LoanApplication.objects.select_related('client').filter(
        application_date__gte=d_from, application_date__lte=d_to,
    )
    if filter_office:
        qs = qs.filter(office=filter_office.name)

    agg   = qs.aggregate(total=Sum('loan_amount'), count=Count('id'),
                          interest=Sum('total_interest_amount'), total_rep=Sum('total_repayment_amount'))
    items = []
    for l in qs.order_by('-application_date'):
        items.append({
            'id':                  l.id,
            'client_name':         f"{l.client.firstname} {l.client.lastname}",
            'check_no':            l.client.checkno or l.client.employmentcardno or '',
            'mobile':              l.client.phonenumber or '',
            'loan_amount':         _d(l.loan_amount),
            'interest_amount':     _d(l.total_interest_amount),
            'total_amount':        _d(l.total_repayment_amount),
            'monthly_installment': _d(l.monthly_installment),
            'period':              l.payment_period_months or 0,
            'office':              l.office or '',
            'date':                _str(l.application_date),
            'loan_type':           l.loan_type or '',
            'status':              l.status or '',
        })

    return Response({
        'date_from':      _str(d_from),
        'date_to':        _str(d_to),
        'total_amount':   _d(agg['total']),
        'total_interest': _d(agg['interest']),
        'total_return':   _d(agg['total_rep']),
        'count':          agg['count'] or 0,
        'loans':          items,
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def report_loans_outstanding(request):
    """GET /api/reports/loans-outstanding/"""
    filter_office = get_filter_office(request)
    qs = LoanApplication.objects.select_related('client').filter(repayment_amount_remaining__gt=0)
    if filter_office:
        qs = qs.filter(office=filter_office.name)

    agg   = qs.aggregate(total=Sum('repayment_amount_remaining'), count=Count('id'))
    items = []
    for l in qs.order_by('-repayment_amount_remaining'):
        items.append({
            'id':           l.id,
            'client_name':  f"{l.client.firstname} {l.client.lastname}",
            'phone':        l.client.phonenumber or '',
            'check_no':     l.client.checkno or '',
            'loan_amount':  _d(l.loan_amount),
            'outstanding':  _d(l.repayment_amount_remaining),
            'office':       l.office or '',
            'loan_type':    l.loan_type or '',
            'date':         _str(l.application_date),
        })

    return Response({
        'total_outstanding': _d(agg['total']),
        'count':             agg['count'] or 0,
        'loans':             items,
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def report_overdue_loans(request):
    """GET /api/reports/overdue-loans/"""
    filter_office = get_filter_office(request)
    today = date.today()
    qs = LoanApplication.objects.select_related('client').filter(
        repayment_amount_remaining__gt=0,
        first_repayment_date__lt=today,
    )
    if filter_office:
        qs = qs.filter(office=filter_office.name)

    items = []
    for l in qs.order_by('first_repayment_date'):
        overdue_days = (today - l.first_repayment_date).days if l.first_repayment_date else 0
        items.append({
            'id':            l.id,
            'client_name':   f"{l.client.firstname} {l.client.lastname}",
            'phone':         l.client.phonenumber or '',
            'outstanding':   _d(l.repayment_amount_remaining),
            'office':        l.office or '',
            'overdue_days':  overdue_days,
            'due_date':      _str(l.first_repayment_date),
        })

    return Response({
        'count':             len(items),
        'total_outstanding': _d(qs.aggregate(t=Sum('repayment_amount_remaining'))['t']),
        'loans':             items,
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def report_expenses(request):
    """GET /api/reports/expenses/?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD"""
    d_from, d_to, err = _parse_dates(request)
    if err:
        return Response({'error': err}, status=400)

    filter_office = get_filter_office(request)
    qs = Expense.objects.select_related('transaction_type', 'recorded_by').filter(
        expense_date__gte=d_from, expense_date__lte=d_to,
    )
    if filter_office:
        qs = qs.filter(office=filter_office.name)

    agg   = qs.aggregate(total=Sum('amount'), count=Count('id'))
    items = []
    for e in qs.order_by('-expense_date'):
        items.append({
            'id':          e.id,
            'description': e.description or '',
            'amount':      _d(e.amount),
            'office':      e.office or '',
            'date':        _str(e.expense_date),
            'category':    e.transaction_type.name if e.transaction_type else '',
            'payment_method': e.payment_method or '',
        })

    return Response({
        'date_from':    _str(d_from),
        'date_to':      _str(d_to),
        'total_amount': _d(agg['total']),
        'count':        agg['count'] or 0,
        'expenses':     items,
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def report_financial(request):
    """GET /api/reports/financial/?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD"""
    d_from, d_to, err = _parse_dates(request)
    if err:
        return Response({'error': err}, status=400)

    filter_office = get_filter_office(request)

    loans_qs = LoanApplication.objects.filter(application_date__gte=d_from, application_date__lte=d_to)
    repay_qs = LoanRepayment.objects.filter(repayment_date__gte=d_from, repayment_date__lte=d_to)
    exp_qs   = Expense.objects.filter(expense_date__gte=d_from, expense_date__lte=d_to)

    if filter_office:
        loans_qs = loans_qs.filter(office=filter_office.name)
        repay_qs = repay_qs.filter(loan_application__office=filter_office.name)
        exp_qs   = exp_qs.filter(office=filter_office.name)

    loans_total = loans_qs.aggregate(t=Sum('loan_amount'))['t'] or 0
    repay_total = repay_qs.aggregate(t=Sum('repayment_amount'))['t'] or 0
    exp_total   = exp_qs.aggregate(t=Sum('amount'))['t'] or 0

    return Response({
        'date_from':        _str(d_from),
        'date_to':          _str(d_to),
        'total_loans':      _d(loans_total),
        'total_repayments': _d(repay_total),
        'total_expenses':   _d(exp_total),
        'net':              _d(repay_total) - _d(exp_total),
        'loans_count':      loans_qs.count(),
        'repayments_count': repay_qs.count(),
        'expenses_count':   exp_qs.count(),
    })


# ─────────────────────────────────────────────────────────────────────────────
#  LOANS OWED
# ─────────────────────────────────────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def loans_owed_summary(request):
    """
    GET /api/loans-owed/
    Matches web: views.loans_owed_summary
    Returns count of active loans with outstanding balance.
    """
    filter_office = get_filter_office(request)

    qs = LoanApplication.objects.filter(
        is_approved=False,
        repayment_amount_remaining__gt=0,
    )
    if filter_office:
        qs = qs.filter(office=filter_office.name)

    total = qs.count()
    total_outstanding = qs.aggregate(t=Sum('repayment_amount_remaining'))['t'] or 0

    return Response({
        'total_loans_owed':    total,
        'cash_loans_count':    total,
        'total_outstanding':   _d(total_outstanding),
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def loans_owed_report(request):
    """
    GET /api/loans-owed/report/
    Matches web: views.loans_owed_report
    Returns loans grouped by first_repayment_date month (last 6 months window).
    Each group has loans with their repayment schedule per month (12 columns).
    """
    import datetime
    from dateutil.relativedelta import relativedelta

    filter_office = get_filter_office(request)
    selected      = get_selected_office_for_api(request)

    today        = datetime.date.today()
    cur_y, cur_m = today.year, today.month
    win_start    = today - relativedelta(months=6)
    win_y, win_m = win_start.year, win_start.month

    loans_qs = LoanApplication.objects.filter(
        is_approved=False,
    ).select_related('client').prefetch_related('topups')

    if filter_office:
        loans_qs = loans_qs.filter(office=filter_office.name)

    loans_list = list(loans_qs)

    # Build repayment map: loan_id → {(year, month): amount}
    rep_map = {l.id: {} for l in loans_list}
    repayments = LoanRepayment.objects.filter(
        loan_application__in=loans_list
    ).values('loan_application_id', 'repayment_date', 'repayment_amount', 'payment_month')

    for r in repayments:
        ref = r['payment_month'] or r['repayment_date']
        if not ref:
            continue
        key = (ref.year, ref.month)
        lid = r['loan_application_id']
        rep_map[lid][key] = rep_map[lid].get(key, Decimal('0')) + r['repayment_amount']

    # Group loans by first_repayment_date month (within 6-month window)
    groups = {}
    for loan in loans_list:
        frd = loan.first_repayment_date
        if not frd:
            continue
        sy, sm = frd.year, frd.month
        if (sy, sm) < (win_y, win_m):
            continue
        groups.setdefault((sy, sm), []).append(loan)

    MONTH_NAMES = {1:'Jan',2:'Feb',3:'Mar',4:'Apr',5:'May',6:'Jun',
                   7:'Jul',8:'Aug',9:'Sep',10:'Oct',11:'Nov',12:'Dec'}

    def label(y, m):
        return f"{MONTH_NAMES[m]}-{y}"

    def months_range(sy, sm, ey, em):
        out, y, m = [], sy, sm
        while (y, m) <= (ey, em):
            out.append((y, m))
            m += 1
            if m > 12:
                m, y = 1, y + 1
        return out

    month_sections = []

    for (sy, sm) in sorted(groups.keys(), reverse=True):
        loans_in_group = sorted(
            groups[(sy, sm)],
            key=lambda l: (l.client.lastname or '', l.client.firstname or '')
        )

        col_end    = datetime.date(sy, sm, 1) + relativedelta(months=11)
        col_months = months_range(sy, sm, col_end.year, col_end.month)
        month_headers = [label(y, m) for y, m in col_months]

        rows = []
        sec_paid = sec_loaned = sec_amount = sec_balance = Decimal('0')

        for loan in loans_in_group:
            client   = loan.client
            name     = f"{client.firstname} {client.middlename or ''} {client.lastname}".strip()
            inst     = loan.monthly_installment or Decimal('0')
            rmap     = rep_map.get(loan.id, {})
            period   = loan.payment_period_months or 0
            frd      = loan.first_repayment_date
            loaned   = loan.loan_amount            or Decimal('0')
            tot_amt  = loan.total_repayment_amount or Decimal('0')
            balance  = loan.repayment_amount_remaining or Decimal('0')

            # Build cells: one per column month
            cells = []
            total_paid_sum = Decimal('0')
            for (cy, cm) in col_months:
                if not frd:
                    cells.append({'type': 'empty', 'paid': 0, 'out': 0})
                    continue

                offset    = (cy - frd.year) * 12 + (cm - frd.month)
                past      = (cy, cm) <= (cur_y, cur_m)
                paid_this = _d(rmap.get((cy, cm), Decimal('0')))
                total_paid_sum += Decimal(str(paid_this))

                if 0 <= offset < period:
                    expected = _d(inst)
                    shortfall = max(expected - paid_this, 0)
                    if paid_this >= expected and expected > 0:
                        cells.append({'type': 'tick',     'paid': paid_this, 'out': 0})
                    elif paid_this > 0:
                        cells.append({'type': 'partial',  'paid': paid_this, 'out': shortfall})
                    elif past:
                        cells.append({'type': 'out_only', 'paid': 0,         'out': expected})
                    else:
                        cells.append({'type': 'future',   'paid': 0,         'out': expected})
                else:
                    if paid_this > 0:
                        cells.append({'type': 'extra',    'paid': paid_this, 'out': 0})
                    else:
                        cells.append({'type': 'empty',    'paid': 0,         'out': 0})

            rows.append({
                'loan_id':       loan.id,
                'loan_id_label': f"{(loan.office or '').lower()}-{loan.id}",
                'name':          name,
                'check_no':      client.checkno or client.employmentcardno or '',
                'mobile':        client.phonenumber or '',
                'cells':         cells,
                'total_paid':    _d(total_paid_sum),
                'loaned_amount': _d(loaned),
                'total_amount':  _d(tot_amt),
                'balance':       _d(balance),
                'is_fully_paid': balance <= Decimal('0'),
            })

            sec_paid    += total_paid_sum
            sec_loaned  += loaned
            sec_amount  += tot_amt
            sec_balance += balance

        month_sections.append({
            'key':          f"{sy}-{sm:02d}",
            'label':        label(sy, sm).upper(),
            'month_headers': month_headers,
            'rows':         rows,
            'total_paid':   _d(sec_paid),
            'total_loaned': _d(sec_loaned),
            'total_amount': _d(sec_amount),
            'total_balance':_d(sec_balance),
        })

    # HAMA section — overdue loans (first_repayment_date older than 6 months)
    hama_cutoff = today - relativedelta(months=6)
    hama_loans  = [
        l for l in loans_list
        if l.first_repayment_date and l.first_repayment_date <= hama_cutoff
        and l.repayment_amount_remaining > 0
    ]

    hama_rows = []
    for loan in sorted(hama_loans, key=lambda l: (l.client.lastname or '', l.client.firstname or '')):
        client  = loan.client
        name    = f"{client.firstname} {client.middlename or ''} {client.lastname}".strip()
        balance = loan.repayment_amount_remaining or Decimal('0')
        paid    = sum(rep_map.get(loan.id, {}).values(), Decimal('0'))
        overdue_days = (today - loan.first_repayment_date).days if loan.first_repayment_date else 0

        hama_rows.append({
            'loan_id':       loan.id,
            'loan_id_label': f"{(loan.office or '').lower()}-{loan.id}",
            'name':          name,
            'check_no':      client.checkno or '',
            'mobile':        client.phonenumber or '',
            'loaned_amount': _d(loan.loan_amount or 0),
            'total_amount':  _d(loan.total_repayment_amount or 0),
            'total_paid':    _d(paid),
            'balance':       _d(balance),
            'overdue_days':  overdue_days,
            'start_month':   label(loan.first_repayment_date.year, loan.first_repayment_date.month)
                             if loan.first_repayment_date else '',
        })

    return Response({
        'branch_name':    selected.name.upper() if selected else 'ALL BRANCHES',
        'month_sections': month_sections,
        'hama_rows':      hama_rows,
        'hama_count':     len(hama_rows),
        'hama_total_balance': _d(sum(Decimal(str(r['balance'])) for r in hama_rows)),
    })


# ─────────────────────────────────────────────────────────────────────────────
#  CUSTOMER STATEMENT
# ─────────────────────────────────────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_customer_statement(request):
    """GET /api/customer-statement/?client_id=<id>
    Matches web: views.customer_statement
    """
    client_id = request.GET.get('client_id')
    if not client_id:
        return Response({'error': 'client_id required'}, status=400)

    try:
        from app.models import Client, LoanApplication, LoanRepayment, LoanTopup
        client = Client.objects.get(id=client_id)
    except Client.DoesNotExist:
        return Response({'error': 'Client not found'}, status=404)

    filter_office = get_filter_office(request)
    loans = LoanApplication.objects.filter(
        client=client
    ).prefetch_related('repayments', 'topups').order_by('application_date', 'id')
    if filter_office:
        loans = loans.filter(office=filter_office.name)

    loan_blocks = []
    global_balance = Decimal('0')

    for loan in loans:
        total_repayable = loan.total_repayment_amount or Decimal('0')
        block_rows = []

        repayments_by_date = {}
        for r in loan.repayments.all().order_by('payment_month', 'id'):
            if r.payment_month is None: continue
            repayments_by_date.setdefault(r.payment_month, []).append(r)

        topups_by_date = {}
        for t in loan.topups.all().order_by('topup_date', 'id'):
            if t.topup_date is None: continue
            topups_by_date.setdefault(t.topup_date, []).append(t)

        all_dates = sorted(
            d for d in set(list(repayments_by_date.keys()) + list(topups_by_date.keys()))
            if d is not None
        )

        global_balance += total_repayable
        block_rows.append({
            'type': 'disbursement',
            'date': str(loan.application_date),
            'receipt_no': str(loan.id).zfill(6),
            'description': 'Loan Taken and interest',
            'loan_amount': _d(total_repayable),
            'paid_amount': 0,
            'balance': _d(global_balance),
        })

        for day in all_dates:
            day_repayments = repayments_by_date.get(day, [])
            day_topups = topups_by_date.get(day, [])
            repayments_to_show = day_repayments[:-1] if day_topups else day_repayments

            for r in repayments_to_show:
                global_balance = max(global_balance - r.repayment_amount, Decimal('0'))
                block_rows.append({
                    'type': 'repayment',
                    'date': str(r.repayment_date or day),
                    'receipt_no': str(r.id).zfill(6),
                    'description': 'Loan payment',
                    'loan_amount': 0,
                    'paid_amount': _d(r.repayment_amount),
                    'balance': _d(global_balance),
                })

            for topup in day_topups:
                old_balance = topup.old_balance_cleared or global_balance or Decimal('0')
                if old_balance > 0:
                    global_balance = Decimal('0')
                    block_rows.append({
                        'type': 'topup_clearance',
                        'date': str(topup.topup_date),
                        'receipt_no': str(topup.id).zfill(6),
                        'description': 'Clearance loan balance for top-up',
                        'loan_amount': 0,
                        'paid_amount': _d(old_balance),
                        'balance': _d(global_balance),
                    })

        loan_blocks.append({
            'loan_id': loan.id,
            'loan_type': loan.loan_type,
            'rows': block_rows,
        })

    return Response({
        'client': {
            'id': client.id,
            'name': f"{client.firstname} {client.lastname}",
            'phone': client.phonenumber or '',
        },
        'loan_blocks': loan_blocks,
    })


# ─────────────────────────────────────────────────────────────────────────────
#  LOAN REPAYMENT SCHEDULE
# ─────────────────────────────────────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_loan_repayment_schedule(request, loan_id):
    """GET /api/loans/<id>/schedule/
    Matches web: views.loan_repayment_schedule
    """
    from app.models import LoanApplication, LoanRepayment, LoanTopup
    from decimal import ROUND_DOWN

    try:
        loan = LoanApplication.objects.get(id=loan_id)
    except LoanApplication.DoesNotExist:
        return Response({'error': 'Loan not found'}, status=404)

    MONTH_NAMES = {1:'Jan',2:'Feb',3:'Mar',4:'Apr',5:'May',6:'Jun',
                   7:'Jul',8:'Aug',9:'Sep',10:'Oct',11:'Nov',12:'Dec'}

    def floor_1000(val):
        return (val / Decimal('1000')).to_integral_value(rounding=ROUND_DOWN) * Decimal('1000')

    periods = loan.payment_period_months or 1
    P = loan.loan_amount or Decimal('0')
    I = loan.total_interest_amount or Decimal('0')

    rounded_principal = floor_1000(P / periods)
    rounded_interest = floor_1000(I / periods)
    rounded_monthly = rounded_principal + rounded_interest
    first_principal = P - (rounded_principal * (periods - 1))
    first_interest = I - (rounded_interest * (periods - 1))
    first_monthly = first_principal + first_interest

    paid_by_month = {}
    for r in loan.repayments.all():
        if r.payment_month:
            key = (r.payment_month.year, r.payment_month.month)
            paid_by_month[key] = paid_by_month.get(key, Decimal('0')) + (r.repayment_amount or Decimal('0'))

    start = loan.first_repayment_date or loan.application_date
    rows = []
    total_paid_sum = Decimal('0')
    total_out_sum = Decimal('0')

    for i in range(periods):
        y = start.year + (start.month - 1 + i) // 12
        m = (start.month - 1 + i) % 12 + 1
        is_first = (i == 0)
        p = first_principal if is_first else rounded_principal
        n = first_interest if is_first else rounded_interest
        t = first_monthly if is_first else rounded_monthly
        paid = paid_by_month.get((y, m), Decimal('0'))
        outstanding = max(t - paid, Decimal('0'))

        rows.append({
            'month': f"{MONTH_NAMES[m]}/{y}",
            'principal': _d(p),
            'interest': _d(n),
            'total': _d(t),
            'paid': _d(paid),
            'outstanding': _d(outstanding),
        })
        total_paid_sum += paid
        total_out_sum += outstanding

    return Response({
        'loan_id': loan.id,
        'loan_amount': _d(loan.loan_amount or 0),
        'total_interest': _d(loan.total_interest_amount or 0),
        'total_repayable': _d(loan.total_repayment_amount or 0),
        'schedule': rows,
        'totals': {
            'paid': _d(total_paid_sum),
            'outstanding': _d(total_out_sum),
        }
    })


# ─────────────────────────────────────────────────────────────────────────────
#  LOAN OUTSTANDING (per client)
# ─────────────────────────────────────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_loan_outstanding(request):
    """GET /api/loan-outstanding/?client_id=<id>
    Matches web: views.loan_outstanding_report
    """
    client_id = request.GET.get('client_id')
    if not client_id:
        # Return list of clients with loans
        from app.models import Client
        filter_office = get_filter_office(request)
        qs = Client.objects.filter(loan_applications__isnull=False).distinct().order_by('firstname')
        if filter_office:
            qs = qs.filter(loan_applications__office=filter_office.name).distinct()
        data = [{'id': c.id, 'name': f"{c.firstname} {c.lastname}", 'phone': c.phonenumber or ''} for c in qs]
        return Response(data)

    from app.models import Client, LoanApplication
    try:
        client = Client.objects.get(id=client_id)
    except Client.DoesNotExist:
        return Response({'error': 'Not found'}, status=404)

    filter_office = get_filter_office(request)
    loans = LoanApplication.objects.filter(client=client).prefetch_related('repayments').order_by('created_at')
    if filter_office:
        loans = loans.filter(office=filter_office.name)

    rows = []
    for loan in loans:
        paid = sum(r.repayment_amount for r in loan.repayments.all())
        outstanding = max(loan.repayment_amount_remaining or Decimal('0'), Decimal('0'))
        rows.append({
            'loan_id': loan.id,
            'loan_id_label': f"{(loan.office or 'loan').lower()}-{loan.id}",
            'loan_amount': _d(loan.loan_amount or 0),
            'interest_amount': _d(loan.total_interest_amount or 0),
            'total_amount': _d(loan.total_repayment_amount or 0),
            'paid_amount': _d(paid),
            'outstanding': _d(outstanding),
            'repayment_count': loan.repayments.count(),
            'is_approved': loan.is_approved,
        })

    return Response({
        'client': {'id': client.id, 'name': f"{client.firstname} {client.lastname}"},
        'loans': rows,
        'totals': {
            'loan_amount': _d(sum(Decimal(str(r['loan_amount'])) for r in rows)),
            'paid_amount': _d(sum(Decimal(str(r['paid_amount'])) for r in rows)),
            'outstanding': _d(sum(Decimal(str(r['outstanding'])) for r in rows)),
        }
    })


# ─────────────────────────────────────────────────────────────────────────────
#  SALARY SLIP / PAYROLL
# ─────────────────────────────────────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_salary_slip(request):
    """GET /api/salary/slip/?month=YYYY-MM
    Matches web: views.salary_slip_list
    """
    import calendar as cal_module
    month_param = request.GET.get('month', '')
    if not month_param:
        import datetime
        month_param = datetime.date.today().strftime('%Y-%m')

    try:
        year, month = map(int, month_param.split('-'))
        start_date = __import__('datetime').date(year, month, 1)
        last_day = cal_module.monthrange(year, month)[1]
        end_date = __import__('datetime').date(year, month, last_day)
    except Exception:
        return Response({'error': 'Invalid month format. Use YYYY-MM'}, status=400)

    salaries = Salary.objects.filter(
        salary_for_month__gte=start_date,
        salary_for_month__lte=end_date,
    ).select_related('employee', 'fund_source').order_by('fund_source__name', 'employee__first_name')

    rows = []
    total_basic = total_deduction = total_net = Decimal('0')

    for sal in salaries:
        emp = sal.employee
        basic = sal.amount or Decimal('0')
        deduction = (emp.deduction_amount if emp and emp.deduction_amount else Decimal('0'))
        net = basic - deduction

        rows.append({
            'employee_name': emp.get_full_name() if emp else '',
            'branch': sal.fund_source.name if sal.fund_source else '',
            'basic_salary': _d(basic),
            'deduction': _d(deduction),
            'net_salary': _d(net),
            'transaction_method': sal.transaction_method or '',
            'salary_for_month': str(sal.salary_for_month),
        })
        total_basic += basic
        total_deduction += deduction
        total_net += net

    return Response({
        'month': month_param,
        'salaries': rows,
        'totals': {
            'basic_salary': _d(total_basic),
            'deduction': _d(total_deduction),
            'net_salary': _d(total_net),
        }
    })


# ─────────────────────────────────────────────────────────────────────────────
#  MONTHLY REPAYMENT REPORT
# ─────────────────────────────────────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_monthly_repayment(request):
    """GET /api/monthly-repayment/?month_from=MM-YYYY&month_to=MM-YYYY
    Matches web: views.monthly_repayment_report
    """
    import calendar as cal_mod, datetime

    filter_office = get_filter_office(request)
    month_from_str = request.GET.get('month_from', '')
    month_to_str   = request.GET.get('month_to', '')

    def parse_month(s):
        try:
            parts = s.strip().split('-')
            return int(parts[0]), int(parts[1])
        except Exception:
            return None, None

    fm, fy = parse_month(month_from_str)
    tm, ty = parse_month(month_to_str)

    if not fm:
        today = datetime.date.today()
        fm, fy = today.month, today.year
        tm, ty = today.month, today.year

    range_start = datetime.date(fy, fm, 1)
    range_end = datetime.date(ty, tm, cal_mod.monthrange(ty, tm)[1])

    repayments = LoanRepayment.objects.filter(
        repayment_date__range=(range_start, range_end),
    ).select_related('loan_application__client', 'processed_by').order_by('payment_month', 'id')
    if filter_office:
        repayments = repayments.filter(loan_application__office=filter_office.name)

    topups = LoanTopup.objects.filter(
        topup_date__range=(range_start, range_end),
    ).select_related('loan_application__client', 'processed_by').order_by('payment_month', 'id')
    if filter_office:
        topups = topups.filter(loan_application__office=filter_office.name)

    MONTH_NAMES = {1:'Jan',2:'Feb',3:'Mar',4:'Apr',5:'May',6:'Jun',
                   7:'Jul',8:'Aug',9:'Sep',10:'Oct',11:'Nov',12:'Dec'}

    buckets = {}
    for rep in repayments:
        if not rep.payment_month: continue
        loan = rep.loan_application
        client = loan.client
        key = (rep.payment_month.year, rep.payment_month.month)
        buckets.setdefault(key, []).append({
            'date': str(rep.repayment_date or ''),
            'receipt_no': str(rep.id).zfill(6),
            'name': f"{client.firstname} {client.middlename or ''} {client.lastname}".strip(),
            'check_no': client.checkno or '',
            'loan_id_label': f"{(loan.office or 'loan').lower()}-{loan.id}",
            'description': 'Loan payment',
            'amount': _d(rep.repayment_amount or 0),
            'record_type': 'repayment',
        })

    for topup in topups:
        if not topup.payment_month: continue
        loan = topup.loan_application
        client = loan.client
        key = (topup.payment_month.year, topup.payment_month.month)
        buckets.setdefault(key, []).append({
            'date': str(topup.topup_date or ''),
            'receipt_no': str(topup.id).zfill(6),
            'name': f"{client.firstname} {client.middlename or ''} {client.lastname}".strip(),
            'check_no': client.checkno or '',
            'loan_id_label': f"{(loan.office or 'loan').lower()}-{loan.id}",
            'description': 'Clearance loan balance for top-up',
            'amount': _d(topup.old_balance_cleared or 0),
            'record_type': 'topup',
        })

    months_data = []
    for key in sorted(buckets.keys()):
        y, m = key
        rows = buckets[key]
        months_data.append({
            'label': f"{MONTH_NAMES[m]}-{y}",
            'rows': rows,
            'grand_total': _d(sum(Decimal(str(r['amount'])) for r in rows)),
        })

    return Response({'months': months_data})


# ─────────────────────────────────────────────────────────────────────────────
#  MONTHLY OUTSTANDING REPORT
# ─────────────────────────────────────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_monthly_outstanding(request):
    """GET /api/monthly-outstanding/?month=YYYY-MM-DD
    Matches web: views.monthly_outstanding_report
    """
    import calendar as cal_mod, datetime
    from dateutil.relativedelta import relativedelta

    filter_office = get_filter_office(request)
    month_str = request.GET.get('month', '')

    try:
        selected_date = datetime.datetime.strptime(month_str, '%Y-%m-%d').date()
    except Exception:
        selected_date = datetime.date.today()

    sel_year  = selected_date.year
    sel_month = selected_date.month
    last_day  = cal_mod.monthrange(sel_year, sel_month)[1]
    month_start = datetime.date(sel_year, sel_month, 1)
    month_end   = datetime.date(sel_year, sel_month, last_day)

    loans = LoanApplication.objects.filter(
        repayment_amount_remaining__gt=0,
    ).select_related('client').prefetch_related('repayments').order_by('client__lastname')
    if filter_office:
        loans = loans.filter(office=filter_office.name)

    rows = []
    for loan in loans:
        if not loan.first_repayment_date or not loan.payment_period_months or not loan.monthly_installment:
            continue

        schedule_months = [
            ((loan.first_repayment_date + relativedelta(months=i)).year,
             (loan.first_repayment_date + relativedelta(months=i)).month)
            for i in range(loan.payment_period_months)
        ]
        slots = sum(1 for (y, m) in schedule_months if y == sel_year and m == sel_month)
        if slots == 0: continue

        amount_to_pay = loan.monthly_installment * slots
        paid_this = sum(
            r.repayment_amount or Decimal('0')
            for r in loan.repayments.all()
            if r.repayment_date and month_start <= r.repayment_date <= month_end
        )
        not_paid = max(amount_to_pay - paid_this, Decimal('0'))
        client = loan.client

        rows.append({
            'name': f"{client.firstname} {client.middlename or ''} {client.lastname}".strip(),
            'check_no': client.checkno or '',
            'contact': client.phonenumber or '',
            'amount_to_be_paid': _d(amount_to_pay),
            'paid_this_month': _d(paid_this),
            'not_paid': _d(not_paid),
            'outstanding_total': _d(loan.repayment_amount_remaining or 0),
        })

    return Response({
        'month': str(selected_date),
        'rows': rows,
        'totals': {
            'amount_to_be_paid': _d(sum(Decimal(str(r['amount_to_be_paid'])) for r in rows)),
            'paid_this_month': _d(sum(Decimal(str(r['paid_this_month'])) for r in rows)),
            'not_paid': _d(sum(Decimal(str(r['not_paid'])) for r in rows)),
            'outstanding_total': _d(sum(Decimal(str(r['outstanding_total'])) for r in rows)),
        }
    })


# ─────────────────────────────────────────────────────────────────────────────
#  LOANS ISSUED REPORT (by branch summary)
# ─────────────────────────────────────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_loans_issued_summary(request):
    """GET /api/reports/loans-issued-summary/?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD
    Matches web: views.loans_issued_report_result — branch summary
    """
    from django.db.models import Count
    d_from, d_to, err = _parse_dates(request)
    if err:
        return Response({'error': err}, status=400)

    qs = LoanApplication.objects.filter(
        application_date__gte=d_from,
        application_date__lte=d_to,
    )

    branch_data = (
        qs.values('office')
        .annotate(
            no_of_loans=Count('id'),
            loaned_amount=Coalesce(Sum('loan_amount'), Decimal('0')),
            interest_amount=Coalesce(Sum('total_interest_amount'), Decimal('0')),
            total_return=Coalesce(Sum('total_repayment_amount'), Decimal('0')),
        )
        .order_by('office')
    )

    summary = [
        {
            'branch': row['office'] or 'N/A',
            'no_of_loans': row['no_of_loans'],
            'loaned_amount': _d(row['loaned_amount']),
            'interest_amount': _d(row['interest_amount']),
            'total_return': _d(row['total_return']),
        }
        for row in branch_data
    ]

    return Response({
        'date_from': str(d_from),
        'date_to': str(d_to),
        'branches': summary,
        'totals': {
            'no_of_loans': sum(r['no_of_loans'] for r in summary),
            'loaned_amount': _d(sum(Decimal(str(r['loaned_amount'])) for r in summary)),
            'interest_amount': _d(sum(Decimal(str(r['interest_amount'])) for r in summary)),
            'total_return': _d(sum(Decimal(str(r['total_return'])) for r in summary)),
        }
    })


# ─────────────────────────────────────────────────────────────────────────────
#  MONTHLY OUTSTANDING SUMMARY (branch totals)
# ─────────────────────────────────────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_monthly_outstanding_summary(request):
    """GET /api/reports/monthly-outstanding-summary/?month=YYYY-MM-DD
    Matches web: views.monthly_outstanding_result_summary — branch summary
    """
    import calendar as cal_mod, datetime
    from django.db.models import Count

    month_str = request.GET.get('month', '')
    try:
        selected_date = datetime.datetime.strptime(month_str, '%Y-%m-%d').date()
    except Exception:
        selected_date = datetime.date.today()

    last_day = cal_mod.monthrange(selected_date.year, selected_date.month)[1]
    end_of_month = selected_date.replace(day=last_day)

    qs = LoanApplication.objects.filter(
        application_date__lte=end_of_month,
        repayment_amount_remaining__gt=Decimal('0'),
    )

    branch_data = (
        qs.values('office')
        .annotate(
            no_of_loans=Count('id'),
            outstanding_amount=Coalesce(Sum('repayment_amount_remaining'), Decimal('0')),
        )
        .order_by('office')
    )

    summary = [
        {
            'branch': row['office'] or 'N/A',
            'no_of_loans': row['no_of_loans'],
            'outstanding_amount': _d(row['outstanding_amount']),
        }
        for row in branch_data
    ]

    return Response({
        'month': str(selected_date),
        'branches': summary,
        'totals': {
            'no_of_loans': sum(r['no_of_loans'] for r in summary),
            'outstanding_amount': _d(sum(Decimal(str(r['outstanding_amount'])) for r in summary)),
        }
    })


# ─────────────────────────────────────────────────────────────────────────────
#  EXPIRED LOANS SUMMARY (branch summary with classification)
# ─────────────────────────────────────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_expired_loans_summary(request):
    """GET /api/reports/expired-loans-summary/
    Matches web: views.expired_loans_report_summary
    """
    import datetime

    today = datetime.date.today()

    expired_qs = LoanApplication.objects.filter(
        first_repayment_date__lt=today,
        repayment_amount_remaining__gt=Decimal('0'),
    ).values('office', 'loan_amount', 'repayment_amount_remaining', 'first_repayment_date')

    branch_map = {}
    for loan in expired_qs:
        branch = loan['office'] or 'N/A'
        days = (today - loan['first_repayment_date']).days if loan['first_repayment_date'] else 999

        if days <= 30: cls = 'current'
        elif days <= 60: cls = 'esm'
        elif days <= 90: cls = 'substandard'
        elif days <= 180: cls = 'doubtful'
        else: cls = 'loss'

        if branch not in branch_map:
            branch_map[branch] = {'branch': branch, 'loan_issued': Decimal('0'),
                'outstanding': Decimal('0'), 'current': 0, 'esm': 0,
                'substandard': 0, 'doubtful': 0, 'loss': 0}

        branch_map[branch]['loan_issued'] += Decimal(str(loan['loan_amount']))
        branch_map[branch]['outstanding'] += Decimal(str(loan['repayment_amount_remaining']))
        branch_map[branch][cls] += 1

    summary = []
    for row in sorted(branch_map.values(), key=lambda x: x['branch']):
        row['total'] = row['current'] + row['esm'] + row['substandard'] + row['doubtful'] + row['loss']
        row['loan_issued'] = _d(row['loan_issued'])
        row['outstanding'] = _d(row['outstanding'])
        summary.append(row)

    return Response({'branches': summary, 'today': str(today)})


# ─────────────────────────────────────────────────────────────────────────────
#  EXPENSES STATEMENT (by category)
# ─────────────────────────────────────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_expenses_statement(request):
    """GET /api/reports/expenses-statement/?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD
    Matches web: views.expenses_statement_result
    """
    d_from, d_to, err = _parse_dates(request)
    if err:
        return Response({'error': err}, status=400)

    all_cats = ExpenseCategory.objects.all().order_by('name')
    expense_totals = (
        Expense.objects.filter(transaction_date__gte=d_from, transaction_date__lte=d_to)
        .values('transaction_type_id')
        .annotate(total=Coalesce(Sum('amount'), Decimal('0')))
    )
    totals_map = {row['transaction_type_id']: row['total'] for row in expense_totals}

    summary = [
        {'category': cat.name, 'total': _d(totals_map.get(cat.id, 0))}
        for cat in all_cats
    ]
    grand = _d(sum(totals_map.values(), Decimal('0')))

    return Response({'categories': summary, 'grand_total': grand})


# ─────────────────────────────────────────────────────────────────────────────
#  BRANCH FINANCIAL SUMMARY (columnar per branch)
# ─────────────────────────────────────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_branch_financial_summary(request):
    """GET /api/reports/branch-financial-summary/?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD
    Matches web: views.branch_financial_summary
    """
    import datetime

    start_str = request.GET.get('start_date', '')
    end_str   = request.GET.get('end_date', '')
    try:
        start_date = datetime.datetime.strptime(start_str, '%Y-%m-%d').date()
        end_date   = datetime.datetime.strptime(end_str,   '%Y-%m-%d').date()
    except Exception:
        today = datetime.date.today()
        start_date = today.replace(day=1)
        end_date = today

    offices = Office.objects.exclude(name__iexact='HQ').order_by('name')
    result = []

    for office in offices:
        def _sum_office(qs, field='amount'):
            return qs.aggregate(t=Sum(field))['t'] or Decimal('0')

        mapato = _sum_office(LoanRepayment.objects.filter(
            loan_application__office=office.name,
            repayment_date__gte=start_date, repayment_date__lte=end_date,
        ), 'repayment_amount')
        nyongeza = _sum_office(Nyongeza.objects.filter(
            Office=office, date__gte=start_date, date__lte=end_date,
        ))
        fomu = _sum_office(LoanApplication.objects.filter(
            office=office.name, application_date__gte=start_date, application_date__lte=end_date,
        ), 'loan_amount')
        expenses = _sum_office(Expense.objects.filter(
            office=office.name, expense_date__gte=start_date, expense_date__lte=end_date,
        ))
        latest = BranchBalance.objects.filter(branch=office).order_by('-last_updated').first()
        cash = _d(latest.office_balance if latest else 0)
        bank = _d(latest.bank_balance if latest else 0)

        result.append({
            'branch': office.name,
            'mapato': _d(mapato),
            'nyongeza': _d(nyongeza),
            'fomu': _d(fomu),
            'expenses': _d(expenses),
            'balance_cash': cash,
            'balance_bank': bank,
            'balance_total': _d(Decimal(str(cash)) + Decimal(str(bank))),
        })

    return Response({'branches': result, 'start_date': str(start_date), 'end_date': str(end_date)})


# ─────────────────────────────────────────────────────────────────────────────
#  NO LOAN CUSTOMERS
# ─────────────────────────────────────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_no_loan_customers(request):
    """GET /api/no-loan-customers/
    Matches web: views.no_loan_customers
    """
    filter_office = get_filter_office(request)
    base_qs = Client.objects.all()
    if filter_office:
        base_qs = base_qs.filter(registered_office=filter_office)

    no_loans = base_qs.filter(loan_applications__isnull=True).distinct()
    all_paid = base_qs.exclude(
        loan_applications__repayment_amount_remaining__gt=0
    ).exclude(loan_applications__isnull=True).distinct()

    all_ids = set(
        list(no_loans.values_list('id', flat=True)) +
        list(all_paid.values_list('id', flat=True))
    )
    clients = Client.objects.filter(id__in=all_ids).order_by('lastname', 'firstname')

    data = [
        {
            'id': c.id,
            'name': f"{c.firstname} {c.lastname}",
            'phone': c.phonenumber or '',
            'check_no': c.checkno or '',
        }
        for c in clients
    ]
    return Response({'count': len(data), 'clients': data})


# ─────────────────────────────────────────────────────────────────────────────
#  EXPENSE CATEGORIES CRUD
# ─────────────────────────────────────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_expense_category_detail(request, pk):
    """GET /api/expense-categories/<pk>/
    Matches web: views.expense_category_detail
    """
    try:
        cat = ExpenseCategory.objects.get(pk=pk)
        return Response({'id': cat.id, 'name': cat.name})
    except ExpenseCategory.DoesNotExist:
        return Response({'error': 'Not found'}, status=404)


# ─────────────────────────────────────────────────────────────────────────────
#  LOAN COLLECTION STATEMENT
# ─────────────────────────────────────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_loan_collection(request):
    """GET /api/loan-collection/?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD
    Matches web: views.loan_collection_statement_report
    """
    import datetime
    d_from, d_to, err = _parse_dates(request)
    if err:
        return Response({'error': err}, status=400)

    filter_office = get_filter_office(request)
    dt_from = datetime.datetime.combine(d_from, datetime.time.min)
    dt_to   = datetime.datetime.combine(d_to,   datetime.time.max)

    repayments = LoanRepayment.objects.filter(
        created_at__range=(dt_from, dt_to),
    ).select_related('loan_application__client', 'processed_by').order_by('created_at')
    if filter_office:
        repayments = repayments.filter(loan_application__office=filter_office.name)

    rows = []
    grand_total = Decimal('0')
    for r in repayments:
        loan = r.loan_application
        client = loan.client
        rows.append({
            'date': str(r.created_at.date()),
            'receipt_no': str(r.id).zfill(6),
            'name': f"{client.firstname} {client.lastname}",
            'description': 'Loan payment',
            'amount': _d(r.repayment_amount),
            'rate': _d(loan.interest_rate or 0),
        })
        grand_total += r.repayment_amount

    return Response({'rows': rows, 'grand_total': _d(grand_total)})


# ─────────────────────────────────────────────────────────────────────────────
#  BRANCH TRANSACTION STATEMENT
# ─────────────────────────────────────────────────────────────────────────────

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_branch_transaction_statement(request):
    """GET /api/branch-transactions/?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD
    Matches web: views.branch_transaction_statement_report
    """
    d_from, d_to, err = _parse_dates(request)
    if err:
        return Response({'error': err}, status=400)

    filter_office = get_filter_office(request)
    selected = get_selected_office_for_api(request)
    office_name = filter_office.name if filter_office else None

    import datetime
    dt_from = datetime.datetime.combine(d_from, datetime.time.min)
    dt_to   = datetime.datetime.combine(d_to,   datetime.time.max)

    raw = []

    # Repayments (CREDIT)
    repayments = LoanRepayment.objects.filter(created_at__range=(dt_from, dt_to))
    if office_name:
        repayments = repayments.filter(loan_application__office=office_name)
    for r in repayments.select_related('loan_application__client', 'processed_by'):
        c = r.loan_application.client
        raw.append({
            'date': str(r.created_at.date()),
            'type': 'repayment',
            'name': f"{c.firstname} {c.lastname}",
            'description': 'Loan payment',
            'credit': _d(r.repayment_amount),
            'debit': None,
            'receipt_no': str(r.id).zfill(6),
        })

    # Disbursements (DEBIT)
    loans_qs = LoanApplication.objects.filter(created_at__date__range=(d_from, d_to))
    if office_name:
        loans_qs = loans_qs.filter(office=office_name)
    for loan in loans_qs.select_related('client'):
        c = loan.client
        raw.append({
            'date': str(loan.created_at.date()),
            'type': 'loan',
            'name': f"{c.firstname} {c.lastname}",
            'description': 'Loan disbursement',
            'credit': None,
            'debit': _d(loan.loan_amount),
            'receipt_no': str(loan.id).zfill(6),
        })

    # Expenses (DEBIT)
    expenses = Expense.objects.filter(created_at__range=(dt_from, dt_to))
    if office_name:
        expenses = expenses.filter(office=office_name)
    for exp in expenses.select_related('transaction_type'):
        cat = exp.transaction_type.name if exp.transaction_type else 'Expense'
        raw.append({
            'date': str(exp.created_at.date()),
            'type': 'expense',
            'name': cat,
            'description': exp.description or '',
            'credit': None,
            'debit': _d(exp.amount),
            'receipt_no': str(exp.id).zfill(6),
        })

    raw.sort(key=lambda e: e['date'])
    grand_credit = _d(sum(Decimal(str(e['credit'])) for e in raw if e['credit']))
    grand_debit  = _d(sum(Decimal(str(e['debit']))  for e in raw if e['debit']))

    return Response({
        'branch': selected.name if selected else 'All',
        'rows': raw,
        'grand_credit': grand_credit,
        'grand_debit': grand_debit,
    })
