"""
MASCO Microfinance — API Views (Mobile-Ready)
=============================================
Badilisha: api/views.py

Changes from original:
  1. ClientListAPI    → ListCreateAPIView  (POST /clients/ works)
  2. LoanListAPI      → ListCreateAPIView  (POST /loans/ works)
  3. ExpenseListAPI   → ListCreateAPIView  (POST /expenses/ works)
  4. All list views   → PageNumberPagination (mobile uses PaginatedResponse)
  5. loan_repayments  → GET + POST (add repayment)
  6. api_salaries     → standard paginated list (not nested dict)
  7. api_monthly_summary → new endpoint for reports/monthly/
  8. ClientSerializer → added checkno, client_id fields
  9. ExpenseSerializer → consistent field names
"""

import datetime
from decimal import Decimal
from django.utils import timezone
from django.db.models import Sum, Count, Q, Max, Min, Avg, F
from django.db.models.functions import Coalesce
from rest_framework import generics, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate
from datetime import date

from app.models import (
    Client, LoanApplication, LoanRepayment, Office, BranchBalance,
    Expense, ExpenseCategory, Nyongeza, Salary, SalaryAdvance,
    BankCharge, UserOfficeAssignment, OfficeTransaction, HQTransaction,
    BankCashTransaction, LoanTopup,
)
from app.serializers import (
    ClientSerializer, LoanApplicationSerializer, LoanRepaymentSerializer,
    OfficeSerializer, ExpenseSerializer, ExpenseCategorySerializer,
    DashboardStatsSerializer,
)
from useraccount.models import CustomUser


# =============================================================================
#  HELPERS
# =============================================================================

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
#  PAGINATION — standard 20-per-page for all list endpoints
# =============================================================================

class StandardPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100


# =============================================================================
#  OFFICE HELPERS
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
    Reads office_id from X-Office-Id header, ?office_id= param, or POST body.
    Falls back to user.office_allocation.
    """
    user = request.user
    allowed_qs = get_user_allowed_offices(user)

    office_id = (
        request.META.get('HTTP_X_OFFICE_ID') or
        request.GET.get('office_id') or
        (request.data.get('office_id') if hasattr(request, 'data') else None)
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
    """
    selected = get_selected_office_api(request)
    if selected and selected.name.strip().upper() == 'HQ':
        return None
    return selected


# =============================================================================
#  AUTH
# =============================================================================

@api_view(['POST'])
@permission_classes([AllowAny])
def api_login(request):
    """POST /api/auth/login/"""
    username = request.data.get('username')
    password = request.data.get('password')
    user = authenticate(username=username, password=password)
    if not user:
        return Response({'detail': 'Jina la mtumiaji au nywila si sahihi.'}, status=401)
    if not user.is_active:
        return Response({'detail': 'Akaunti hii imezuiwa.'}, status=401)

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
            'phone':        _str(getattr(user, 'phone', '')),
            'employee_id':  _str(getattr(user, 'employee_id', '')),
            'role':         str(user.role) if getattr(user, 'role', None) else '',
            'is_superuser': user.is_superuser,
            'is_active':    user.is_active,
            'office':       office.name if office else '',
            'office_name':  office.name if office else '',
            'branch':       office.name if office else '',
            'office_id':    office.id   if office else None,
            'branch_id':    office.id   if office else None,
        }
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_logout(request):
    try:
        RefreshToken(request.data.get('refresh')).blacklist()
    except Exception:
        pass
    return Response({'detail': 'Umefanikiwa kutoka.'})


# =============================================================================
#  BRANCH MANAGEMENT
# =============================================================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def my_branches(request):
    """GET /api/my-branches/"""
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
    """POST /api/switch-branch/"""
    if not request.user.is_superuser:
        return Response({'detail': 'Hairuhusiwi.'}, status=403)
    office_id = request.data.get('office_id')
    allowed   = get_user_allowed_offices(request.user)
    try:
        office = allowed.get(id=office_id)
        return Response({
            'office_id':   office.id,
            'office_name': office.name,
            'message':     f'Umebadilisha tawi hadi {office.name}',
        })
    except Office.DoesNotExist:
        return Response({'detail': 'Tawi halipatikani.'}, status=404)


# =============================================================================
#  DASHBOARD
# =============================================================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_branches_loan_report(request):
    # GET /api/hq/loans-report/?start_date=&end_date=&status=&loan_type=&search=&office=&region=
    # Mirrors branches_loan_report() web view exactly, including stats strip
    # fields shown in the screenshot: Total Loans, Principal Issued, Total
    # Interest, Total Repayable (P+I), Amount Collected, Outstanding,
    # Collection Rate.
    try:
        from django.utils import timezone as tz
        from dateutil.relativedelta import relativedelta

        # Accept both start_date/end_date (web param names) and date_from/date_to
        # (legacy mobile param names) for backward compatibility
        start_date    = (request.GET.get('start_date') or request.GET.get('date_from') or '').strip()
        end_date      = (request.GET.get('end_date')   or request.GET.get('date_to')   or '').strip()
        status_filter = request.GET.get('status', '').strip()
        loan_type_f   = request.GET.get('loan_type', '').strip()
        search_query  = request.GET.get('search', '').strip()
        office_filter = request.GET.get('office', '').strip()
        region_filter = request.GET.get('region', '').strip()

        loans = (
            LoanApplication.objects
            .select_related('client')
            .prefetch_related('repayments')
            .order_by('-created_at')
        )

        if start_date:
            try:
                d = datetime.datetime.strptime(start_date, '%Y-%m-%d').date()
                loans = loans.filter(created_at__gte=tz.make_aware(datetime.datetime.combine(d, datetime.time.min)))
            except (ValueError, TypeError):
                start_date = ''
        if end_date:
            try:
                d = datetime.datetime.strptime(end_date, '%Y-%m-%d').date()
                loans = loans.filter(created_at__lte=tz.make_aware(datetime.datetime.combine(d, datetime.time.max)))
            except (ValueError, TypeError):
                end_date = ''

        if status_filter:
            loans = loans.filter(status=status_filter)
        if loan_type_f:
            loans = loans.filter(loan_type=loan_type_f)
        if office_filter:
            loans = loans.filter(office__iexact=office_filter)
        if region_filter:
            loans = loans.filter(client__region=region_filter)
        if search_query:
            loans = loans.filter(
                Q(client__firstname__icontains=search_query) |
                Q(client__lastname__icontains=search_query) |
                Q(client__phonenumber__icontains=search_query) |
                Q(client__checkno__icontains=search_query) |
                Q(client__employmentcardno__icontains=search_query)
            )

        loan_data = []
        total_loan_amount = Decimal('0')
        total_paid_amount = Decimal('0')
        total_outstanding = Decimal('0')
        total_interest    = Decimal('0')

        today = tz.now().date()

        skipped_count = 0
        for index, loan in enumerate(loans, 1):
            # Wrap the ENTIRE per-loan block: one malformed record (bad type,
            # missing FK, non-Decimal numeric field from a data import, etc.)
            # must never abort the whole response — that previously caused the
            # mobile app to receive nothing at all instead of partial results.
            try:
                client = loan.client
                if not client:
                    skipped_count += 1
                    continue

                prefetched_repayments = sorted(
                    loan.repayments.all(),
                    key=lambda r: r.repayment_date or today,
                    reverse=True,
                )
                repayment_count = len(prefetched_repayments)
                last_repayment   = prefetched_repayments[0] if prefetched_repayments else None

                paid_amount = sum((r.repayment_amount or Decimal('0')) for r in prefetched_repayments)

                outstanding = (
                    loan.repayment_amount_remaining
                    if loan.repayment_amount_remaining is not None
                    else (
                        (loan.total_repayment_amount - paid_amount)
                        if loan.total_repayment_amount
                        else ((loan.loan_amount or Decimal('0')) - paid_amount)
                    )
                )

                if loan.total_repayment_amount and loan.total_repayment_amount > 0:
                    payment_percentage = (paid_amount / loan.total_repayment_amount) * 100
                else:
                    payment_percentage = Decimal('0')

                status_lower = (loan.status or '').lower()
                if status_lower == 'approved':
                    if outstanding <= 0:
                        current_status = 'Completed'; status_color = 'success'
                    elif paid_amount > 0:
                        current_status = 'Active';    status_color = 'primary'
                    else:
                        current_status = 'Approved';  status_color = 'info'
                else:
                    current_status = loan.status or 'Pending'
                    status_color   = 'warning' if current_status == 'Pending' else 'secondary'

                next_payment_date = None
                if status_lower == 'approved' and outstanding > 0 and loan.first_repayment_date:
                    if repayment_count < (loan.payment_period_months or 0):
                        next_payment_date = loan.first_repayment_date + relativedelta(months=repayment_count)

                try:
                    processor = loan.processed_by
                    processed_by_name = (processor.get_full_name() or processor.username) if processor else 'N/A'
                except Exception:
                    processed_by_name = 'N/A'

                frd = loan.first_repayment_date
                starting_month = frd.strftime('%b/%Y') if frd else '—'
                loan_date = loan.created_at.date() if loan.created_at else today

                # interest_rate may have been imported as float/str/None instead
                # of Decimal — coerce safely instead of calling .normalize()
                # directly on whatever type it happens to be.
                try:
                    ir = Decimal(str(loan.interest_rate)) if loan.interest_rate is not None else Decimal('0')
                    ir_display = str(ir.normalize()) + '%'
                except Exception:
                    ir_display = (str(loan.interest_rate) + '%') if loan.interest_rate is not None else '0%'

                loan_data.append({
                    'sn':                     index,
                    'loan_id':                loan.id,
                    'date':                   str(loan_date),
                    'client_name':            f"{client.firstname} {getattr(client,'middlename','') or ''} {client.lastname}".strip(),
                    'check_no':               client.checkno or getattr(client,'employmentcardno','') or 'N/A',
                    'mobile':                 client.phonenumber or 'N/A',
                    'region':                 getattr(client, 'region', '') or 'N/A',
                    'district':               getattr(client, 'district', '') or 'N/A',
                    'work_station':           getattr(client, 'employername', '') or 'N/A',
                    'loan_id_label':          f"{(loan.office or 'branch').lower()}-{loan.id}",
                    'rate_type':              'Flat',
                    'starting_month':         starting_month,
                    'loan_type':              loan.loan_type,
                    'loan_amount':            _d(loan.loan_amount),
                    'period':                 loan.payment_period_months or 0,
                    'interest_rate':          ir_display,
                    'interest_amount':        _d(loan.interest_amount or 0),
                    'total_interest':         _d(loan.total_interest_amount or 0),
                    'total_repayment_amount': _d(loan.total_repayment_amount or loan.loan_amount),
                    'monthly_installment':    _d(loan.monthly_installment or 0),
                    'paid_amount':            _d(paid_amount),
                    'outstanding':            _d(outstanding),
                    'payment_percentage':     round(float(payment_percentage), 2),
                    'status':                 current_status,
                    'status_color':           status_color,
                    'original_status':        loan.status,
                    'office':                 loan.office or 'N/A',
                    'processed_by':           processed_by_name,
                    'next_payment_date':      str(next_payment_date) if next_payment_date else None,
                    'last_repayment_date':    str(last_repayment.repayment_date) if last_repayment else None,
                    'repayments_count':       repayment_count,
                })

                total_loan_amount += loan.loan_amount or Decimal('0')
                total_paid_amount += paid_amount
                total_outstanding += outstanding
                total_interest    += (loan.total_interest_amount or Decimal('0'))

            except Exception:
                # Skip this single malformed loan record rather than failing
                # the entire report. Without this guard, ANY one bad row
                # (bad FK, wrong field type from a data import, etc.) caused
                # a 500 and the mobile app received no data whatsoever.
                skipped_count += 1
                continue

        # ── Dropdown options (for filter UI) ────────────────────────────────────
        loan_types = list(
            LoanApplication.objects.values_list('loan_type', flat=True).distinct().order_by('loan_type')
        )
        offices = list(
            LoanApplication.objects.exclude(office__isnull=True).exclude(office='')
            .values_list('office', flat=True).distinct().order_by('office')
        )
        regions = list(
            Client.objects.exclude(region__isnull=True).exclude(region='')
            .values_list('region', flat=True).distinct().order_by('region')
        )
        statuses = ['Pending', 'Approved', 'Rejected', 'Completed', 'Active']

        # ── Summary (stats strip in screenshot) ──────────────────────────────────
        total_loans = len(loan_data)
        total_repayable = total_loan_amount + total_interest
        collection_rate = (
            float(total_paid_amount / total_loan_amount * 100) if total_loan_amount > 0 else 0.0
        )

        # overdue_loans needs to re-parse next_payment_date strings — guard this
        # individually so a single malformed date string (unexpected format,
        # already-suffixed, etc.) can't take down the whole response the way it
        # did before. Any row that fails to parse is simply not counted as overdue.
        overdue_loans_count = 0
        for l in loan_data:
            if l['status'] != 'Active' or not l['next_payment_date']:
                continue
            try:
                npd = datetime.datetime.strptime(l['next_payment_date'][:10], '%Y-%m-%d').date()
                if npd < today:
                    overdue_loans_count += 1
            except Exception:
                continue

        summary = {
            'total_loans':         total_loans,
            'total_loan_amount':   _d(total_loan_amount),
            'total_paid_amount':   _d(total_paid_amount),
            'total_outstanding':   _d(total_outstanding),
            'total_interest':      _d(total_interest),
            'total_repayable':     _d(total_repayable),
            'average_loan_amount': _d(total_loan_amount / total_loans) if total_loans else _d(0),
            'collection_rate':     round(collection_rate, 1),
            'active_loans':    sum(1 for l in loan_data if l['status'] in ('Active', 'Approved')),
            'completed_loans': sum(1 for l in loan_data if l['status'] == 'Completed'),
            'pending_loans':   sum(1 for l in loan_data if l['status'] == 'Pending'),
            'overdue_loans':   overdue_loans_count,
        }

        # ── Loan-type breakdown ───────────────────────────────────────────────────
        # NOTE: loan_data values (loan_amount, paid_amount, outstanding) are
        # already plain floats here (produced by the _d() helper above), not
        # Decimal — initialise the accumulator as floats too, otherwise
        # Decimal += float raises TypeError and crashes the whole response.
        loan_type_summary = {}
        for loan in loan_data:
            lt = loan['loan_type']
            if lt not in loan_type_summary:
                loan_type_summary[lt] = {'count': 0, 'total_amount': 0.0, 'paid_amount': 0.0, 'outstanding': 0.0}
            loan_type_summary[lt]['count']        += 1
            loan_type_summary[lt]['total_amount'] += float(loan['loan_amount'] or 0)
            loan_type_summary[lt]['paid_amount']  += float(loan['paid_amount'] or 0)
            loan_type_summary[lt]['outstanding']  += float(loan['outstanding'] or 0)

        loan_type_summary_out = {
            lt: {
                'count': v['count'],
                'total_amount': _d(v['total_amount']),
                'paid_amount':  _d(v['paid_amount']),
                'outstanding':  _d(v['outstanding']),
            } for lt, v in loan_type_summary.items()
        }

        branch_label = office_filter if office_filter else 'All Branches'

        return Response({
            # legacy field names (kept for backward compatibility with the
            # existing mobile screen that reads top-level totals directly)
            'loans':             loan_data,
            'count':              total_loans,
            'total_loan_amount':  _d(total_loan_amount),
            'total_paid_amount':  _d(total_paid_amount),
            'total_outstanding':  _d(total_outstanding),
            'total_interest':     _d(total_interest),
            'collection_rate':    round(collection_rate, 1),

            # new fields mirroring branches_loan_report() exactly
            'loan_data':          loan_data,
            'summary':            summary,
            'loan_type_summary':  loan_type_summary_out,
            'loan_types':         loan_types,
            'offices':            offices,
            'regions':            regions,
            'statuses':           statuses,
            'branch_label':       branch_label,
            'filters': {
                'start_date': start_date,
                'end_date':   end_date,
                'status':     status_filter,
                'loan_type':  loan_type_f,
                'search':     search_query,
                'office':     office_filter,
                'region':     region_filter,
            },
            'today': str(today),
        })

    except Exception as _e:
        import traceback
        return Response({'detail': f'Server error: {str(_e)}', 'trace': traceback.format_exc()}, status=500)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_hq_expense_report(request):
    # GET /api/hq/expense-report/?start_date=&end_date=&office=&recorded_by=
    # Mirrors expense_report() web view exactly:
    #   - transaction_date is a plain DateField range, no timezone handling
    #   - office is exact-match (not iexact) per the reference view
    #   - default range = today minus 28 days -> today
    #   - 'Particular' display = category bold + [description] (screenshot)
    today_d = date.today()
    default_start = today_d - datetime.timedelta(days=28)

    start_date_str = request.GET.get('start_date') or request.GET.get('date_from') or default_start.strftime('%Y-%m-%d')
    end_date_str   = request.GET.get('end_date')   or request.GET.get('date_to')   or today_d.strftime('%Y-%m-%d')
    office_filter      = request.GET.get('office', '')
    recorded_by_filter = request.GET.get('recorded_by', '')

    try:
        start_date = datetime.datetime.strptime(start_date_str, '%Y-%m-%d').date()
        end_date   = datetime.datetime.strptime(end_date_str,   '%Y-%m-%d').date()
    except (ValueError, TypeError):
        start_date = default_start
        end_date   = today_d
        start_date_str = start_date.strftime('%Y-%m-%d')
        end_date_str   = end_date.strftime('%Y-%m-%d')

    # transaction_date is a DateField — plain range, no timezone needed
    expenses = (
        Expense.objects
        .filter(transaction_date__range=[start_date, end_date])
        .select_related('transaction_type', 'recorded_by')
        .order_by('-transaction_date')
    )

    if office_filter:
        expenses = expenses.filter(office=office_filter)
    if recorded_by_filter:
        expenses = expenses.filter(recorded_by__username=recorded_by_filter)

    total_expenses = expenses.count()
    total_amount    = expenses.aggregate(total=Sum('amount'))['total'] or Decimal('0')
    avg_expense     = expenses.aggregate(avg=Avg('amount'))['avg']     or Decimal('0')

    unique_offices = list(
        Expense.objects.exclude(office__isnull=True).exclude(office='')
        .values_list('office', flat=True).distinct().order_by('office')
    )

    highest = expenses.order_by('-amount').first()
    lowest  = expenses.order_by('amount').first()

    rows = []
    prev_date = None
    for e in expenses.order_by('transaction_date', 'id'):
        try:
            recorder = e.recorded_by
            recorded_by_name = (recorder.get_full_name() or recorder.username) if recorder else 'N/A'
        except Exception:
            recorded_by_name = 'N/A'

        edate = e.transaction_date or e.expense_date
        cat   = e.transaction_type.name if e.transaction_type else '—'
        desc  = (e.description or '').strip()

        rows.append({
            'id':           e.id,
            'date':         str(edate) if edate else '',
            'receipt_no':   str(e.id).zfill(6),
            'category':     cat,
            'description':  desc,
            # 'particular' matches the screenshot's combined display:
            # bold category followed by [description] in brackets
            'particular':   f"{cat} [{desc}]" if desc else cat,
            'amount':       _d(e.amount),
            'attachment':   e.attachment.url if e.attachment else None,
            'recorded_by':  recorded_by_name,
            'hide_date':    (edate == prev_date),
        })
        prev_date = edate

    branch_name = office_filter.upper() if office_filter else 'ALL BRANCHES'

    return Response({
        'rows':               rows,
        'grand_total':        _d(total_amount),
        'total_expenses':     total_expenses,
        'avg_expense':        _d(avg_expense),
        'highest_expense':    (_d(highest.amount) if highest else None),
        'lowest_expense':     (_d(lowest.amount) if lowest else None),
        'unique_offices':     unique_offices,
        'branch_name':        branch_name,
        'date_from':          str(start_date),
        'date_to':            str(end_date),
        'start_date':         str(start_date),
        'end_date':           str(end_date),
        'date_from_display':  start_date.strftime('%d %b %Y'),
        'date_to_display':    end_date.strftime('%d %b %Y'),
        'office_filter':      office_filter,
        'count':              len(rows),
    })

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_loan_collection_report(request):
    # GET /api/hq/loan-collection/?start_date=&end_date=&office=
    # Mirrors loan_collection_statement2() web view exactly.
    # Screenshot stat cards: Transactions, Total Principal, Total Interest,
    # Total Collected, Office, Generated By (the requesting user + timestamp).
    from django.utils import timezone as tz

    start_date_str = request.GET.get('start_date') or request.GET.get('date_from') or ''
    end_date_str   = request.GET.get('end_date')   or request.GET.get('date_to')   or ''
    office_filter  = request.GET.get('office', '')

    repayments = (
        LoanRepayment.objects
        .select_related('loan_application', 'loan_application__client', 'processed_by')
        .order_by('-created_at')
    )

    start_date = None
    end_date   = None

    if start_date_str:
        try:
            start_date = datetime.datetime.strptime(start_date_str, '%Y-%m-%d').date()
            start_dt = tz.make_aware(datetime.datetime.combine(start_date, datetime.time.min))
            repayments = repayments.filter(created_at__gte=start_dt)
        except (ValueError, TypeError):
            start_date_str = None
    if end_date_str:
        try:
            end_date = datetime.datetime.strptime(end_date_str, '%Y-%m-%d').date()
            end_dt = tz.make_aware(datetime.datetime.combine(end_date, datetime.time.max))
            repayments = repayments.filter(created_at__lte=end_dt)
        except (ValueError, TypeError):
            end_date_str = None

    if office_filter:
        repayments = repayments.filter(loan_application__office__iexact=office_filter)

    offices = list(
        LoanApplication.objects.exclude(office__isnull=True).exclude(office='')
        .values_list('office', flat=True).distinct().order_by('office')
    )

    collection_data = []
    running_balance = Decimal('0')

    for index, repayment in enumerate(repayments, 1):
        try:
            loan   = repayment.loan_application
            client = loan.client
            if not client:
                continue
        except Exception:
            continue

        if loan.payment_period_months and loan.payment_period_months > 0:
            interest_per_payment  = (loan.total_interest_amount or Decimal('0')) / loan.payment_period_months
            principal_per_payment = (loan.loan_amount or Decimal('0')) / loan.payment_period_months
        else:
            interest_per_payment  = Decimal('0')
            principal_per_payment = repayment.repayment_amount or Decimal('0')

        interest_amount  = min(interest_per_payment, repayment.repayment_amount or Decimal('0'))
        principal_amount = (repayment.repayment_amount or Decimal('0')) - interest_amount

        running_balance += repayment.repayment_amount or Decimal('0')

        try:
            processor  = repayment.processed_by
            created_by = (processor.get_full_name() or processor.username) if processor else 'N/A'
        except Exception:
            created_by = 'N/A'

        rdate = repayment.created_at.date() if repayment.created_at else None

        collection_data.append({
            'sn':              index,
            'date':            str(rdate) if rdate else '',
            'receipt_no':      f"RCP-{repayment.id:06d}",
            'client_name':     f"{client.firstname} {client.lastname}".strip(),
            'client_id_label': f"CLT-{client.id:06d}",
            'description':     f"Loan Repayment - {loan.loan_type} (LON-{loan.id:06d})",
            'rate':            str(loan.interest_rate) + '%' if loan.interest_rate is not None else '0%',
            'principal':       _d(principal_amount),
            'interest':        _d(interest_amount),
            'total':           _d(repayment.repayment_amount),
            'running_balance': _d(running_balance),
            'processed_by':    created_by,
            'loan_id':         loan.id,
            'client_id':       client.id,
            'office':          loan.office or 'N/A',
        })

    total_principal    = _d(sum(Decimal(str(r['principal'])) for r in collection_data))
    total_interest      = _d(sum(Decimal(str(r['interest']))  for r in collection_data))
    total_collected     = _d(sum(Decimal(str(r['total']))     for r in collection_data))
    total_transactions  = len(collection_data)

    # "Generated By" — the user who is currently viewing/requesting the report
    try:
        gen_user = request.user
        generated_by = (gen_user.get_full_name() or gen_user.username) if gen_user and gen_user.is_authenticated else 'N/A'
    except Exception:
        generated_by = 'N/A'

    branch_name = office_filter.upper() if office_filter else 'ALL BRANCHES'

    return Response({
        'rows':               collection_data,
        'collection_data':    collection_data,
        'total_principal':    total_principal,
        'total_interest':     total_interest,
        'total_collected':    total_collected,
        'total_transactions': total_transactions,
        'generated_by':       generated_by,
        'generated_at':       str(tz.now()),
        'start_date':         start_date_str,
        'end_date':           end_date_str,
        'date_from':          start_date_str,
        'date_to':            end_date_str,
        'office_filter':      office_filter,
        'branch_name':        branch_name,
        'offices':            offices,
    })

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_hq_bank_transfer_report(request):
    # GET /api/hq/bank-transfer/?date_from=&date_to=&office=
    # Mirrors bank_transfer_expenses2() web view exactly.
    # Screenshot stat cards: Total Records, Payment Method (always "Bank
    # Transfer"), Grand Total, Office (branch filter), Period (date range).
    from django.utils import timezone as tz

    date_from_str = request.GET.get('date_from') or request.GET.get('start_date') or ''
    date_to_str   = request.GET.get('date_to')   or request.GET.get('end_date')   or ''
    office_filter = request.GET.get('office', '')

    transactions = (
        HQTransaction.objects
        .select_related('from_branch', 'to_branch', 'processed_by')
        .order_by('-created_at', '-id')
    )

    if date_from_str:
        try:
            d = datetime.datetime.strptime(date_from_str, '%Y-%m-%d').date()
            start_dt = tz.make_aware(datetime.datetime.combine(d, datetime.time.min))
            transactions = transactions.filter(created_at__gte=start_dt)
        except (ValueError, TypeError):
            date_from_str = ''
    if date_to_str:
        try:
            d = datetime.datetime.strptime(date_to_str, '%Y-%m-%d').date()
            end_dt = tz.make_aware(datetime.datetime.combine(d, datetime.time.max))
            transactions = transactions.filter(created_at__lte=end_dt)
        except (ValueError, TypeError):
            date_to_str = ''

    if office_filter:
        transactions = transactions.filter(
            Q(from_branch__name__iexact=office_filter) | Q(to_branch__name__iexact=office_filter)
        )

    # Offices dropdown — only offices that have ever appeared in a transfer
    offices = list(
        Office.objects.filter(
            Q(hq_transactions_from__isnull=False) | Q(hq_transactions_to__isnull=False)
        ).values_list('name', flat=True).distinct().order_by('name')
    )

    grand_total = transactions.aggregate(total=Sum('amount'))['total'] or Decimal('0')

    rows = []
    for idx, t in enumerate(transactions, 1):
        try:
            processor = t.processed_by
            processed_by_name = (processor.get_full_name() or processor.username) if processor else 'N/A'
        except Exception:
            processed_by_name = 'N/A'

        rows.append({
            'sn':            idx,
            'date':          str(t.created_at.date()) if t.created_at else '',
            'receipt_no':    str(t.id).zfill(6),
            'receipt_number':str(t.id).zfill(6),
            'description':   t.description or f"Branch transfer (Bank) from {t.from_branch.name if t.from_branch else '?'} to {t.to_branch.name if t.to_branch else '?'}",
            'from_branch':   t.from_branch.name if t.from_branch else 'N/A',
            'to_branch':     t.to_branch.name   if t.to_branch   else 'N/A',
            'amount':        _d(t.amount),
            'processed_by':  processed_by_name,
        })

    total_count = len(rows)
    branch_name = office_filter.upper() if office_filter else 'ALL BRANCHES'

    return Response({
        'rows':              rows,
        'transactions_with_receipt': rows,
        'grand_total':       _d(grand_total),
        'branch_name':       branch_name,
        'payment_method':    'Bank Transfer',
        'date_from':         date_from_str,
        'date_to':           date_to_str,
        'period_from':       date_from_str,
        'period_to':         date_to_str,
        'total_records':     total_count,
        'total_count':       total_count,
        'offices':           offices,
        'office_filter':     office_filter,
    })

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_balance_sheet_report(request):
    # GET /api/reports/balance-sheet/?as_of_date=YYYY-MM-DD
    # Mirrors balance_sheet_report() web view exactly.
    # ASSETS = EQUITY identity:
    #   Cash + Bank + Receivables = OwnerCapital + Nyongeza + RetainedEarnings
    #   RetainedEarnings is the balancing figure (Total Assets - Capital - Nyongeza)
    try:
        from django.utils import timezone

        filter_office = get_filter_office(request)
        selected      = get_selected_office_api(request)
        branch_name   = selected.name.upper() if (selected and not filter_office is None and filter_office) else (
            filter_office.name.upper() if filter_office else 'ALL BRANCHES'
        )
        # branch_name should reflect filter_office when scoped, else ALL BRANCHES
        branch_name = filter_office.name.upper() if filter_office else 'ALL BRANCHES'

        as_of_str = request.GET.get('as_of_date', '').strip()
        try:
            as_of_date = datetime.datetime.strptime(as_of_str, '%Y-%m-%d').date()
        except (ValueError, TypeError):
            as_of_date = date.today()

        end_dt = timezone.make_aware(datetime.datetime.combine(as_of_date, datetime.time.max))

        def rep_qs(q):
            qs = LoanRepayment.objects.filter(q)
            if filter_office:
                qs = qs.filter(loan_application__office__iexact=filter_office.name)
            return qs

        def loan_qs(q):
            qs = LoanApplication.objects.filter(q)
            if filter_office:
                qs = qs.filter(office__iexact=filter_office.name)
            return qs

        def nyo_qs(q):
            qs = Nyongeza.objects.filter(q)
            if filter_office:
                qs = qs.filter(Office=filter_office)
            return qs

        def exp_qs(q):
            qs = Expense.objects.filter(q)
            if filter_office:
                qs = qs.filter(office__iexact=filter_office.name)
            return qs

        def transfer_in_qs(q):
            qs = OfficeTransaction.objects.filter(q)
            if filter_office:
                qs = qs.filter(office_to=filter_office)
            return qs

        def transfer_out_qs(q):
            qs = OfficeTransaction.objects.filter(q)
            if filter_office:
                qs = qs.filter(office_from=filter_office)
            return qs

        def bank_charge_qs(q):
            qs = BankCharge.objects.filter(q)
            if filter_office:
                qs = qs.filter(office__iexact=filter_office.name)
            return qs

        def bank_cash_txn_qs(q):
            qs = BankCashTransaction.objects.filter(q)
            if filter_office:
                qs = qs.filter(office_from=filter_office)
            return qs

        upto_q = Q(created_at__lte=end_dt)

        # ── CASH IN OFFICE ──────────────────────────────────────────────
        cash_rep = rep_qs(upto_q).filter(transaction_method__iexact='cash').aggregate(t=Sum('repayment_amount'))['t'] or Decimal('0')
        cash_nyo = nyo_qs(upto_q).filter(deposit_method__iexact='cash').aggregate(t=Sum('amount'))['t'] or Decimal('0')
        cash_to_bank = bank_cash_txn_qs(upto_q).filter(source__iexact='cash', destination__iexact='bank').aggregate(t=Sum('amount'))['t'] or Decimal('0')
        bank_to_cash = bank_cash_txn_qs(upto_q).filter(source__iexact='bank', destination__iexact='cash').aggregate(t=Sum('amount'))['t'] or Decimal('0')
        cash_exp = exp_qs(upto_q).filter(payment_method__iexact='cash').aggregate(t=Sum('amount'))['t'] or Decimal('0')
        cash_loan = loan_qs(upto_q).filter(transaction_method__iexact='cash').aggregate(t=Sum('loan_amount'))['t'] or Decimal('0')
        cash_charge = bank_charge_qs(upto_q).filter(payment_method__iexact='cash').aggregate(t=Sum('amount'))['t'] or Decimal('0')

        cash_in_office = (cash_rep + cash_nyo + bank_to_cash) - (cash_exp + cash_loan + cash_charge + cash_to_bank)

        # ── CASH IN BANK ────────────────────────────────────────────────
        bank_rep = rep_qs(upto_q).filter(transaction_method__iexact='bank').aggregate(t=Sum('repayment_amount'))['t'] or Decimal('0')
        bank_nyo = nyo_qs(upto_q).filter(deposit_method__iexact='bank').aggregate(t=Sum('amount'))['t'] or Decimal('0')
        bank_transfer_in = transfer_in_qs(upto_q).aggregate(t=Sum('amount'))['t'] or Decimal('0')
        bank_exp = exp_qs(upto_q).filter(payment_method__iexact='bank').aggregate(t=Sum('amount'))['t'] or Decimal('0')
        bank_loan = loan_qs(upto_q).filter(transaction_method__iexact='bank').aggregate(t=Sum('loan_amount'))['t'] or Decimal('0')
        bank_transfer_out = transfer_out_qs(upto_q).aggregate(t=Sum('amount'))['t'] or Decimal('0')
        bank_charge_total = bank_charge_qs(upto_q).filter(payment_method__iexact='bank').aggregate(t=Sum('amount'))['t'] or Decimal('0')

        cash_in_bank = (bank_rep + bank_nyo + bank_transfer_in + cash_to_bank) - (
            bank_exp + bank_loan + bank_transfer_out + bank_charge_total + bank_to_cash
        )

        # ── RECEIVABLES ─────────────────────────────────────────────────
        receivables_qs = LoanApplication.objects.filter(created_at__lte=end_dt, repayment_amount_remaining__gt=0)
        if filter_office:
            receivables_qs = receivables_qs.filter(office__iexact=filter_office.name)
        receivables = receivables_qs.aggregate(t=Sum('repayment_amount_remaining'))['t'] or Decimal('0')

        total_current_assets = cash_in_office + cash_in_bank + receivables
        total_assets = total_current_assets

        # ── EQUITY ──────────────────────────────────────────────────────
        owner_capital = Decimal('0')
        opening_balance_equity = nyo_qs(upto_q).aggregate(t=Sum('amount'))['t'] or Decimal('0')
        retained_earnings = total_assets - owner_capital - opening_balance_equity
        total_equity = owner_capital + opening_balance_equity + retained_earnings
        total_liabilities_equity = total_equity

        is_balanced = abs(total_assets - total_liabilities_equity) < Decimal('0.01')

        return Response({
            'branch_name':              branch_name,
            'as_of_date':               str(as_of_date),
            'as_of_date_display':       as_of_date.strftime('%B %d, %Y'),
            'generated_at':             str(timezone.now()),
            'cash_in_office':           _d(cash_in_office),
            'cash_in_bank':             _d(cash_in_bank),
            'receivables':              _d(receivables),
            'total_current_assets':     _d(total_current_assets),
            'total_assets':             _d(total_assets),
            'owner_capital':            _d(owner_capital),
            'opening_balance_equity':   _d(opening_balance_equity),
            'retained_earnings':        _d(retained_earnings),
            'total_equity':             _d(total_equity),
            'total_liabilities_equity': _d(total_liabilities_equity),
            'is_balanced':              is_balanced,
        })
    except Exception as _e:
        import traceback
        return Response({'detail': f'Server error: {str(_e)}', 'trace': traceback.format_exc()}, status=500)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_trial_balance_report(request):
    # GET /api/reports/trial-balance/?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD
    # Mirrors trial_balance_report() web view exactly: opening balances
    # computed before start_date, period movements within the range,
    # closing = opening + debit - credit, with Retained Earnings as the
    # balancing plug so the trial balance always reconciles to zero.
    try:
        from django.utils import timezone

        filter_office = get_filter_office(request)

        start_str = request.GET.get('start_date', '').strip()
        end_str   = request.GET.get('end_date', '').strip()
        try:
            start_date = datetime.datetime.strptime(start_str, '%Y-%m-%d').date()
            end_date   = datetime.datetime.strptime(end_str,   '%Y-%m-%d').date()
        except (ValueError, TypeError):
            end_date   = date.today()
            start_date = end_date.replace(month=1, day=1)

        branch_name = filter_office.name.upper() if filter_office else 'ALL BRANCHES'

        before_dt = timezone.make_aware(datetime.datetime.combine(start_date, datetime.time.min))
        start_dt  = before_dt
        end_dt    = timezone.make_aware(datetime.datetime.combine(end_date, datetime.time.max))

        def rep_qs(q):
            qs = LoanRepayment.objects.filter(q)
            if filter_office:
                qs = qs.filter(loan_application__office__iexact=filter_office.name)
            return qs

        def loan_qs(q):
            qs = LoanApplication.objects.filter(q)
            if filter_office:
                qs = qs.filter(office__iexact=filter_office.name)
            return qs

        def nyo_qs(q):
            qs = Nyongeza.objects.filter(q)
            if filter_office:
                qs = qs.filter(Office=filter_office)
            return qs

        def exp_qs(q):
            qs = Expense.objects.filter(q)
            if filter_office:
                qs = qs.filter(office__iexact=filter_office.name)
            return qs

        def bank_charge_qs(q):
            qs = BankCharge.objects.filter(q)
            if filter_office:
                qs = qs.filter(office__iexact=filter_office.name)
            return qs

        def bank_cash_txn_qs(q):
            qs = BankCashTransaction.objects.filter(q)
            if filter_office:
                qs = qs.filter(office_from=filter_office)
            return qs

        def transfer_in_qs(q):
            qs = OfficeTransaction.objects.filter(q)
            if filter_office:
                qs = qs.filter(office_to=filter_office)
            return qs

        def transfer_out_qs(q):
            qs = OfficeTransaction.objects.filter(q)
            if filter_office:
                qs = qs.filter(office_from=filter_office)
            return qs

        accounts = []
        period_q = Q(created_at__gte=start_dt, created_at__lte=end_dt)
        before_q = Q(created_at__lt=before_dt)

        # ── 1. CASH (1010) ──────────────────────────────────────────────
        open_cash_in = (
            (rep_qs(before_q).filter(transaction_method__iexact='cash').aggregate(t=Sum('repayment_amount'))['t'] or Decimal('0')) +
            (nyo_qs(before_q).filter(deposit_method__iexact='cash').aggregate(t=Sum('amount'))['t'] or Decimal('0')) +
            (bank_cash_txn_qs(before_q).filter(source__iexact='bank', destination__iexact='cash').aggregate(t=Sum('amount'))['t'] or Decimal('0'))
        )
        open_cash_out = (
            (exp_qs(before_q).filter(payment_method__iexact='cash').aggregate(t=Sum('amount'))['t'] or Decimal('0')) +
            (loan_qs(before_q).filter(transaction_method__iexact='cash').aggregate(t=Sum('loan_amount'))['t'] or Decimal('0')) +
            (bank_charge_qs(before_q).filter(payment_method__iexact='cash').aggregate(t=Sum('amount'))['t'] or Decimal('0')) +
            (bank_cash_txn_qs(before_q).filter(source__iexact='cash', destination__iexact='bank').aggregate(t=Sum('amount'))['t'] or Decimal('0'))
        )
        opening_cash = open_cash_in - open_cash_out

        cash_debit = (
            (rep_qs(period_q).filter(transaction_method__iexact='cash').aggregate(t=Sum('repayment_amount'))['t'] or Decimal('0')) +
            (nyo_qs(period_q).filter(deposit_method__iexact='cash').aggregate(t=Sum('amount'))['t'] or Decimal('0')) +
            (bank_cash_txn_qs(period_q).filter(source__iexact='bank', destination__iexact='cash').aggregate(t=Sum('amount'))['t'] or Decimal('0'))
        )
        cash_credit = (
            (exp_qs(period_q).filter(payment_method__iexact='cash').aggregate(t=Sum('amount'))['t'] or Decimal('0')) +
            (loan_qs(period_q).filter(transaction_method__iexact='cash').aggregate(t=Sum('loan_amount'))['t'] or Decimal('0')) +
            (bank_charge_qs(period_q).filter(payment_method__iexact='cash').aggregate(t=Sum('amount'))['t'] or Decimal('0')) +
            (bank_cash_txn_qs(period_q).filter(source__iexact='cash', destination__iexact='bank').aggregate(t=Sum('amount'))['t'] or Decimal('0'))
        )
        closing_cash = opening_cash + cash_debit - cash_credit

        accounts.append({'code': '1010', 'name': 'Cash', 'type': 'Asset',
            'opening': _d(opening_cash), 'debit': _d(cash_debit),
            'credit': _d(cash_credit), 'closing': _d(closing_cash),
            'is_credit_balance': closing_cash < 0, 'normal_balance': 'debit'})

        # ── 2. BANK (1050) ──────────────────────────────────────────────
        open_bank_in = (
            (rep_qs(before_q).filter(transaction_method__iexact='bank').aggregate(t=Sum('repayment_amount'))['t'] or Decimal('0')) +
            (nyo_qs(before_q).filter(deposit_method__iexact='bank').aggregate(t=Sum('amount'))['t'] or Decimal('0')) +
            (transfer_in_qs(before_q).aggregate(t=Sum('amount'))['t'] or Decimal('0')) +
            (bank_cash_txn_qs(before_q).filter(source__iexact='cash', destination__iexact='bank').aggregate(t=Sum('amount'))['t'] or Decimal('0'))
        )
        open_bank_out = (
            (exp_qs(before_q).filter(payment_method__iexact='bank').aggregate(t=Sum('amount'))['t'] or Decimal('0')) +
            (loan_qs(before_q).filter(transaction_method__iexact='bank').aggregate(t=Sum('loan_amount'))['t'] or Decimal('0')) +
            (transfer_out_qs(before_q).aggregate(t=Sum('amount'))['t'] or Decimal('0')) +
            (bank_charge_qs(before_q).filter(payment_method__iexact='bank').aggregate(t=Sum('amount'))['t'] or Decimal('0')) +
            (bank_cash_txn_qs(before_q).filter(source__iexact='bank', destination__iexact='cash').aggregate(t=Sum('amount'))['t'] or Decimal('0'))
        )
        opening_bank = open_bank_in - open_bank_out

        bank_debit = (
            (rep_qs(period_q).filter(transaction_method__iexact='bank').aggregate(t=Sum('repayment_amount'))['t'] or Decimal('0')) +
            (nyo_qs(period_q).filter(deposit_method__iexact='bank').aggregate(t=Sum('amount'))['t'] or Decimal('0')) +
            (transfer_in_qs(period_q).aggregate(t=Sum('amount'))['t'] or Decimal('0')) +
            (bank_cash_txn_qs(period_q).filter(source__iexact='cash', destination__iexact='bank').aggregate(t=Sum('amount'))['t'] or Decimal('0'))
        )
        bank_credit = (
            (exp_qs(period_q).filter(payment_method__iexact='bank').aggregate(t=Sum('amount'))['t'] or Decimal('0')) +
            (loan_qs(period_q).filter(transaction_method__iexact='bank').aggregate(t=Sum('loan_amount'))['t'] or Decimal('0')) +
            (transfer_out_qs(period_q).aggregate(t=Sum('amount'))['t'] or Decimal('0')) +
            (bank_charge_qs(period_q).filter(payment_method__iexact='bank').aggregate(t=Sum('amount'))['t'] or Decimal('0')) +
            (bank_cash_txn_qs(period_q).filter(source__iexact='bank', destination__iexact='cash').aggregate(t=Sum('amount'))['t'] or Decimal('0'))
        )
        closing_bank = opening_bank + bank_debit - bank_credit

        accounts.append({'code': '1050', 'name': 'Bank', 'type': 'Asset',
            'opening': _d(opening_bank), 'debit': _d(bank_debit),
            'credit': _d(bank_credit), 'closing': _d(closing_bank),
            'is_credit_balance': closing_bank < 0, 'normal_balance': 'debit'})

        # ── 3. RECEIVABLES (1100) ───────────────────────────────────────
        open_recv_qs = LoanApplication.objects.filter(created_at__lt=before_dt)
        if filter_office:
            open_recv_qs = open_recv_qs.filter(office__iexact=filter_office.name)
        open_loans_total = open_recv_qs.aggregate(t=Sum('total_repayment_amount'))['t'] or Decimal('0')
        open_rep_total = rep_qs(before_q).aggregate(t=Sum('repayment_amount'))['t'] or Decimal('0')
        opening_recv = open_loans_total - open_rep_total

        recv_debit = loan_qs(period_q).aggregate(t=Sum('total_repayment_amount'))['t'] or Decimal('0')
        recv_credit = rep_qs(period_q).aggregate(t=Sum('repayment_amount'))['t'] or Decimal('0')
        closing_recv = opening_recv + recv_debit - recv_credit

        accounts.append({'code': '1100', 'name': 'Receivables', 'type': 'Asset',
            'opening': _d(opening_recv), 'debit': _d(recv_debit),
            'credit': _d(recv_credit), 'closing': _d(closing_recv),
            'is_credit_balance': closing_recv < 0, 'normal_balance': 'debit'})

        # ── 4. OPENING BALANCE EQUITY (3000) ────────────────────────────
        open_equity = nyo_qs(before_q).aggregate(t=Sum('amount'))['t'] or Decimal('0')
        equity_credit = nyo_qs(period_q).aggregate(t=Sum('amount'))['t'] or Decimal('0')
        equity_debit = Decimal('0')
        closing_equity = open_equity + equity_credit - equity_debit

        accounts.append({'code': '3000', 'name': 'Opening Balance Equity', 'type': 'Equity',
            'opening': _d(open_equity), 'debit': _d(equity_debit),
            'credit': _d(equity_credit), 'closing': _d(closing_equity),
            'is_credit_balance': True, 'normal_balance': 'credit'})

        # ── 5. RETAINED EARNINGS (3900) — balancing plug ────────────────
        # Opening Retained Earnings = Opening Assets - Opening Equity
        # (Expenses always open at 0 because P&L closes at year-end)
        opening_retained = (opening_cash + opening_bank + opening_recv) - open_equity

        # KEY FIX (mirrors new web view): current-period expenses appear as
        # SEPARATE debit lines (5000, 5100). If we let them also reduce
        # Retained Earnings here they get counted twice on the debit side.
        # Add them back so Retained Earnings holds only historical accumulated
        # profit + current period income, with expenses offset by the separate lines.
        current_period_expenses = (
            (exp_qs(period_q).aggregate(t=Sum('amount'))['t'] or Decimal('0')) +
            (bank_charge_qs(period_q).aggregate(t=Sum('amount'))['t'] or Decimal('0'))
        )

        closing_retained = (
            (closing_cash + closing_bank + closing_recv)
            - closing_equity
            + current_period_expenses
        )

        re_movement = closing_retained - opening_retained
        if re_movement >= 0:
            re_debit = Decimal('0'); re_credit = re_movement
        else:
            re_debit = abs(re_movement); re_credit = Decimal('0')

        accounts.append({'code': '3900', 'name': 'Retained Earnings', 'type': 'Equity',
            'opening': _d(opening_retained), 'debit': _d(re_debit),
            'credit': _d(re_credit), 'closing': _d(closing_retained),
            'is_credit_balance': True, 'normal_balance': 'credit'})

        # ── 6. EXPENSES (5000) ───────────────────────────────────────────
        exp_debit = exp_qs(period_q).aggregate(t=Sum('amount'))['t'] or Decimal('0')
        accounts.append({'code': '5000', 'name': 'Expenses', 'type': 'Expense',
            'opening': 0.0, 'debit': _d(exp_debit), 'credit': 0.0, 'closing': _d(exp_debit),
            'is_credit_balance': False, 'normal_balance': 'debit'})

        # ── 7. BANK CHARGES (5100) ───────────────────────────────────────
        bc_debit = bank_charge_qs(period_q).aggregate(t=Sum('amount'))['t'] or Decimal('0')
        accounts.append({'code': '5100', 'name': 'Bank Charges', 'type': 'Expense',
            'opening': 0.0, 'debit': _d(bc_debit), 'credit': 0.0, 'closing': _d(bc_debit),
            'is_credit_balance': False, 'normal_balance': 'debit'})

        # ── TOTALS ───────────────────────────────────────────────────────
        total_debit  = sum(Decimal(str(a['debit']))  for a in accounts)
        total_credit = sum(Decimal(str(a['credit'])) for a in accounts)

        total_debit_closing  = Decimal('0')
        total_credit_closing = Decimal('0')
        for a in accounts:
            closing = Decimal(str(a['closing']))
            if a['normal_balance'] == 'debit':
                if closing >= 0: total_debit_closing += closing
                else: total_credit_closing += abs(closing)
            else:
                if closing >= 0: total_credit_closing += closing
                else: total_debit_closing += abs(closing)

        total_opening_debit  = Decimal('0')
        total_opening_credit = Decimal('0')
        for a in accounts:
            opening = Decimal(str(a['opening']))
            if a['normal_balance'] == 'debit':
                if opening >= 0: total_opening_debit += opening
                else: total_opening_credit += abs(opening)
            else:
                if opening >= 0: total_opening_credit += opening
                else: total_opening_debit += abs(opening)

        is_balanced = abs(total_debit_closing - total_credit_closing) < Decimal('0.01')

        return Response({
            'branch_name':          branch_name,
            'start_date':           str(start_date),
            'end_date':             str(end_date),
            'start_date_display':   start_date.strftime('%d %b %Y'),
            'end_date_display':     end_date.strftime('%d %b %Y'),
            'generated_at':         str(timezone.now()),
            'accounts':             accounts,
            'total_debit':          _d(total_debit),
            'total_credit':         _d(total_credit),
            'total_debit_closing':  _d(total_debit_closing),
            'total_credit_closing': _d(total_credit_closing),
            'total_opening_debit':  _d(total_opening_debit),
            'total_opening_credit': _d(total_opening_credit),
            'is_balanced':          is_balanced,
        })
    except Exception as _e:
        import traceback
        return Response({'detail': f'Server error: {str(_e)}', 'trace': traceback.format_exc()}, status=500)



