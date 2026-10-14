# 6-Minute Presentation & Q&A Strategy Guide
**Wissen Campus Assessment — Price Alert Tool**

---

## 6-Minute Presentation Timing Breakdown

### Minute 1–2: What the Tool Does & Architecture
- **Objective**: Demonstrate that you built a robust, zero-dependency financial alert engine.
- **Talking Points**:
  - *"The tool evaluates daily close prices against two types of rules: price level breaches and moving average crossovers (e.g. 5/20 MA cross)."*
  - *"It is designed around pure Python standard library (`csv`, `json`, `sys`) so it runs cleanly on any evaluator's machine in one command: `python alerts.py prices.csv rules.json`."*
  - *"The architecture separates data loading, per-instrument chronological normalization, rule evaluation, and deterministic output formatting."*

### Minute 3–4: How You Verified It & Handled Real-World Edge Cases
- **Objective**: Prove engineering depth and rigor.
- **Talking Points**:
  - *"Real financial market data is messy. I wrote a dedicated test suite with 13 comprehensive unit and integration tests covering conditions not in the base sample."*
  - **1. Unordered dates & interleaved tickers**: *"CSV rows may arrive in arbitrary order across multiple tickers. The tool partitions by ticker and sorts chronologically before running moving window aggregations."*
  - **2. Cold Start / Day 1 Semantics**: *"If a stock starts trading below 1500 on Day 1, does it trigger? No, because the brief states it must have been on the other side the previous day. Day 1 has no previous trading day."*
  - **3. MA Window Warmup Period**: *"For a 5/20 crossover, the 20-day MA is undefined until day 20. But day 20 itself cannot be a crossover because on day 19 the 20-day MA did not exist. Therefore, the earliest crossover can only occur on day 21 (index 20)."*
  - **4. Output Determinism**: *"If multiple rules trigger on the same date, outputs are sorted alphabetically by `rule_id`."*

### Minute 5: One Thing the Assistant Got Wrong (Crucial Honesty Section)
- **Objective**: Fulfill the specific evaluation rubric with honesty and clarity.
- **Talking Points**:
  - *"The AI assistant initially gave me code that checked `close < level` without checking the previous day state. This caused two major bugs:"*
    - *"1) It triggered immediately on Day 1 if the opening price was already below 1500."*
    - *"2) It triggered continuously on every single day the price remained low, rather than only on the crossing day."*
  - *"Additionally, the assistant attempted to evaluate rows in streaming order from the CSV file without sorting dates per instrument, which broke moving averages when rows were shuffled."*
  - *"I discarded that logic, built explicit state-transition checks (`prev > level and curr < level`), and enforced per-instrument time-series sorting."*

### Minute 6: Quick Live Demo & Transition to Q&A
- **Action**: Run the command in your terminal:
  ```bash
  python alerts.py prices.csv rules.json
  ```
- **Show stdout**: Point out the exact output lines matching the brief:
  ```text
  2026-09-03 r1 INFY level below 1500
  2026-09-24 r2 TCS ma_cross 5/20 above
  ```
- **Optional Visual**: Show `http://localhost:8000` to visually inspect the exact crossover point on the chart.
- *"I am ready to run the tool on any dataset you have brought."*

---

## 6-Minute Q&A Anticipated Questions & Answers

### Q1: "How do you handle weekends and missing dates? Does a 20-day MA mean 20 calendar days or 20 trading days?"
- **Answer**: *"In quantitative finance and stock exchanges, moving averages are computed over trading days (active trading sessions), not calendar days. The CSV represents one row per instrument per trading day. The tool computes the moving average over the last $N$ available trading sessions for that instrument."*

### Q2: "What happens if our test file has duplicate dates for the same instrument?"
- **Answer**: *"The parser detects duplicate timestamps per instrument, logs a non-fatal warning to `stderr` with the line number, and uses the latest record so stdout remains clean and the pipeline does not crash."*

### Q3: "What if a rule references a stock that doesn't exist in the CSV?"
- **Answer**: *"The tool safely handles empty series: it skips evaluation for unrepresented symbols without raising exceptions or emitting false alerts."*

### Q4: "What if the price touches 1500 exactly (e.g. 1510 -> 1500 -> 1490)?"
- **Answer**: *"At 1500, the price is not below 1500, so it does not trigger. When it drops to 1490, it is below 1500 and the previous day was on the other side (>= 1500), so the alert fires on the day it drops to 1490."*

### Q5: "Why did you avoid external libraries like Pandas or NumPy?"
- **Answer**: *"The evaluation criteria states that the tool must run from a clean download with one command on any machine. By implementing moving averages with Python standard library, there is zero risk of version incompatibility or missing dependencies."*
