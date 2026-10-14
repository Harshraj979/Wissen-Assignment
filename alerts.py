#!/usr/bin/env python3
"""
Price Alert Tool
----------------
A command-line tool that reads daily prices for financial instruments,
applies alert rules from a configuration file, and outputs which alerts
fired on which day in chronological order.

Complies with the Wissen Campus Assessment Build Brief.
Standard library only (zero external dependencies).
"""

from __future__ import annotations

import csv
import json
import os
import sys
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

EPSILON = 1e-9


@dataclass(frozen=True)
class PricePoint:
    date: str
    close: float


@dataclass(frozen=True)
class Alert:
    date: str
    rule_id: str
    instrument: str
    rule_type: str
    details: str

    def to_output_line(self) -> str:
        return f"{self.date} {self.rule_id} {self.instrument} {self.rule_type} {self.details}"


def format_level_number(val: float) -> str:
    """Format a level number cleanly (e.g. 1500 instead of 1500.0 if whole)."""
    if abs(val - round(val)) < EPSILON:
        return str(int(round(val)))
    return f"{val:g}"


def parse_prices_csv(filepath_or_stream) -> Dict[str, List[PricePoint]]:
    """
    Parse the CSV prices file and return prices grouped by instrument,
    sorted chronologically by date.
    
    Expected CSV header: date,instrument,close
    Handles:
      - Dates out of order
      - Extra whitespace around headers or values
      - Malformed or blank rows (skipped with warning to stderr)
      - Duplicate dates for the same instrument (keeps the latest row)
    """
    if isinstance(filepath_or_stream, str):
        if not os.path.exists(filepath_or_stream):
            raise FileNotFoundError(f"Prices file not found: {filepath_or_stream}")
        f = open(filepath_or_stream, mode="r", encoding="utf-8-sig")
        should_close = True
    else:
        f = filepath_or_stream
        should_close = False

    raw_by_instrument: Dict[str, Dict[str, float]] = {}

    try:
        reader = csv.reader(f)
        header = None
        for row_num, row in enumerate(reader, start=1):
            if not row or not any(cell.strip() for cell in row):
                continue

            cleaned_row = [cell.strip() for cell in row]

            if header is None:
                header = [c.lower() for c in cleaned_row]
                if len(header) < 3 or "date" not in header or "instrument" not in header or "close" not in header:
                    raise ValueError(
                        f"Invalid CSV header: {row}. Expected columns: date, instrument, close"
                    )
                date_idx = header.index("date")
                inst_idx = header.index("instrument")
                close_idx = header.index("close")
                continue

            if len(cleaned_row) <= max(date_idx, inst_idx, close_idx):
                sys.stderr.write(f"[WARN] Line {row_num}: Malformed row skipped: {row}\n")
                continue

            date_str = cleaned_row[date_idx]
            instrument = cleaned_row[inst_idx].upper()
            close_raw = cleaned_row[close_idx]

            try:
                close_val = float(close_raw)
            except ValueError:
                sys.stderr.write(f"[WARN] Line {row_num}: Invalid close price '{close_raw}' skipped\n")
                continue

            if instrument not in raw_by_instrument:
                raw_by_instrument[instrument] = {}

            if date_str in raw_by_instrument[instrument]:
                sys.stderr.write(
                    f"[WARN] Duplicate entry for {instrument} on {date_str} at line {row_num}. Using latest.\n"
                )

            raw_by_instrument[instrument][date_str] = close_val
    finally:
        if should_close:
            f.close()

    # Sort each instrument's price points strictly by date
    sorted_by_instrument: Dict[str, List[PricePoint]] = {}
    for inst, date_map in raw_by_instrument.items():
        sorted_dates = sorted(date_map.keys())
        sorted_by_instrument[inst] = [PricePoint(date=d, close=date_map[d]) for d in sorted_dates]

    return sorted_by_instrument


