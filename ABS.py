import csv
import pandas as pd
from datetime import datetime

# ----- Dynamic/Tiered Fees -----
class Fee:
    def __init__(self, name, base_rate, priority, tier_schedule=None):
        self.name = name
        self.base_rate = base_rate  # Default annual rate
        self.priority = priority
        self.tier_schedule = tier_schedule or []  # [(period_start, period_end, rate)]
        self.accrued = 0

    def get_rate(self, period, pool_balance):
        for sched in self.tier_schedule:
            if sched[0] <= period <= sched[1]:
                return sched[2]
        return self.base_rate

    def calculate(self, pool_balance, period):
        rate = self.get_rate(period, pool_balance)
        fee = pool_balance * rate / 12
        self.accrued += fee
        return fee

# ----- Advanced IFRS/EIR & Stage Impairment -----
class IFRSAccount:
    def __init__(self, eir, gross_carrying, stage=1):
        self.eir = eir
        self.gross_carrying = gross_carrying
        self.stage = stage
        self.impairment = 0
        self.interest_income = 0

    def accrue_interest(self):
        interest = self.gross_carrying * self.eir / 12
        self.interest_income += interest
        return interest

    def recognize_impairment(self, expected_loss):
        if self.stage == 1:
            self.impairment += expected_loss * 0.01  # 1% for Stage 1
        elif self.stage == 2:
            self.impairment += expected_loss * 0.03  # 3% for Stage 2
        elif self.stage == 3:
            self.impairment += expected_loss  # 100% for default
        return self.impairment

    def move_stage(self, stage):
        self.stage = stage

# ----- Loan -----
class Loan:
    def __init__(self, principal, rate, term):
        self.principal = principal
        self.rate = rate
        self.term = term
        self.remaining_principal = principal
        self.active = True

    def monthly_payment(self):
        r = self.rate / 12
        n = self.term
        if r == 0:
            return self.principal / n
        return self.principal * (r * (1 + r) ** n) / ((1 + r) ** n - 1)

    def step(self, prepay_rate=0, default_rate=0):
        if not self.active or self.remaining_principal <= 0:
            return dict(interest=0, principal=0, prepayment=0, default=0, cashflow=0, remaining_principal=0)
        payment = self.monthly_payment()
        interest = self.remaining_principal * self.rate / 12
        principal = payment - interest

        prepayment = prepay_rate * self.remaining_principal
        default = default_rate * self.remaining_principal

        total_principal = min(self.remaining_principal, principal + prepayment + default)
        cashflow = interest + total_principal

        self.remaining_principal -= total_principal
        if self.remaining_principal < 1e-8:
            self.remaining_principal = 0
            self.active = False
        return dict(
            interest=interest,
            principal=principal,
            prepayment=prepayment,
            default=default,
            cashflow=cashflow,
            remaining_principal=self.remaining_principal,
        )

# ----- Tranche (with IFRS) -----
class Tranche:
    def __init__(self, name, principal, rate, subordination_level, eir=None):
        self.name = name
        self.principal = principal
        self.rate = rate
        self.remaining_principal = principal
        self.subordination_level = subordination_level
        self.ifrs = IFRSAccount(eir or rate, principal)
        self.interest_due = 0
        self.interest_paid = 0
        self.principal_paid = 0
        self.losses = 0

    def pay_interest(self, cash_available):
        interest = self.remaining_principal * self.rate / 12
        pay = min(interest, cash_available)
        self.interest_due = interest
        self.interest_paid = pay
        self.ifrs.accrue_interest()
        return pay

    def pay_principal(self, cash_available):
        pay = min(self.remaining_principal, cash_available)
        self.principal_paid = pay
        self.remaining_principal -= pay
        self.ifrs.gross_carrying = self.remaining_principal
        return pay

    def allocate_loss(self, loss, period):
        applied = min(self.remaining_principal, loss)
        self.losses += applied
        self.remaining_principal -= applied
        # Example: move to Stage 3 if loss applied
        if applied > 0:
            self.ifrs.move_stage(3)
        self.ifrs.recognize_impairment(applied)
        return loss - applied

# ----- Reserve -----
class ReserveAccount:
    def __init__(self, target):
        self.target = target
        self.balance = 0

    def fill(self, cash_available):
        to_fill = self.target - self.balance
        added = min(cash_available, to_fill)
        self.balance += added
        return added

    def withdraw(self, amount):
        taken = min(self.balance, amount)
        self.balance -= taken
        return taken

# ----- Waterfall -----
def waterfall(tranches, reserve, fees, total_interest, total_principal, total_losses, triggers, pool_balance, period, pro_rata_start=36, turbo_redemption=True):
    cash_interest = total_interest
    cash_principal = total_principal
    losses = total_losses
    results = {}

    # 1. Fees by priority
    fees_paid = {}
    for fee in sorted(fees, key=lambda f: f.priority):
        pay = min(fee.calculate(pool_balance, period), cash_interest)
        fees_paid[fee.name] = pay
        cash_interest -= pay
    results['fees_paid'] = fees_paid

    # 2. Interest payments
    for tranche in sorted(tranches, key=lambda t: t.subordination_level):
        pay = tranche.pay_interest(cash_interest)
        cash_interest -= pay
        results[f'{tranche.name}_interest_paid'] = pay

    # 3. Principal payments
    if period < pro_rata_start:
        # Sequential (turbo)
        for tranche in sorted(tranches, key=lambda t: t.subordination_level):
            pay = tranche.pay_principal(cash_principal)
            cash_principal -= pay
            results[f'{tranche.name}_principal_paid'] = pay
    else:
        # Pro-rata
        total_outstanding = sum(tr.remaining_principal for tr in tranches)
        for tranche in tranches:
            share = (tranche.remaining_principal / total_outstanding) if total_outstanding > 0 else 0
            pay = min(cash_principal * share, tranche.remaining_principal)
            pay = min(pay, cash_principal)
            pay = max(pay, 0)
            tranche.pay_principal(pay)
            cash_principal -= pay
            results[f'{tranche.name}_principal_paid'] = pay

    # 4. Allocate losses (junior first)
    for tranche in sorted(tranches, key=lambda t: -t.subordination_level):
        losses = tranche.allocate_loss(losses, period)
        results[f'{tranche.name}_losses'] = tranche.losses

    # 5. Reserve
    reserve_fill = reserve.fill(cash_interest + cash_principal)
    results['reserve_fill'] = reserve_fill

    return results, cash_principal