@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_dashboard(request):
    # GET /api/dashboard/?date=YYYY-MM-DD
    # Mirrors the web index() view exactly, including the critical
    # is_hq_allocated rule:
    #   superuser OR null office_allocation OR office_allocation.name == 'HQ'
    #     -> see ALL branches regardless of X-Office-Id header
    #   otherwise -> scoped to filter_office / user_primary_office
    try:
        import datetime as _dt
        from django.utils import timezone as tz

        # 1. Resolve target date
        date_param = request.GET.get('date', '').strip()
        if date_param:
            try:
                target_date = _dt.datetime.strptime(date_param, '%Y-%m-%d').date()
            except ValueError:
                return Response({'error': 'Invalid date. Use YYYY-MM-DD.'}, status=400)
        else:
            target_date = date.today()

        month_start = target_date.replace(day=1)

        # 2. Timezone-aware range for DateTimeFields (EAT = UTC+3)
        start_dt = tz.make_aware(_dt.datetime.combine(target_date, _dt.time.min))
        end_dt   = tz.make_aware(_dt.datetime.combine(target_date, _dt.time.max))

        # 3. Office scope
        filter_office = get_filter_office(request)
        selected      = get_selected_office_api(request)

        # ── Determine user's primary office allocation safely (mirrors web view) ──
        try:
            user_primary_office = request.user.office_allocation
        except Exception:
            user_primary_office = None

        # HQ rule: superuser OR null allocation OR explicitly HQ -> see all branches
        # This takes priority over whatever branch is currently selected on the
        # mobile app (X-Office-Id header) — an HQ-allocated user always sees the
        # all-branches summary on the dashboard, regardless of which branch they
        # have open for transactional screens.
        is_hq_allocated = bool(
            getattr(request.user, 'is_superuser', False) or
            not user_primary_office or
            (
                user_primary_office and
                hasattr(user_primary_office, 'name') and
                user_primary_office.name.strip().upper() == 'HQ'
            )
        )

        is_hq_view = is_hq_allocated or (filter_office is None)

        loans_qs      = LoanApplication.objects.all()
        repayments_qs = LoanRepayment.objects.all()
        clients_qs    = Client.objects.all()
        expenses_qs   = Expense.objects.all()

        # Only scope global totals to filter_office when the user is NOT
        # HQ-allocated (mirrors web view: global stats always scoped to
        # filter_office, but filter_office itself is None for HQ users
        # unless they explicitly switch to a branch — same as web)
        if filter_office and not is_hq_allocated:
            loans_qs      = loans_qs.filter(office=filter_office.name)
            repayments_qs = repayments_qs.filter(loan_application__office=filter_office.name)
            clients_qs    = clients_qs.filter(registered_office=filter_office)
            expenses_qs   = expenses_qs.filter(office=filter_office.name)
        elif filter_office and is_hq_allocated:
            # HQ user has explicitly drilled into one branch elsewhere in the
            # app; for the dashboard summary we still respect that explicit
            # selection only if they are NOT asking for the all-branches view.
            # Since the mobile sends no office_id at all for HQ-view dashboard
            # calls, filter_office will normally be None here anyway.
            loans_qs      = loans_qs.filter(office=filter_office.name)
            repayments_qs = repayments_qs.filter(loan_application__office=filter_office.name)
            clients_qs    = clients_qs.filter(registered_office=filter_office)
            expenses_qs   = expenses_qs.filter(office=filter_office.name)

        # 4. Overall totals
        total_clients      = clients_qs.count()
        total_active_loans = loans_qs.filter(repayment_amount_remaining__gt=0).count()
        loan_agg = loans_qs.aggregate(
            total_disbursed=Sum('loan_amount'),
            total_due=Sum('repayment_amount_remaining'),
        )
        total_due_loan    = loan_agg['total_due'] or Decimal('0')
        total_repayments  = repayments_qs.aggregate(total=Sum('repayment_amount'))['total'] or Decimal('0')

        denom = total_repayments + total_due_loan
        repayment_rate = (
            (total_repayments / denom) * Decimal('100')
        ) if denom > 0 else Decimal('0')
        repayment_rate = repayment_rate.quantize(Decimal('0.01'))

        new_clients = clients_qs.filter(created_at__range=(
            tz.make_aware(_dt.datetime.combine(month_start, _dt.time.min)), end_dt
        )).count() if hasattr(Client, 'created_at') else 0

        loans_month = loans_qs.filter(created_at__range=(
            tz.make_aware(_dt.datetime.combine(month_start, _dt.time.min)), end_dt
        )).count()

        exp_month = expenses_qs.filter(
            Q(transaction_date__range=(month_start, target_date)) |
            Q(transaction_date__isnull=True, expense_date__range=(month_start, target_date))
        ).aggregate(total=Sum('amount'))

        # 5. Target offices for per-office breakdown — mirrors web view exactly:
        #    HQ-allocated user -> ALL branches (zero-filled)
        #    Otherwise -> just filter_office, or user_primary_office, or all as last resort
        if is_hq_allocated:
            target_offices = list(Office.objects.exclude(name__iexact='HQ').order_by('name'))
        elif filter_office:
            target_offices = list(Office.objects.filter(pk=filter_office.pk).exclude(name__iexact='HQ'))
        elif user_primary_office:
            target_offices = list(Office.objects.filter(pk=user_primary_office.pk).exclude(name__iexact='HQ'))
        else:
            target_offices = list(Office.objects.exclude(name__iexact='HQ').order_by('name'))

        target_names = [o.name for o in target_offices]

        # 6. Per-office breakdown — exact field/date-type rules from web view:
        #    - Loans & Repayments: created_at (DateTimeField) -> aware range
        #    - Expenses: expense_date (DateField) with transaction_date fallback
        #    - Transactions: transaction_date (DateField) -> plain date compare
        loans_map = {
            row['office']: {'amount': _d(row['total']), 'count': row['cnt']}
            for row in LoanApplication.objects
                .filter(office__in=target_names, created_at__range=(start_dt, end_dt))
                .values('office')
                .annotate(total=Sum('loan_amount'), cnt=Count('id'))
        }

        repayments_map = {
            row['loan_application__office']: {'amount': _d(row['total']), 'count': row['cnt']}
            for row in LoanRepayment.objects
                .filter(loan_application__office__in=target_names, created_at__range=(start_dt, end_dt))
                .values('loan_application__office')
                .annotate(total=Sum('repayment_amount'), cnt=Count('id'))
        }

        expenses_map = {
            row['office']: {'amount': _d(row['total']), 'count': row['cnt']}
            for row in Expense.objects
                .filter(office__in=target_names, expense_date=target_date)
                .values('office')
                .annotate(total=Sum('amount'), cnt=Count('id'))
        }

        # Transactions: combine office_from + office_to per office (matches web view)
        # FIXED: dashboard was reading OfficeTransaction (branch-to-branch
        # internal transfers) but the detail screen reads HQTransaction
        # (the actual bank-transfer-expenses report model). Switched to
        # HQTransaction with created_at range so dashboard totals and the
        # tapped detail report always agree on the same underlying rows.
        tx_to_map = {
            row['to_branch__name']: {'amount': _d(row['total']), 'count': row['cnt']}
            for row in HQTransaction.objects
                .filter(to_branch__name__in=target_names, created_at__range=(start_dt, end_dt))
                .exclude(from_branch=F('to_branch'))
                .values('to_branch__name')
                .annotate(total=Sum('amount'), cnt=Count('id'))
        }
        tx_from_map = {
            row['from_branch__name']: {'amount': _d(row['total']), 'count': row['cnt']}
            for row in HQTransaction.objects
                .filter(from_branch__name__in=target_names, created_at__range=(start_dt, end_dt))
                .exclude(from_branch=F('to_branch'))
                .values('from_branch__name')
                .annotate(total=Sum('amount'), cnt=Count('id'))
        }

        zero = {'amount': Decimal('0'), 'count': 0}
        loans_today      = []
        repayments_today = []
        expenses_today   = []
        transactions_today = []

        for name in target_names:
            l = loans_map.get(name, zero)
            loans_today.append({'office': name, 'amount': _d(l['amount']), 'count': l['count']})

            r = repayments_map.get(name, zero)
            repayments_today.append({'office': name, 'amount': _d(r['amount']), 'count': r['count']})

            e = expenses_map.get(name, zero)
            expenses_today.append({'office': name, 'amount': _d(e['amount']), 'count': e['count']})

            to_ = tx_to_map.get(name, zero)
            fr_ = tx_from_map.get(name, zero)
            transactions_today.append({
                'office': name,
                'amount': _d((to_['amount'] if isinstance(to_['amount'], Decimal) else Decimal(str(to_['amount']))) +
                             (fr_['amount'] if isinstance(fr_['amount'], Decimal) else Decimal(str(fr_['amount'])))),
                'count':  to_['count'] + fr_['count'],
            })

        # 7. Recent activity feed (timezone-aware)
        recent = []
        for l in loans_qs.select_related('client').filter(
            created_at__range=(start_dt, end_dt)
        ).order_by('-created_at')[:10]:
            try:
                cname = f"{l.client.firstname} {l.client.lastname}".strip()
            except Exception:
                cname = '—'
            recent.append({
                'type': 'loan', 'id': l.id, 'office': l.office or '',
                'client_name': cname, 'amount': _d(l.loan_amount),
                'created_at': str(l.created_at),
            })

        branch_name = (filter_office.name.upper() if (filter_office and not is_hq_allocated)
                       else 'ALL BRANCHES' if is_hq_allocated
                       else (selected.name.upper() if selected else 'ALL BRANCHES'))

        return Response({
            'date':                   str(target_date),
            'branch_name':            branch_name,
            'is_hq_view':             is_hq_allocated,
            'total_clients':          total_clients,
            'total_active_loans':     total_active_loans,
            'total_due_loan':         _d(total_due_loan),
            'total_repayments':       _d(total_repayments),
            'repayment_rate':         float(repayment_rate),
            'new_clients_this_month': new_clients,
            'loans_this_month':       loans_month,
            'expenses_this_month':    _d(exp_month.get('total')),
            'loans_today':               loans_today,
            'repayments_today':         repayments_today,
            'expenses_today':           expenses_today,
            'transactions_today':       transactions_today,
            'loans_total_today':        _d(sum(Decimal(str(x['amount'])) for x in loans_today)),
            'repayments_total_today':   _d(sum(Decimal(str(x['amount'])) for x in repayments_today)),
            'expenses_total_today':     _d(sum(Decimal(str(x['amount'])) for x in expenses_today)),
            'transactions_total_today':_d(sum(Decimal(str(x['amount'])) for x in transactions_today)),
            'recent_activity':       recent,
        })
    except Exception as _e:
        import traceback
        return Response({'detail': str(_e), 'trace': traceback.format_exc()}, status=500)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def client_loans(request, client_id):
    """GET /api/clients/<client_id>/loans/"""
    loans = LoanApplication.objects.filter(
        client_id=client_id
    ).prefetch_related('repayments').order_by('-created_at')
    return Response(LoanApplicationSerializer(loans, many=True).data)



