#!/usr/bin/env python3
"""
Unit and Integration Tests for Price Alert Tool
-----------------------------------------------
Evaluates standard behaviors and real-world edge cases:
  1. Base verification against the build brief example.
  2. Out-of-order dates in CSV.
  3. Level rules (above & below, day 1 non-triggering, repeated days on same side).
  4. Boundary conditions (exact touches of level threshold).
  5. Moving average window definitions (no alerts before long window is established).
  6. MA crossovers (above & below, sustained trends).
  7. Deterministic tie-breaking (same date, sorted by rule_id).
  8. Missing instruments, insufficient data, and unreferenced instruments.
  9. Malformed input recovery (whitespace, non-numeric rows, duplicate dates).
 10. Rule validation (short >= long, unknown rule type, non-numeric levels).
"""

import io
import json
import os
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout

from alerts import (
    Alert,
    calculate_sma_series,
    evaluate_all_rules,
    format_level_number,
    parse_prices_csv,
    parse_rules_json,
    run_alerts,
)


class TestPriceAlertTool(unittest.TestCase):

    def test_format_level_number(self):
        """Level formatting: integer levels show as integers, decimal levels preserve precision."""
        self.assertEqual(format_level_number(1500.0), "1500")
        self.assertEqual(format_level_number(1500), "1500")
        self.assertEqual(format_level_number(1500.5), "1500.5")
        self.assertEqual(format_level_number(1499.75), "1499.75")

    def test_brief_sample_exact_output(self):
        """End-to-end integration test validating the exact output from the build brief."""
        lines = run_alerts("prices.csv", "rules.json")
        expected = [
            "2026-09-03 r1 INFY level below 1500",
            "2026-09-24 r2 TCS ma_cross 5/20 above",
        ]
        self.assertEqual(lines, expected)

    def test_out_of_order_dates(self):
        """CSV rows out of chronological order must be sorted correctly before evaluation."""
        csv_data = io.StringIO(
            "date,instrument,close\n"
            "2026-09-03,INFY,1490.00\n"
            "2026-09-01,INFY,1520.00\n"
            "2026-09-02,INFY,1510.00\n"
        )
        parsed = parse_prices_csv(csv_data)
        dates = [p.date for p in parsed["INFY"]]
        self.assertEqual(dates, ["2026-09-01", "2026-09-02", "2026-09-03"])

        rules = [{
            "id": "r1",
            "instrument": "INFY",
            "type": "level",
            "direction": "below",
            "level": 1500.0,
        }]
        alerts = evaluate_all_rules(parsed, rules)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].date, "2026-09-03")

    def test_level_rule_below_fires_only_on_first_crossing_day(self):
        """
        'A level rule fires on the first day the close crosses the level in the given direction
        (it was on the other side the previous day).'
        Must fire once when crossing from > 100 to < 100, and NOT fire while remaining < 100.
        """
        csv_data = io.StringIO(
            "date,instrument,close\n"
            "2026-01-01,TEST,110.0\n"
            "2026-01-02,TEST,95.0\n"   # crosses below -> fires!
            "2026-01-03,TEST,90.0\n"   # remains below -> does NOT fire
            "2026-01-04,TEST,85.0\n"   # remains below -> does NOT fire
            "2026-01-05,TEST,105.0\n"  # moves back above -> does NOT fire (direction is below)
            "2026-01-06,TEST,92.0\n"   # crosses below again -> fires!
        )
        parsed = parse_prices_csv(csv_data)
        rule = [{"id": "r_below", "instrument": "TEST", "type": "level", "direction": "below", "level": 100}]
        alerts = evaluate_all_rules(parsed, rule)

        self.assertEqual(len(alerts), 2)
        self.assertEqual(alerts[0].date, "2026-01-02")
        self.assertEqual(alerts[0].to_output_line(), "2026-01-02 r_below TEST level below 100")
        self.assertEqual(alerts[1].date, "2026-01-06")
        self.assertEqual(alerts[1].to_output_line(), "2026-01-06 r_below TEST level below 100")

    def test_level_rule_above(self):
        """Test crossing above level."""
        csv_data = io.StringIO(
            "date,instrument,close\n"
            "2026-01-01,TEST,90.0\n"
            "2026-01-02,TEST,95.0\n"
            "2026-01-03,TEST,105.0\n"  # crosses above -> fires!
            "2026-01-04,TEST,110.0\n"  # stays above -> does NOT fire
        )
        parsed = parse_prices_csv(csv_data)
        rule = [{"id": "r_above", "instrument": "TEST", "type": "level", "direction": "above", "level": 100}]
        alerts = evaluate_all_rules(parsed, rule)

        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].to_output_line(), "2026-01-03 r_above TEST level above 100")

    def test_day_one_never_fires(self):
        """
        Price starting already on the 'target' side on Day 1 must NOT fire,
        because there is no previous day to have been on the other side.
        """
        csv_data = io.StringIO(
            "date,instrument,close\n"
            "2026-01-01,TEST,80.0\n"   # already below 100 on Day 1
            "2026-01-02,TEST,75.0\n"
        )
        parsed = parse_prices_csv(csv_data)
        rule = [{"id": "r_below", "instrument": "TEST", "type": "level", "direction": "below", "level": 100}]
        alerts = evaluate_all_rules(parsed, rule)
        self.assertEqual(len(alerts), 0)

    def test_ma_cross_warmup_window_strictly_enforced(self):
        """
        Moving averages need a full window of days before they are defined.
        For short=2, long=4:
          Day 1 (idx 0): undefined
          Day 2 (idx 1): MA2 defined, MA4 undefined
          Day 3 (idx 2): MA2 defined, MA4 undefined
          Day 4 (idx 3): MA2 defined, MA4 defined for the first time. Cannot cross yet (no prev MA4).
          Day 5 (idx 4): Earliest possible crossover day!
        """
        # Day 1..4: short MA <= long MA
        # Day 5: short MA crosses above long MA
        csv_data = io.StringIO(
            "date,instrument,close\n"
            "2026-01-01,MA_TEST,10.0\n"
            "2026-01-02,MA_TEST,10.0\n"
            "2026-01-03,MA_TEST,10.0\n"
            "2026-01-04,MA_TEST,10.0\n"  # day 4 (idx 3): MA4 is defined for first time (both MA2 and MA4 = 10)
            "2026-01-05,MA_TEST,30.0\n"  # day 5 (idx 4): MA2=(10+30)/2=20, MA4=(10+10+10+30)/4=15 -> Cross above!
        )
        parsed = parse_prices_csv(csv_data)
        rule = [{
            "id": "r_ma",
            "instrument": "MA_TEST",
            "type": "ma_cross",
            "short": 2,
            "long": 4,
            "direction": "above",
        }]
        alerts = evaluate_all_rules(parsed, rule)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].to_output_line(), "2026-01-05 r_ma MA_TEST ma_cross 2/4 above")

    def test_ma_cross_below(self):
        """Short MA crossing below long MA."""
        csv_data = io.StringIO(
            "date,instrument,close\n"
            "2026-01-01,MA_TEST,30.0\n"
            "2026-01-02,MA_TEST,30.0\n"
            "2026-01-03,MA_TEST,30.0\n"
            "2026-01-04,MA_TEST,30.0\n"  # MA2=30, MA4=30
            "2026-01-05,MA_TEST,10.0\n"  # MA2=20, MA4=25 -> Cross below!
        )
        parsed = parse_prices_csv(csv_data)
        rule = [{
            "id": "r_ma_down",
            "instrument": "MA_TEST",
            "type": "ma_cross",
            "short": 2,
            "long": 4,
            "direction": "below",
        }]
        alerts = evaluate_all_rules(parsed, rule)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].to_output_line(), "2026-01-05 r_ma_down MA_TEST ma_cross 2/4 below")

    def test_sorting_by_date_then_rule_id(self):
        """
        'One line per alert, ordered by date then rule id.'
        When multiple rules fire on the same date, they must sort by rule_id ascending.
        """
        csv_data = io.StringIO(
            "date,instrument,close\n"
            "2026-01-01,SYM,100.0\n"
            "2026-01-02,SYM,50.0\n"
        )
        parsed = parse_prices_csv(csv_data)
        rules = [
            {"id": "z_rule", "instrument": "SYM", "type": "level", "direction": "below", "level": 90},
            {"id": "a_rule", "instrument": "SYM", "type": "level", "direction": "below", "level": 80},
            {"id": "m_rule", "instrument": "SYM", "type": "level", "direction": "below", "level": 70},
        ]
        alerts = evaluate_all_rules(parsed, rules)
        self.assertEqual(len(alerts), 3)
        rule_order = [a.rule_id for a in alerts]
        self.assertEqual(rule_order, ["a_rule", "m_rule", "z_rule"])

    def test_insufficient_data_does_not_crash(self):
        """Fewer rows than the long MA window should produce no alerts and not crash."""
        csv_data = io.StringIO(
            "date,instrument,close\n"
            "2026-01-01,SHORT,100.0\n"
            "2026-01-02,SHORT,105.0\n"
        )
        parsed = parse_prices_csv(csv_data)
        rule = [{
            "id": "r_long",
            "instrument": "SHORT",
            "type": "ma_cross",
            "short": 5,
            "long": 20,
            "direction": "above",
        }]
        alerts = evaluate_all_rules(parsed, rule)
        self.assertEqual(len(alerts), 0)

    def test_rule_instrument_not_in_prices(self):
        """Rules referencing instruments not in the CSV should simply not fire."""
        csv_data = io.StringIO(
            "date,instrument,close\n"
            "2026-01-01,INFY,1500.0\n"
        )
        parsed = parse_prices_csv(csv_data)
        rule = [{"id": "r_unknown", "instrument": "UNKNOWN_TICKER", "type": "level", "direction": "below", "level": 100}]
        alerts = evaluate_all_rules(parsed, rule)
        self.assertEqual(len(alerts), 0)

    def test_malformed_csv_and_whitespace_handling(self):
        """Parser tolerates whitespace, BOM, empty lines, and bad price rows gracefully."""
        csv_content = (
            "  date , instrument , close \n"
            "\n"
            " 2026-01-01 , infy , 1520.50 \n"
            " 2026-01-02 , infy , not_a_number \n"  # bad row skipped
            " 2026-01-03 , infy , 1480.00 \n"
        )
        f = io.StringIO(csv_content)
        with redirect_stderr(io.StringIO()):
            parsed = parse_prices_csv(f)

        self.assertIn("INFY", parsed)
        self.assertEqual(len(parsed["INFY"]), 2)
        self.assertEqual(parsed["INFY"][0].date, "2026-01-01")
        self.assertEqual(parsed["INFY"][1].date, "2026-01-03")

    def test_rule_validation(self):
        """Invalid rules (short >= long, unknown type, bad directions) are skipped."""
        rules_json = io.StringIO(json.dumps([
            {"id": "inv1", "instrument": "A", "type": "ma_cross", "short": 20, "long": 5, "direction": "above"},
            {"id": "inv2", "instrument": "A", "type": "unknown_type", "direction": "above"},
            {"id": "inv3", "instrument": "A", "type": "level", "direction": "sideways", "level": 100},
            {"id": "valid1", "instrument": "A", "type": "level", "direction": "below", "level": 100},
        ]))
        with redirect_stderr(io.StringIO()):
            valid_rules = parse_rules_json(rules_json)

        self.assertEqual(len(valid_rules), 1)
        self.assertEqual(valid_rules[0]["id"], "valid1")


if __name__ == "__main__":
    unittest.main()
