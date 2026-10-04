"""Focused synthetic checks for the reusable research math; no data files read."""
from fractions import Fraction
from itertools import product
from math import prod
import unittest
from unittest.mock import Mock, patch

import numpy as np
import pandas as pd

import ast
import json
from pathlib import Path


def _load_notebook_functions():
    root = Path(__file__).resolve().parents[1]
    if not (root / "notebooks/01_states_and_first_passage.ipynb").exists():
        root = root / "prepared"
    notebook_path = root / "notebooks" / "01_states_and_first_passage.ipynb"
    notebook = json.loads(notebook_path.read_text(encoding="utf-8"))
    expected = {
        "_validate_daily_index",
        "classify_states",
        "make_features",
        "count_transitions",
        "first_passage_probabilities",
        "make_event_labels",
    }
    trees, names = [], set()
    for index, cell in enumerate(notebook["cells"]):
        if cell.get("cell_type") != "code" or "part-a-functions" not in cell.get("metadata", {}).get("tags", []):
            continue
        source = cell.get("source", [])
        source = source if isinstance(source, str) else "".join(source)
        tree = ast.parse(source, filename=f"{notebook_path}#cell-{index}")
        for node in tree.body:
            if not isinstance(node, ast.FunctionDef):
                raise ValueError("part-a-functions cells must contain only function definitions")
            if node.name in names:
                raise ValueError(f"Duplicate notebook function: {node.name}")
            names.add(node.name)
        trees.append((index, tree))
    if not expected.issubset(names):
        raise ValueError(f"Missing notebook functions: {sorted(expected - names)}")
    # Validate the entire tagged set before executing any definition. Loading and
    # analysis cells are never compiled or executed by this test loader.
    namespace = {"np": np, "pd": pd}
    for index, tree in trees:
        exec(compile(tree, f"{notebook_path}#cell-{index}", "exec"), namespace)
    return {name: namespace[name] for name in expected}


globals().update(_load_notebook_functions())


def daily(values, *, start="2020-01-01", dtype=None, tz=None):
    return pd.Series(values, index=pd.date_range(start, periods=len(values), freq="D", tz=tz), dtype=dtype)


def closes(n=70):
    returns = np.resize(np.array([0.01, -0.02, 0.015, -0.005, 0.025]), n - 1)
    return daily(np.r_[100.0, 100.0 * np.cumprod(1 + returns)])


