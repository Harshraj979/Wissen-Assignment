# Price Alert Tool

A lightweight, zero-dependency command-line utility (with an optional visual dashboard) that evaluates daily instrument prices against alert rules and outputs chronological triggers.

---

## 1. How to Run It

Built with Python 3 standard library only (`csv`, `json`, `sys`). **No third-party packages or installations required.**

### Command Line (Standard Assessment Execution)
```bash
python alerts.py prices.csv rules.json
```
Output conforms strictly to the specification:
```text
2026-09-03 r1 INFY level below 1500
2026-09-24 r2 TCS ma_cross 5/20 above
```
*(One line per alert, sorted chronologically by date, then by rule ID. Days without triggers emit nothing.)*

### Run Tests
```bash
python -m unittest -v test_alerts.py
```

### Optional Visual Dashboard
```bash
python alerts.py --web
# or: python web_server.py
```
Opens a local interface at `http://localhost:8000` to inspect interactive charts, moving averages, threshold lines, and test custom data.

---

## 2. How I Used the Assistant (Prompts in Brief)

1. **Initial Scaffold Prompt**: *"Generate a Python script parsing CSV prices and JSON rules to evaluate level and MA crossover alerts as specified in the brief."*
2. **Edge-Case Brainstorm Prompt**: *"List potential failure modes when running price alerts on unseen historical datasets (e.g. date gaps, duplicate dates, boundaries)."*
3. **Test Suite Generation Prompt**: *"Write unit tests covering unordered dates, Day 1 boundary non-triggers, and exact threshold touches."*

---

## 3. What the Assistant Got Wrong

1. **False Trigger on Initial Data (Day 1)**: The assistant's first implementation checked `close < level` without verifying whether a previous day existed. As a result, if an instrument started trading below 1500 on Day 1, it fired an alert immediately, violating the rule that it must have been on the other side the previous day.
2. **Streaming Rows Without Per-Instrument Date Sorting**: The assistant attempted to evaluate rows sequentially from the CSV. Because the brief states *"dates may be out of order"* and multiple instruments are interleaved, streaming produced inverted intervals and corrupt moving average windows.
3. **Off-by-One on Moving Average Warmup**: For an MA cross rule with window sizes `short` ($S$) and `long` ($L$), the assistant evaluated crossovers starting on day index $L - 1$. However, on day $L - 1$ the long MA is defined for the very first time; its previous day ($L - 2$) is undefined. A crossover cannot be established without a valid previous day for both moving averages. The earliest valid crossover day is day index $L$ (the $(L+1)$-th trading day).
4. **Boundary and Equality Bounces**: The assistant used `>=` and `<=`, causing false positive triggers when prices touched the exact threshold and bounced back rather than crossing through.

---

## 4. What I Changed and Why

- **Stateful Pre-Processing**: Grouped rows by instrument and sorted each series strictly chronologically by ISO date before evaluation.
- **Strict Cross Logic**: 
  - For `level below`: enforced `prev_close > level` and `curr_close < level` with an epsilon buffer (`1e-9`) to avoid binary floating-point drift.
  - For `ma_cross`: required both $MA_S$ and $MA_L$ to be non-null on both day $t-1$ and day $t$, triggering only when $(S_{t-1} \le L_{t-1})$ transitions to $(S_t > L_t)$ for `above` (and vice-versa for `below`).
- **Deterministic Ordering**: Implemented multi-key sorting on alerts (`date`, then `rule_id`) so outputs remain consistent regardless of JSON rule order.
- **Graceful Error Recovery**: Malformed lines, non-numeric prices, and duplicate dates emit warnings to `stderr` without crashing stdout.