@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_client_active_loans(request, client_id):
    # GET /api/clients/<client_id>/active-loans/
    # Mirrors process_loan_partb() web view get_active_loan() exactly:
    #   status__in=['Approved','Pending'] AND repayment_amount_remaining > 0
    #   If balance is zero/missing -> treated as no active loan (same as web)
    # Rules enforced by mobile:
    #   - existing_maendeleo -> selecting Maendeleo forces top-up
    #   - existing_dharura   -> selecting Dharura is blocked entirely

    def get_active(loan_type):
        # Exact copy of web's get_active_loan() helper
        loan = (
            LoanApplication.objects
            .filter(
                client_id=client_id,
                status__in=['Approved', 'Pending'],
                loan_type=loan_type,
            )
            .order_by('-created_at')
            .first()
        )
        # Treat as "no active loan" if balance is zero or missing (web rule)
        if loan and (loan.repayment_amount_remaining or 0) > 0:
            return {
                'id':          loan.id,
                'outstanding': _d(loan.repayment_amount_remaining or 0),
                'loan_amount': _d(loan.loan_amount or 0),
                'interest':    _d(loan.interest_rate or 0),
                'period':      loan.payment_period_months or 0,
                'loan_type':   loan.loan_type or '',
            }
        return None

    return Response({
        'existing_maendeleo': get_active('Maendeleo'),
        'existing_dharura':   get_active('Dharura'),
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_loan_topup(request, loan_id):
    # POST /api/loans/<loan_id>/topup/
    # Mirrors loan_topup() web view exactly:
    #   - atomic transaction
    #   - validates topup > outstanding
    #   - net_disbursement = topup - outstanding
    #   - checks cash/bank balance using BranchBalance
    #   - creates new LoanApplication
    #   - creates LoanTopup record
    #   - creates LoanRepayment on original to clear it
    #   - closes original loan (status=Closed, remaining=0)
    import datetime as _dt
    from decimal import Decimal
    from django.db import transaction as db_transaction

    try:
        original_loan = LoanApplication.objects.get(pk=loan_id)
    except LoanApplication.DoesNotExist:
        return Response({'detail': 'Loan not found.'}, status=404)

    try:
        with db_transaction.atomic():
            topup_amount  = Decimal(str(request.data.get('topup_amount', '0')).replace(',', '').strip())
            ir            = Decimal(str(request.data.get('interest_rate', original_loan.interest_rate or 0)))
            tx_method     = request.data.get('transaction_method', original_loan.transaction_method or 'cash')
            tm            = int(request.data.get('term_months', original_loan.payment_period_months or 1))
            app_date_str  = request.data.get('application_date', '')

            # Parse application date — accept YYYY-MM-DD or DD/MM/YYYY
            app_date = None
            for fmt in ('%Y-%m-%d', '%d/%m/%Y'):
                try:
                    app_date = _dt.datetime.strptime(app_date_str, fmt).date()
                    break
                except Exception:
                    pass
            if not app_date:
                app_date = _dt.date.today()

            # topup_date = application_date (matches web: topup_date = today)
            topup_date    = app_date
            payment_month = topup_date

            # ── Branch office ─────────────────────────────────────────────
            branch_office = get_selected_office_api(request)
            if not branch_office:
                return Response({'detail': 'No branch office found for your account.'}, status=400)

            # ── Re-fetch outstanding ──────────────────────────────────────
            outstanding = original_loan.repayment_amount_remaining or Decimal('0')

            # ── Validate topup > outstanding ──────────────────────────────
            if topup_amount <= outstanding:
                return Response({
                    'detail': f'Top-up amount ({topup_amount:,.0f}) must exceed outstanding balance ({outstanding:,.0f})'
                }, status=400)

            net_disbursement = topup_amount - outstanding
            new_loan_amount  = topup_amount

            # ── Balance check using BranchBalance snapshot ────────────────
            latest_bal = BranchBalance.objects.filter(branch=branch_office).order_by('-last_updated').first()
            cash_in_office = Decimal(str(latest_bal.office_balance)) if latest_bal else Decimal('0')
            cash_in_bank   = Decimal(str(latest_bal.bank_balance))   if latest_bal else Decimal('0')

            if tx_method == 'cash':
                if cash_in_office < net_disbursement:
                    return Response({
                        'detail': f'Insufficient cash balance. Available: TZS {cash_in_office:,.0f}/='
                    }, status=400)
            else:
                if cash_in_bank < net_disbursement:
                    return Response({
                        'detail': f'Insufficient bank balance. Available: TZS {cash_in_bank:,.0f}/='
                    }, status=400)

            # ── Create new loan for the top-up ────────────────────────────
            new_loan = LoanApplication.objects.create(
                client=original_loan.client,
                loan_amount=new_loan_amount,
                loan_purpose=(
                    f"Topup of loan #{original_loan.id} - "
                    f"Original total: {topup_amount:,.0f}/=, "
                    f"Outstanding: {outstanding:,.0f}/=, "
                    f"Net: {net_disbursement:,.0f}/= - "
                    f"{original_loan.loan_purpose or ''}"
                ),
                loan_type=original_loan.loan_type,
                interest_rate=ir,
                payment_period_months=tm,
                application_date=topup_date,
                first_repayment_date=app_date,
                status='Approved',
                processed_by=request.user,
                office=branch_office.name,
                transaction_method=tx_method,
            )

            # ── Create LoanTopup record ───────────────────────────────────
            LoanTopup.objects.create(
                loan_application=original_loan,
                topup_amount=topup_amount,
                old_balance_cleared=outstanding,
                interest_rate=ir,
                transaction_method=tx_method,
                processed_by=request.user,
                topup_date=topup_date,
                payment_month=payment_month,
            )

            # ── Final clearance repayment on original loan ────────────────
            if outstanding > Decimal('0.00'):
                LoanRepayment.objects.create(
                    loan_application=original_loan,
                    repayment_amount=outstanding,
                    repayment_date=topup_date,
                    transaction_method=tx_method,
                    processed_by=request.user,
                )

            # ── Close original loan ───────────────────────────────────────
            original_loan.status = 'Closed'
            original_loan.repayment_amount_remaining = Decimal('0.00')
            original_loan.save()

            return Response({
                'id':              new_loan.id,
                'loan_amount':     _d(new_loan.loan_amount),
                'net_disbursement':_d(net_disbursement),
                'outstanding_cleared': _d(outstanding),
                'message': (
                    f'Top-up completed. New Loan #{new_loan.id}: TZS {new_loan_amount:,.0f}/=. '
                    f'Client receives: TZS {net_disbursement:,.0f}/=. '
                    f'Original Loan #{original_loan.id} closed.'
                ),
            }, status=201)

    except Exception as e:
        return Response({'detail': f'Error processing top-up: {str(e)}'}, status=500)



@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def loan_repayments(request, loan_id):
    """
    GET  /api/loans/<loan_id>/repayments/ — list all repayments
    POST /api/loans/<loan_id>/repayments/ — add a repayment
    """
    try:
        loan = LoanApplication.objects.get(pk=loan_id)
    except LoanApplication.DoesNotExist:
        return Response({'detail': 'Mkopo haujapatikana.'}, status=404)

    if request.method == 'GET':
        reps = LoanRepayment.objects.filter(loan_application=loan).order_by('-created_at')
        return Response(LoanRepaymentSerializer(reps, many=True).data)

    # POST — create repayment
    amount = request.data.get('amount') or request.data.get('repayment_amount')
    if not amount:
        return Response({'detail': 'Kiasi kinahitajika.'}, status=400)

    try:
        amount = Decimal(str(amount))
    except Exception:
        return Response({'detail': 'Kiasi si sahihi.'}, status=400)

    payment_date   = request.data.get('repayment_date') or request.data.get('payment_date') or date.today()
    payment_month  = request.data.get('payment_month') or payment_date
    payment_method = request.data.get('payment_method') or request.data.get('transaction_method') or 'cash'

    rep = LoanRepayment.objects.create(
        loan_application=loan,
        repayment_amount=amount,
        repayment_date=payment_date,
        payment_month=payment_month,
        transaction_method=payment_method,
        processed_by=request.user,
    )

    # Update remaining balance on the loan
    new_remaining = max((loan.repayment_amount_remaining or Decimal('0')) - amount, Decimal('0'))
    loan.repayment_amount_remaining = new_remaining
    loan.save(update_fields=['repayment_amount_remaining', 'updated_at'])

    return Response(LoanRepaymentSerializer(rep).data, status=201)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_loan_repayment_schedule(request, loan_id):
    # GET /api/loans/<loan_id>/schedule/
    # Mirrors loan_repayment_schedule() web view: ceil_1000, last row absorbs remainder,
    # paid_by_month + topup pool applied top-down, extra rows for out-of-schedule payments.
    from decimal import ROUND_CEILING as RC

    try:
        loan = LoanApplication.objects.get(id=loan_id)
    except LoanApplication.DoesNotExist:
        return Response({'error': 'Loan not found.'}, status=404)

    client     = loan.client
    repayments = list(loan.repayments.all().order_by('repayment_date', 'id'))
    topups     = list(loan.topups.all()) if hasattr(loan, 'topups') else []

    paid_by_month = {}
    for r in repayments:
        if r.payment_month:
            k = (r.payment_month.year, r.payment_month.month)
            paid_by_month[k] = paid_by_month.get(k, Decimal('0')) + (r.repayment_amount or Decimal('0'))

    topup_by_month = {}
    for t in topups:
        pm = getattr(t, 'payment_month', None)
        if pm:
            k = (pm.year, pm.month)
            topup_by_month[k] = topup_by_month.get(k, Decimal('0')) + (t.old_balance_cleared or Decimal('0'))

    total_topup_paid = sum(topup_by_month.values(), Decimal('0'))

    def c1000(val):
        return (val / Decimal('1000')).to_integral_value(rounding=RC) * Decimal('1000')

    periods      = loan.payment_period_months or 1
    loan_amount  = loan.loan_amount or Decimal('0')
    total_int    = loan.total_interest_amount or Decimal('0')
    total_return = loan_amount + total_int

    std_monthly   = c1000(total_return / periods)
    std_principal = c1000(loan_amount  / periods)
    std_interest  = std_monthly - std_principal
    last_principal = loan_amount - std_principal * (periods - 1)
    last_interest  = total_int   - std_interest  * (periods - 1)
    last_monthly   = last_principal + last_interest

    MN = {1:'Jan',2:'Feb',3:'Mar',4:'Apr',5:'May',6:'Jun',
          7:'Jul',8:'Aug',9:'Sep',10:'Oct',11:'Nov',12:'Dec'}

    start = loan.first_repayment_date or loan.application_date
    sched_months = set()
    sched_raw    = []
    balance      = total_return
    tp = ti = tt = Decimal('0')

    for i in range(periods):
        yr = start.year  + (start.month - 1 + i) // 12
        mo = (start.month - 1 + i) % 12 + 1
        sched_months.add((yr, mo))
        is_last = (i == periods - 1)
        p = last_principal if is_last else std_principal
        n = last_interest  if is_last else std_interest
        t = last_monthly   if is_last else std_monthly
        balance -= t
        if abs(balance) < Decimal('0.50'):
            balance = Decimal('0')
        paid = paid_by_month.get((yr, mo), Decimal('0'))
        sched_raw.append({'yr':yr,'mo':mo,'label':f"{MN[mo]}/{yr}",
                          'p':p,'n':n,'t':t,'paid':paid,'bal':balance})
        tp += p; ti += n; tt += t

    pool = sum(r['paid'] for r in sched_raw) + total_topup_paid
    total_paid_sum = Decimal('0')
    rows = []

    for row in sched_raw:
        t = row['t']
        if pool >= t:   pool -= t; out = Decimal('0')
        elif pool > 0:  out = t - pool; pool = Decimal('0')
        else:           out = t
        total_paid_sum += row['paid']
        rows.append({'month_label': row['label'],
            'principal':   _d(row['p']), 'interest': _d(row['n']),
            'penalty':     0,            'total':    _d(t),
            'paid':        _d(row['paid']), 'outstanding': _d(out),
            'loan_balance':_d(row['bal']), 'extra': False, 'is_topup': False})

    final_out = sum(Decimal(str(r['outstanding'])) for r in rows)

    for (yr, mo) in sorted(k for k in paid_by_month if k not in sched_months):
        paid = paid_by_month[(yr, mo)]
        total_paid_sum += paid
        rows.append({'month_label':f"{MN[mo]}/{yr}", 'principal':0,'interest':0,
            'penalty':0,'total':0,'paid':_d(paid),'outstanding':0,
            'loan_balance':0,'extra':True,'is_topup':False})

    for (yr, mo) in sorted(topup_by_month.keys()):
        paid = topup_by_month[(yr, mo)]
        lbl  = f"{MN[mo]}/{yr}" + (" (Topup)" if (yr,mo) in sched_months else "")
        total_paid_sum += paid
        rows.append({'month_label':lbl, 'principal':0,'interest':0,
            'penalty':0,'total':0,'paid':_d(paid),'outstanding':0,
            'loan_balance':0,'extra':True,'is_topup':True})

    cname = ' '.join(filter(None,[
        getattr(client,'firstname',''), getattr(client,'middlename',''),
        getattr(client,'lastname','')]))

    return Response({
        'loan_id':         loan.id,
        'client_name':     cname,
        'branch':          (loan.office or '-').upper(),
        'nida':            getattr(client,'checkno','') or '',
        'work_station':    getattr(client,'mtaa','') or '',
        'loan_amount':     _d(loan.loan_amount or 0),
        'total_interest':  _d(total_int),
        'total_repayable': _d(total_return),
        'schedule':        rows,
        'totals': {
            'principal':   _d(tp), 'interest': _d(ti),
            'penalty':     0,      'total':    _d(tt),
            'paid':        _d(total_paid_sum), 'outstanding': _d(final_out),
        }
    })



# =============================================================================
#  OFFICES
# =============================================================================


class ClientListAPI(generics.ListCreateAPIView):
    """
    GET  /api/clients/?search=&page=&page_size=  — list clients (scoped to selected office)
    POST /api/clients/                            — register new client
    """
    serializer_class   = ClientSerializer
    permission_classes = [IsAuthenticated]
    pagination_class   = StandardPagination

    def get_queryset(self):
        qs = Client.objects.all().order_by('firstname', 'lastname')
        filter_office = get_filter_office(self.request)
        if filter_office:
            qs = qs.filter(registered_office=filter_office)

        search = self.request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(
                Q(firstname__icontains=search) |
                Q(middlename__icontains=search) |
                Q(lastname__icontains=search) |
                Q(phonenumber__icontains=search) |
                Q(checkno__icontains=search) |
                Q(employmentcardno__icontains=search)
            )
        return qs

    def perform_create(self, serializer):
        office = get_selected_office_api(self.request)
        serializer.save(registered_office=office)


class ClientDetailAPI(generics.RetrieveUpdateAPIView):
    """
    GET   /api/clients/<pk>/  — retrieve single client
    PATCH /api/clients/<pk>/  — update client fields
    """
    serializer_class   = ClientSerializer
    permission_classes = [IsAuthenticated]
    queryset            = Client.objects.select_related('registered_office').all()


class LoanListAPI(generics.ListCreateAPIView):
    """
    GET  /api/loans/?status=&search=&page=&page_size=  — list loans (scoped to selected office)
    POST /api/loans/                                     — create new loan application
    """
    serializer_class   = LoanApplicationSerializer
    permission_classes = [IsAuthenticated]
    pagination_class   = StandardPagination

    def get_queryset(self):
        qs = LoanApplication.objects.select_related('client').all().order_by('-created_at')
        filter_office = get_filter_office(self.request)
        if filter_office:
            qs = qs.filter(office=filter_office.name)

        status_f = self.request.query_params.get('status', '').strip()
        if status_f:
            qs = qs.filter(status=status_f)

        search = self.request.query_params.get('search', '').strip()
        if search:
            qs = qs.filter(
                Q(client__firstname__icontains=search) |
                Q(client__lastname__icontains=search) |
                Q(client__phonenumber__icontains=search) |
                Q(client__checkno__icontains=search)
            )
        return qs

    def perform_create(self, serializer):
        from decimal import Decimal as _Dec
        from django.db import transaction as db_transaction
        office = get_selected_office_api(self.request)
        client_id = self.request.data.get('client')
        try:
            client = Client.objects.get(pk=int(client_id))
        except (Client.DoesNotExist, ValueError, TypeError):
            from rest_framework.exceptions import ValidationError
            raise ValidationError({'client': 'Invalid client ID.'})

        tx_method = self.request.data.get('transaction_method', 'cash')
        loan_amount = serializer.validated_data.get('loan_amount') or _Dec('0')

        latest_bal = None
        if office:
            latest_bal = BranchBalance.objects.filter(branch=office).order_by('-last_updated').first()

        with db_transaction.atomic():
            new_loan = serializer.save(
                client=client,
                processed_by=self.request.user,
                office=office.name if office else '',
            )
            if latest_bal:
                if tx_method == 'cash':
                    BranchBalance.objects.create(
                        branch=office,
                        office_balance=latest_bal.office_balance - loan_amount,
                        bank_balance=latest_bal.bank_balance,
                        updated_by=self.request.user,
                    )
                else:
                    BranchBalance.objects.create(
                        branch=office,
                        office_balance=latest_bal.office_balance,
                        bank_balance=latest_bal.bank_balance - loan_amount,
                        updated_by=self.request.user,
                    )



class LoanDetailAPI(generics.RetrieveUpdateAPIView):
    """
    GET   /api/loans/<pk>/  — retrieve single loan
    PATCH /api/loans/<pk>/  — update loan fields
    """
    serializer_class   = LoanApplicationSerializer
    permission_classes = [IsAuthenticated]
    queryset           = LoanApplication.objects.select_related('client').all()


class OfficeListAPI(generics.ListAPIView):
    serializer_class   = OfficeSerializer
    permission_classes = [IsAuthenticated]
    pagination_class   = None
    queryset           = Office.objects.all().order_by('name')


# =============================================================================
#  EXPENSES — GET (paginated) + POST (create)
# =============================================================================

class ExpenseListAPI(generics.ListCreateAPIView):
    """
    GET  /api/expenses/?page=&page_size=
    POST /api/expenses/
    """
    serializer_class   = ExpenseSerializer
    permission_classes = [IsAuthenticated]
    pagination_class   = StandardPagination

    def get_queryset(self):
        filter_office = get_filter_office(self.request)
        qs = Expense.objects.select_related('transaction_type').all().order_by('-expense_date', '-id')
        if filter_office:
            qs = qs.filter(office=filter_office.name)
        return qs

    def perform_create(self, serializer):
        from app.models import ExpenseCategory as EC
        office = get_selected_office_api(self.request)

        # Manually resolve transaction_type FK to avoid silent NULL issue
        tx_type_id = self.request.data.get('transaction_type')
        if not tx_type_id:
            from rest_framework.exceptions import ValidationError
            raise ValidationError({'transaction_type': 'Category is required.'})
        try:
            category = EC.objects.get(pk=int(tx_type_id))
        except (EC.DoesNotExist, ValueError, TypeError):
            from rest_framework.exceptions import ValidationError
            raise ValidationError({'transaction_type': 'Invalid category ID: ' + str(tx_type_id)})

        serializer.save(
            recorded_by=self.request.user,
            office=office.name if office else '',
            transaction_type=category,
        )


class ExpenseCategoryListAPI(generics.ListAPIView):
    """GET /api/expense-categories/"""
    serializer_class   = ExpenseCategorySerializer
    permission_classes = [IsAuthenticated]
    queryset           = ExpenseCategory.objects.all().order_by('name')


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_expense_category_detail(request, pk):
    """GET /api/expense-categories/<pk>/"""
    try:
        cat = ExpenseCategory.objects.get(pk=pk)
        return Response({'id': cat.id, 'name': cat.name})
    except ExpenseCategory.DoesNotExist:
        return Response({'error': 'Haijapatanikana.'}, status=404)


# =============================================================================
#  SALARIES — paginated list (mobile uses PaginatedResponse<Salary>)
# =============================================================================

class SalaryListAPI(generics.ListAPIView):
    """
    GET /api/salaries/?month=YYYY-MM&page=&page_size=

    Returns standard paginated response:
    { count, next, previous, results: [...] }
    Each salary includes: id, employee_name, gross_salary, net_salary,
    payment_date, salary_for_month, transaction_method
    """
    permission_classes = [IsAuthenticated]
    pagination_class   = StandardPagination

    def list(self, request, *args, **kwargs):
        qs = Salary.objects.select_related('employee', 'fund_source').order_by('-salary_for_month', '-id')

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

        page = self.paginate_queryset(qs)
        data = [self._serialize_salary(s) for s in (page if page is not None else qs)]
        return self.get_paginated_response(data) if page is not None else Response(data)

    def _serialize_salary(self, s):
        emp = s.employee
        basic = s.amount or Decimal('0')
        deduction = getattr(emp, 'deduction_amount', None) or Decimal('0')
        return {
            'id':                 s.id,
            'employee_name':      emp.get_full_name() if emp else '',
            'employee_id':        _str(getattr(emp, 'employee_id', '')),
            'gross_salary':       _d(basic),
            'net_salary':         _d(basic - deduction),
            'deduction':          _d(deduction),
            'salary_for_month':   _str(s.salary_for_month),
            'payment_date':       _str(getattr(s, 'payment_date', '')),
            'transaction_method': s.transaction_method or '',
            'fund_source':        s.fund_source.name if s.fund_source else '',
        }


# =============================================================================
#  MONTHLY SUMMARY REPORT — new endpoint for mobile reports screen
# =============================================================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_monthly_summary(request):
    """
    GET /api/reports/monthly/?month=1-12&year=YYYY

    Response:
    {
      month, year,
      total_disbursed, total_collected, total_expenses, new_clients,
      loans_by_status: { "Approved": 34, ... },
      expenses_by_type: { "Benki": 200000, ... }
    }
    """
    try:
        month = int(request.GET.get('month', date.today().month))
        year  = int(request.GET.get('year',  date.today().year))
    except ValueError:
        return Response({'detail': 'month/year si sahihi.'}, status=400)

    filter_office = get_filter_office(request)

    loan_qs     = LoanApplication.objects.filter(application_date__year=year, application_date__month=month)
    repay_qs    = LoanRepayment.objects.filter(repayment_date__year=year, repayment_date__month=month)
    expense_qs  = Expense.objects.filter(expense_date__year=year, expense_date__month=month)
    client_qs   = Client.objects.filter(registered_date__year=year, registered_date__month=month)

    if filter_office:
        loan_qs    = loan_qs.filter(office=filter_office.name)
        repay_qs   = repay_qs.filter(loan_application__office=filter_office.name)
        expense_qs = expense_qs.filter(office=filter_office.name)
        client_qs  = client_qs.filter(registered_office=filter_office)

    total_disbursed = _d(loan_qs.filter(status='Approved').aggregate(
        t=Coalesce(Sum('loan_amount'), Decimal('0')))['t'])

    total_collected = _d(repay_qs.aggregate(
        t=Coalesce(Sum('repayment_amount'), Decimal('0')))['t'])

    total_expenses = _d(expense_qs.aggregate(
        t=Coalesce(Sum('amount'), Decimal('0')))['t'])

    new_clients = client_qs.count()

    loans_by_status = {}
    for row in loan_qs.values('status').annotate(c=Count('id')):
        loans_by_status[row['status']] = row['c']

    TTYPE_LABELS = {1: 'Benki', 2: 'Taslimu', 3: 'Simu'}
    expenses_by_type = {}
    for row in expense_qs.values('transaction_type_id').annotate(
            t=Coalesce(Sum('amount'), Decimal('0'))):
        label = TTYPE_LABELS.get(row['transaction_type_id'], str(row['transaction_type_id']))
        expenses_by_type[label] = _d(row['t'])

    return Response({
        'month':            month,
        'year':             year,
        'total_disbursed':  total_disbursed,
        'total_collected':  total_collected,
        'total_expenses':   total_expenses,
        'new_clients':      new_clients,
        'loans_by_status':  loans_by_status,
        'expenses_by_type': expenses_by_type,
    })


# =============================================================================
#  RECENT ACTIVITY
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
#  STAFF
# =============================================================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_staff(request):
    """GET /api/staff/"""
    staff = CustomUser.objects.all().order_by('id')
    data  = []
    for u in staff:
        o = getattr(u, 'office_allocation', None)
        data.append({
            'id':           u.id,
            'full_name':    u.get_full_name(),
            'username':     u.username,
            'email':        u.email,
            'phone':        _str(getattr(u, 'phone', '')),
            'employee_id':  _str(getattr(u, 'employee_id', '')),
            'role':         str(u.role) if getattr(u, 'role', None) else '',
            'is_active':    u.is_active,
            'is_superuser': u.is_superuser,
            'office':       o.name if o else '',
            'office_id':    o.id   if o else None,
        })
    return Response(data)


# =============================================================================
#  NYONGEZA
# =============================================================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_nyongeza(request):
    """GET /api/nyongeza/"""
    filter_office = get_filter_office(request)
    qs = Nyongeza.objects.all().order_by('-id')
    if filter_office:
        qs = qs.filter(Office=filter_office)

    totals = qs.aggregate(
        total_bank=Sum('amount', filter=Q(deposit_method='bank')),
        total_cash=Sum('amount', filter=Q(deposit_method='cash')),
        total_all=Sum('amount'),
    )

    data = [{
        'id':             n.id,
        'amount':         _d(n.amount),
        'deposit_method': n.deposit_method or '',
        'description':    n.description or '',
        'date':           _str(n.date),
        'office':         n.Office.name if n.Office else '',
        'recorded_by':    n.recorded_by.get_full_name() if n.recorded_by else '',
    } for n in qs]

    return Response({
        'total_bank': _d(totals['total_bank']),
        'total_cash': _d(totals['total_cash']),
        'total_all':  _d(totals['total_all']),
        'nyongeza':   data,
    })


# =============================================================================
#  SALARY ADVANCES
# =============================================================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_salary_advances(request):
    """GET /api/salary-advances/"""
    qs = SalaryAdvance.objects.select_related('employee').all().order_by('-created_at')
    data = [{
        'id':                     s.id,
        'employee_name':          s.employee.get_full_name() if s.employee else '',
        'account':                s.account or '',
        'amount':                 _d(s.amount),
        'payment_period':         s.payment_period,
        'monthly_installment':    _d(s.monthly_installment),
        'starting_payment_month': _str(s.starting_payment_month),
        'ending_payment_month':   _str(s.ending_payment_month),
        'status':                 s.status or '',
    } for s in qs]
    return Response(data)


# =============================================================================
#  SALARY SLIP
# =============================================================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_salary_slip(request):
    """GET /api/salary/slip/?month=YYYY-MM"""
    import calendar as cal_module

    month_param = request.GET.get('month', date.today().strftime('%Y-%m'))
    try:
        year, month = map(int, month_param.split('-'))
        start_date = datetime.date(year, month, 1)
        last_day   = cal_module.monthrange(year, month)[1]
        end_date   = datetime.date(year, month, last_day)
    except Exception:
        return Response({'error': 'Muundo si sahihi. Tumia YYYY-MM'}, status=400)

    salaries = Salary.objects.filter(
        salary_for_month__gte=start_date,
        salary_for_month__lte=end_date,
    ).select_related('employee', 'fund_source').order_by('fund_source__name', 'employee__first_name')

    rows = []
    total_basic = total_deduction = total_net = Decimal('0')
    for sal in salaries:
        emp       = sal.employee
        basic     = sal.amount or Decimal('0')
        deduction = getattr(emp, 'deduction_amount', None) or Decimal('0')
        net       = basic - deduction
        rows.append({
            'employee_name':      emp.get_full_name() if emp else '',
            'branch':             sal.fund_source.name if sal.fund_source else '',
            'basic_salary':       _d(basic),
            'deduction':          _d(deduction),
            'net_salary':         _d(net),
            'transaction_method': sal.transaction_method or '',
            'salary_for_month':   _str(sal.salary_for_month),
        })
        total_basic     += basic
        total_deduction += deduction
        total_net       += net

    return Response({
        'month': month_param,
        'salaries': rows,
        'totals': {
            'basic_salary': _d(total_basic),
            'deduction':    _d(total_deduction),
            'net_salary':   _d(total_net),
        }
    })


# =============================================================================
#  OFFICE TRANSACTIONS
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
        qs = qs.filter(Q(office_from=filter_office) | Q(office_to=filter_office))

    data = [{
        'id':                 t.id,
        'office_from':        t.office_from.name if t.office_from else '',
        'office_to':          t.office_to.name   if t.office_to   else '',
        'transaction_type':   t.transaction_type or '',
        'transaction_method': t.transaction_method or '',
        'amount':             _d(t.amount),
        'transaction_date':   _str(t.transaction_date),
        'processed_by':       t.processed_by.get_full_name() if t.processed_by else '',
    } for t in qs[:100]]
    return Response(data)


# =============================================================================
#  COMPLETED LOANS
# =============================================================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_completed_loans(request):
    """GET /api/completed-loans/"""
    filter_office = get_filter_office(request)
    qs = LoanApplication.objects.filter(
        repayment_amount_remaining__lte=0
    ).select_related('client').order_by('-updated_at')
    if filter_office:
        qs = qs.filter(office=filter_office.name)

    agg = qs.aggregate(
        total=Sum('total_repayment_amount'),
        interest=Sum('total_interest_amount'),
    )
    data = [{
        'id':          l.id,
        'client_name': f"{l.client.firstname} {l.client.lastname}",
        'loan_amount': _d(l.loan_amount),
        'total_paid':  _d(l.total_repayment_amount),
        'office':      l.office or '',
        'date':        _str(l.application_date),
        'loan_type':   l.loan_type or '',
    } for l in qs[:100]]

    return Response({
        'count':                 len(data),
        'total_amount_repaid':   _d(agg['total']),
        'total_interest_earned': _d(agg['interest']),
        'loans':                 data,
    })


# =============================================================================
#  LOAN REPORT
# =============================================================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_loan_report(request):
    """GET /api/loan-report/"""
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
        paid     = sum(r.repayment_amount for r in l.repayments.all())
        loan_amt = l.loan_amount            or Decimal('0')
        interest = l.total_interest_amount  or Decimal('0')
        total    = l.total_repayment_amount or Decimal('0')
        balance  = max(l.repayment_amount_remaining or Decimal('0'), Decimal('0'))

        rows.append({
            'name':            f"{l.client.firstname} {l.client.middlename or ''} {l.client.lastname}".strip(),
            'check_no':        l.client.checkno or l.client.employmentcardno or '',
            'mobile':          l.client.phonenumber or '',
            'loan_type':       l.loan_type or '',
            'loan_amount':     _d(loan_amt),
            'interest_amount': _d(interest),
            'total_amount':    _d(total),
            'paid_amount':     _d(paid),
            'balance':         _d(balance),
        })
        grand_loan     += loan_amt
        grand_interest += interest
        grand_total    += total
        grand_paid     += paid
        grand_balance  += balance

    return Response({
        'rows':                  rows,
        'grand_loan_amount':     _d(grand_loan),
        'grand_interest_amount': _d(grand_interest),
        'grand_total_amount':    _d(grand_total),
        'grand_paid_amount':     _d(grand_paid),
        'grand_balance':         _d(grand_balance),
    })


# =============================================================================
#  EXPIRED LOANS
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
    ).select_related('client').prefetch_related('repayments').order_by('client__firstname', 'application_date', 'id')
    if filter_office:
        qs = qs.filter(office=filter_office.name)

    MONTH_NAMES = {1:'Jan',2:'Feb',3:'Mar',4:'Apr',5:'May',6:'Jun',
                   7:'Jul',8:'Aug',9:'Sep',10:'Oct',11:'Nov',12:'Dec'}

    def month_label(d):
        return f"{MONTH_NAMES[d.month]}/{d.year}"

    def classify(days):
        if days <= 30:  return 'Substandard'
        elif days <= 90: return 'Doubtful'
        else:           return 'Loss'

    rows = []
    total_loaned = total_paid = total_outstanding = Decimal('0')
    for l in qs:
        if not l.first_repayment_date or not l.payment_period_months:
            continue
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
            'name':          f"{client.firstname} {client.middlename or ''} {client.lastname}".strip().upper(),
            'check_no':      client.checkno or getattr(client,'employmentcardno','') or '—',
            'contact':       client.phonenumber or '—',
            'loan_type':     l.loan_type or '—',
            'decision_date': str(l.application_date) if l.application_date else '—',
            'start_month':   month_label(l.first_repayment_date),
            'end_month':     month_label(end_date),
            'loaned_amount': _d(l.loan_amount),
            'paid_amount':   _d(paid_amt),
            'outstanding':   _d(outstanding),
            'expired_days':  expired_days,
            'status':        classify(expired_days),
            'office':        l.office or '',
        })
        total_loaned      += l.loan_amount or Decimal('0')
        total_paid        += paid_amt
        total_outstanding += outstanding

    # Web view: order_by('client__firstname', 'application_date', 'id') - keep as is
    # rows already in that order from queryset; no extra sort needed

    # Add S/N after sort
    for i, r in enumerate(rows, 1):
        r['sn'] = i

    filter_office2 = get_filter_office(request)
    selected2      = get_selected_office_api(request)
    branch_name    = (filter_office2.name.upper() if filter_office2
                      else selected2.name.upper() if selected2 else 'ALL BRANCHES')
    up_to_label    = month_label(today).upper()

    return Response({
        'count':             len(rows),
        'branch_name':       branch_name,
        'up_to_label':       up_to_label,
        'total_loaned':      _d(total_loaned),
        'total_paid':        _d(total_paid),
        'total_outstanding': _d(total_outstanding),
        'loans':             rows,
    })