class MarkovTests(unittest.TestCase):
    def test_state_boundaries_and_nonfinite_values(self):
        z = daily([-np.inf, -1.01, -1.0, -0.999, 0.0, 0.999, 1.0, 1.01, np.inf, np.nan])
        actual = classify_states(z)
        expected = pd.Series([pd.NA, 0, 0, 1, 1, 1, 2, 2, pd.NA, pd.NA],
                             index=z.index, dtype="Int64", name="state")
        pd.testing.assert_series_equal(actual, expected)

    def test_returns_strict_previous_twenty_sample_std_and_first_valid_date(self):
        close = closes()
        features = make_features(close)
        self.assertEqual(list(features.columns), ["close", "ret", "sigma", "z", "state"])
        self.assertAlmostEqual(features["ret"].iloc[1], close.iloc[1] / close.iloc[0] - 1)
        expected = np.std(features["ret"].iloc[1:21].to_numpy(), ddof=1)
        self.assertAlmostEqual(features["sigma"].iloc[21], expected)
        self.assertFalse(np.isclose(expected, np.std(features["ret"].iloc[1:21], ddof=0)))
        self.assertTrue(features["sigma"].iloc[:21].isna().all())
        self.assertEqual(features["state"].first_valid_index(), pd.Timestamp("2020-01-22"))

    def test_future_prices_do_not_change_past_features_or_current_sigma(self):
        original = closes()
        changed = original.copy()
        cutoff = original.index[35]
        changed.loc[cutoff:] *= 1.5
        first, second = make_features(original), make_features(changed)
        pd.testing.assert_frame_equal(first.loc[first.index < cutoff], second.loc[second.index < cutoff])
        self.assertEqual(first.at[cutoff, "sigma"], second.at[cutoff, "sigma"])
        self.assertNotEqual(first.at[cutoff, "ret"], second.at[cutoff, "ret"])

    def test_missing_close_is_not_forward_filled_and_invalidates_required_window(self):
        close = closes()
        close.iloc[25] = np.nan
        result = make_features(close)
        self.assertTrue(result["ret"].iloc[25:27].isna().all())
        self.assertTrue(result["state"].iloc[25:47].isna().all())
        self.assertTrue(result["sigma"].iloc[26:47].isna().all())
        self.assertTrue(pd.notna(result["sigma"].iloc[47]))

    def test_zero_volatility_leaves_states_unavailable(self):
        result = make_features(daily([100.0] * 45))
        self.assertTrue(result["sigma"].isna().all())
        self.assertTrue(result["z"].isna().all())
        self.assertTrue(result["state"].isna().all())

    def test_invalid_nonmissing_close_values_are_rejected(self):
        for invalid in [0.0, -1.0, np.inf, -np.inf]:
            with self.subTest(invalid=invalid):
                close = closes()
                close.iloc[30] = invalid
                with self.assertRaises(ValueError):
                    make_features(close)

    def test_features_and_transition_counting_require_a_complete_daily_index(self):
        base = pd.date_range("2020-01-01", periods=3, freq="D")
        invalid_indexes = {
            "duplicate": pd.DatetimeIndex([base[0], base[0], base[2]]),
            "unsorted": pd.DatetimeIndex([base[1], base[0], base[2]]),
            "gap": pd.DatetimeIndex([base[0], base[1], base[2] + pd.Timedelta(days=1)]),
            "not_midnight": base + pd.Timedelta(hours=12),
            "not_datetime": pd.RangeIndex(3),
            "non_utc_midnight": pd.date_range("2020-01-01", periods=3, tz="America/New_York"),
        }
        for name, index in invalid_indexes.items():
            with self.subTest(index=name, operation="features"):
                with self.assertRaises(ValueError):
                    make_features(pd.Series([100.0, 101.0, 99.0], index=index))
            with self.subTest(index=name, operation="transitions"):
                with self.assertRaises(ValueError):
                    count_transitions(pd.Series([0, 1, 2], index=index))

    def test_utc_daily_index_is_accepted_without_changing_dates(self):
        close = closes()
        close.index = close.index.tz_localize("UTC")
        result = make_features(close)
        self.assertTrue(result.index.equals(close.index))
        actual = count_transitions(daily([0, 1, 2], tz="UTC"))
        expected = np.zeros((3, 3), dtype=int)
        expected[0, 1], expected[1, 2] = 1, 1
        np.testing.assert_array_equal(actual, expected)

    def test_toy_transition_counts_use_origins_and_destinations_in_correct_order(self):
        states = daily([1, 1, 0, 1, 2, 2, 1, 0, 0, 1], dtype="Int64")
        counts = count_transitions(states)
        np.testing.assert_array_equal(counts, [[1, 2, 0], [2, 1, 1], [0, 1, 1]])
        self.assertTrue(np.issubdtype(counts.dtype, np.integer))
        self.assertEqual(int(counts.sum()), len(states) - 1)

    def test_missing_states_are_not_bridged_and_unused_labels_keep_their_rows(self):
        states = daily([1, pd.NA, 0, 1, pd.NA, 2], dtype="Int64")
        expected = np.zeros((3, 3), dtype=int)
        expected[0, 1] = 1
        np.testing.assert_array_equal(count_transitions(states), expected)

    def test_invalid_state_labels_are_rejected(self):
        for invalid in [-1, 3, 0.5, np.inf, "invalid"]:
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    count_transitions(daily([0, invalid, 1]))

    def test_first_passage_matches_independent_exact_path_enumeration(self):
        F = Fraction
        probabilities = [[F(1, 3), F(2, 3), F(0)],
                         [F(1, 2), F(1, 4), F(1, 4)],
                         [F(0), F(1, 2), F(1, 2)]]
        matrix = np.array(probabilities, dtype=float)
        for horizon in [0, 1, 2, 5]:
            result = first_passage_probabilities(matrix, horizon=horizon)
            self.assertEqual(result.name, "hit_probability")
            self.assertEqual(result.index.tolist(), [1, 2])
            for initial in [1, 2]:
                probability = F(0)
                for future in product(range(3), repeat=horizon):
                    if 0 in future:
                        path = (initial,) + future
                        probability += prod(probabilities[a][b] for a, b in zip(path[:-1], path[1:]))
                self.assertAlmostEqual(result.loc[initial], float(probability), places=14)

    def test_first_hit_differs_from_endpoint_and_q_is_not_renormalized(self):
        matrix = np.array([[1 / 3, 2 / 3, 0], [.5, .25, .25], [0, .5, .5]])
        result = first_passage_probabilities(matrix, horizon=5)
        np.testing.assert_allclose(result.to_numpy(), [431 / 512, 175 / 256])
        endpoints = np.linalg.matrix_power(matrix, 5)[1:, 0]
        self.assertTrue((result.to_numpy() > endpoints).all())
        # Changing behavior AFTER a first hit cannot alter first-hit probabilities.
        modified = matrix.copy()
        modified[0] = [1, 0, 0]
        pd.testing.assert_series_equal(result, first_passage_probabilities(modified, horizon=5))
        np.testing.assert_allclose(first_passage_probabilities(matrix, horizon=1), [.5, 0.0])

    def test_invalid_probability_matrices_and_horizons_are_rejected(self):
        valid = np.array([[.2, .5, .3], [1, 0, 0], [.5, 0, .5]])
        for invalid in [np.ones((2, 2)), np.ones((3, 3)),
                        np.array([[-.1, .6, .5], [1, 0, 0], [.5, 0, .5]]),
                        np.full((3, 3), np.nan), np.full((3, 3), np.inf)]:
            with self.subTest(matrix=invalid):
                with self.assertRaises(ValueError):
                    first_passage_probabilities(invalid)
        for horizon in [-1, 1.5, True, False, "5"]:
            with self.subTest(horizon=horizon):
                with self.assertRaises(ValueError):
                    first_passage_probabilities(valid, horizon=horizon)
        np.testing.assert_allclose(first_passage_probabilities(valid, horizon=0), [0, 0])