# ----- Callable Feature -----
class CallableOption:
    def __init__(self, call_period, call_price_pct=1.0):
        self.call_period = call_period
        self.call_price_pct = call_price_pct
        self.called = False

    def check_call(self, period, pool_balance, call_trigger=0.05):
        if period >= self.call_period and pool_balance < call_trigger:
            self.called = True
        return self.called

# ----- Main Simulation -----
def simulate_abs(pool, tranches, reserve, fees, callable_opt, periods, loan_rate, loan_term, cpr=0.05, cdr=0.01, lgd=1.0, turbo_redemption=True, pro_rata_start=36, csv_file="abs_cashflows.csv", excel_file="abs_cashflows.xlsx"):
    history = []
    for t in range(periods):
        period = dict(month=t+1, date=(datetime.today() + pd.DateOffset(months=t)).strftime('%Y-%m-%d'))
        period['total_interest'] = 0
        period['total_principal'] = 0
        period['total_prepayment'] = 0
        period['total_default'] = 0
        period['total_losses'] = 0

        for loan in pool:
            cf = loan.step(prepay_rate=cpr/12, default_rate=cdr/12)
            period['total_interest'] += cf['interest']
            period['total_principal'] += cf['principal'] + cf['prepayment']
            period['total_prepayment'] += cf['prepayment']
            period['total_default'] += cf['default']
            period['total_losses'] += cf['default'] * lgd

        pool_balance = sum(l.remaining_principal for l in pool)
        notes_balance = sum(tr.remaining_principal for tr in tranches)

        # Callable feature
        if callable_opt and callable_opt.check_call(period=t+1, pool_balance=pool_balance, call_trigger=0.05 * notes_balance):
            for tranche in tranches:
                pay = tranche.remaining_principal * callable_opt.call_price_pct
                tranche.pay_principal(pay)
                period[f'{tranche.name}_call_redemption'] = pay
            period['called'] = True
            history.append(period)
            break

        # Waterfall
        wf, leftover_principal = waterfall(
            tranches, reserve, fees,
            period['total_interest'],
            period['total_principal'],
            period['total_losses'],
            triggers=None,
            pool_balance=pool_balance,
            period=t+1,
            pro_rata_start=pro_rata_start,
            turbo_redemption=turbo_redemption
        )
        period.update(wf)

        # Reinvestment logic (example: only before pro-rata)
        if t+1 < pro_rata_start:
            loan_size = 100000
            while leftover_principal >= loan_size:
                pool.append(Loan(loan_size, loan_rate, loan_term))
                leftover_principal -= loan_size
        period['reinvested_principal'] = period['total_principal'] - leftover_principal

        for tranche in tranches:
            period[f'{tranche.name}_outstanding'] = tranche.remaining_principal
            period[f'{tranche.name}_ifrs_interest_income'] = tranche.ifrs.interest_income
            period[f'{tranche.name}_ifrs_impairment'] = tranche.ifrs.impairment
            period[f'{tranche.name}_stage'] = tranche.ifrs.stage
        for fee in fees:
            period[f'{fee.name}_accrued'] = fee.accrued
        period['reserve_balance'] = reserve.balance
        period['pool_balance'] = pool_balance
        history.append(period)

        # Early exit: all tranches paid off
        if all(abs(tr.remaining_principal) < 1e-8 for tr in tranches):
            break

    # Export to CSV/Excel
    df = pd.DataFrame(history)
    df.to_csv(csv_file, index=False)
    df.to_excel(excel_file, index=False)
    return history

# ----- Example usage -----
if __name__ == "__main__":
    pool = [Loan(100000, 0.05, 360) for _ in range(100)]
    pool_principal = sum(l.principal for l in pool)

    # Tranches with EIR
    tranches = [
        Tranche("A", 0.80 * pool_principal, 0.03, 1, eir=0.032),
        Tranche("B", 0.15 * pool_principal, 0.06, 2, eir=0.061),
        Tranche("C", 0.05 * pool_principal, 0.09, 3, eir=0.092),
    ]
    reserve = ReserveAccount(target=0.01 * pool_principal)

    # Tiered fees: 0-12 months 0.5%, 13-24 months 0.8%, then 0.3%
    fees = [
        Fee("ServicerFee", 0.005, 1, tier_schedule=[(1, 12, 0.005), (13, 24, 0.008), (25, 360, 0.003)]),
        Fee("AdminFee", 0.002, 2, tier_schedule=[(1, 360, 0.002)]),
    ]

    callable_opt = CallableOption(call_period=36, call_price_pct=1.0)

    results = simulate_abs(
        pool, tranches, reserve, fees, callable_opt,
        periods=360, loan_rate=0.05, loan_term=360,
        cpr=0.06, cdr=0.02, lgd=1.0,
        turbo_redemption=True, pro_rata_start=36,
        csv_file="abs_cashflows.csv",
        excel_file="abs_cashflows.xlsx"
    )

    print("First 12 months, see CSV/Excel for all results:")
    import pprint
    pprint.pprint(results[:12])