# =============================================================================
#  LOANS OWED
# =============================================================================

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_loans_owed_approve(request):
    # POST /api/loans-owed/approve/  body: {loan_ids: [id, ...]}
    # Mirrors loans_owed_approve() web view — only approves fully-paid loans
    loan_ids = request.data.get('loan_ids', [])
    if not loan_ids:
        return Response({'detail': 'No loan_ids provided.'}, status=400)
    approved = LoanApplication.objects.filter(
        Q(repayment_amount_remaining__lte=Decimal('1')) | Q(repayment_amount_remaining__isnull=True),
        id__in=loan_ids,
        is_approved=False,
    ).update(is_approved=True)
    return Response({'success': True, 'approved': approved,
                     'message': f'{approved} loan(s) approved and removed from report.'})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def loans_owed_summary(request):
    """GET /api/loans-owed/"""
    filter_office = get_filter_office(request)
    qs = LoanApplication.objects.filter(is_approved=False, repayment_amount_remaining__gt=0)
    if filter_office:
        qs = qs.filter(office=filter_office.name)
    total             = qs.count()
    total_outstanding = qs.aggregate(t=Sum('repayment_amount_remaining'))['t'] or 0
    return Response({
        'total_loans_owed':  total,
        'total_outstanding': _d(total_outstanding),
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def loans_owed_report(request):
    # GET /api/loans-owed/report/
    # Mirrors loans_owed_report() web view exactly.
    from dateutil.relativedelta import relativedelta

    try:
        filter_office = get_filter_office(request)
        selected      = get_selected_office_api(request)
        today         = date.today()
        cur_y, cur_m  = today.year, today.month
        win_start     = today - relativedelta(months=6)
        win_y, win_m  = win_start.year, win_start.month

        # Web view: is_approved=False only — includes both paid AND unpaid unapproved loans
        # Paid loans show ✓ ✓ in balance column and get the approve checkbox
        loans_qs = LoanApplication.objects.filter(
            is_approved=False,
            client__isnull=False,
        ).select_related('client').prefetch_related('repayments')
        if filter_office:
            loans_qs = loans_qs.filter(office=filter_office.name)
        loans_list = list(loans_qs)

        # rep_map: loan_id -> {(year,month): total_paid}
        # Use only the loan IDs we fetched to limit the repayment query
        loan_id_list = [l.id for l in loans_list]
        rep_map = {lid: {} for lid in loan_id_list}
        if loan_id_list:
            for r in LoanRepayment.objects.filter(
                    loan_application_id__in=loan_id_list
            ).values('loan_application_id', 'repayment_date', 'repayment_amount', 'payment_month'):
                ref = r['payment_month'] or r['repayment_date']
                if not ref: continue
                key = (ref.year, ref.month)
                lid = r['loan_application_id']
                rep_map[lid][key] = rep_map[lid].get(key, Decimal('0')) + (r['repayment_amount'] or Decimal('0'))

        MONTHS_AB = {1:'Jan',2:'Feb',3:'Mar',4:'Apr',5:'May',6:'Jun',
                     7:'Jul',8:'Aug',9:'Sep',10:'Oct',11:'Nov',12:'Dec'}

        def lbl_ab(y, m): return f"{MONTHS_AB[m]}-{y}"

        def month_range_ab(sy, sm, count):
            out = []
            for i in range(count):
                tm = sm + i
                ty = sy + (tm - 1) // 12
                tm = (tm - 1) % 12 + 1
                out.append((ty, tm))
            return out

        def build_cells_ab(col_months, rmap, inst, frd, periods, cur_y, cur_m):
            pool = sum(rmap.values(), Decimal('0'))
            cells = []
            contribs = []
            for (cy, cm) in col_months:
                paid_this = rmap.get((cy, cm), Decimal('0'))
                if not frd:
                    cells.append({'type': 'empty', 'paid': 0, 'out': 0})
                    contribs.append((Decimal('0'), Decimal('0')))
                    continue
                midx = (cy - frd.year) * 12 + (cm - frd.month)
                in_sched = 0 <= midx < periods
                if not in_sched:
                    if paid_this > 0:
                        cells.append({'type': 'extra_paid', 'paid': _d(paid_this), 'out': 0})
                        contribs.append((paid_this, Decimal('0')))
                    else:
                        cells.append({'type': 'empty', 'paid': 0, 'out': 0})
                        contribs.append((Decimal('0'), Decimal('0')))
                    continue
                is_future = (cy > cur_y) or (cy == cur_y and cm > cur_m)
                if is_future:
                    cells.append({'type': 'future_out', 'paid': 0, 'out': _d(inst)})
                    contribs.append((Decimal('0'), inst))
                    continue
                if pool >= inst:
                    pool -= inst
                    if paid_this > 0:
                        cells.append({'type': 'tick', 'paid': _d(paid_this), 'out': 0})
                    else:
                        cells.append({'type': 'tick_no_paid', 'paid': 0, 'out': 0})
                    contribs.append((paid_this, Decimal('0')))
                elif pool > Decimal('0'):
                    out_val = inst - pool
                    cells.append({'type': 'partial', 'paid': _d(paid_this) if paid_this else 0, 'out': _d(out_val)})
                    contribs.append((paid_this, out_val))
                    pool = Decimal('0')
                else:
                    if paid_this > 0:
                        cells.append({'type': 'tick_out', 'paid': _d(paid_this), 'out': 0})
                        contribs.append((paid_this, Decimal('0')))
                    else:
                        cells.append({'type': 'out_only', 'paid': 0, 'out': _d(inst)})
                        contribs.append((Decimal('0'), inst))
            return cells, contribs

        # Section A: active loans grouped by first_repayment_date (last 6 months)
        groups = {}
        for loan in loans_list:
            frd = loan.first_repayment_date
            if not frd or (frd.year, frd.month) < (win_y, win_m): continue
            groups.setdefault((frd.year, frd.month), []).append(loan)

        month_sections = []
        for (sy, sm) in sorted(groups.keys(), reverse=True):
            grp_loans = sorted(groups[(sy, sm)],
                key=lambda l: (getattr(l.client, 'firstname', '') or '', getattr(l.client, 'lastname', '') or ''))
            col_months = month_range_ab(sy, sm, 12)
            month_headers = [lbl_ab(y, m) for y, m in col_months]
            col_totals = [{'paid': Decimal('0'), 'out': Decimal('0')} for _ in col_months]
            rows = []
            sec_paid = sec_loaned = sec_amount = sec_balance = Decimal('0')

            for loan in grp_loans:
                try:
                    client = loan.client
                    if not client: continue
                except Exception:
                    continue
                rmap    = rep_map.get(loan.id, {})
                inst    = loan.monthly_installment or Decimal('0')
                periods = loan.payment_period_months or 0
                cells, contribs = build_cells_ab(col_months, rmap, inst, loan.first_repayment_date, periods, cur_y, cur_m)

                for idx, (p, o) in enumerate(contribs):
                    col_totals[idx]['paid'] += p
                    col_totals[idx]['out']  += o

                total_paid = sum(rmap.values(), Decimal('0'))
                loaned     = loan.loan_amount or Decimal('0')
                tot_amt    = loan.total_repayment_amount or Decimal('0')
                balance    = loan.repayment_amount_remaining or Decimal('0')

                rows.append({
                    'loan_id':       loan.id,
                    'name':          f"{client.firstname} {getattr(client, 'middlename', '') or ''} {client.lastname}".strip(),
                    'check_no':      client.checkno or getattr(client, 'employmentcardno', '') or '—',
                    'loan_id_label': f"{(loan.office or '').lower()}-{loan.id}",
                    'cells':         cells,
                    'total_paid':    _d(total_paid),
                    'loaned_amount': _d(loaned),
                    'total_amount':  _d(tot_amt),
                    'balance':       _d(balance),
                    'is_fully_paid': balance <= Decimal('0'),
                    'mobile':        client.phonenumber or '—',
                })
                sec_paid += total_paid; sec_loaned += loaned
                sec_amount += tot_amt; sec_balance += balance

            month_sections.append({
                'key':           f"{sy}-{sm:02d}",
                'label':         lbl_ab(sy, sm).upper(),
                'month_headers': month_headers,
                'col_totals':    [{'paid': _d(ct['paid']), 'out': _d(ct['out'])} for ct in col_totals],
                'rows':          rows,
                'total_paid':    _d(sec_paid),
                'total_loaned':  _d(sec_loaned),
                'total_amount':  _d(sec_amount),
                'total_balance': _d(sec_balance),
                'count':         len(rows),
            })

        # Section B: HAMA (overdue > 6 months), grouped by loan start year
        hama_cutoff = today - relativedelta(months=6)
        hama_loans  = [l for l in loans_list
                       if l.first_repayment_date and l.first_repayment_date <= hama_cutoff]

        # Dec of last year through Dec of this year = 13 months
        hama_col_months = month_range_ab(cur_y - 1, 12, 13)
        hama_month_hdrs = [lbl_ab(y, m) for y, m in hama_col_months]

        hama_year_groups = {}
        for loan in hama_loans:
            yr = loan.first_repayment_date.year
            hama_year_groups.setdefault(yr, []).append(loan)

        hama_sections = []
        for yr in sorted(hama_year_groups.keys(), reverse=True):
            h_loans = sorted(hama_year_groups[yr],
                key=lambda l: (getattr(l.client, 'firstname', '') or '', getattr(l.client, 'lastname', '') or ''))
            h_col_totals = [{'paid': Decimal('0'), 'out': Decimal('0')} for _ in hama_col_months]
            rows = []
            h_paid = h_loaned = h_interest = h_amount = h_balance = Decimal('0')

            for loan in h_loans:
                try:
                    client = loan.client
                    if not client: continue
                except Exception:
                    continue
                rmap    = rep_map.get(loan.id, {})
                inst    = loan.monthly_installment or Decimal('0')
                periods = loan.payment_period_months or 0
                cells, contribs = build_cells_ab(hama_col_months, rmap, inst, loan.first_repayment_date, periods, cur_y, cur_m)

                for idx, (p, o) in enumerate(contribs):
                    h_col_totals[idx]['paid'] += p
                    h_col_totals[idx]['out']  += o

                total_paid = sum(rmap.values(), Decimal('0'))
                loaned     = loan.loan_amount or Decimal('0')
                interest   = loan.total_interest_amount or Decimal('0')
                tot_amt    = loan.total_repayment_amount or Decimal('0')
                balance    = loan.repayment_amount_remaining or Decimal('0')

                rows.append({
                    'loan_id':       loan.id,
                    'name':          f"{client.firstname} {getattr(client, 'middlename', '') or ''} {client.lastname}".strip(),
                    'check_no':      client.checkno or getattr(client, 'employmentcardno', '') or '—',
                    'loan_id_label': f"{(loan.office or '').lower()}-{loan.id}",
                    'cells':         cells,
                    'total_paid':    _d(total_paid),
                    'loaned_amount': _d(loaned),
                    'interest':      _d(interest),
                    'total_amount':  _d(tot_amt),
                    'balance':       _d(balance),
                    'mobile':        client.phonenumber or '—',
                })
                h_paid += total_paid; h_loaned += loaned
                h_interest += interest; h_amount += tot_amt; h_balance += balance

            hama_sections.append({
                'label':          f"HAMA-{yr}",
                'key':            f"hama-{yr}",
                'month_headers':  hama_month_hdrs,
                'col_totals':     [{'paid': _d(ct['paid']), 'out': _d(ct['out'])} for ct in h_col_totals],
                'rows':           rows,
                'total_paid':     _d(h_paid),
                'total_loaned':   _d(h_loaned),
                'total_interest': _d(h_interest),
                'total_amount':   _d(h_amount),
                'total_balance':  _d(h_balance),
                'count':          len(rows),
            })

        branch_name = (filter_office.name.upper() if filter_office
                       else selected.name.upper() if selected else 'ALL BRANCHES')

        return Response({
            'branch_name':    branch_name,
            'month_sections': month_sections,
            'hama_sections':  hama_sections,
        })

    except Exception as e:
        import traceback
        return Response({'detail': f'Error: {str(e)}', 'trace': traceback.format_exc()}, status=500)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_customer_statement(request):
    """GET /api/customer-statement/?client_id=<id>"""
    client_id = request.GET.get('client_id')
    if not client_id:
        return Response({'error': 'client_id inahitajika.'}, status=400)
    try:
        client = Client.objects.get(id=client_id)
    except Client.DoesNotExist:
        return Response({'error': 'Mteja hajapatikana.'}, status=404)

    filter_office = get_filter_office(request)
    loans = LoanApplication.objects.filter(
        client=client
    ).prefetch_related('repayments', 'topups').order_by('application_date', 'id')
    if filter_office:
        loans = loans.filter(office=filter_office.name)

    loan_blocks    = []
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

        all_dates = sorted(d for d in set(
            list(repayments_by_date.keys()) + list(topups_by_date.keys())
        ) if d is not None)

        global_balance += total_repayable
        block_rows.append({
            'type': 'disbursement', 'date': str(loan.application_date),
            'receipt_no': str(loan.id).zfill(6),
            'description': 'Loan Taken and interest',
            'loan_amount': _d(total_repayable), 'paid_amount': 0, 'balance': _d(global_balance),
        })

        for day in all_dates:
            day_repayments = repayments_by_date.get(day, [])
            day_topups     = topups_by_date.get(day, [])
            for r in (day_repayments[:-1] if day_topups else day_repayments):
                global_balance = max(global_balance - r.repayment_amount, Decimal('0'))
                block_rows.append({
                    'type': 'repayment', 'date': str(r.repayment_date or day),
                    'receipt_no': str(r.id).zfill(6), 'description': 'Loan payment',
                    'loan_amount': 0, 'paid_amount': _d(r.repayment_amount), 'balance': _d(global_balance),
                })
            for topup in day_topups:
                old_balance = topup.old_balance_cleared or global_balance or Decimal('0')
                if old_balance > 0:
                    global_balance = Decimal('0')
                    block_rows.append({
                        'type': 'topup_clearance', 'date': str(topup.topup_date),
                        'receipt_no': str(topup.id).zfill(6),
                        'description': 'Clearance loan balance for top-up',
                        'loan_amount': 0, 'paid_amount': _d(old_balance), 'balance': _d(global_balance),
                    })

        loan_blocks.append({'loan_id': loan.id, 'loan_type': loan.loan_type, 'rows': block_rows})

    return Response({
        'client': {'id': client.id, 'name': f"{client.firstname} {client.lastname}", 'phone': client.phonenumber or ''},
        'loan_blocks': loan_blocks,
    })


# =============================================================================
#  LOAN OUTSTANDING
# =============================================================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_loan_outstanding(request):
    """GET /api/loan-outstanding/?client_id=<id>"""
    client_id = request.GET.get('client_id')
    if not client_id:
        filter_office = get_filter_office(request)
        qs = Client.objects.filter(loan_applications__isnull=False).distinct().order_by('firstname')
        if filter_office:
            qs = qs.filter(loan_applications__office=filter_office.name).distinct()
        return Response([{'id': c.id, 'name': f"{c.firstname} {c.lastname}", 'phone': c.phonenumber or ''} for c in qs])

    try:
        client = Client.objects.get(id=client_id)
    except Client.DoesNotExist:
        return Response({'error': 'Mteja hajapatikana.'}, status=404)

    filter_office = get_filter_office(request)
    loans = LoanApplication.objects.filter(client=client).prefetch_related('repayments').order_by('created_at')
    if filter_office:
        loans = loans.filter(office=filter_office.name)

    rows = []
    for loan in loans:
        paid        = sum(r.repayment_amount for r in loan.repayments.all())
        outstanding = max(loan.repayment_amount_remaining or Decimal('0'), Decimal('0'))
        rows.append({
            'loan_id':         loan.id,
            'loan_amount':     _d(loan.loan_amount or 0),
            'interest_amount': _d(loan.total_interest_amount or 0),
            'total_amount':    _d(loan.total_repayment_amount or 0),
            'paid_amount':     _d(paid),
            'outstanding':     _d(outstanding),
            'is_approved':     loan.is_approved,
        })

    return Response({
        'client': {'id': client.id, 'name': f"{client.firstname} {client.lastname}"},
        'loans':  rows,
        'totals': {
            'loan_amount': _d(sum(Decimal(str(r['loan_amount'])) for r in rows)),
            'paid_amount': _d(sum(Decimal(str(r['paid_amount'])) for r in rows)),
            'outstanding': _d(sum(Decimal(str(r['outstanding'])) for r in rows)),
        }
    })


# =============================================================================
#  FINANCIAL STATEMENT
# =============================================================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_financial_statement(request):
    # GET /api/financial-statement/?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD
    # Mirrors financial_statement_report() web view exactly.
    # Returns all rows from the screenshot:
    #   Opening Balance, MAPATO, NYONGEZA, HAZINA, Income Subtotal,
    #   FOMU, MATUMIZI OFISINI, MATUMIZI BENKI-[KITUO],
    #   MATUMIZI BENKI-[MKURUGENZI], MAKATO BANK, Outflow Subtotal,
    #   BALANCE CASH, BALANCE BENKI, Total Cash
    from django.utils import timezone as tz

    d_from, d_to, err = _parse_dates(request)
    if err:
        return Response({'error': err}, status=400)

    filter_office = get_filter_office(request)
    selected      = get_selected_office_api(request)

    start_dt  = tz.make_aware(datetime.datetime.combine(d_from, datetime.time.min))
    end_dt    = tz.make_aware(datetime.datetime.combine(d_to,   datetime.time.max))
    before_dt = start_dt

    def _s(qs, field='amount'):
        return qs.aggregate(t=Sum(field))['t'] or Decimal('0')

    # ── Scope helpers (mirror web view helper functions) ──────────────────────
    def rep_qs(q):
        qs = LoanRepayment.objects.filter(q)
        if filter_office:
            qs = qs.filter(loan_application__office__iexact=filter_office.name)
        return qs

    def loan_qs(q):
        qs = LoanApplication.objects.filter(q)
        if filter_office:
            qs = qs.filter(office__iexact=filter_office.name)
        return qs

    def nyo_qs(q):
        qs = Nyongeza.objects.filter(q)
        if filter_office:
            qs = qs.filter(Office=filter_office)
        return qs

    def exp_qs(q):
        qs = Expense.objects.filter(q)
        if filter_office:
            qs = qs.filter(office__iexact=filter_office.name)
        return qs

    def transfer_in_qs(q):
        qs = OfficeTransaction.objects.filter(q)
        if filter_office:
            qs = qs.filter(office_to=filter_office)
        return qs

    def transfer_out_non_hq_qs(q):
        qs = OfficeTransaction.objects.filter(q)
        if filter_office:
            qs = qs.filter(office_from=filter_office)
        return qs.exclude(office_to__name__iexact='HQ')

    def transfer_out_hq_qs(q):
        qs = OfficeTransaction.objects.filter(q)
        if filter_office:
            qs = qs.filter(office_from=filter_office)
        return qs.filter(office_to__name__iexact='HQ')

    def transfer_out_qs(q):
        qs = OfficeTransaction.objects.filter(q)
        if filter_office:
            qs = qs.filter(office_from=filter_office)
        return qs

    def bank_charge_qs(q):
        qs = BankCharge.objects.filter(q)
        if filter_office:
            qs = qs.filter(office__iexact=filter_office.name)
        return qs

    def bank_cash_txn_qs(q):
        qs = BankCashTransaction.objects.filter(q)
        if filter_office:
            qs = qs.filter(office_from=filter_office)
        return qs

    before_q = Q(created_at__lt=before_dt)
    pq       = Q(created_at__gte=start_dt, created_at__lte=end_dt)

    # ══════════════════════════════════════════════════════════════════════════
    # OPENING BALANCE (cash + bank before start_date)
    # ══════════════════════════════════════════════════════════════════════════
    try:
        cash_to_bank_b = _s(bank_cash_txn_qs(before_q).filter(source__iexact='cash', destination__iexact='bank'))
        bank_to_cash_b = _s(bank_cash_txn_qs(before_q).filter(source__iexact='bank', destination__iexact='cash'))
    except Exception:
        cash_to_bank_b = bank_to_cash_b = Decimal('0')

    cash_rep_b     = _s(rep_qs(before_q).exclude(loan_application__loan_type__iexact='Hazina').filter(transaction_method__iexact='cash'), 'repayment_amount')
    cash_hazina_b  = _s(rep_qs(before_q).filter(loan_application__loan_type__iexact='Hazina', transaction_method__iexact='cash'), 'repayment_amount')
    cash_nyo_b     = _s(nyo_qs(before_q).filter(deposit_method__iexact='cash'))
    cash_exp_b     = _s(exp_qs(before_q).filter(payment_method__iexact='cash'))
    cash_loan_b    = _s(loan_qs(before_q).filter(transaction_method__iexact='cash'), 'loan_amount')
    cash_charge_b  = _s(bank_charge_qs(before_q).filter(payment_method__iexact='cash'))
    opening_cash   = (cash_rep_b + cash_hazina_b + cash_nyo_b + bank_to_cash_b) - (cash_exp_b + cash_loan_b + cash_charge_b + cash_to_bank_b)

    bank_rep_b      = _s(rep_qs(before_q).exclude(loan_application__loan_type__iexact='Hazina').filter(transaction_method__iexact='bank'), 'repayment_amount')
    bank_hazina_b   = _s(rep_qs(before_q).filter(loan_application__loan_type__iexact='Hazina', transaction_method__iexact='bank'), 'repayment_amount')
    bank_nyo_b      = _s(nyo_qs(before_q).filter(deposit_method__iexact='bank'))
    bank_trx_in_b   = _s(transfer_in_qs(before_q))
    bank_exp_b      = _s(exp_qs(before_q).filter(payment_method__iexact='bank'))
    bank_loan_b     = _s(loan_qs(before_q).filter(transaction_method__iexact='bank'), 'loan_amount')
    bank_trx_out_b  = _s(transfer_out_qs(before_q))
    bank_charge_b   = _s(bank_charge_qs(before_q).filter(payment_method__iexact='bank'))
    opening_bank    = (bank_rep_b + bank_hazina_b + bank_nyo_b + bank_trx_in_b + cash_to_bank_b) - (bank_exp_b + bank_loan_b + bank_trx_out_b + bank_charge_b + bank_to_cash_b)

    opening_stock   = opening_cash + opening_bank

    # ══════════════════════════════════════════════════════════════════════════
    # PERIOD INCOME
    # ══════════════════════════════════════════════════════════════════════════
    total_mapato       = _s(rep_qs(pq).exclude(loan_application__loan_type__iexact='Hazina'), 'repayment_amount')
    total_nyongeza     = _s(nyo_qs(pq))
    total_hazina       = _s(rep_qs(pq).filter(loan_application__loan_type__iexact='Hazina'), 'repayment_amount')
    total_transfers_in = _s(transfer_in_qs(pq))
    total_income_with_opening = opening_stock + total_mapato + total_nyongeza + total_transfers_in

    # ══════════════════════════════════════════════════════════════════════════
    # PERIOD EXPENDITURE
    # ══════════════════════════════════════════════════════════════════════════
    period_expenses = exp_qs(pq)
    period_loans    = loan_qs(pq)

    total_loans_disbursed = _s(period_loans, 'loan_amount')
    loan_cash_amount      = _s(period_loans.filter(transaction_method__iexact='cash'), 'loan_amount')
    loan_bank_amount      = _s(period_loans.filter(transaction_method__iexact='bank'), 'loan_amount')

    # MATUMIZI OFISINI — per category
    from app.models import ExpenseCategory as EC
    matumizi_rows = []
    for cat in EC.objects.all().order_by('name'):
        ce = period_expenses.filter(transaction_type=cat)
        cash_amt = _s(ce.filter(payment_method__iexact='cash'))
        bank_amt = _s(ce.filter(payment_method__iexact='bank'))
        total    = cash_amt + bank_amt
        if total > 0:
            matumizi_rows.append({'name': cat.name, 'cash_amount': _d(cash_amt) if cash_amt else None, 'bank_amount': _d(bank_amt) if bank_amt else None, 'total': _d(total)})
    unc = period_expenses.filter(transaction_type__isnull=True)
    unc_c = _s(unc.filter(payment_method__iexact='cash')); unc_b = _s(unc.filter(payment_method__iexact='bank')); unc_t = unc_c + unc_b
    if unc_t > 0:
        matumizi_rows.append({'name': 'Matumizi Mengineyo', 'cash_amount': _d(unc_c) if unc_c else None, 'bank_amount': _d(unc_b) if unc_b else None, 'total': _d(unc_t)})
    total_matumizi_ofisini = sum(Decimal(str(r['total'])) for r in matumizi_rows)

    transfers_kituo         = _s(transfer_out_non_hq_qs(pq))
    total_matumizi_mkurugenzi = _s(transfer_out_hq_qs(pq))

    period_bank_charges = bank_charge_qs(pq)
    makato_benki_cash   = _s(period_bank_charges.filter(payment_method__iexact='cash'))
    makato_benki_bank   = _s(period_bank_charges.filter(payment_method__iexact='bank'))
    total_makato_benki  = makato_benki_cash + makato_benki_bank

    total_outflow = total_loans_disbursed + total_matumizi_ofisini + transfers_kituo + total_matumizi_mkurugenzi + total_makato_benki

    # ══════════════════════════════════════════════════════════════════════════
    # CLOSING BALANCE (cash / bank split)
    # ══════════════════════════════════════════════════════════════════════════
    try:
        cash_to_bank_p = _s(bank_cash_txn_qs(pq).filter(source__iexact='cash', destination__iexact='bank'))
        bank_to_cash_p = _s(bank_cash_txn_qs(pq).filter(source__iexact='bank', destination__iexact='cash'))
    except Exception:
        cash_to_bank_p = bank_to_cash_p = Decimal('0')

    cash_rep_p     = _s(rep_qs(pq).exclude(loan_application__loan_type__iexact='Hazina').filter(transaction_method__iexact='cash'), 'repayment_amount')
    cash_nyo_p     = _s(nyo_qs(pq).filter(deposit_method__iexact='cash'))
    cash_exp_p     = sum(Decimal(str(r['cash_amount'] or '0')) for r in matumizi_rows)
    cash_in_office = opening_cash + cash_rep_p + bank_to_cash_p + cash_nyo_p - loan_cash_amount - cash_exp_p - makato_benki_cash - cash_to_bank_p

    bank_rep_p      = _s(rep_qs(pq).exclude(loan_application__loan_type__iexact='Hazina').filter(transaction_method__iexact='bank'), 'repayment_amount')
    bank_nyo_p      = _s(nyo_qs(pq).filter(deposit_method__iexact='bank'))
    bank_trx_in_p   = total_transfers_in
    bank_exp_p      = sum(Decimal(str(r['bank_amount'] or '0')) for r in matumizi_rows)
    bank_trx_out_p  = transfers_kituo + total_matumizi_mkurugenzi
    cash_in_bank    = opening_bank + bank_rep_p + bank_nyo_p + bank_trx_in_p + cash_to_bank_p - loan_bank_amount - bank_exp_p - bank_trx_out_p - makato_benki_bank - bank_to_cash_p

    total_cash = cash_in_office + cash_in_bank

    branch_name = (filter_office.name.upper() if filter_office
                   else selected.name.upper() if selected else 'ALL BRANCHES')

    return Response({
        'date_from':    str(d_from),
        'date_to':      str(d_to),
        'branch_name':  branch_name,
        # Opening
        'opening_stock': _d(opening_stock),
        'opening_cash':  _d(opening_cash),
        'opening_bank':  _d(opening_bank),
        # Income
        'total_mapato':              _d(total_mapato)       if total_mapato       else None,
        'total_nyongeza':            _d(total_nyongeza)     if total_nyongeza     else None,
        'total_hazina':              _d(total_hazina)       if total_hazina       else None,
        'total_transfers_in':        _d(total_transfers_in) if total_transfers_in else None,
        'total_income_with_opening': _d(total_income_with_opening),
        # Expenditure
        'total_loans_disbursed':      _d(total_loans_disbursed)      if total_loans_disbursed      else None,
        'matumizi_ofisini_rows':      matumizi_rows,
        'total_matumizi_ofisini':     _d(total_matumizi_ofisini)     if total_matumizi_ofisini     else None,
        'transfers_kituo':            _d(transfers_kituo)            if transfers_kituo            else None,
        'total_matumizi_mkurugenzi':  _d(total_matumizi_mkurugenzi)  if total_matumizi_mkurugenzi  else None,
        'makato_benki_cash':          _d(makato_benki_cash)          if makato_benki_cash          else None,
        'makato_benki_bank':          _d(makato_benki_bank)          if makato_benki_bank          else None,
        'total_makato_benki':         _d(total_makato_benki)         if total_makato_benki         else None,
        'total_outflow':             _d(total_outflow),
        # Closing
        'cash_in_office': _d(cash_in_office),
        'cash_in_bank':   _d(cash_in_bank),
        'total_cash':     _d(total_cash),
    })

# =============================================================================
#  REPORTS
# =============================================================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def report_loans_issued(request):
    # GET /api/reports/loans-issued/?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD
    # Mirrors loan_issued_report() web view exactly:
    #   - Uses created_at with timezone-aware range (EAT = UTC+3)
    #   - Returns all columns from the screenshot:
    #     S/N, Date, Name, Check No, Mobile No, Work Station, Loan ID,
    #     Rate Type, Starting Month, Loaned Amount, Period, Interest Rate %,
    #     Interest Amount, Total Amount (P+I), Monthly Installment
    from django.utils import timezone as tz
    import datetime as _dt

    d_from, d_to, err = _parse_dates(request)
    if err: return Response({'error': err}, status=400)

    # Timezone-aware range (EAT = UTC+3) — matches web view
    start_dt = tz.make_aware(_dt.datetime.combine(d_from, _dt.time.min))
    end_dt   = tz.make_aware(_dt.datetime.combine(d_to,   _dt.time.max))

    filter_office = get_filter_office(request)
    selected      = get_selected_office_api(request)

    qs = LoanApplication.objects.select_related('client').filter(
        created_at__gte=start_dt,
        created_at__lte=end_dt,
    ).order_by('created_at', 'id')
    if filter_office:
        qs = qs.filter(office=filter_office.name)

    MONTH_NAMES = {1:'Jan',2:'Feb',3:'Mar',4:'Apr',5:'May',6:'Jun',
                   7:'Jul',8:'Aug',9:'Sep',10:'Oct',11:'Nov',12:'Dec'}

    items = []
    grand_loan = grand_interest = grand_total = grand_monthly = Decimal('0')

    for i, loan in enumerate(qs, 1):
        try:
            client = loan.client
        except Exception:
            continue  # skip orphan loans

        # Starting month from first_repayment_date
        if loan.first_repayment_date:
            m = loan.first_repayment_date
            starting_month = f"{MONTH_NAMES[m.month]}/{m.year}"
        else:
            starting_month = '—'

        loan_amount    = loan.loan_amount            or Decimal('0')
        interest_amt   = loan.total_interest_amount  or Decimal('0')
        total_amt      = loan.total_repayment_amount or Decimal('0')
        monthly_inst   = loan.monthly_installment    or Decimal('0')
        ir             = loan.interest_rate          or Decimal('0')

        items.append({
            'sn':                  i,
            'id':                  loan.id,
            'date':                str(loan.created_at.date()),
            'name':                f"{client.firstname} {client.middlename or ''} {client.lastname}".strip(),
            'check_no':            client.checkno or getattr(client,'employmentcardno','') or '—',
            'mobile':              client.phonenumber or '—',
            'work_station':        client.employername or '—',
            'loan_id_label':       f"{(loan.office or 'loan').lower()}-{loan.id}",
            'rate_type':           'Flat',
            'starting_month':      starting_month,
            'loan_amount':         _d(loan_amount),
            'period':              loan.payment_period_months or 0,
            'interest_rate':       str(ir.normalize()) + ' %',
            'interest_amount':     _d(interest_amt),
            'total_amount':        _d(total_amt),
            'monthly_installment': _d(monthly_inst),
            'loan_type':           loan.loan_type or '',
            'office':              loan.office or '',
        })

        grand_loan    += loan_amount
        grand_interest += interest_amt
        grand_total   += total_amt
        grand_monthly += monthly_inst

    branch_name = (filter_office.name.upper() if filter_office
                   else selected.name.upper() if selected else 'ALL BRANCHES')

    return Response({
        'date_from':      str(d_from),
        'date_to':        str(d_to),
        'branch_name':    branch_name,
        'count':          len(items),
        'loans':          items,
        'grand_loan_amount':         _d(grand_loan),
        'grand_interest_amount':     _d(grand_interest),
        'grand_total_amount':        _d(grand_total),
        'grand_monthly_installment': _d(grand_monthly),
        # legacy aliases
        'total_amount':   _d(grand_loan),
        'total_interest': _d(grand_interest),
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def report_loans_outstanding(request):
    """GET /api/reports/loans-outstanding/"""
    filter_office = get_filter_office(request)
    qs = LoanApplication.objects.select_related('client').filter(repayment_amount_remaining__gt=0)
    if filter_office: qs = qs.filter(office=filter_office.name)

    agg   = qs.aggregate(total=Sum('repayment_amount_remaining'), count=Count('id'))
    items = [{
        'id': l.id, 'client_name': f"{l.client.firstname} {l.client.lastname}",
        'phone': l.client.phonenumber or '', 'check_no': l.client.checkno or '',
        'loan_amount': _d(l.loan_amount), 'outstanding': _d(l.repayment_amount_remaining),
        'office': l.office or '', 'loan_type': l.loan_type or '', 'date': _str(l.application_date),
    } for l in qs.order_by('-repayment_amount_remaining')]

    return Response({'total_outstanding': _d(agg['total']), 'count': agg['count'] or 0, 'loans': items})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def report_overdue_loans(request):
    """GET /api/reports/overdue-loans/"""
    filter_office = get_filter_office(request)
    today = date.today()
    qs = LoanApplication.objects.select_related('client').filter(
        repayment_amount_remaining__gt=0, first_repayment_date__lt=today,
    )
    if filter_office: qs = qs.filter(office=filter_office.name)

    items = [{
        'id': l.id, 'client_name': f"{l.client.firstname} {l.client.lastname}",
        'phone': l.client.phonenumber or '', 'outstanding': _d(l.repayment_amount_remaining),
        'office': l.office or '',
        'overdue_days': (today - l.first_repayment_date).days if l.first_repayment_date else 0,
        'due_date': _str(l.first_repayment_date),
    } for l in qs.order_by('first_repayment_date')]

    return Response({
        'count': len(items),
        'total_outstanding': _d(qs.aggregate(t=Sum('repayment_amount_remaining'))['t']),
        'loans': items,
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def report_expenses(request):
    # GET /api/reports/expenses/?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD
    # Groups by ExpenseCategory (Account Name) - matches web expenses statement
    # Table: S/N | Account Name | Amount (blank = no expenses that category/period)
    d_from, d_to, err = _parse_dates(request)
    if err: return Response({'error': err}, status=400)

    filter_office = get_filter_office(request)
    qs = Expense.objects.select_related('transaction_type').filter(
        expense_date__gte=d_from, expense_date__lte=d_to,
    )
    if filter_office:
        qs = qs.filter(office=filter_office.name)

    grand_total_agg = qs.aggregate(
        total=Coalesce(Sum('amount'), Decimal('0')), count=Count('id')
    )

    # GROUP BY ExpenseCategory - only categories with expenses in range
    category_map = {
        r['transaction_type_id']: _d(r['total'])
        for r in qs.filter(transaction_type__isnull=False)
            .values('transaction_type_id')
            .annotate(total=Coalesce(Sum('amount'), Decimal('0')))
    }

    # ALL registered expense categories (including zero-expense ones = blank cell)
    from app.models import ExpenseCategory
    all_categories = ExpenseCategory.objects.all().order_by('name')
    category_summary = []
    for i, cat in enumerate(all_categories, 1):
        total = category_map.get(cat.id, None)
        category_summary.append({
            'sn':           i,
            'account_name': cat.name,
            'amount':       _d(total) if total is not None else None,
            'has_expense':  total is not None,
        })

    # Uncategorised expenses (transaction_type is null)
    uncat = qs.filter(transaction_type__isnull=True).aggregate(
        total=Coalesce(Sum('amount'), Decimal('0')), count=Count('id')
    )
    if uncat['count'] > 0:
        category_summary.append({
            'sn':           len(category_summary) + 1,
            'account_name': 'Uncategorised',
            'amount':       _d(uncat['total']),
            'has_expense':  True,
        })

    # Per-branch summary (ALL offices, even zero) for HQ context
    office_map = {
        r['office']: _d(r['total'])
        for r in qs.values('office').annotate(total=Coalesce(Sum('amount'), Decimal('0')))
    }
    all_offices = Office.objects.exclude(name__iexact='HQ').order_by('name')
    branch_summary = []
    for i, office in enumerate(all_offices, 1):
        total = office_map.get(office.name, None)
        branch_summary.append({
            'sn':          i,
            'branch':      office.name,
            'amount':      _d(total) if total is not None else None,
            'has_expense': total is not None,
        })

    return Response({
        'date_from':        _str(d_from),
        'date_to':          _str(d_to),
        'grand_total':      _d(grand_total_agg['total']),
        'count':            grand_total_agg['count'] or 0,
        'category_summary': category_summary,
        'branch_summary':   branch_summary,
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def report_financial(request):
    """GET /api/reports/financial/?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD"""
    d_from, d_to, err = _parse_dates(request)
    if err: return Response({'error': err}, status=400)

    filter_office = get_filter_office(request)
    loans_qs = LoanApplication.objects.filter(application_date__gte=d_from, application_date__lte=d_to)
    repay_qs = LoanRepayment.objects.filter(repayment_date__gte=d_from, repayment_date__lte=d_to)
    exp_qs   = Expense.objects.filter(expense_date__gte=d_from, expense_date__lte=d_to)

    if filter_office:
        loans_qs = loans_qs.filter(office=filter_office.name)
        repay_qs = repay_qs.filter(loan_application__office=filter_office.name)
        exp_qs   = exp_qs.filter(office=filter_office.name)

    return Response({
        'date_from': _str(d_from), 'date_to': _str(d_to),
        'total_loans':      _d(loans_qs.aggregate(t=Sum('loan_amount'))['t']),
        'total_repayments': _d(repay_qs.aggregate(t=Sum('repayment_amount'))['t']),
        'total_expenses':   _d(exp_qs.aggregate(t=Sum('amount'))['t']),
        'loans_count':      loans_qs.count(),
        'repayments_count': repay_qs.count(),
        'expenses_count':   exp_qs.count(),
    })


# =============================================================================
#  LOAN COLLECTION STATEMENT
# =============================================================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_loan_collection(request):
    """GET /api/loan-collection/?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD"""
    d_from, d_to, err = _parse_dates(request)
    if err: return Response({'error': err}, status=400)

    filter_office = get_filter_office(request)
    dt_from = datetime.datetime.combine(d_from, datetime.time.min)
    dt_to   = datetime.datetime.combine(d_to,   datetime.time.max)

    repayments = LoanRepayment.objects.filter(
        created_at__range=(dt_from, dt_to),
    ).select_related('loan_application__client').order_by('created_at')
    if filter_office:
        repayments = repayments.filter(loan_application__office=filter_office.name)

    rows = []
    grand_total = Decimal('0')
    for r in repayments:
        loan   = r.loan_application
        client = loan.client
        rows.append({
            'date':       str(r.created_at.date()),
            'receipt_no': str(r.id).zfill(6),
            'name':       f"{client.firstname} {client.lastname}",
            'description':'Loan payment',
            'amount':     _d(r.repayment_amount),
            'rate':       _d(loan.interest_rate or 0),
        })
        grand_total += r.repayment_amount

    return Response({'rows': rows, 'grand_total': _d(grand_total)})


# =============================================================================
#  NO LOAN CUSTOMERS
# =============================================================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_no_loan_customers(request):
    # GET /api/no-loan-customers/
    # Mirrors no_loan_customers() web view exactly:
    #   - Clients with NO loans at all
    #   - Clients whose ALL loans are fully paid (remaining = 0)
    #   - Sorted by firstname, lastname (matches web ORDER BY)
    #   - Returns: S/N, Name (full with middlename), Check no, Contact
    filter_office = get_filter_office(request)
    selected      = get_selected_office_api(request)

    base_qs = Client.objects.all()
    if filter_office:
        base_qs = base_qs.filter(registered_office=filter_office)

    # Clients with NO loans at all
    clients_no_loans = base_qs.filter(loan_applications__isnull=True).distinct()

    # Clients whose ALL loans are fully paid
    clients_all_paid = base_qs.exclude(
        loan_applications__repayment_amount_remaining__gt=0
    ).exclude(loan_applications__isnull=True).distinct()

    all_ids = set(
        list(clients_no_loans.values_list('id', flat=True)) +
        list(clients_all_paid.values_list('id', flat=True))
    )

    # Web sorts: firstname, lastname
    clients = Client.objects.filter(
        id__in=all_ids
    ).order_by('firstname', 'lastname')

    rows = []
    for i, c in enumerate(clients, 1):
        full_name = ' '.join(filter(None, [
            c.firstname,
            getattr(c, 'middlename', '') or '',
            c.lastname,
        ])).upper()  # screenshot shows names in uppercase
        rows.append({
            'sn':       i,
            'id':       c.id,
            'name':     full_name,
            'check_no': c.checkno or getattr(c, 'employmentcardno', '') or '0',
            'contact':  c.phonenumber or '—',
        })

    branch_name = (filter_office.name.upper() if filter_office
                   else selected.name.upper() if selected else 'ALL BRANCHES')

    return Response({
        'count':       len(rows),
        'branch_name': branch_name,
        'clients':     rows,
    })


# =============================================================================
#  BRANCH TRANSACTION STATEMENT
# =============================================================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_branch_transactions(request):
    # GET /api/branch-transactions/?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD
    # Mirrors branch_transaction_statement_report() web view exactly.
    # Uses created_at__gte/lte (not __range), processed_at for HQ sort,
    # deletable = not repayments.exists() and not topups.exists() for loans,
    # old_balance = t.old_balance_cleared or t.loan_application.repayment_amount_remaining
    import pytz
    from django.utils import timezone as dj_tz
    from datetime import timezone as py_tz
    from django.db.models import F

    d_from, d_to, err = _parse_dates(request)
    if err: return Response({'error': err}, status=400)

    filter_office = get_filter_office(request)
    selected      = get_selected_office_api(request)
    office_name   = filter_office.name if filter_office else None

    date_from_dt = datetime.datetime.combine(d_from, datetime.time.min)
    date_to_dt   = datetime.datetime.combine(d_to,   datetime.time.max)

    _epoch = datetime.datetime(2000, 1, 1, tzinfo=py_tz.utc)

    def _aware(dt):
        if dt is None: return _epoch
        if dj_tz.is_naive(dt): return dj_tz.make_aware(dt, pytz.UTC)
        return dt

    def _name(user):
        if not user: return ''
        parts = [getattr(user,'first_name',''), getattr(user,'last_name','')]
        return ' '.join(p for p in parts if p) or getattr(user,'username','')

    raw = []

    # ── 1. Loan Repayments (CREDIT) ───────────────────────────────────
    rep_qs = LoanRepayment.objects.filter(
        created_at__gte=date_from_dt,
        created_at__lte=date_to_dt,
    ).select_related('loan_application__client', 'processed_by').order_by('created_at', 'id')
    if office_name:
        rep_qs = rep_qs.filter(loan_application__office=office_name)
    for r in rep_qs:
        c = r.loan_application.client
        raw.append({
            'created_at':  _aware(r.created_at), 'sort_sub': 0,
            'record_type': 'repayment', 'record_id': r.id,
            'date':        r.created_at,
            'receipt_no':  str(r.id).zfill(6),
            'name':        f"{c.firstname} {c.middlename or ''} {c.lastname}".strip(),
            'description': 'Loan payment', 'description_bold': False, 'is_expense': False,
            'credit':      r.repayment_amount, 'debit': None,
            'processed_by':_name(r.processed_by), 'deletable': True,
        })

    # ── 2. Loan Top-ups ───────────────────────────────────────────────
    topup_qs = LoanTopup.objects.filter(
        created_at__gte=date_from_dt,
        created_at__lte=date_to_dt,
    ).select_related('loan_application__client', 'processed_by').order_by('created_at', 'id')
    if office_name:
        topup_qs = topup_qs.filter(loan_application__office=office_name)
    topup_loan_ids = set()
    for t in topup_qs:
        topup_loan_ids.add(t.loan_application_id)
        c           = t.loan_application.client
        # Web: old_balance = t.old_balance_cleared OR loan.repayment_amount_remaining
        old_balance = t.old_balance_cleared or t.loan_application.repayment_amount_remaining
        cname       = f"{c.firstname} {c.middlename or ''} {c.lastname}".strip()
        officer     = _name(t.processed_by)
        ts          = _aware(t.created_at)
        if old_balance and old_balance > 0:
            raw.append({
                'created_at': ts, 'sort_sub': 1,
                'record_type': 'topup', 'record_id': t.id,
                'date': t.created_at, 'receipt_no': str(t.id).zfill(6),
                'name': cname, 'description': 'Clearance loan balance for top-up',
                'description_bold': False, 'is_expense': False,
                'credit': old_balance, 'debit': None,
                'processed_by': officer, 'deletable': True,
            })
        raw.append({
            'created_at': ts, 'sort_sub': 2,
            'record_type': 'topup', 'record_id': t.id,
            'date': t.created_at, 'receipt_no': str(t.id).zfill(6),
            'name': cname, 'description': 'Loan amount deposited to customer',
            'description_bold': False, 'is_expense': False,
            'credit': None, 'debit': t.topup_amount,
            'processed_by': officer, 'deletable': False,
        })

    # ── 3. New Loan Disbursements (DEBIT) — skip topup loans ──────────
    loan_qs = LoanApplication.objects.filter(
        created_at__gte=date_from_dt,
        created_at__lte=date_to_dt,
    ).select_related('client', 'processed_by').order_by('created_at', 'id')
    if office_name:
        loan_qs = loan_qs.filter(office=office_name)
    for loan in loan_qs:
        if loan.id in topup_loan_ids:
            continue
        c = loan.client
        raw.append({
            'created_at': _aware(loan.created_at), 'sort_sub': 0,
            'record_type': 'loan', 'record_id': loan.id,
            'date': loan.created_at, 'receipt_no': str(loan.id).zfill(6),
            'name': f"{c.firstname} {c.middlename or ''} {c.lastname}".strip(),
            'description': 'Loan amount deposited to customer',
            'description_bold': False, 'is_expense': False,
            'credit': None, 'debit': loan.loan_amount,
            'processed_by': _name(loan.processed_by),
            # Web: deletable only if no repayments AND no topups
            'deletable': not loan.repayments.exists() and not loan.topups.exists(),
        })

    # ── 4. Expenses (DEBIT) ───────────────────────────────────────────
    exp_qs = Expense.objects.filter(
        created_at__gte=date_from_dt,
        created_at__lte=date_to_dt,
    ).select_related('recorded_by', 'transaction_type').order_by('created_at', 'id')
    if office_name:
        exp_qs = exp_qs.filter(office=office_name)
    for exp in exp_qs:
        cat = exp.transaction_type.name if exp.transaction_type else 'Expense'
        raw.append({
            'created_at': _aware(exp.created_at), 'sort_sub': 0,
            'record_type': 'expense', 'record_id': exp.id,
            'date': exp.created_at, 'receipt_no': str(exp.id).zfill(6),
            'name': _name(exp.recorded_by),
            'description': f"{cat} [{exp.description}],",   # web appends comma
            'description_bold': True, 'is_expense': True,
            'credit': None, 'debit': exp.amount,
            'processed_by': _name(exp.recorded_by), 'deletable': True,
        })

    # ── 5. Salaries (DEBIT) ───────────────────────────────────────────
    sal_qs = Salary.objects.filter(
        created_at__gte=date_from_dt,
        created_at__lte=date_to_dt,
    ).select_related('employee', 'processed_by').order_by('created_at', 'id')
    if filter_office:
        sal_qs = sal_qs.filter(fund_source=filter_office)
    elif office_name:
        sal_qs = sal_qs.filter(fund_source__name=office_name)
    for sal in sal_qs:
        raw.append({
            'created_at': _aware(sal.created_at), 'sort_sub': 0,
            'record_type': 'salary', 'record_id': sal.id,
            'date': sal.created_at, 'receipt_no': str(sal.id).zfill(6),
            'name': _name(sal.employee), 'description': 'Salary payment',
            'description_bold': False, 'is_expense': False,
            'credit': None, 'debit': sal.amount,
            'processed_by': _name(sal.processed_by), 'deletable': True,
        })

    # ── 6. Bank Charges (DEBIT) ───────────────────────────────────────
    bc_qs = BankCharge.objects.filter(
        created_at__gte=date_from_dt,
        created_at__lte=date_to_dt,
    ).select_related('recorded_by').order_by('created_at', 'id')
    if office_name:
        bc_qs = bc_qs.filter(office=office_name)
    for bc in bc_qs:
        raw.append({
            'created_at': _aware(bc.created_at), 'sort_sub': 0,
            'record_type': 'bankcharge', 'record_id': bc.id,
            'date': bc.created_at, 'receipt_no': str(bc.id).zfill(6),
            'name': _name(bc.recorded_by),
            'description': f"Bank Charge [{bc.description}]",
            'description_bold': True, 'is_expense': True,
            'credit': None, 'debit': bc.amount,
            'processed_by': _name(bc.recorded_by), 'deletable': True,
        })

    # ── 7. HQ Transfers — sorted by processed_at (matches web) ────────
    try:
        hq_qs = HQTransaction.objects.filter(
            created_at__gte=date_from_dt,
            created_at__lte=date_to_dt,
        ).exclude(
            from_branch=F('to_branch')
        ).select_related(
            'from_branch', 'to_branch', 'processed_by'
        ).order_by('processed_at', 'id')   # ← web uses processed_at
        if office_name:
            hq_qs = hq_qs.filter(
                Q(from_branch__name=office_name) | Q(to_branch__name=office_name))
        for hq in hq_qs:
            officer = _name(hq.processed_by)
            ts      = _aware(hq.processed_at)   # ← web uses processed_at for sort
            hq_date = hq.created_at             # ← display date = created_at
            is_recv = (hq.to_branch   and hq.to_branch.name   == office_name) if office_name else True
            is_sent = (hq.from_branch and hq.from_branch.name == office_name) if office_name else False
            if is_recv:
                from_lbl = hq.from_branch.name if hq.from_branch else 'HQ'
                raw.append({
                    'created_at': ts, 'sort_sub': 1,
                    'record_type': 'hq', 'record_id': hq.id,
                    'date': hq_date, 'receipt_no': str(hq.id).zfill(6),
                    'name': from_lbl,
                    'description': f"Transfer received from {from_lbl}",
                    'description_bold': False, 'is_expense': False,
                    'credit': hq.amount, 'debit': None,
                    'processed_by': officer, 'deletable': True,
                })
            if is_sent:
                to_lbl = hq.to_branch.name if hq.to_branch else 'HQ'
                raw.append({
                    'created_at': ts, 'sort_sub': 2,
                    'record_type': 'hq', 'record_id': hq.id,
                    'date': hq_date, 'receipt_no': str(hq.id).zfill(6),
                    'name': to_lbl,
                    'description': f"Transfer sent to {to_lbl}",
                    'description_bold': False, 'is_expense': True,
                    'credit': None, 'debit': hq.amount,
                    'processed_by': officer, 'deletable': False,
                })
    except Exception:
        pass

    # ── Sort: date → created_at → sort_sub ───────────────────────────
    raw.sort(key=lambda e: (e['date'], e['created_at'], e['sort_sub']))

    # ── Annotate hide_date (web logic) ────────────────────────────────
    prev_date = None
    for entry in raw:
        entry_date = entry['date'].date() if hasattr(entry['date'], 'date') else entry['date']
        entry['hide_date'] = (entry_date == prev_date)
        prev_date = entry_date
        entry['date'] = str(entry_date)
        entry['credit'] = _d(entry['credit']) if entry['credit'] else None
        entry['debit']  = _d(entry['debit'])  if entry['debit']  else None
        del entry['created_at']

    grand_credit = _d(sum(Decimal(str(e['credit'])) for e in raw if e['credit']))
    grand_debit  = _d(sum(Decimal(str(e['debit']))  for e in raw if e['debit']))

    return Response({
        'branch':       selected.name if selected else office_name or 'All',
        'branch_name':  (selected.name if selected else office_name or 'All').upper(),
        'date_from':    str(d_from),
        'date_to':      str(d_to),
        'rows':         raw,
        'grand_credit': grand_credit,
        'grand_debit':  grand_debit,
    })

# =============================================================================
#  SUMMARY REPORTS
# =============================================================================

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_loans_issued_summary(request):
    # GET /api/reports/loans-issued-summary/?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD
    # Mirrors loans_issued_report_result() web view exactly:
    #   - Uses created_at with timezone-aware range (EAT = UTC+3), not application_date
    #   - Filters client__isnull=False to skip orphan loans
    #   - Includes ALL non-HQ offices (zero-loan branches show zeros)
    #   - Also appends orphan office names found in loan data but not in Office table
    from django.utils import timezone as tz
    import datetime as _dt

    d_from, d_to, err = _parse_dates(request)
    if err: return Response({'error': err}, status=400)

    # Timezone-aware datetime range (EAT = UTC+3)
    start_dt = tz.make_aware(_dt.datetime.combine(d_from, _dt.time.min))
    end_dt   = tz.make_aware(_dt.datetime.combine(d_to,   _dt.time.max))

    # GROUP BY office - same annotations as web view
    # Filter: timezone-aware range on created_at + client must exist
    loan_data = {
        row['office']: row
        for row in (
            LoanApplication.objects
            .filter(
                created_at__gte=start_dt,
                created_at__lte=end_dt,
                client__isnull=False,
            )
            .values('office')
            .annotate(
                no_of_loans     = Count('id'),
                loaned_amount   = Coalesce(Sum('loan_amount'),           Decimal('0')),
                interest_amount = Coalesce(Sum('total_interest_amount'), Decimal('0')),
                total_return    = Coalesce(Sum('total_repayment_amount'),Decimal('0')),
            )
            .order_by('office')
        )
    }

    # All non-HQ registered offices (including zero-loan branches)
    all_office_names = list(
        Office.objects.exclude(name__iexact='HQ')
        .values_list('name', flat=True)
        .order_by('name')
    )
    known_names = set(all_office_names)

    summary = []
    for office_name in all_office_names:
        row = loan_data.get(office_name)
        summary.append({
            'branch':          office_name,
            'no_of_loans':     row['no_of_loans']              if row else 0,
            'loaned_amount':   _d(row['loaned_amount'])        if row else 0.0,
            'interest_amount': _d(row['interest_amount'])      if row else 0.0,
            'total_return':    _d(row['total_return'])         if row else 0.0,
        })

    # Append orphan office names (in loan data but not in Office table, skip HQ)
    for office_name, row in loan_data.items():
        if office_name not in known_names and (office_name or '').upper() != 'HQ':
            summary.append({
                'branch':          office_name or 'N/A',
                'no_of_loans':     row['no_of_loans'],
                'loaned_amount':   _d(row['loaned_amount']),
                'interest_amount': _d(row['interest_amount']),
                'total_return':    _d(row['total_return']),
            })

    # Sort alphabetically (matches web view)
    summary.sort(key=lambda r: r['branch'])

    # Add S/N after sort
    for i, row in enumerate(summary, 1):
        row['sn'] = i

    totals = {
        'no_of_loans':     sum(r['no_of_loans']                       for r in summary),
        'loaned_amount':   _d(sum(Decimal(str(r['loaned_amount']))   for r in summary)),
        'interest_amount': _d(sum(Decimal(str(r['interest_amount'])) for r in summary)),
        'total_return':    _d(sum(Decimal(str(r['total_return']))    for r in summary)),
    }

    return Response({
        'date_from': str(d_from),
        'date_to':   str(d_to),
        'branches':  summary,
        'totals':    totals,
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_monthly_outstanding_summary(request):
    """GET /api/reports/monthly-outstanding-summary/?month=YYYY-MM-DD"""
    import calendar as cal_mod
    month_str = request.GET.get('month', '')
    try:
        selected_date = datetime.datetime.strptime(month_str, '%Y-%m-%d').date()
    except Exception:
        selected_date = date.today()

    last_day = cal_mod.monthrange(selected_date.year, selected_date.month)[1]
    end_of_month = selected_date.replace(day=last_day)
    qs = LoanApplication.objects.filter(
        application_date__lte=end_of_month, repayment_amount_remaining__gt=Decimal('0'),
    )
    branch_data = (
        qs.values('office').annotate(
            no_of_loans=Count('id'),
            outstanding_amount=Coalesce(Sum('repayment_amount_remaining'), Decimal('0')),
        ).order_by('office')
    )
    summary = [{'branch': r['office'] or 'N/A', 'no_of_loans': r['no_of_loans'],
                'outstanding_amount': _d(r['outstanding_amount'])} for r in branch_data]
    return Response({
        'month': str(selected_date), 'branches': summary,
        'totals': {
            'no_of_loans':       sum(r['no_of_loans'] for r in summary),
            'outstanding_amount': _d(sum(Decimal(str(r['outstanding_amount'])) for r in summary)),
        }
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_expired_loans_summary(request):
    """GET /api/reports/expired-loans-summary/"""
    today = date.today()
    expired_qs = LoanApplication.objects.filter(
        first_repayment_date__lt=today, repayment_amount_remaining__gt=Decimal('0'),
    ).values('office', 'loan_amount', 'repayment_amount_remaining', 'first_repayment_date')

    branch_map = {}
    for loan in expired_qs:
        branch = loan['office'] or 'N/A'
        days   = (today - loan['first_repayment_date']).days if loan['first_repayment_date'] else 999
        cls = 'current' if days <= 30 else 'esm' if days <= 60 else 'substandard' if days <= 90 else 'doubtful' if days <= 180 else 'loss'
        if branch not in branch_map:
            branch_map[branch] = {'branch': branch, 'loan_issued': Decimal('0'),
                'outstanding': Decimal('0'), 'current': 0, 'esm': 0, 'substandard': 0, 'doubtful': 0, 'loss': 0}
        branch_map[branch]['loan_issued'] += Decimal(str(loan['loan_amount']))
        branch_map[branch]['outstanding'] += Decimal(str(loan['repayment_amount_remaining']))
        branch_map[branch][cls] += 1

    summary = []
    for row in sorted(branch_map.values(), key=lambda x: x['branch']):
        row['total']       = row['current'] + row['esm'] + row['substandard'] + row['doubtful'] + row['loss']
        row['loan_issued'] = _d(row['loan_issued'])
        row['outstanding'] = _d(row['outstanding'])
        summary.append(row)
    return Response({'branches': summary, 'today': str(today)})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_branch_financial_summary(request):
    # GET /api/reports/branch-financial/?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD
    # Mirrors branch_financial_summary() web view exactly.
    # Returns cross-tab: rows = financial items, columns = branches + TOTAL
    # Rows: Opening Balance, MAPATO, NYONGEZA, HAZINA,
    #       Income Subtotal, FOMU, MATUMIZI OFISINI,
    #       MATUMIZI BENKI-[KITUO], MATUMIZI BENKI-[MKURUGENZI], MAKATO BANK,
    #       Outflow Subtotal, BALANCE CASH, BALANCE BENKI, Balance Total
    from django.utils import timezone as tz
    import datetime as _dt

    start_str = request.GET.get('start_date', '')
    end_str   = request.GET.get('end_date',   '')
    try:
        start_date = _dt.datetime.strptime(start_str, '%Y-%m-%d').date()
        end_date   = _dt.datetime.strptime(end_str,   '%Y-%m-%d').date()
    except Exception:
        today = date.today()
        start_date = today.replace(day=1)
        end_date   = today

    start_dt  = tz.make_aware(_dt.datetime.combine(start_date, _dt.time.min))
    end_dt    = tz.make_aware(_dt.datetime.combine(end_date,   _dt.time.max))
    before_dt = start_dt

    def _s(qs, field='amount'):
        return qs.aggregate(t=Sum(field))['t'] or Decimal('0')

    offices = list(Office.objects.exclude(name__iexact='HQ').order_by('name'))

    # ── Row accumulators (totals across all branches) ─────────────────────────
    ROW_KEYS = [
        'opening_balance', 'mapato', 'nyongeza', 'hazina',
        'income_subtotal',
        'fomu', 'matumizi_ofisini', 'matumizi_kituo', 'matumizi_mkurugenzi', 'makato_benki',
        'outflow_subtotal',
        'balance_cash', 'balance_benki', 'balance_total',
    ]
    totals = {k: Decimal('0') for k in ROW_KEYS}
    branch_data = []   # list of dicts, one per office

    for office in offices:
        d = {}   # this office's values

        # ── OPENING BALANCE ───────────────────────────────────────────────────
        rep_b        = _s(LoanRepayment.objects.filter(loan_application__office=office.name, repayment_date__lt=start_date).exclude(loan_application__loan_type__iexact='Hazina'), 'repayment_amount')
        haz_rep_b    = _s(LoanRepayment.objects.filter(loan_application__office=office.name, repayment_date__lt=start_date, loan_application__loan_type__iexact='Hazina'), 'repayment_amount')
        nyo_b        = _s(Nyongeza.objects.filter(Office=office, date__lt=start_date))
        trx_in_b     = _s(OfficeTransaction.objects.filter(office_to=office, transaction_date__lt=start_date))
        exp_b        = _s(Expense.objects.filter(office=office.name, expense_date__lt=start_date))
        loan_b       = _s(LoanApplication.objects.filter(office=office.name, created_at__lt=before_dt), 'loan_amount')
        trx_out_b    = _s(OfficeTransaction.objects.filter(office_from=office, transaction_date__lt=start_date))
        bank_chg_b   = _s(BankCharge.objects.filter(office=office.name, expense_date__lt=start_date))

        opening_balance = (rep_b + haz_rep_b + nyo_b + trx_in_b) - (exp_b + loan_b + trx_out_b + bank_chg_b)
        d['opening_balance'] = opening_balance

        # ── PERIOD INCOME ─────────────────────────────────────────────────────
        mapato = _s(LoanRepayment.objects.filter(
            loan_application__office=office.name,
            repayment_date__gte=start_date, repayment_date__lte=end_date,
        ).exclude(loan_application__loan_type__iexact='Hazina'), 'repayment_amount')
        d['mapato'] = mapato

        hazina = _s(LoanRepayment.objects.filter(
            loan_application__office=office.name,
            repayment_date__gte=start_date, repayment_date__lte=end_date,
            loan_application__loan_type__iexact='Hazina',
        ), 'repayment_amount')
        d['hazina'] = hazina

        nyongeza = _s(Nyongeza.objects.filter(Office=office, date__gte=start_date, date__lte=end_date))
        d['nyongeza'] = nyongeza

        transfers_in = _s(OfficeTransaction.objects.filter(office_to=office, transaction_date__gte=start_date, transaction_date__lte=end_date))
        d['transfers_in'] = transfers_in

        income_subtotal = opening_balance + mapato + nyongeza + transfers_in
        d['income_subtotal'] = income_subtotal

        # ── PERIOD OUTFLOW ────────────────────────────────────────────────────
        fomu = _s(LoanApplication.objects.filter(office=office.name, created_at__gte=start_dt, created_at__lte=end_dt), 'loan_amount')
        d['fomu'] = fomu

        matumizi_ofisini = _s(Expense.objects.filter(office=office.name, expense_date__gte=start_date, expense_date__lte=end_date))
        d['matumizi_ofisini'] = matumizi_ofisini

        matumizi_kituo = _s(OfficeTransaction.objects.filter(
            office_from=office, transaction_date__gte=start_date, transaction_date__lte=end_date,
        ).exclude(office_to__name__iexact='HQ'))
        d['matumizi_kituo'] = matumizi_kituo

        matumizi_mkurugenzi = _s(OfficeTransaction.objects.filter(
            office_from=office, transaction_date__gte=start_date, transaction_date__lte=end_date,
            office_to__name__iexact='HQ',
        ))
        d['matumizi_mkurugenzi'] = matumizi_mkurugenzi

        makato_benki = _s(BankCharge.objects.filter(office=office.name, expense_date__gte=start_date, expense_date__lte=end_date))
        d['makato_benki'] = makato_benki

        outflow_subtotal = fomu + matumizi_ofisini + matumizi_kituo + matumizi_mkurugenzi + makato_benki
        d['outflow_subtotal'] = outflow_subtotal

        # ── CLOSING BALANCES (cash vs bank split) ─────────────────────────────
        # Opening cash — BankCashTransaction is optional; skip if model missing
        try:
            cash_to_bank_b = _s(BankCashTransaction.objects.filter(office_from=office, transaction_date__lt=start_date, source__iexact='cash', destination__iexact='bank'))
            bank_to_cash_b = _s(BankCashTransaction.objects.filter(office_from=office, transaction_date__lt=start_date, source__iexact='bank', destination__iexact='cash'))
        except Exception:
            cash_to_bank_b = Decimal('0')
            bank_to_cash_b = Decimal('0')
        cash_rep_b  = _s(LoanRepayment.objects.filter(loan_application__office=office.name, repayment_date__lt=start_date, transaction_method__iexact='cash').exclude(loan_application__loan_type__iexact='Hazina'), 'repayment_amount')
        cash_haz_b  = _s(LoanRepayment.objects.filter(loan_application__office=office.name, repayment_date__lt=start_date, loan_application__loan_type__iexact='Hazina', transaction_method__iexact='cash'), 'repayment_amount')
        cash_nyo_b  = _s(Nyongeza.objects.filter(Office=office, date__lt=start_date, deposit_method__iexact='cash'))
        cash_exp_b  = _s(Expense.objects.filter(office=office.name, expense_date__lt=start_date, payment_method__iexact='cash'))
        cash_loan_b = _s(LoanApplication.objects.filter(office=office.name, created_at__lt=before_dt, transaction_method__iexact='cash'), 'loan_amount')
        cash_chg_b  = _s(BankCharge.objects.filter(office=office.name, expense_date__lt=start_date, payment_method__iexact='cash'))
        opening_cash = (cash_rep_b + cash_haz_b + cash_nyo_b + bank_to_cash_b) - (cash_exp_b + cash_loan_b + cash_chg_b + cash_to_bank_b)

        bank_rep_b   = _s(LoanRepayment.objects.filter(loan_application__office=office.name, repayment_date__lt=start_date, transaction_method__iexact='bank').exclude(loan_application__loan_type__iexact='Hazina'), 'repayment_amount')
        bank_haz_b   = _s(LoanRepayment.objects.filter(loan_application__office=office.name, repayment_date__lt=start_date, loan_application__loan_type__iexact='Hazina', transaction_method__iexact='bank'), 'repayment_amount')
        bank_nyo_b   = _s(Nyongeza.objects.filter(Office=office, date__lt=start_date, deposit_method__iexact='bank'))
        bank_trxin_b = _s(OfficeTransaction.objects.filter(office_to=office, transaction_date__lt=start_date))
        bank_exp_b   = _s(Expense.objects.filter(office=office.name, expense_date__lt=start_date, payment_method__iexact='bank'))
        bank_loan_b  = _s(LoanApplication.objects.filter(office=office.name, created_at__lt=before_dt, transaction_method__iexact='bank'), 'loan_amount')
        bank_out_b   = _s(OfficeTransaction.objects.filter(office_from=office, transaction_date__lt=start_date))
        bank_chg_b2  = _s(BankCharge.objects.filter(office=office.name, expense_date__lt=start_date, payment_method__iexact='bank'))
        opening_bank = (bank_rep_b + bank_haz_b + bank_nyo_b + bank_trxin_b + cash_to_bank_b) - (bank_exp_b + bank_loan_b + bank_out_b + bank_chg_b2 + bank_to_cash_b)

        # Period cash — BankCashTransaction is optional; skip if model missing
        try:
            cash_to_bank_p = _s(BankCashTransaction.objects.filter(office_from=office, transaction_date__gte=start_date, transaction_date__lte=end_date, source__iexact='cash', destination__iexact='bank'))
            bank_to_cash_p = _s(BankCashTransaction.objects.filter(office_from=office, transaction_date__gte=start_date, transaction_date__lte=end_date, source__iexact='bank', destination__iexact='cash'))
        except Exception:
            cash_to_bank_p = Decimal('0')
            bank_to_cash_p = Decimal('0')
        cash_rep_p  = _s(LoanRepayment.objects.filter(loan_application__office=office.name, repayment_date__gte=start_date, repayment_date__lte=end_date, transaction_method__iexact='cash').exclude(loan_application__loan_type__iexact='Hazina'), 'repayment_amount')
        cash_nyo_p  = _s(Nyongeza.objects.filter(Office=office, date__gte=start_date, date__lte=end_date, deposit_method__iexact='cash'))
        cash_loan_p = _s(LoanApplication.objects.filter(office=office.name, created_at__gte=start_dt, created_at__lte=end_dt, transaction_method__iexact='cash'), 'loan_amount')
        cash_exp_p  = _s(Expense.objects.filter(office=office.name, expense_date__gte=start_date, expense_date__lte=end_date, payment_method__iexact='cash'))
        cash_chg_p  = _s(BankCharge.objects.filter(office=office.name, expense_date__gte=start_date, expense_date__lte=end_date, payment_method__iexact='cash'))
        bal_cash = (opening_cash + cash_rep_p + cash_nyo_p + bank_to_cash_p) - (cash_loan_p + cash_exp_p + cash_chg_p + cash_to_bank_p)

        bank_rep_p   = _s(LoanRepayment.objects.filter(loan_application__office=office.name, repayment_date__gte=start_date, repayment_date__lte=end_date, transaction_method__iexact='bank').exclude(loan_application__loan_type__iexact='Hazina'), 'repayment_amount')
        bank_nyo_p   = _s(Nyongeza.objects.filter(Office=office, date__gte=start_date, date__lte=end_date, deposit_method__iexact='bank'))
        bank_trxin_p = _s(OfficeTransaction.objects.filter(office_to=office, transaction_date__gte=start_date, transaction_date__lte=end_date))
        bank_loan_p  = _s(LoanApplication.objects.filter(office=office.name, created_at__gte=start_dt, created_at__lte=end_dt, transaction_method__iexact='bank'), 'loan_amount')
        bank_exp_p   = _s(Expense.objects.filter(office=office.name, expense_date__gte=start_date, expense_date__lte=end_date, payment_method__iexact='bank'))
        bank_out_p   = _s(OfficeTransaction.objects.filter(office_from=office, transaction_date__gte=start_date, transaction_date__lte=end_date))
        bank_chg_p   = _s(BankCharge.objects.filter(office=office.name, expense_date__gte=start_date, expense_date__lte=end_date, payment_method__iexact='bank'))
        bal_bank = (opening_bank + bank_rep_p + bank_nyo_p + bank_trxin_p + cash_to_bank_p) - (bank_loan_p + bank_exp_p + bank_out_p + bank_chg_p + bank_to_cash_p)

        d['balance_cash']  = bal_cash
        d['balance_benki'] = bal_bank
        d['balance_total'] = bal_cash + bal_bank

        # Accumulate totals
        for k in ROW_KEYS:
            totals[k] += d.get(k, Decimal('0'))

        branch_data.append({'office': office.name, 'office_id': office.id, **{k: _d(d[k]) for k in ROW_KEYS}})

    return Response({
        'start_date':   str(start_date),
        'end_date':     str(end_date),
        'offices':      [o.name for o in offices],
        'branches':     branch_data,
        'totals':       {k: _d(totals[k]) for k in ROW_KEYS},
        'row_labels': {
            'opening_balance':     'Opening Balance',
            'mapato':              'MAPATO',
            'nyongeza':            'NYONGEZA',
            'hazina':              'HAZINA',
            'income_subtotal':     'Income Subtotal',
            'fomu':                'FOMU',
            'matumizi_ofisini':    'MATUMIZI OFISINI',
            'matumizi_kituo':      'MATUMIZI BENKI-[KITUO]',
            'matumizi_mkurugenzi': 'MATUMIZI BENKI-[MKURUGENZI]',
            'makato_benki':        'MAKATO BANK',
            'outflow_subtotal':    'Outflow Subtotal',
            'balance_cash':        'BALANCE CASH',
            'balance_benki':       'BALANCE BENKI',
            'balance_total':       'Balance Total',
        }
    })


# =============================================================================
#  MOBILE API ADDITIONS
#  All 14 new endpoints + 6 staff/office management functions
# =============================================================================

import calendar as cal_module
from decimal import Decimal


def _d(val):
    try: return float(val or 0)
    except: return 0.0

def _str(val):
    return str(val) if val is not None else ''


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_nyongeza_add(request):
    amount_raw     = request.data.get('amount')
    deposit_method = request.data.get('deposit_method', 'cash')
    description    = request.data.get('description', '')

    if not amount_raw:
        return Response({'detail': 'amount inahitajika.'}, status=400)
    try:
        amount_decimal = Decimal(str(amount_raw))
    except Exception:
        return Response({'detail': 'Kiasi si sahihi.'}, status=400)

    branch_office = get_selected_office_api(request)
    if not branch_office:
        return Response({'detail': 'Tafadhali chagua tawi kwanza.'}, status=400)

    branch_balance = BranchBalance.objects.filter(branch=branch_office).last()
    if not branch_balance:
        BranchBalance.objects.create(
            branch=branch_office,
            office_balance=amount_decimal if deposit_method == 'cash' else Decimal('0'),
            bank_balance=amount_decimal   if deposit_method != 'cash' else Decimal('0'),
            updated_by=request.user,
        )
    else:
        if deposit_method == 'cash':
            BranchBalance.objects.create(
                branch=branch_office,
                office_balance=branch_balance.office_balance + amount_decimal,
                bank_balance=branch_balance.bank_balance,
                updated_by=request.user,
            )
        else:
            BranchBalance.objects.create(
                branch=branch_office,
                office_balance=branch_balance.office_balance,
                bank_balance=branch_balance.bank_balance + amount_decimal,
                updated_by=request.user,
            )

    obj = Nyongeza.objects.create(
        amount=amount_decimal,
        description=description,
        deposit_method=deposit_method,
        recorded_by=request.user,
        Office=branch_office,
    )
    return Response({
        'id': obj.id,
        'amount': _d(obj.amount),
        'deposit_method': obj.deposit_method,
        'description': obj.description or '',
        'office': branch_office.name,
        'date': _str(obj.date),
    }, status=201)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_monthly_repayment_v2(request):
    # GET /api/monthly-repayment/?month_from=MM-YYYY&month_to=MM-YYYY
    # Mirrors monthly_repayment_report() web view exactly:
    #   - Includes both LoanRepayment and LoanTopup records
    #   - Returns check_no, loan_id_label, description, record_type, record_id, row_key
    #   - Grouped by payment_month, sorted within each month
    import calendar as _cal

    def parse_mm_yyyy(s):
        try:
            parts = s.strip().split('-')
            if len(parts) == 2:
                return int(parts[0]), int(parts[1])
        except Exception:
            pass
        return None, None

    filter_office = get_filter_office(request)
    selected      = get_selected_office_api(request)

    month_from_str = request.GET.get('month_from', '')
    month_to_str   = request.GET.get('month_to',   '')
    fm, fy = parse_mm_yyyy(month_from_str)
    tm, ty = parse_mm_yyyy(month_to_str)

    if not fm:
        today = date.today()
        fm, fy = today.month, today.year
        tm, ty = today.month, today.year

    import datetime as _dt2
    range_start = _dt2.date(fy, fm, 1)
    range_end   = _dt2.date(ty, tm, _cal.monthrange(ty, tm)[1])

    MN = {1:'Jan',2:'Feb',3:'Mar',4:'Apr',5:'May',6:'Jun',
          7:'Jul',8:'Aug',9:'Sep',10:'Oct',11:'Nov',12:'Dec'}

    def _cname(client):
        return f"{client.firstname} {getattr(client,'middlename','') or ''} {client.lastname}".strip()

    # ── LoanRepayment ─────────────────────────────────────────────────────
    rep_qs = LoanRepayment.objects.filter(
        repayment_date__range=(range_start, range_end),
    ).select_related('loan_application', 'loan_application__client').order_by('payment_month', 'id')
    if filter_office:
        rep_qs = rep_qs.filter(loan_application__office=filter_office.name)

    # ── LoanTopup ────────────────────────────────────────────────────────
    topup_qs = LoanTopup.objects.filter(
        topup_date__range=(range_start, range_end),
    ).select_related('loan_application', 'loan_application__client').order_by('payment_month', 'id')
    if filter_office:
        topup_qs = topup_qs.filter(loan_application__office=filter_office.name)

    buckets = {}

    for rep in rep_qs:
        pm = rep.payment_month or rep.repayment_date
        if not pm: continue
        key  = (pm.year, pm.month)
        loan = rep.loan_application
        c    = loan.client
        buckets.setdefault(key, []).append({
            'sort_key':      (pm, 0, rep.id),
            'date':          _str(rep.repayment_date),
            'receipt_no':    str(rep.id).zfill(6),
            'name':          _cname(c).upper(),
            'check_no':      c.checkno or getattr(c,'employmentcardno','') or '—',
            'loan_id_label': f"{(loan.office or 'loan').lower()}-{loan.id}",
            'description':   'Loan payment',
            'amount':        _d(rep.repayment_amount),
            'row_key':       f"repayment-{rep.id}",
            'record_type':   'repayment',
            'record_id':     rep.id,
        })

    for topup in topup_qs:
        pm = topup.payment_month or topup.topup_date
        if not pm: continue
        key    = (pm.year, pm.month)
        loan   = topup.loan_application
        c      = loan.client
        cleared = topup.old_balance_cleared or Decimal('0')
        buckets.setdefault(key, []).append({
            'sort_key':      (pm, 1, topup.id),
            'date':          _str(topup.topup_date),
            'receipt_no':    str(topup.id).zfill(6),
            'name':          _cname(c).upper(),
            'check_no':      c.checkno or getattr(c,'employmentcardno','') or '—',
            'loan_id_label': f"{(loan.office or 'loan').lower()}-{loan.id}",
            'description':   'Clearance loan balance for top-up',
            'amount':        _d(cleared),
            'row_key':       f"topup-{topup.id}",
            'record_type':   'topup',
            'record_id':     topup.id,
        })

    months_data = []
    for key in sorted(buckets.keys()):
        y, m = key
        rows = sorted(buckets[key], key=lambda r: r['sort_key'])
        for r in rows:
            del r['sort_key']
        months_data.append({
            'label':       f"{MN[m]}-{y}",
            'key':         f"{y}-{m:02d}",
            'rows':        rows,
            'grand_total': _d(sum(Decimal(str(r['amount'])) for r in rows)),
            'count':       len(rows),
        })

    branch_name = (filter_office.name.upper() if filter_office
                   else selected.name.upper() if selected else 'ALL BRANCHES')

    return Response({
        'months':      months_data,
        'branch_name': branch_name,
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_bulk_update_payment_month(request):
    # POST /api/monthly-repayment/bulk-update/
    # Mirrors bulk_update_payment_month() web view exactly
    selected_items   = request.data.get('selected_items', [])
    transaction_date = request.data.get('transaction_date') or None

    if not selected_items or not transaction_date:
        return Response({'detail': 'Select records and provide transaction_date.'}, status=400)

    updated = 0
    for item in selected_items:
        try:
            rtype, rid = item.split('-', 1)
            if rtype == 'repayment':
                LoanRepayment.objects.filter(id=int(rid)).update(payment_month=transaction_date)
                updated += 1
            elif rtype == 'topup':
                topup = LoanTopup.objects.select_related('loan_application','processed_by').filter(id=int(rid)).first()
                if not topup: continue
                linked = LoanRepayment.objects.filter(loan_application=topup.loan_application, payment_month=topup.payment_month).first()
                if not linked:
                    linked = LoanRepayment.objects.filter(loan_application=topup.loan_application).order_by('-created_at').first()
                topup.payment_month = transaction_date
                topup.save()
                if linked:
                    linked.payment_month  = transaction_date
                    linked.repayment_date = transaction_date
                    linked.save()
                else:
                    LoanRepayment.objects.create(
                        loan_application=topup.loan_application,
                        repayment_amount=topup.old_balance_cleared,
                        repayment_date=transaction_date, payment_month=transaction_date,
                        transaction_method=topup.transaction_method, processed_by=topup.processed_by,
                    )
                updated += 1
        except Exception:
            continue

    return Response({'success': True, 'updated': updated, 'message': f'{updated} record(s) updated.'})


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def api_edit_repayment(request, repayment_type, repayment_id):
    # GET /api/repayment/<type>/<id>/edit/  → returns record data
    # POST /api/repayment/<type>/<id>/edit/ → updates record
    # Mirrors edit_repayment() web view exactly
    try:
        if repayment_type == 'repayment':
            obj = LoanRepayment.objects.select_related('loan_application__client','processed_by').get(id=repayment_id)
            c   = obj.loan_application.client
            data_out = {
                'repayment_type':     'repayment',
                'repayment_id':       obj.id,
                'name':               f"{c.firstname} {getattr(c,'middlename','') or ''} {c.lastname}".strip(),
                'receipt_no':         str(obj.id).zfill(6),
                'amount':             _d(obj.repayment_amount),
                'transaction_method': obj.transaction_method or 'cash',
                'payment_month':      _str(obj.payment_month),
                'repayment_date':     _str(obj.repayment_date),
            }
        else:
            obj = LoanTopup.objects.select_related('loan_application__client','processed_by').get(id=repayment_id)
            c   = obj.loan_application.client
            data_out = {
                'repayment_type':     'topup',
                'repayment_id':       obj.id,
                'name':               f"{c.firstname} {getattr(c,'middlename','') or ''} {c.lastname}".strip(),
                'receipt_no':         str(obj.id).zfill(6),
                'amount':             _d(obj.old_balance_cleared),
                'transaction_method': obj.transaction_method or 'cash',
                'payment_month':      _str(obj.payment_month),
                'repayment_date':     _str(obj.topup_date),
            }
    except (LoanRepayment.DoesNotExist, LoanTopup.DoesNotExist):
        return Response({'detail': 'Record not found.'}, status=404)

    if request.method == 'GET':
        return Response(data_out)

    # POST — update
    try:
        new_pm   = request.data.get('payment_month')
        new_meth = request.data.get('transaction_method', obj.transaction_method)
        new_date = request.data.get('transaction_date') or request.data.get('repayment_date')

        if repayment_type == 'topup':
            linked = LoanRepayment.objects.filter(loan_application=obj.loan_application, payment_month=obj.payment_month).first()
            if not linked:
                linked = LoanRepayment.objects.filter(loan_application=obj.loan_application).order_by('-created_at').first()

        if new_pm:   obj.payment_month      = new_pm
        if new_meth: obj.transaction_method = new_meth
        if new_date:
            if repayment_type == 'repayment': obj.repayment_date = new_date
            else:                              obj.topup_date     = new_date
        obj.save()

        if repayment_type == 'topup' and new_pm:
            if linked:
                linked.payment_month  = new_pm
                linked.repayment_date = new_pm
                linked.save()
            else:
                LoanRepayment.objects.create(
                    loan_application=obj.loan_application,
                    repayment_amount=obj.old_balance_cleared,
                    repayment_date=new_pm, payment_month=new_pm,
                    transaction_method=new_meth or obj.transaction_method,
                    processed_by=obj.processed_by,
                )

        return Response({'success': True, 'message': 'Record updated successfully.'})
    except Exception as e:
        return Response({'detail': f'Error: {str(e)}'}, status=500)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_monthly_outstanding_v2(request):
    # GET /api/monthly-outstanding/?month=YYYY-MM-DD
    # Mirrors monthly_outstanding_report() web view exactly:
    #   - Cumulative arrears logic (not just current-month installment)
    #   - due_cutoff = min(month_end, today)   -> installments due up to selected month
    #   - paid_cutoff = today                   -> all payments counted, including late ones
    #   - Shows loan if cumulative not_paid > 0, regardless of whether an
    #     installment falls in the selected month (covers HAMA/overdue loans)
    #   - amount_to_be_paid: this month's installment if due this month,
    #     else the full arrears balance (not_paid) for overdue-only loans
    #   - Sorted alphabetically by client name (not by not_paid desc)
    from dateutil.relativedelta import relativedelta
    import datetime as _dt3

    filter_office = get_filter_office(request)
    selected      = get_selected_office_api(request)

    month_str = request.GET.get('month', '')
    try:
        selected_date = _dt3.datetime.strptime(month_str, '%Y-%m-%d').date()
    except Exception:
        selected_date = date.today()

    sel_year  = selected_date.year
    sel_month = selected_date.month
    last_day  = cal_module.monthrange(sel_year, sel_month)[1]
    month_start = _dt3.date(sel_year, sel_month, 1)
    month_end   = _dt3.date(sel_year, sel_month, last_day)

    today       = date.today()
    due_cutoff  = min(month_end, today)   # installments due up to end of selected month
    paid_cutoff = today                    # all payments counted, including late ones

    loans = LoanApplication.objects.filter(
        repayment_amount_remaining__gt=0,
    ).select_related('client').prefetch_related('repayments').order_by(
        'client__lastname', 'client__firstname', 'id'
    )
    if filter_office:
        loans = loans.filter(office=filter_office.name)

    rows = []
    for loan in loans:
        if not loan.first_repayment_date or not loan.payment_period_months or not loan.monthly_installment:
            continue

        periods          = loan.payment_period_months
        first_repay_date = loan.first_repayment_date
        monthly_inst     = loan.monthly_installment
        all_repayments   = list(loan.repayments.all())

        # ── Full repayment schedule ────────────────────────────────────────
        schedule = [
            first_repay_date + relativedelta(months=i)
            for i in range(periods)
        ]
        last_due_date = schedule[-1]

        # ── Installments due up to the selected month's cutoff ─────────────
        slots_due_to_date = [d for d in schedule if d <= due_cutoff]
        if not slots_due_to_date:
            continue  # loan hasn't started due dates yet for this month

        # ── Cumulative due vs cumulative paid ──────────────────────────────
        total_due_to_date  = monthly_inst * len(slots_due_to_date)
        total_paid_to_date = sum(
            (r.repayment_amount or Decimal('0'))
            for r in all_repayments
            if r.repayment_date and r.repayment_date <= paid_cutoff
        )
        not_paid = max(total_due_to_date - total_paid_to_date, Decimal('0'))

        # Only visibility criterion: is there any outstanding arrears at all?
        if not_paid <= Decimal('0'):
            continue

        # ── Display-only metadata (doesn't affect visibility) ──────────────
        slots_this_month_due = [
            d for d in slots_due_to_date
            if d.year == sel_year and d.month == sel_month
        ]
        is_overdue_loan = last_due_date < month_start

        # "Amount to be paid": this month's installment if due, else full arrears
        if slots_this_month_due:
            amount_to_be_paid = monthly_inst * len(slots_this_month_due)
        else:
            amount_to_be_paid = not_paid

        paid_this_month = sum(
            (r.repayment_amount or Decimal('0'))
            for r in all_repayments
            if r.repayment_date and month_start <= r.repayment_date <= month_end
        )

        outstanding = loan.repayment_amount_remaining or Decimal('0')
        client      = loan.client

        rows.append({
            'name':              f"{client.firstname} {getattr(client,'middlename','') or ''} {client.lastname}".strip(),
            'check_no':          client.checkno or getattr(client,'employmentcardno','') or '—',
            'employer':          getattr(client,'employername','') or '—',
            'contact':           client.phonenumber or '—',
            'amount_to_be_paid': _d(amount_to_be_paid),
            'paid_this_month':   _d(paid_this_month),
            'not_paid':          _d(not_paid),
            'outstanding_total': _d(outstanding),
            'is_overdue_loan':   is_overdue_loan,
        })

    # Sort alphabetically by name (matches web view exactly)
    rows.sort(key=lambda r: r['name'].lower())

    # Add S/N after sort
    for i, r in enumerate(rows, 1):
        r['sn'] = i

    branch_name = (filter_office.name.upper() if filter_office
                   else selected.name.upper() if selected else 'ALL BRANCHES')

    MN2 = {1:'Jan',2:'Feb',3:'Mar',4:'Apr',5:'May',6:'Jun',
           7:'Jul',8:'Aug',9:'Sep',10:'Oct',11:'Nov',12:'Dec'}
    month_label = f"{MN2[sel_month]}/{sel_year}".upper()

    total_amount_to_pay   = _d(sum(Decimal(str(r['amount_to_be_paid'])) for r in rows))
    total_paid_this_month = _d(sum(Decimal(str(r['paid_this_month']))   for r in rows))
    total_not_paid         = _d(sum(Decimal(str(r['not_paid']))          for r in rows))
    total_outstanding     = _d(sum(Decimal(str(r['outstanding_total'])) for r in rows))

    return Response({
        'branch_name':           branch_name,
        'month_label':           month_label,
        'arrears_cutoff':        str(due_cutoff),
        'total_amount_to_pay':   total_amount_to_pay,
        'total_paid_this_month': total_paid_this_month,
        'total_not_paid':        total_not_paid,
        'total_outstanding':     total_outstanding,
        'month': _str(selected_date),
        'rows': rows,
        'totals': {
            'amount_to_be_paid': total_amount_to_pay,
            'paid_this_month':   total_paid_this_month,
            'not_paid':          total_not_paid,
            'outstanding':       total_outstanding,
        }
    })

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_bank_charge_add(request):
    # POST /api/bank-charges/add/
    # Mirrors bank_charge_add() web view exactly:
    #   - validates cash/bank balance before creating
    #   - creates BankCharge record
    #   - updates BranchBalance snapshot
    from decimal import Decimal
    from django.db import transaction as db_transaction

    try:
        with db_transaction.atomic():
            description      = request.data.get('description', '')
            amount_raw       = str(request.data.get('amount', '0')).replace(',', '').strip()
            payment_method   = request.data.get('payment_method', 'bank')
            transaction_date_str = request.data.get('transaction_date', '')
            # attachment handled separately (multipart)
            attachment = request.FILES.get('attachment')

            amount = Decimal(amount_raw) if amount_raw else Decimal('0.00')

            import datetime as _dt
            try:
                transaction_date = _dt.datetime.strptime(transaction_date_str, '%Y-%m-%d').date()
            except Exception:
                transaction_date = _dt.date.today()

            branch_office = get_selected_office_api(request)
            if not branch_office:
                return Response({'detail': 'No branch office found.'}, status=400)

            # Balance check + update BranchBalance
            latest_bal     = BranchBalance.objects.filter(branch=branch_office).order_by('-last_updated').first()
            cash_in_office = Decimal(str(latest_bal.office_balance)) if latest_bal else Decimal('0')
            cash_in_bank   = Decimal(str(latest_bal.bank_balance))   if latest_bal else Decimal('0')

            if payment_method == 'cash':
                if cash_in_office < amount:
                    return Response({'detail': f'Insufficient cash. Available: TZS {cash_in_office:,.0f}/='}, status=400)
                if latest_bal:
                    BranchBalance.objects.create(
                        branch=branch_office,
                        office_balance=latest_bal.office_balance - amount,
                        bank_balance=latest_bal.bank_balance,
                        updated_by=request.user,
                    )
            else:
                if cash_in_bank < amount:
                    return Response({'detail': f'Insufficient bank balance. Available: TZS {cash_in_bank:,.0f}/='}, status=400)
                if latest_bal:
                    BranchBalance.objects.create(
                        branch=branch_office,
                        office_balance=latest_bal.office_balance,
                        bank_balance=latest_bal.bank_balance - amount,
                        updated_by=request.user,
                    )

            charge = BankCharge.objects.create(
                description=description,
                amount=amount,
                recorded_by=request.user,
                office=branch_office.name,
                payment_method=payment_method,
                expense_date=transaction_date,
            )
            if attachment:
                charge.attachment = attachment
                charge.save(update_fields=['attachment'])

            return Response({
                'id': charge.id,
                'message': f'Bank charge of TZS {amount:,.0f}/= recorded.',
            }, status=201)

    except Exception as e:
        return Response({'detail': f'Error: {str(e)}'}, status=500)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_bank_cash_transaction_add(request):
    # POST /api/bank-cash-transaction/add/
    # Mirrors bank_cash_transaction_add() web view:
    #   Transfer between Cash and Bank for the selected office
    from decimal import Decimal
    from django.db import transaction as db_transaction

    try:
        with db_transaction.atomic():
            source         = request.data.get('source', '')       # 'cash' or 'bank'
            destination    = request.data.get('destination', '')   # 'bank' or 'cash'
            amount_raw     = str(request.data.get('amount', '0')).replace(',', '').strip()
            date_str       = request.data.get('transaction_date', '')
            attachment     = request.FILES.get('attachment')

            amount = Decimal(amount_raw)

            import datetime as _dt
            try:
                txn_date = _dt.datetime.strptime(date_str, '%Y-%m-%d').date()
            except Exception:
                txn_date = _dt.date.today()

            office_from = get_selected_office_api(request)
            if not office_from:
                return Response({'detail': 'No branch office found.'}, status=400)

            if source not in ('cash', 'bank') or destination not in ('cash', 'bank') or source == destination:
                return Response({'detail': 'Invalid source/destination combination.'}, status=400)

            # Balance check using BranchBalance
            latest_bal     = BranchBalance.objects.filter(branch=office_from).order_by('-last_updated').first()
            cash_in_office = Decimal(str(latest_bal.office_balance)) if latest_bal else Decimal('0')
            cash_in_bank   = Decimal(str(latest_bal.bank_balance))   if latest_bal else Decimal('0')

            if source == 'cash' and destination == 'bank':
                if cash_in_office < amount:
                    return Response({'detail': f'Insufficient cash. Available: TZS {cash_in_office:,.0f}/='}, status=400)
                description = f'Cash to Bank transfer for {office_from.name}'
            else:
                if cash_in_bank < amount:
                    return Response({'detail': f'Insufficient bank balance. Available: TZS {cash_in_bank:,.0f}/='}, status=400)
                description = f'Bank to Cash transfer for {office_from.name}'

            # Create BankCashTransaction
            try:
                bct = BankCashTransaction.objects.create(
                    office_from=office_from,
                    source=source,
                    destination=destination,
                    amount=amount,
                    transaction_date=txn_date,
                )
                if attachment:
                    bct.attachment = attachment
                    bct.save(update_fields=['attachment'])
            except Exception:
                bct = None  # BankCashTransaction optional

            # Create HQTransaction record
            hq_txn = HQTransaction.objects.create(
                from_branch=office_from,
                to_branch=office_from,
                amount=amount,
                description=description,
                transaction_date=txn_date,
                processed_by=request.user,
            )
            if attachment and bct:
                hq_txn.attachment = bct.attachment
                hq_txn.save(update_fields=['attachment'])

            return Response({
                'id': hq_txn.id,
                'message': f'Transfer of TZS {amount:,.0f}/= from {source} to {destination} completed.',
            }, status=201)

    except Exception as e:
        return Response({'detail': f'Error: {str(e)}'}, status=500)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_branch_expenses_report(request):
    # GET /api/reports/branch-expenses/?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD
    # Mirrors expenses_report() web view for branch:
    #   Uses transaction_date (DateField range) - web: transaction_date__range
    #   Returns per-row: date, receipt_no, category, description, amount, is_bank, hide_date
    d_from, d_to, err = _parse_dates(request)
    if err: return Response({'error': err}, status=400)
    filter_office = get_filter_office(request)
    selected      = get_selected_office_api(request)

    # Mirror web view: transaction_date__range
    # BUT also include expenses where transaction_date is null → fall back to expense_date range
    qs = Expense.objects.filter(
        Q(transaction_date__range=(d_from, d_to)) |
        Q(transaction_date__isnull=True, expense_date__range=(d_from, d_to))
    ).select_related('transaction_type', 'recorded_by').order_by(
        'transaction_date', 'expense_date', 'id'
    )
    if filter_office:
        qs = qs.filter(office=filter_office.name)

    rows = []
    prev_date = None
    for exp in qs:
        cat    = exp.transaction_type.name if exp.transaction_type else 'Expense'
        is_bank = (getattr(exp, 'payment_method', 'cash') or 'cash').lower() == 'bank'
        # Use transaction_date if set, else fall back to expense_date
        txn_date = exp.transaction_date or exp.expense_date
        rows.append({
            'id':          exp.id,
            'date':        str(txn_date) if txn_date else '',
            'receipt_no':  str(exp.id).zfill(6),
            'category':    cat,
            'description': (exp.description or '').strip(),
            'amount':      _d(exp.amount),
            'is_bank':     is_bank,
            'hide_date':   (txn_date == prev_date),
        })
        prev_date = txn_date

    grand_total = _d(sum(Decimal(str(r['amount'])) for r in rows))
    branch_name = (filter_office.name.upper() if filter_office
                   else selected.name.upper() if selected else 'ALL BRANCHES')

    return Response({
        'rows':        rows,
        'grand_total': grand_total,
        'branch_name': branch_name,
        'date_from':   str(d_from),
        'date_to':     str(d_to),
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_bank_charges(request):
    # GET /api/reports/bank-charges/?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD
    d_from, d_to, err = _parse_dates(request)
    if err:
        return Response({'error': err}, status=400)
    filter_office = get_filter_office(request)
    charges = BankCharge.objects.filter(
        Q(transaction_date__range=(d_from, d_to)) |
        Q(transaction_date__isnull=True, expense_date__range=(d_from, d_to))
    ).order_by('transaction_date', 'expense_date', 'id')
    if filter_office:
        charges = charges.filter(office=filter_office.name)
    rows = [{'id': c.id, 'date': _str(c.transaction_date or c.expense_date), 'receipt_no': str(c.id).zfill(6), 'description': (c.description or '').strip(), 'amount': _d(c.amount), 'payment_method': c.payment_method or '', 'office': c.office or ''} for c in charges]
    return Response({'rows': rows, 'charges': rows, 'grand_total': _d(sum(Decimal(str(r['amount'])) for r in rows))})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_bank_transfer_expenses(request):
    # GET /api/reports/bank-transfer-expenses/?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD
    # Mirrors bank_transfer_expenses_report() web view:
    #   OfficeTransaction where transaction_method='bank', filtered to current branch
    #   Returns rows with: date, receipt_no, name, description, amount, processed_by
    d_from, d_to, err = _parse_dates(request)
    if err:
        return Response({'error': err}, status=400)
    filter_office = get_filter_office(request)
    dt_from = datetime.datetime.combine(d_from, datetime.time.min)
    dt_to   = datetime.datetime.combine(d_to,   datetime.time.max)

    def _pname(user):
        if not user: return ''
        parts = [getattr(user,'first_name',''), getattr(user,'last_name','')]
        return ' '.join(p for p in parts if p) or getattr(user,'username','')

    txns = OfficeTransaction.objects.filter(
        created_at__range=(dt_from, dt_to),
        transaction_method='bank',
    ).select_related('office_from', 'office_to', 'processed_by').order_by('created_at', 'id')

    if filter_office:
        txns = txns.filter(office_from=filter_office)

    rows = []
    for t in txns:
        dest_name = t.office_to.name if t.office_to else 'HQ'
        rows.append({
            'txn_id':       t.id,
            'date':         str(t.created_at.date()),
            'receipt_no':   str(t.id).zfill(6),
            'name':         _pname(t.processed_by),
            'description':  f"Amount to Branch [{dest_name}]",
            'amount':       _d(t.amount),
            'processed_by': _pname(t.processed_by),
            'office_from':  t.office_from.name if t.office_from else '',
            'office_to':    dest_name,
        })

    office_totals = {}
    for r in rows:
        fn = r['office_from']
        office_totals[fn] = office_totals.get(fn, {'count': 0, 'amount': Decimal('0')})
        office_totals[fn]['count']  += 1
        office_totals[fn]['amount'] += Decimal(str(r['amount']))

    all_offices = Office.objects.exclude(name__iexact='HQ').order_by('name')
    branch_summary = []
    for i, office in enumerate(all_offices, 1):
        info = office_totals.get(office.name, {'count': 0, 'amount': Decimal('0')})
        branch_summary.append({'sn': i, 'branch': office.name,
            'count': info['count'], 'amount': _d(info['amount'])})

    grand_total = _d(sum(Decimal(str(r['amount'])) for r in rows))
    branch_name = filter_office.name.upper() if filter_office else 'ALL BRANCHES'

    return Response({
        'rows': rows, 'branch_summary': branch_summary,
        'grand_total': grand_total, 'branch_name': branch_name,
        'date_from': str(d_from), 'date_to': str(d_to),
    })

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_branch_to_hq_expenses(request):
    # GET /api/reports/branch-to-hq-expenses/?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD
    # Mirrors branch_to_hq_expenses_result() web view exactly:
    #   Uses HQTransaction model, from_branch FK (branch sent to HQ)
    #   - transaction_date is DateField - plain date comparison
    #   - from_branch FK - the sending branch
    #   - total_amount=None means no transfers (shown as dash in table)
    d_from, d_to, err = _parse_dates(request)
    if err:
        return Response({'error': err}, status=400)

    # All non-HQ offices sorted alphabetically
    all_offices = Office.objects.exclude(name__iexact='HQ').order_by('name')

    # Transfers SENT by each branch to HQ in date range
    branch_sent = (
        HQTransaction.objects
        .filter(
            transaction_date__gte=d_from,
            transaction_date__lte=d_to,
            from_branch__isnull=False,
        )
        .values('from_branch_id')
        .annotate(total=Coalesce(Sum('amount'), Decimal('0')))
    )

    # Build lookup: office_id -> total sent
    sent_map = {row['from_branch_id']: row['total'] for row in branch_sent}

    # Every office gets a row - None means no transfers sent
    branch_summary = []
    for i, office in enumerate(all_offices, 1):
        total = sent_map.get(office.id, None)
        branch_summary.append({
            'sn':           i,
            'branch':       office.name,
            'total_amount': _d(total) if total is not None else 0.0,
            'has_transfer': total is not None,
        })

    grand_total = _d(sum(
        Decimal(str(r['total_amount'])) for r in branch_summary if r['has_transfer']
    ))

    return Response({
        'date_from':      str(d_from),
        'date_to':        str(d_to),
        'branch_summary': branch_summary,
        'grand_total':    grand_total,
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_delete_office_transaction(request, txn_id):
    # POST /api/office-transactions/<id>/delete/
    # Mirrors delete_office_transaction() web view:
    #   - Restores sender's balance
    #   - Deducts from receiver's balance
    #   - Deletes linked HQTransaction
    #   - Deletes the OfficeTransaction
    from django.db import transaction as db_transaction
    try:
        txn = OfficeTransaction.objects.get(pk=txn_id)
    except OfficeTransaction.DoesNotExist:
        return Response({'detail': 'Transaction not found.'}, status=404)

    try:
        with db_transaction.atomic():
            method = (txn.transaction_method or '').lower()

            bal_from = BranchBalance.objects.filter(branch=txn.office_from).order_by('-last_updated').first()
            bal_to   = BranchBalance.objects.filter(branch=txn.office_to).order_by('-last_updated').first()

            if bal_from:
                BranchBalance.objects.create(
                    branch=txn.office_from,
                    office_balance=bal_from.office_balance + (txn.amount if method == 'cash' else Decimal('0')),
                    bank_balance=bal_from.bank_balance     + (txn.amount if method == 'bank' else Decimal('0')),
                    updated_by=request.user,
                )
            if bal_to:
                BranchBalance.objects.create(
                    branch=txn.office_to,
                    office_balance=bal_to.office_balance - (txn.amount if method == 'cash' else Decimal('0')),
                    bank_balance=bal_to.bank_balance     - (txn.amount if method == 'bank' else Decimal('0')),
                    updated_by=request.user,
                )

            # Delete linked HQTransaction
            hq_link = HQTransaction.objects.filter(
                from_branch=txn.office_from,
                to_branch=txn.office_to,
                amount=txn.amount,
            ).order_by('-id').first()
            if hq_link:
                hq_link.delete()

            receipt = str(txn_id).zfill(6)
            txn.delete()

        return Response({
            'success': True,
            'message': f'Transaction #{receipt} deleted and balances reversed.',
        })
    except Exception as e:
        return Response({'detail': f'Error: {str(e)}'}, status=500)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_hq_financial_statement(request):
    # GET /api/reports/hq-financial/?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD
    # Mirrors general_financial_statement_report() web view exactly.
    # Screenshot layout:
    #   Opening Balance
    #   External Sources (repayments excl. Hazina)
    #   Hazina
    #   ── Income Subtotal (bold, underlined)
    #   Loans Disbursed (Fomu)
    #   Money to Branch (HQ->branch transfers)
    #   Expenses
    #   Bank Charges
    #   ── Outflow Subtotal (bold, underlined)
    #   Closing Balance
    from django.utils import timezone as tz
    import datetime as _dt

    d_from, d_to, err = _parse_dates(request)
    if err:
        return Response({'error': err}, status=400)

    start_date = d_from
    end_date   = d_to

    # Timezone-aware datetimes for DateTimeField filters
    start_dt  = tz.make_aware(_dt.datetime.combine(start_date, _dt.time.min))
    end_dt    = tz.make_aware(_dt.datetime.combine(end_date,   _dt.time.max))
    before_dt = start_dt   # exclusive upper bound for opening balance

    def _s(qs, field):
        return qs.aggregate(t=Sum(field))['t'] or Decimal('0')

    # ── OPENING BALANCE (all transactions BEFORE start_date) ─────────────────
    open_repayments   = _s(LoanRepayment.objects.filter(repayment_date__lt=start_date),  'repayment_amount')
    open_nyongeza     = _s(Nyongeza.objects.filter(date__lt=start_date),                  'amount')
    open_external     = _s(OfficeTransaction.objects.filter(
                               transaction_date__lt=start_date,
                               office_from__name__iexact='HQ'),                            'amount')
    open_loans        = _s(LoanApplication.objects.filter(created_at__lt=before_dt),      'loan_amount')
    open_expenses     = _s(Expense.objects.filter(expense_date__lt=start_date),            'amount')
    open_salaries     = _s(Salary.objects.filter(salary_for_month__lt=start_date),         'amount')
    open_bank_charges = _s(BankCharge.objects.filter(expense_date__lt=start_date),         'amount')

    opening_balance = (
        open_repayments + open_nyongeza + open_external
    ) - (
        open_loans + open_expenses + open_salaries + open_bank_charges
    )

    # ── CURRENT PERIOD INCOME ─────────────────────────────────────────────────

    # External Sources = repayments EXCLUDING Hazina loan type
    total_repayments = _s(
        LoanRepayment.objects.filter(
            repayment_date__gte=start_date,
            repayment_date__lte=end_date,
        ).exclude(loan_application__loan_type__iexact='Hazina'),
        'repayment_amount'
    )

    # Hazina repayments — separated per web view
    total_hazina = _s(
        LoanRepayment.objects.filter(
            repayment_date__gte=start_date,
            repayment_date__lte=end_date,
            loan_application__loan_type__iexact='Hazina',
        ),
        'repayment_amount'
    )

    # total_nyongeza = 0 per web view (commented out)
    total_nyongeza = Decimal('0')

    income_subtotal = (
        opening_balance
        + total_repayments
        + total_hazina
        + total_nyongeza
    )

    # ── CURRENT PERIOD OUTFLOW ────────────────────────────────────────────────

    # Loans Disbursed (Fomu) — DateTimeField needs tz-aware range
    total_loans_disbursed = _s(
        LoanApplication.objects.filter(
            created_at__gte=start_dt,
            created_at__lte=end_dt,
        ),
        'loan_amount'
    )

    # Money to Branch — HQ->branch transfers only (avoids double-counting)
    total_hq_transfers_out = _s(
        OfficeTransaction.objects.filter(
            transaction_date__gte=start_date,
            transaction_date__lte=end_date,
            office_from__name__iexact='HQ',
        ),
        'amount'
    )

    # Expenses — DateField
    period_expenses = _s(
        Expense.objects.filter(
            expense_date__gte=start_date,
            expense_date__lte=end_date,
        ),
        'amount'
    )

    # Salaries — DateField
    total_salaries = _s(
        Salary.objects.filter(
            salary_for_month__gte=start_date,
            salary_for_month__lte=end_date,
        ),
        'amount'
    )

    # Bank Charges — DateField
    total_bank_charges = _s(
        BankCharge.objects.filter(
            expense_date__gte=start_date,
            expense_date__lte=end_date,
        ),
        'amount'
    )

    total_expenses   = period_expenses + total_salaries
    outflow_subtotal = (
        total_loans_disbursed
        + total_hq_transfers_out
        + total_expenses
        + total_bank_charges
    )

    closing_balance = income_subtotal - outflow_subtotal

    return Response({
        'date_from': str(start_date),
        'date_to':   str(end_date),

        # Opening
        'opening_balance':        _d(opening_balance),

        # Income rows (matches screenshot order)
        'total_repayments':       _d(total_repayments),    # External Sources
        'total_hazina':           _d(total_hazina),
        'total_nyongeza':         _d(total_nyongeza),
        'income_subtotal':        _d(income_subtotal),

        # Outflow rows (matches screenshot order)
        'total_loans_disbursed':  _d(total_loans_disbursed),   # Loans Disbursed (Fomu)
        'total_hq_transfers_out': _d(total_hq_transfers_out),  # Money to Branch
        'total_expenses':         _d(total_expenses),           # Expenses (period_expenses + salaries)
        'total_bank_charges':     _d(total_bank_charges),
        'outflow_subtotal':       _d(outflow_subtotal),

        # Closing
        'closing_balance':        _d(closing_balance),
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_payroll_report(request):
    # GET /api/payroll/report/?month=YYYY-MM
    from useraccount.models import CustomUser
    month_param = request.GET.get('month', '').strip()
    if not month_param:
        today = date.today()
        month_param = str(today.year) + '-' + str(today.month).zfill(2)
    try:
        y, m = map(int, month_param.split('-'))
        import datetime as _dt6
        salary_date = _dt6.date(y, m, 1)
    except Exception:
        return Response({'error': 'Invalid month. Use YYYY-MM'}, status=400)
    all_staff = CustomUser.objects.filter(is_active=True, is_superuser=False).order_by('last_name', 'first_name')
    paid_ids = set(Salary.objects.filter(salary_for_month=salary_date).values_list('employee_id', flat=True))
    employees = []
    totals = {'basic_salary': Decimal('0'), 'deduction': Decimal('0'), 'net_salary': Decimal('0')}
    for user in all_staff:
        basic  = user.salary or Decimal('0')
        deduct = user.deduction_amount or Decimal('0')
        net    = max(basic - deduct, Decimal('0'))
        o      = user.office_allocation
        employees.append({'id': user.id, 'employee_name': user.get_full_name(), 'branch': o.name if o else '', 'basic_salary': _d(basic), 'deduction': _d(deduct), 'net_salary': _d(net), 'already_paid': user.id in paid_ids})
        totals['basic_salary'] += basic
        totals['deduction']    += deduct
        totals['net_salary']   += net
    return Response({'month': month_param, 'employees': employees, 'salaries': employees, 'totals': {'basic_salary': _d(totals['basic_salary']), 'deduction': _d(totals['deduction']), 'net_salary': _d(totals['net_salary'])}, 'total_net': _d(totals['net_salary'])})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_payroll_submit(request):
    # POST /api/payroll/submit/  body: {month: 'YYYY-MM'}
    from useraccount.models import CustomUser
    month_param = request.data.get('month', '').strip()
    if not month_param:
        return Response({'error': 'month inahitajika (YYYY-MM).'}, status=400)
    try:
        y, m = map(int, month_param.split('-'))
        import datetime as _dt7
        salary_date = _dt7.date(y, m, 1)
    except Exception:
        return Response({'error': 'Muundo si sahihi. Tumia YYYY-MM'}, status=400)
    selected_office = get_selected_office_api(request)
    staff_qs = CustomUser.objects.filter(is_active=True, is_superuser=False)
    paid_ids = set(Salary.objects.filter(salary_for_month=salary_date).values_list('employee_id', flat=True))
    created_count = skipped_count = 0
    for user in staff_qs:
        if user.id in paid_ids:
            skipped_count += 1
            continue
        basic  = user.salary or Decimal('0')
        deduct = user.deduction_amount or Decimal('0')
        net    = max(basic - deduct, Decimal('0'))
        Salary.objects.create(employee=user, amount=net, salary_for_month=salary_date, transaction_method='bank', fund_source=selected_office, processed_by=request.user)
        created_count += 1
    return Response({'message': 'Payroll submitted for ' + salary_date.strftime('%B %Y') + '.', 'created': created_count, 'skipped': skipped_count, 'month': month_param})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_completed_loans_approval(request):
    # GET /api/loans/completed-approval/
    # Mirrors completed_loans_approval() web view exactly.
    # Returns sections grouped by completion month, newest first.
    try:
        filter_office = get_filter_office(request)
        loans_qs = LoanApplication.objects.filter(
            Q(repayment_amount_remaining__lte=Decimal('1')) | Q(repayment_amount_remaining__isnull=True),
            is_approved=False,
        ).select_related('client').order_by('first_repayment_date', 'client__firstname')
        if filter_office:
            loans_qs = loans_qs.filter(office=filter_office.name)

        loan_ids = [l.id for l in loans_qs]

        rep_map = {
            r['loan_application_id']: r
            for r in LoanRepayment.objects
            .filter(loan_application_id__in=loan_ids)
            .values('loan_application_id')
            .annotate(last_date=Max('repayment_date'), total_paid=Sum('repayment_amount'))
        }

        sections_dict = {}
        for loan in loans_qs:
            try:
                client = loan.client
                if not client:
                    continue
            except Exception:
                continue

            info      = rep_map.get(loan.id, {})
            last_date = info.get('last_date') or loan.application_date
            if not last_date:
                continue

            key   = (last_date.year, last_date.month)
            label = last_date.strftime('%B %Y').upper()
            tp    = info.get('total_paid', Decimal('0')) or Decimal('0')

            sections_dict.setdefault(key, {'label': label, 'loans': []})
            sections_dict[key]['loans'].append({
                'id':              loan.id,
                'sn':              len(sections_dict[key]['loans']) + 1,
                'loan_id_label':   f"{(loan.office or '').lower()}-{loan.id}",
                'client_name':     f"{client.firstname} {getattr(client,'middlename','') or ''} {client.lastname}".strip(),
                'check_no':        client.checkno or getattr(client, 'employmentcardno', '') or '—',
                'mobile':          client.phonenumber or '—',
                'office':          loan.office or '—',
                'loan_date':       _str(loan.application_date),
                'completion_date': _str(info.get('last_date')),
                'months':          loan.payment_period_months or 0,
                'loan_amount':     _d(loan.loan_amount),
                'interest':        _d(loan.total_interest_amount),
                'total_repayment': _d(loan.total_repayment_amount),
                'total_paid':      _d(tp),
                'loan_type':       loan.loan_type or '',
            })

        sections = []
        for k in sorted(sections_dict.keys(), reverse=True):
            grp        = sections_dict[k]
            loans_list = grp['loans']
            sections.append({
                'label':           grp['label'],
                'key':             f"{k[0]}-{k[1]:02d}",
                'loans':           loans_list,
                'count':           len(loans_list),
                'total_loaned':    _d(sum(Decimal(str(l['loan_amount']))     for l in loans_list)),
                'total_repayment': _d(sum(Decimal(str(l['total_repayment'])) for l in loans_list)),
                'total_paid':      _d(sum(Decimal(str(l['total_paid']))      for l in loans_list)),
            })

        filter_off2 = get_filter_office(request)
        sel2        = get_selected_office_api(request)
        branch_name = (filter_off2.name.upper() if filter_off2
                       else sel2.name.upper() if sel2 else 'ALL BRANCHES')

        return Response({
            'sections':    sections,
            'branch_name': branch_name,
            'total':       sum(s['count'] for s in sections),
        })

    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        return Response({'detail': f'Server error: {str(e)}', 'trace': tb}, status=500)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_completed_loans_approve(request):
    # POST /api/loans/completed-approval/approve/  body: {loan_id} or {loan_ids:[]}
    loan_id  = request.data.get('loan_id')
    loan_ids = request.data.get('loan_ids', [])
    if loan_id:
        loan_ids = [loan_id]
    if not loan_ids:
        return Response({'error': 'loan_id au loan_ids inahitajika.'}, status=400)
    approved = LoanApplication.objects.filter(
        Q(repayment_amount_remaining__lte=Decimal('1')) | Q(repayment_amount_remaining__isnull=True),
        id__in=loan_ids,
    )
    count = approved.count()
    approved.update(is_approved=True)
    return Response({'approved': count, 'message': str(count) + ' loan(s) approved.'})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_loan_receipt(request):
    # GET /api/loan-receipt/?client_id=<id>
    filter_office = get_filter_office(request)
    client_id = request.GET.get('client_id')
    if not client_id:
        return Response({'error': 'client_id inahitajika.'}, status=400)
    try:
        client = Client.objects.get(id=client_id)
    except Client.DoesNotExist:
        return Response({'error': 'Mteja hajapatikana.'}, status=404)
    loans = LoanApplication.objects.filter(client=client).prefetch_related('repayments').order_by('-created_at')
    if filter_office:
        loans = loans.filter(office=filter_office.name)
    result = []
    for loan in loans:
        reps = loan.repayments.all().order_by('created_at', 'id')
        result.append({'loan_id': loan.id, 'loan_type': loan.loan_type or '', 'loan_amount': _d(loan.loan_amount), 'total_repayment_amount': _d(loan.total_repayment_amount), 'repayment_amount_remaining': _d(loan.repayment_amount_remaining), 'repayments': [{'id': r.id, 'repayment_amount': _d(r.repayment_amount), 'repayment_date': _str(r.repayment_date), 'payment_month': _str(r.payment_month), 'transaction_method': r.transaction_method or '', 'receipt_no': str(r.id).zfill(6)} for r in reps]})
    return Response({'client': {'id': client.id, 'name': client.firstname + ' ' + client.lastname, 'phone': client.phonenumber or ''}, 'loans': result})


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_bank_cash_transaction_statement(request):
    # GET /api/bank-cash-transaction-statement/?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD
    # Mirrors bank_cash_transfer_report() web view exactly:
    #   Uses created_at DateTimeField range (not transaction_date)
    #   Returns: txn_id, date, receipt_no, name (office_from), description, amount, processed_by
    d_from, d_to, err = _parse_dates(request)
    if err:
        return Response({'error': err}, status=400)
    try:
        filter_office = get_filter_office(request)
        selected      = get_selected_office_api(request)

        dt_from = datetime.datetime.combine(d_from, datetime.time.min)
        dt_to   = datetime.datetime.combine(d_to,   datetime.time.max)

        txns = BankCashTransaction.objects.filter(
            created_at__range=(dt_from, dt_to),
        ).select_related('office_from').order_by('created_at', 'id')

        if filter_office:
            txns = txns.filter(office_from=filter_office)

        def _pname(user):
            if not user: return ''
            parts = [getattr(user,'first_name',''), getattr(user,'last_name','')]
            return ' '.join(p for p in parts if p) or getattr(user,'username','')

        rows = []
        for t in txns:
            src  = (t.source or '').lower()
            dest = (t.destination or '').lower()
            if src == 'bank' and dest == 'cash':
                desc = 'Bank to Cash transfer'
            elif src == 'cash' and dest == 'bank':
                desc = 'Cash to Bank transfer'
            else:
                desc = f"{t.source.title()} to {t.destination.title()} transfer"

            rows.append({
                'txn_id':       t.id,
                'date':         str(t.created_at.date()),
                'receipt_no':   str(t.id).zfill(6),
                'name':         t.office_from.name if t.office_from else '—',
                'description':  desc,
                'amount':       _d(t.amount),
                'processed_by': _pname(getattr(t, 'processed_by', None)) or (selected.name if selected else ''),
                'source':       t.source,
                'destination':  t.destination,
            })

        grand_total = _d(sum(Decimal(str(r['amount'])) for r in rows))
        branch_name = (filter_office.name.upper() if filter_office
                       else selected.name.upper() if selected else 'ALL BRANCHES')

        return Response({
            'rows':        rows,
            'count':       len(rows),
            'grand_total': grand_total,
            'branch_name': branch_name,
            'date_from':   str(d_from),
            'date_to':     str(d_to),
        })
    except Exception as e:
        return Response({'rows': [], 'count': 0, 'detail': str(e)})



@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_delete_bank_cash_transaction(request, txn_id):
    # POST /api/bank-cash-transaction/<id>/delete/
    # Mirrors delete_bank_cash_transaction() web view:
    #   Reverses the cash/bank balance change then deletes the transaction
    from django.db import transaction as db_transaction
    try:
        txn = BankCashTransaction.objects.get(pk=txn_id)
    except BankCashTransaction.DoesNotExist:
        return Response({'detail': 'Transaction not found.'}, status=404)
    try:
        with db_transaction.atomic():
            balance = BranchBalance.objects.filter(
                branch=txn.office_from).order_by('-last_updated').first()
            if not balance:
                return Response({'detail': f'No balance record for {txn.office_from.name}.'}, status=400)

            src  = (txn.source or '').lower()
            dest = (txn.destination or '').lower()
            new_office = balance.office_balance
            new_bank   = balance.bank_balance

            if src == 'cash' and dest == 'bank':
                # Original: cash↓ bank↑  → Reverse: cash↑ bank↓
                new_office += txn.amount
                new_bank   -= txn.amount
            elif src == 'bank' and dest == 'cash':
                # Original: bank↓ cash↑  → Reverse: bank↑ cash↓
                new_bank   += txn.amount
                new_office -= txn.amount

            BranchBalance.objects.create(
                branch=txn.office_from,
                office_balance=new_office,
                bank_balance=new_bank,
                updated_by=request.user,
            )

            # Delete linked HQTransaction (from_branch == to_branch, same office)
            hq_link = HQTransaction.objects.filter(
                from_branch=txn.office_from,
                to_branch=txn.office_from,
                amount=txn.amount,
            ).order_by('-id').first()
            if hq_link:
                hq_link.delete()

            receipt = str(txn_id).zfill(6)
            txn.delete()

        return Response({
            'success': True,
            'message': f'Transaction #{receipt} deleted and balances reversed.',
        })
    except Exception as e:
        return Response({'detail': f'Error: {str(e)}'}, status=500)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def api_customer_report(request):
    # GET /api/customer-report/?name=&branch=&status=active|completed&page=1&page_size=20
    # Mirrors customer_report() web view:
    #   - Searches firstname, middlename, and lastname (web searches all three)
    #   - branch filter uses icontains (office is a CharField)
    #   - orders by -application_date
    #   - paginates; returns branch list for dropdown
    search_name   = request.GET.get('name',     '').strip()
    branch_filter = request.GET.get('branch',   '').strip()
    status_filter = request.GET.get('status',   '').strip()   # active | completed | ''
    page_size     = min(int(request.GET.get('page_size', 20)), 100)
    page          = int(request.GET.get('page', 1))

    loans = (
        LoanApplication.objects
        .select_related('client')
        .order_by('-application_date')
    )

    # Name search — firstname, middlename, AND lastname (matches web view)
    if search_name:
        loans = loans.filter(
            Q(client__firstname__icontains=search_name)  |
            Q(client__middlename__icontains=search_name) |
            Q(client__lastname__icontains=search_name)
        )

    # Branch filter — office is a CharField, use icontains (matches web view)
    if branch_filter:
        loans = loans.filter(office__icontains=branch_filter)

    # Status filter
    if status_filter == 'active':
        loans = loans.filter(repayment_amount_remaining__gt=0)
    elif status_filter == 'completed':
        loans = loans.filter(repayment_amount_remaining__lte=0)

    total     = loans.count()
    start     = (page - 1) * page_size
    page_qs   = loans[start:start + page_size]

    rows = []
    for l in page_qs:
        c = l.client
        full_name = ' '.join(filter(None, [c.firstname, c.middlename or '', c.lastname]))
        rows.append({
            'loan_id':     l.id,
            'client_id':   c.id,
            'name':        full_name,
            'firstname':   c.firstname or '',
            'middlename':  c.middlename or '',
            'lastname':    c.lastname  or '',
            'phone':       c.phonenumber or '',
            'office':      l.office or '',
            'loan_type':   l.loan_type or '',
            'loan_amount': _d(l.loan_amount),
            'outstanding': _d(l.repayment_amount_remaining),
            'status':      'active' if (l.repayment_amount_remaining or 0) > 0 else 'completed',
            'date':        _str(l.application_date),
        })

    # Branch list for filter dropdown (distinct offices with loans)
    branches = list(
        LoanApplication.objects
        .exclude(office__isnull=True).exclude(office='')
        .values_list('office', flat=True)
        .distinct().order_by('office')
    )

    return Response({
        'count':       total,
        'page':        page,
        'page_size':   page_size,
        'total_pages': (total + page_size - 1) // page_size,
        'rows':        rows,
        'clients':     rows,    # alias
        'branches':    branches,
    })


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_office_transaction_add(request):
    # POST /api/office-transactions/add/
    # Accepts both office_from/office_to (ids) and office_from_id/office_to_id for compatibility
    import datetime as _dt

    office_from_id = (request.data.get('office_from')
                   or request.data.get('office_from_id'))
    office_to_id   = (request.data.get('office_to')
                   or request.data.get('office_to_id'))
    amount_raw     = str(request.data.get('amount', '') or '').replace(',', '').strip()
    tx_type        = request.data.get('transaction_type', 'Transfer')
    tx_method      = request.data.get('transaction_method', 'cash')
    date_str       = request.data.get('transaction_date', '')

    # Validate required fields
    missing = []
    if not office_from_id: missing.append('office_from')
    if not office_to_id:   missing.append('office_to')
    if not amount_raw:     missing.append('amount')
    if missing:
        return Response({'detail': 'Missing required fields: ' + ', '.join(missing)}, status=400)

    try:
        amount      = Decimal(amount_raw)
        office_from = Office.objects.get(id=int(office_from_id))
        office_to   = Office.objects.get(id=int(office_to_id))
    except Office.DoesNotExist as e:
        return Response({'detail': 'Office not found: ' + str(e)}, status=404)
    except (ValueError, TypeError) as e:
        return Response({'detail': 'Invalid office ID or amount: ' + str(e)}, status=400)

    # Parse transaction date
    txn_date = None
    for fmt in ('%Y-%m-%d', '%d/%m/%Y'):
        try:
            txn_date = _dt.datetime.strptime(date_str, fmt).date()
            break
        except Exception:
            pass
    if not txn_date:
        txn_date = _dt.date.today()

    txn = OfficeTransaction.objects.create(
        office_from=office_from,
        office_to=office_to,
        amount=amount,
        transaction_type=tx_type,
        transaction_method=tx_method,
        transaction_date=txn_date,
        processed_by=request.user,
    )
    return Response({
        'id':                 txn.id,
        'office_from':        office_from.name,
        'office_to':          office_to.name,
        'amount':             _d(txn.amount),
        'transaction_type':   txn.transaction_type,
        'transaction_method': txn.transaction_method,
        'transaction_date':   str(txn_date),
    }, status=201)


# ── Staff & Office Management ──────────────────────────────────────────────────

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_staff_add(request):
    from useraccount.models import CustomUser
    from django.contrib.auth.hashers import make_password
    data = request.data
    for f in ('first_name', 'last_name', 'username', 'password'):
        if not data.get(f):
            return Response({'detail': f + ' inahitajika.'}, status=400)
    if CustomUser.objects.filter(username=data['username']).exists():
        return Response({'detail': 'Username ' + data['username'] + ' tayari inatumika.'}, status=400)
    user = CustomUser.objects.create(first_name=data['first_name'], last_name=data['last_name'], username=data['username'], email=data.get('email', ''), password=make_password(data['password']), is_active=True, is_superuser=False)
    if data.get('salary'):
        try: user.salary = Decimal(str(data['salary']))
        except: pass
    if data.get('office_id'):
        try: user.office_allocation = Office.objects.get(id=data['office_id'])
        except: pass
    user.save()
    return Response({'id': user.id, 'full_name': user.get_full_name(), 'username': user.username, 'message': user.get_full_name() + ' amesajiliwa.'}, status=201)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_staff_block(request):
    from useraccount.models import CustomUser
    user_id = request.data.get('user_id')
    block   = request.data.get('block', True)
    if not user_id:
        return Response({'detail': 'user_id inahitajika.'}, status=400)
    try:
        target = CustomUser.objects.get(id=user_id)
    except CustomUser.DoesNotExist:
        return Response({'detail': 'Mtumiaji hajapatikana.'}, status=404)
    if target.is_superuser:
        return Response({'detail': 'Haiwezekani kuzuia superuser.'}, status=403)
    target.is_active = not bool(block)
    target.save(update_fields=['is_active'])
    action = 'Amezuiwa' if block else 'Amefunguliwa'
    return Response({'message': target.get_full_name() + ' ' + action + ' kwa mafanikio.', 'is_active': target.is_active})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_staff_transfer(request):
    from useraccount.models import CustomUser
    user_id   = request.data.get('user_id')
    office_id = request.data.get('office_id')
    if not user_id or not office_id:
        return Response({'detail': 'user_id na office_id vinahitajika.'}, status=400)
    try:
        target = CustomUser.objects.get(id=user_id)
        office = Office.objects.get(id=office_id)
    except CustomUser.DoesNotExist:
        return Response({'detail': 'Mtumiaji hajapatikana.'}, status=404)
    except Office.DoesNotExist:
        return Response({'detail': 'Tawi halijapatanikana.'}, status=404)
    target.office_allocation = office
    target.save(update_fields=['office_allocation'])
    return Response({'message': target.get_full_name() + ' amehamishwa kwenda ' + office.name + '.', 'user_id': target.id, 'new_office': office.name})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_office_add(request):
    name = request.data.get('name', '').strip()
    if not name:
        return Response({'detail': 'Jina la ofisi linahitajika.'}, status=400)
    if Office.objects.filter(name__iexact=name).exists():
        return Response({'detail': 'Ofisi ' + name + ' tayari ipo.'}, status=400)
    office = Office.objects.create(name=name, region=request.data.get('region', ''), district=request.data.get('district', ''), ward=request.data.get('ward', ''), street=request.data.get('street', ''), founded_date=request.data.get('founded_date') or None)
    return Response({'id': office.id, 'name': office.name, 'region': office.region, 'district': office.district, 'message': office.name + ' imesajiliwa.'}, status=201)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_expense_category_add(request):
    from app.models import ExpenseCategory
    name = request.data.get('name', '').strip()
    if not name:
        return Response({'detail': 'Jina la kategoria linahitajika.'}, status=400)
    if ExpenseCategory.objects.filter(name__iexact=name).exists():
        return Response({'detail': 'Kategoria ' + name + ' tayari ipo.'}, status=400)
    cat = ExpenseCategory.objects.create(name=name)
    return Response({'id': cat.id, 'name': cat.name}, status=201)


@api_view(['PATCH', 'DELETE'])
@permission_classes([IsAuthenticated])
def api_expense_category_edit(request, pk):
    from app.models import ExpenseCategory
    try:
        cat = ExpenseCategory.objects.get(pk=pk)
    except ExpenseCategory.DoesNotExist:
        return Response({'detail': 'Haijapatanikana.'}, status=404)
    if request.method == 'DELETE':
        cat.delete()
        return Response({'message': 'Imefutwa.'})
    name = request.data.get('name', '').strip()
    if name:
        cat.name = name
        cat.save(update_fields=['name'])
    return Response({'id': cat.id, 'name': cat.name})



@api_view(['POST'])
@permission_classes([IsAuthenticated])
def manage_admin_branches_add(request):
    # POST /api/manage-admin-branches/add/  body: {user_id, office_id}
    from useraccount.models import CustomUser
    user_id   = request.data.get('user_id')
    office_id = request.data.get('office_id')
    if not user_id or not office_id:
        return Response({'detail': 'user_id na office_id vinahitajika.'}, status=400)
    try:
        user   = CustomUser.objects.get(pk=user_id)
        office = Office.objects.get(pk=office_id)
    except (CustomUser.DoesNotExist, Office.DoesNotExist):
        return Response({'detail': 'User au Office haijapatanikana.'}, status=404)
    _, created = UserOfficeAssignment.objects.get_or_create(user=user, office=office)
    if not user.office_allocation:
        user.office_allocation = office
        user.save(update_fields=['office_allocation'])
    return Response({'message': office.name + ' added to ' + user.get_full_name() + '.', 'created': created})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def manage_admin_branches_set_current(request):
    # POST /api/manage-admin-branches/set-current/  body: {user_id, office_id}
    from useraccount.models import CustomUser
    user_id   = request.data.get('user_id')
    office_id = request.data.get('office_id')
    if not user_id or not office_id:
        return Response({'detail': 'user_id na office_id vinahitajika.'}, status=400)
    try:
        user   = CustomUser.objects.get(pk=user_id)
        office = Office.objects.get(pk=office_id)
    except (CustomUser.DoesNotExist, Office.DoesNotExist):
        return Response({'detail': 'User au Office haijapatanikana.'}, status=404)
    user.office_allocation = office
    user.save(update_fields=['office_allocation'])
    return Response({'message': 'Current branch changed to ' + office.name + '.', 'office': office.name, 'office_id': office.id})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def manage_admin_branches_remove(request):
    # POST /api/manage-admin-branches/remove/  body: {user_id, office_id}
    from useraccount.models import CustomUser
    user_id   = request.data.get('user_id')
    office_id = request.data.get('office_id')
    if not user_id or not office_id:
        return Response({'detail': 'user_id na office_id vinahitajika.'}, status=400)
    try:
        user   = CustomUser.objects.get(pk=user_id)
        office = Office.objects.get(pk=office_id)
    except (CustomUser.DoesNotExist, Office.DoesNotExist):
        return Response({'detail': 'User au Office haijapatanikana.'}, status=404)
    if user.office_allocation and user.office_allocation.id == office.id:
        return Response({'detail': 'Cannot remove current branch. Set another branch as current first.'}, status=400)
    UserOfficeAssignment.objects.filter(user=user, office=office).delete()
    return Response({'message': office.name + ' removed from ' + user.get_full_name() + '.'})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def api_toggle_loan_approve(request, loan_id):
    # POST /api/loans/<loan_id>/toggle-approve/
    # Mirrors toggle_loan_approve() web view
    try:
        loan = LoanApplication.objects.get(pk=loan_id)
    except LoanApplication.DoesNotExist:
        return Response({'detail': 'Loan not found.'}, status=404)
    loan.is_approved = not loan.is_approved
    loan.save(update_fields=['is_approved'])
    return Response({
        'success':     True,
        'loan_id':     loan.id,
        'is_approved': loan.is_approved,
        'message':     'Approved' if loan.is_approved else 'Approval removed',
    })