def parse_rules_json(filepath_or_stream) -> List[Dict[str, Any]]:
    """
    Parse and validate the JSON rules file.
    
    Validates:
      - Rule list structure
      - Required fields: id, instrument, type, direction
      - Valid types ('level', 'ma_cross')
      - Valid directions ('above', 'below')
      - Numeric parameters (level, short, long where short < long)
    """
    if isinstance(filepath_or_stream, str):
        if not os.path.exists(filepath_or_stream):
            raise FileNotFoundError(f"Rules file not found: {filepath_or_stream}")
        with open(filepath_or_stream, mode="r", encoding="utf-8") as f:
            data = json.load(f)
    else:
        data = json.load(filepath_or_stream)

    if not isinstance(data, list):
        raise ValueError("Rules file must contain a JSON array of rule objects.")

    validated_rules: List[Dict[str, Any]] = []
    seen_ids = set()

    for idx, rule in enumerate(data):
        if not isinstance(rule, dict):
            sys.stderr.write(f"[WARN] Rule at index {idx} is not an object. Skipping.\n")
            continue

        rule_id = str(rule.get("id", "")).strip()
        if not rule_id:
            sys.stderr.write(f"[WARN] Rule at index {idx} missing 'id'. Skipping.\n")
            continue

        if rule_id in seen_ids:
            sys.stderr.write(f"[WARN] Duplicate rule id '{rule_id}'. Skipping.\n")
            continue
        seen_ids.add(rule_id)

        instrument = str(rule.get("instrument", "")).strip().upper()
        rule_type = str(rule.get("type", "")).strip().lower()
        direction = str(rule.get("direction", "")).strip().lower()

        if not instrument or not rule_type or not direction:
            sys.stderr.write(f"[WARN] Rule '{rule_id}' missing required fields. Skipping.\n")
            continue

        if direction not in ("above", "below"):
            sys.stderr.write(
                f"[WARN] Rule '{rule_id}' has invalid direction '{direction}'. Must be 'above' or 'below'. Skipping.\n"
            )
            continue

        if rule_type == "level":
            if "level" not in rule:
                sys.stderr.write(f"[WARN] Level rule '{rule_id}' missing 'level' field. Skipping.\n")
                continue
            try:
                level_val = float(rule["level"])
            except (ValueError, TypeError):
                sys.stderr.write(f"[WARN] Level rule '{rule_id}' has non-numeric level. Skipping.\n")
                continue

            validated_rules.append({
                "id": rule_id,
                "instrument": instrument,
                "type": "level",
                "direction": direction,
                "level": level_val,
            })

        elif rule_type == "ma_cross":
            try:
                short_w = int(rule.get("short", 0))
                long_w = int(rule.get("long", 0))
            except (ValueError, TypeError):
                sys.stderr.write(f"[WARN] MA cross rule '{rule_id}' has non-integer windows. Skipping.\n")
                continue

            if short_w <= 0 or long_w <= 0 or short_w >= long_w:
                sys.stderr.write(
                    f"[WARN] MA cross rule '{rule_id}' invalid window sizes (short={short_w}, long={long_w}). Short must be < long. Skipping.\n"
                )
                continue

            validated_rules.append({
                "id": rule_id,
                "instrument": instrument,
                "type": "ma_cross",
                "short": short_w,
                "long": long_w,
                "direction": direction,
            })
        else:
            sys.stderr.write(f"[WARN] Unknown rule type '{rule_type}' for rule '{rule_id}'. Skipping.\n")
            continue

    return validated_rules


def calculate_sma_series(prices: List[float], window: int) -> List[Optional[float]]:
    """
    Calculate Simple Moving Average for a sequence of prices.
    Returns a list of the same length as prices.
    Values before the full window has elapsed are None.
    """
    sma: List[Optional[float]] = [None] * len(prices)
    if window <= 0 or len(prices) < window:
        return sma

    running_sum = sum(prices[:window])
    sma[window - 1] = running_sum / window

    for i in range(window, len(prices)):
        running_sum += prices[i] - prices[i - window]
        sma[i] = running_sum / window

    return sma


def evaluate_level_rule(rule: Dict[str, Any], series: List[PricePoint]) -> List[Alert]:
    """
    Evaluate a level rule on a chronological price series.
    
    Specification:
    'A level rule fires on the first day the close crosses the level in the given direction
    (it was on the other side the previous day).'
    
    Direction 'below':
      Previous day close was > level (on the other side).
      Current day close is < level.
      
    Direction 'above':
      Previous day close was < level (on the other side).
      Current day close is > level.
    """
    alerts: List[Alert] = []
    level = rule["level"]
    direction = rule["direction"]
    rule_id = rule["id"]
    instrument = rule["instrument"]
    level_str = format_level_number(level)

    for i in range(1, len(series)):
        prev_close = series[i - 1].close
        curr_close = series[i].close

        if direction == "below":
            # Crossed below: was strictly above, now strictly below
            if prev_close > (level + EPSILON) and curr_close < (level - EPSILON):
                alerts.append(Alert(
                    date=series[i].date,
                    rule_id=rule_id,
                    instrument=instrument,
                    rule_type="level",
                    details=f"below {level_str}",
                ))
        elif direction == "above":
            # Crossed above: was strictly below, now strictly above
            if prev_close < (level - EPSILON) and curr_close > (level + EPSILON):
                alerts.append(Alert(
                    date=series[i].date,
                    rule_id=rule_id,
                    instrument=instrument,
                    rule_type="level",
                    details=f"above {level_str}",
                ))

    return alerts