class EventLabelTests(unittest.TestCase):
    def test_event_excludes_current_state_and_status_precedence_is_explicit(self):
        states = daily([0, pd.NA, 1, 2, 0, 1], dtype="Int64")
        result = make_event_labels(states, horizon=1)
        expected_target = pd.Series([pd.NA, pd.NA, 0, 1, pd.NA, pd.NA],
                                    index=states.index, name="target", dtype="Int64")
        pd.testing.assert_series_equal(result["target"], expected_target)
        self.assertEqual(result["label_status"].tolist(),
                         ["risk_origin", "origin_missing", "available", "available",
                          "risk_origin", "incomplete_future"])
        # A risk origin remains excluded even if its next state is missing.
        self.assertEqual(result["label_status"].iloc[0], "risk_origin")

    def test_day_five_is_included_and_day_six_is_excluded(self):
        on_day_five = make_event_labels(daily([1, 2, 1, 2, 1, 0, 2], dtype="Int64"))
        on_day_six = make_event_labels(daily([1, 2, 1, 2, 1, 2, 0], dtype="Int64"))
        self.assertEqual(on_day_five["target"].iloc[0], 1)
        self.assertEqual(on_day_six["target"].iloc[0], 0)
        self.assertEqual(on_day_six["target"].iloc[1], 1)
        self.assertEqual(on_day_five["target_end_date"].iloc[0], pd.Timestamp("2020-01-06"))

    def test_early_hit_does_not_make_an_incomplete_future_available(self):
        states = daily([1, 0, 2], dtype="Int64")
        result = make_event_labels(states)
        self.assertTrue(pd.isna(result["target"].iloc[0]))
        self.assertEqual(result["label_status"].iloc[0], "incomplete_future")
        self.assertEqual(result["target_end_date"].iloc[0], pd.Timestamp("2020-01-06"))
        self.assertNotEqual(result["target_end_date"].iloc[0], states.index[1])
        self.assertTrue(result["target"].isna().all())

    def test_missing_state_inside_full_calendar_window_invalidates_even_an_early_hit(self):
        states = daily([1, 0, pd.NA, 2, 1, 2, 1, 1, 2], dtype="Int64")
        result = make_event_labels(states)
        self.assertTrue(pd.isna(result["target"].iloc[0]))
        self.assertEqual(result["label_status"].iloc[0], "incomplete_future")
        self.assertEqual(result["label_status"].iloc[2], "origin_missing")
        # The missing date must not be skipped to collect five observed states.
        self.assertEqual(result["target"].iloc[3], 0)
        self.assertEqual(result["label_status"].iloc[3], "available")

    def test_schema_index_and_theoretical_end_dates_preserve_naive_or_utc_dates(self):
        for timezone in [None, "UTC"]:
            with self.subTest(timezone=timezone):
                states = daily([1, 2, pd.NA, 0, 1, 2, 1], dtype="Int64", tz=timezone)
                result = make_event_labels(states)
                self.assertEqual(list(result.columns), ["state", "target", "target_end_date", "label_status"])
                pd.testing.assert_index_equal(result.index, states.index)
                pd.testing.assert_series_equal(result["state"], states.rename("state"))
                self.assertEqual(str(result["target"].dtype), "Int64")
                self.assertIsInstance(result["label_status"].dtype, pd.StringDtype)
                expected_end = pd.Series(states.index + pd.Timedelta(days=5),
                                         index=states.index, name="target_end_date")
                pd.testing.assert_series_equal(result["target_end_date"], expected_end)

    def test_event_horizon_requires_a_positive_integer_excluding_bool(self):
        states = daily([1, 2, 0], dtype="Int64")
        for horizon in [0, -1, 1.5, True, False, "5", None, np.nan]:
            with self.subTest(horizon=horizon):
                with self.assertRaises(ValueError):
                    make_event_labels(states, horizon=horizon)
        self.assertEqual(make_event_labels(states, horizon=1)["target"].iloc[1], 1)

    def test_event_inputs_reject_invalid_states_and_broken_daily_indexes(self):
        base = pd.date_range("2020-01-01", periods=3, freq="D")
        invalid_indexes = {
            "duplicate": pd.DatetimeIndex([base[0], base[0], base[2]]),
            "unsorted": pd.DatetimeIndex([base[1], base[0], base[2]]),
            "gap": pd.DatetimeIndex([base[0], base[1], base[2] + pd.Timedelta(days=1)]),
            "not_midnight": base + pd.Timedelta(hours=12),
            "not_datetime": pd.RangeIndex(3),
            "non_utc_midnight": pd.date_range("2020-01-01", periods=3, tz="America/New_York"),
        }
        for name, index in invalid_indexes.items():
            with self.subTest(index=name):
                with self.assertRaises(ValueError):
                    make_event_labels(pd.Series([0, 1, 2], index=index))
        for invalid in [-1, 3, 0.5, np.inf, -np.inf, "invalid"]:
            with self.subTest(state=invalid):
                with self.assertRaises(ValueError):
                    make_event_labels(daily([1, invalid, 2]))

    def test_as_of_mature_labels_are_unchanged_by_later_states(self):
        states = daily([1] * 20, dtype="Int64")
        states.iloc[3] = 0
        cutoff = states.index[10]
        changed = states.copy()
        changed.iloc[11] = 0
        before, after = make_event_labels(states), make_event_labels(changed)
        before_mature = before.loc[before["target"].notna() & (before["target_end_date"] <= cutoff)]
        after_mature = after.loc[after["target"].notna() & (after["target_end_date"] <= cutoff)]
        self.assertGreater(len(before_mature), 0)
        pd.testing.assert_frame_equal(before_mature, after_mature)
        self.assertIn(states.index[5], before_mature.index)  # Ends exactly at cutoff.
        self.assertNotIn(states.index[6], before_mature.index)
        self.assertEqual(before["target"].iloc[6], 0)
        self.assertEqual(after["target"].iloc[6], 1)  # Changed label is still immature at cutoff.

    def test_all_nonrisk_futures_have_zero_targets_only_when_complete(self):
        states = daily([1, 2] * 5, dtype="Int64")
        result = make_event_labels(states)
        self.assertEqual(result["target"].iloc[:5].tolist(), [0] * 5)
        self.assertEqual(result["label_status"].iloc[:5].tolist(), ["available"] * 5)
        self.assertTrue(result["target"].iloc[5:].isna().all())
        self.assertEqual(result["label_status"].iloc[5:].tolist(), ["incomplete_future"] * 5)



if __name__ == "__main__":
    unittest.main()
