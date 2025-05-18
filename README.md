# Asset-Backed-Security-ABS-
Structured Finance

# ABS Cashflow Engine

A production-level Asset-Backed Securities (ABS) cashflow engine in Python, featuring:

- **Dynamic/Tiered Fee Structures:** Fees can change based on period or pool balance.
- **Advanced IFRS Accounting:** Simulates EIR (Effective Interest Rate), impairment stages (1/2/3), and loss recognition.
- **Callable Features:** Handles clean-up calls/early redemption.
- **Pro-Rata and Time-Dependent Waterfall:** Waterfall switches from sequential to pro-rata after a set period.
- **Integration Hooks:** Outputs results to CSV, Excel, and Pandas DataFrame (easy to use with dashboards or databases).

## Features

- Amortizing loan pool simulation (with prepayments and defaults)
- Tranche structure and waterfall logic (sequential/turbo and pro-rata)
- Multiple fee types with tiered/dynamic schedules
- Reserve account with configurable target
- IFRS 9/15-style accounting per tranche
- Callable ABS notes (early redemption)
- Outputs to CSV and Excel for reporting and audit
- Modular code – easy to extend for more triggers, fee types, reporting, etc.

## Requirements

- Python 3.8+
- pandas
- openpyxl (for Excel output)

Install requirements:
```bash
pip install pandas openpyxl
```

## Usage

1. **Clone or copy the repository.**
2. **Run the main script:**
    ```bash
    python abs_production_full.py
    ```
3. **Output files:**
    - `abs_cashflows.csv`
    - `abs_cashflows.xlsx`
4. **First 12 months of results are printed to the screen.**

## Customization

- **Change pool, tranche, or fee parameters** in the `if __name__ == "__main__"` section.
- **Modify waterfall logic, triggers, or fee schedules** by editing the respective classes or logic blocks.
- **Integrate with a database or dashboard** using the Pandas DataFrame (`df`) that’s created at the end of the simulation.

## File Structure

- `abs_production_full.py` — Main engine with all features
- `abs_cashflows.csv` — CSV output (after run)
- `abs_cashflows.xlsx` — Excel output (after run)
- `README.md` — This file

## Example Tiered Servicer Fee

```python
fees = [
    Fee("ServicerFee", 0.005, 1, tier_schedule=[(1, 12, 0.005), (13, 24, 0.008), (25, 360, 0.003)]),
]
```

## Example Callable Tranche

```python
callable_opt = CallableOption(call_period=36, call_price_pct=1.0)
```

## Extending

- Add more advanced triggers (IC/OC, event-driven pro-rata, etc.)
- Add dashboard output (use Streamlit or Dash with the DataFrame)
- Connect to a database (see integration stubs in code)

## Support

Open a GitHub issue or discussion for help, suggestions, or requests!

---