def evaluate_ma_cross_rule(rule: Dict[str, Any], series: List[PricePoint]) -> List[Alert]:
    """
    Evaluate an ma_cross rule on a chronological price series.
    
    Specification:
    'An ma_cross rule fires on the day the short moving average crosses the long one
    in the given direction. Moving averages need a full window of days before they are defined.'
    
    Because moving averages require a full window of days, both short and long MAs
    must be defined on both day t-1 and day t to evaluate a crossover.
    The long window is strictly greater than the short window, so day t=long is the
    earliest possible day on which a crossover can occur (as day t-1=long-1 is the first
    day the long MA is defined).
    """
    alerts: List[Alert] = []
    short_w = rule["short"]
    long_w = rule["long"]
    direction = rule["direction"]
    rule_id = rule["id"]
    instrument = rule["instrument"]

    if len(series) <= long_w:
        # Not enough days to have a previous day where long MA was also defined
        return alerts

    closes = [p.close for p in series]
    short_ma = calculate_sma_series(closes, short_w)
    long_ma = calculate_sma_series(closes, long_w)

    # Earliest index where both day i-1 and day i have defined long MAs is i = long_w
    for i in range(long_w, len(series)):
        prev_s = short_ma[i - 1]
        prev_l = long_ma[i - 1]
        curr_s = short_ma[i]
        curr_l = long_ma[i]

        if prev_s is None or prev_l is None or curr_s is None or curr_l is None:
            continue

        prev_diff = prev_s - prev_l
        curr_diff = curr_s - curr_l

        if direction == "above":
            # Crossed above: previous short was <= long, current short is > long
            if prev_diff <= EPSILON and curr_diff > EPSILON:
                alerts.append(Alert(
                    date=series[i].date,
                    rule_id=rule_id,
                    instrument=instrument,
                    rule_type="ma_cross",
                    details=f"{short_w}/{long_w} above",
                ))
        elif direction == "below":
            # Crossed below: previous short was >= long, current short is < long
            if prev_diff >= -EPSILON and curr_diff < -EPSILON:
                alerts.append(Alert(
                    date=series[i].date,
                    rule_id=rule_id,
                    instrument=instrument,
                    rule_type="ma_cross",
                    details=f"{short_w}/{long_w} below",
                ))

    return alerts


def evaluate_all_rules(
    prices_by_instrument: Dict[str, List[PricePoint]],
    rules: List[Dict[str, Any]],
) -> List[Alert]:
    """
    Evaluate all rules across all instruments.
    Returns alerts sorted primarily by date, then secondarily by rule_id.
    """
    all_alerts: List[Alert] = []

    for rule in rules:
        instrument = rule["instrument"]
        series = prices_by_instrument.get(instrument, [])
        if not series:
            continue

        if rule["type"] == "level":
            alerts = evaluate_level_rule(rule, series)
            all_alerts.extend(alerts)
        elif rule["type"] == "ma_cross":
            alerts = evaluate_ma_cross_rule(rule, series)
            all_alerts.extend(alerts)

    # Sort alerts by date ascending, then rule_id ascending
    all_alerts.sort(key=lambda a: (a.date, a.rule_id))
    return all_alerts


def run_alerts(prices_path: str, rules_path: str) -> List[str]:
    """
    Run alert evaluation and return formatted output strings.
    """
    prices_by_instrument = parse_prices_csv(prices_path)
    rules = parse_rules_json(rules_path)
    alerts = evaluate_all_rules(prices_by_instrument, rules)
    return [alert.to_output_line() for alert in alerts]


def main():
    if len(sys.argv) == 2 and sys.argv[1] in ("--web", "-w", "web"):
        # Launch optional web UI
        import web_server
        web_server.start_server()
        return

    if len(sys.argv) < 3:
        sys.stderr.write("Usage: python alerts.py <prices.csv> <rules.json>\n")
        sys.stderr.write("Optional web dashboard: python alerts.py --web\n")
        sys.exit(1)

    prices_path = sys.argv[1]
    rules_path = sys.argv[2]

    try:
        lines = run_alerts(prices_path, rules_path)
        for line in lines:
            print(line)
    except Exception as e:
        sys.stderr.write(f"Error: {e}\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
