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
    notebook_path = Path(__file__).resolve().parents[1] / "notebooks" / "01_states_and_first_passage.ipynb"
    notebook = json.loads(notebook_path.read_text(encoding="utf-8"))
    expected = {
        "_validate_daily_index", "classify_states", "make_features",
        "count_transitions", "estimate_transition_matrix", "first_passage_probabilities",
        "make_event_labels",
        "count_lagged_transitions", "ck_statistic", "simulate_markov_paths", "ck_bootstrap",
    }
    trees, names = [], set()
    for index, cell in enumerate(notebook["cells"]):
        if cell.get("cell_type") != "code" or "research-functions" not in cell.get("metadata", {}).get("tags", []):
            continue
        source = cell.get("source", [])
        source = source if isinstance(source, str) else "".join(source)
        tree = ast.parse(source, filename=f"{notebook_path}#cell-{index}")
        for node in tree.body:
            if not isinstance(node, ast.FunctionDef):
                raise ValueError("research-functions cells must contain only function definitions")
            if node.name in names:
                raise ValueError(f"Duplicate notebook function: {node.name}")
            names.add(node.name)
        trees.append((index, tree))
    if names != expected:
        raise ValueError(f"Unexpected notebook functions: missing={sorted(expected - names)}, extra={sorted(names - expected)}")
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

    def test_raw_row_mle_is_not_smoothed_and_invalid_count_matrices_fail(self):
        counts = np.array([[1, 2, 0], [2, 1, 1], [0, 1, 1]])
        expected = np.array([[1 / 3, 2 / 3, 0], [1 / 2, 1 / 4, 1 / 4], [0, 1 / 2, 1 / 2]])
        np.testing.assert_allclose(estimate_transition_matrix(counts), expected)
        for invalid in [np.ones((2, 3)), np.ones((3, 4)),
                        np.array([[0, 0, 0], [1, 1, 1], [1, 1, 1]]),
                        np.array([[-1, 2, 2], [1, 1, 1], [1, 1, 1]]),
                        np.array([[0.5, 1, 1], [1, 1, 1], [1, 1, 1]]),
                        np.full((3, 3), np.nan), np.full((3, 3), np.inf)]:
            with self.subTest(counts=invalid):
                with self.assertRaises(ValueError):
                    estimate_transition_matrix(invalid)

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


class ChapmanKolmogorovTests(unittest.TestCase):
    def test_five_day_counts_match_manual_endpoint_pairs_in_correct_direction(self):
        states = daily([0, 1, 2, 0, 2, 1, 0, 1, 2, 2], dtype="Int64")
        # The five endpoint pairs are 0->1, 1->0, 2->1, 0->2, 2->2.
        counts = count_lagged_transitions(states, lag=5)
        np.testing.assert_array_equal(counts, [[0, 1, 1], [1, 0, 0], [0, 1, 1]])
        self.assertTrue(np.issubdtype(counts.dtype, np.integer))
        self.assertEqual(int(counts.sum()), 5)

    def test_full_year_counts_use_n_minus_lag_overlapping_pairs(self):
        states = daily(np.arange(365) % 3, dtype="Int64", tz="UTC")
        one_step = count_lagged_transitions(states, lag=1)
        five_step = count_lagged_transitions(states, lag=5)
        np.testing.assert_array_equal(one_step, count_transitions(states))
        self.assertEqual(int(one_step.sum()), 364)
        self.assertEqual(int(five_step.sum()), 360)
        np.testing.assert_array_equal(five_step, [[0, 0, 120], [120, 0, 0], [0, 120, 0]])

    def test_lag_counts_reject_bad_lags_missing_states_and_discontinuous_indexes(self):
        states = daily([0, 1, 2, 0, 1, 2], dtype="Int64")
        for lag in [0, -1, 6, 7, 1.5, True, False, "5"]:
            with self.subTest(lag=lag):
                with self.assertRaises(ValueError):
                    count_lagged_transitions(states, lag=lag)
        for invalid in [pd.NA, np.nan, np.inf, -1, 3, 0.5, "invalid"]:
            with self.subTest(state=invalid):
                with self.assertRaises(ValueError):
                    count_lagged_transitions(daily([0, 1, invalid, 2, 1, 0]), lag=5)
        base = states.index
        indexes = [base.delete(2).append(pd.DatetimeIndex([base[-1] + pd.Timedelta(days=1)])),
                   pd.DatetimeIndex([base[0], base[0], *base[2:]]),
                   base[::-1], base + pd.Timedelta(hours=12), pd.RangeIndex(6)]
        for index in indexes:
            with self.subTest(index=index):
                with self.assertRaises(ValueError):
                    count_lagged_transitions(pd.Series(states.to_numpy(), index=index), lag=5)

    def test_deterministic_cycle_has_zero_discrepancy_and_bootstrap_p_one(self):
        states = daily([0, 1, 2] * 12, dtype="Int64")
        observed = ck_statistic(states)
        transition = np.array([[0., 1., 0.], [0., 0., 1.], [1., 0., 0.]])
        power_five = np.array([[0., 0., 1.], [1., 0., 0.], [0., 1., 0.]])
        np.testing.assert_array_equal(observed["P1"], transition)
        np.testing.assert_array_equal(observed["P_lag"], power_five)
        np.testing.assert_array_equal(observed["P_power"], power_five)
        self.assertEqual(observed["statistic"], 0.0)
        result = ck_bootstrap(states, n_simulations=7, seed=123)
        np.testing.assert_array_equal(result["simulated_statistics"], np.zeros(7))
        self.assertEqual(result["invalid_simulations"], 0)
        self.assertEqual(result["exceedances"], 7)  # Ties count as exceedances.
        self.assertEqual(result["p_value"], 1.0)

    def test_empty_lag_source_rows_have_nan_probabilities_and_zero_weight(self):
        states = daily([0, 0, 0, 1, 2, 0], dtype="Int64")
        result = ck_statistic(states, lag=5)
        np.testing.assert_array_equal(result["counts_lag"], [[1, 0, 0], [0, 0, 0], [0, 0, 0]])
        np.testing.assert_array_equal(result["source_weights"], [1., 0., 0.])
        np.testing.assert_array_equal(result["P_lag"][0], [1., 0., 0.])
        self.assertTrue(np.isnan(result["P_lag"][1:]).all())
        p_one = np.array([[2 / 3, 1 / 3, 0.], [0., 0., 1.], [1., 0., 0.]])
        expected = float(np.square(np.array([1., 0., 0.]) - np.linalg.matrix_power(p_one, 5)[0]).sum())
        self.assertTrue(np.isfinite(result["statistic"]))
        self.assertAlmostEqual(result["statistic"], expected, places=14)
        self.assertGreaterEqual(result["statistic"], 0.0)
        self.assertLessEqual(result["statistic"], 2.0)

    def test_unobserved_one_step_source_row_makes_statistic_undefined(self):
        # State 2 exists only at the final observation and has no outgoing pair.
        states = daily([0, 1, 0, 1, 0, 2], dtype="Int64")
        with self.assertRaises(ValueError):
            ck_statistic(states, lag=5)
        with self.assertRaises(ValueError):
            ck_bootstrap(states, lag=5, n_simulations=3)

    def test_simulation_matches_independent_seeded_inverse_cdf_and_fixed_initial_state(self):
        matrix = np.array([[.25, .5, .25], [.1, .2, .7], [.65, .25, .1]])
        seed, n_paths, length, initial = 17, 7, 10, 1
        uniforms = np.random.default_rng(seed).random((n_paths, length - 1))
        expected = np.full((n_paths, length), initial, dtype=int)
        for path in range(n_paths):
            for step in range(1, length):
                cumulative = np.cumsum(matrix[expected[path, step - 1]])
                cumulative[-1] = 1.0
                expected[path, step] = np.searchsorted(cumulative, uniforms[path, step - 1], side="right")
        actual = simulate_markov_paths(matrix, initial, length, n_paths, seed=seed)
        np.testing.assert_array_equal(actual, expected)
        np.testing.assert_array_equal(actual, simulate_markov_paths(matrix, initial, length, n_paths, seed=seed))
        self.assertTrue(np.issubdtype(actual.dtype, np.integer))
        self.assertTrue(np.isin(actual, [0, 1, 2]).all())
        np.testing.assert_array_equal(actual[:, 0], [initial] * n_paths)
        np.testing.assert_array_equal(simulate_markov_paths(matrix, 2, 1, 4, seed=0), [[2]] * 4)

    def test_simulation_validates_probability_matrix_and_integer_parameters(self):
        valid = np.array([[.2, .5, .3], [.1, .8, .1], [.4, .3, .3]])
        invalid_matrices = [np.ones((2, 2)), np.ones((3, 3)), np.full((3, 3), np.nan),
                            np.full((3, 3), np.inf),
                            np.array([[-.1, .6, .5], [.1, .8, .1], [.4, .3, .3]])]
        for matrix in invalid_matrices:
            with self.subTest(matrix=matrix):
                with self.assertRaises(ValueError):
                    simulate_markov_paths(matrix, 0, 10, 3)
        for parameter, invalid_values in {
            "length": [0, -1, 1.5, True, "10"],
            "n_paths": [0, -1, 1.5, True, "3"],
            "initial_state": [-1, 3, 0.5, True, "1"],
            "seed": [-1, 1.5, True, "17"],
        }.items():
            for value in invalid_values:
                arguments = dict(initial_state=0, length=10, n_paths=3, seed=17)
                arguments[parameter] = value
                with self.subTest(parameter=parameter, value=value):
                    with self.assertRaises(ValueError):
                        simulate_markov_paths(valid, **arguments)

    def test_bootstrap_matches_independent_reestimation_on_every_simulated_path(self):
        states = daily([0, 0, 1, 2, 1, 0, 2, 2, 0, 1, 1, 2] * 10, dtype="Int64")
        lag, n_simulations, seed = 5, 11, 1234

        def manual_statistic(sequence):
            matrices = []
            for distance in [1, lag]:
                counts = np.zeros((3, 3), dtype=int)
                for origin, destination in zip(sequence[:-distance], sequence[distance:]):
                    counts[int(origin), int(destination)] += 1
                matrices.append(counts)
            one, later = matrices
            p_one = one / one.sum(axis=1)[:, None]
            p_power = np.eye(3)
            for _ in range(lag):
                p_power = p_power @ p_one
            total = 0.0
            for row in range(3):
                source_count = later[row].sum()
                if source_count:
                    row_probability = later[row] / source_count
                    total += (source_count / later.sum()) * sum(
                        (float(row_probability[column]) - float(p_power[row, column])) ** 2
                        for column in range(3))
            return float(total), p_one, one, later

        observed_statistic, fitted, one, later = manual_statistic(states.to_numpy())
        paths = simulate_markov_paths(fitted, int(states.iloc[0]), len(states), n_simulations, seed=seed)
        expected = np.array([manual_statistic(path)[0] for path in paths])
        result = ck_bootstrap(states, lag=lag, n_simulations=n_simulations, seed=seed)
        np.testing.assert_array_equal(result["observed"]["counts_1"], one)
        np.testing.assert_array_equal(result["observed"]["counts_lag"], later)
        self.assertAlmostEqual(result["observed"]["statistic"], observed_statistic, places=14)
        np.testing.assert_allclose(result["simulated_statistics"], expected, atol=1e-14, rtol=1e-12)
        self.assertTrue(((expected >= 0) & (expected <= 2)).all())
        exceedances = int(np.count_nonzero(expected >= observed_statistic))
        self.assertEqual(result["exceedances"], exceedances)
        self.assertEqual(result["p_value"], (1 + exceedances) / (n_simulations + 1))
        self.assertEqual(result["invalid_simulations"], 0)
        self.assertEqual(result["n_simulations"], n_simulations)
        self.assertEqual(result["seed"], seed)
        repeat = ck_bootstrap(states, lag=lag, n_simulations=n_simulations, seed=seed)
        np.testing.assert_array_equal(result["simulated_statistics"], repeat["simulated_statistics"])

    def test_any_invalid_simulation_withholds_p_value_without_deleting_or_redrawing(self):
        states = daily([0, 1, 2] * 4, dtype="Int64")
        fixed_paths = np.array([states.to_numpy(dtype=int), np.zeros(len(states), dtype=int)])
        simulator = Mock(return_value=fixed_paths)
        with patch.dict(ck_bootstrap.__globals__, {"simulate_markov_paths": simulator}):
            result = ck_bootstrap(states, n_simulations=2, seed=77)
        simulator.assert_called_once()
        self.assertEqual(result["n_simulations"], 2)
        self.assertEqual(result["invalid_simulations"], 1)
        self.assertEqual(result["simulated_statistics"].shape, (2,))
        self.assertEqual(result["simulated_statistics"][0], 0.0)
        self.assertTrue(np.isnan(result["simulated_statistics"][1]))
        self.assertTrue(np.isnan(result["p_value"]))
        self.assertIsNone(result["exceedances"])

    def test_bootstrap_rejects_invalid_simulation_counts_and_seeds(self):
        states = daily([0, 1, 2] * 4, dtype="Int64")
        for parameter, invalid_values in {
            "n_simulations": [0, -1, 1.5, True, "3"],
            "seed": [-1, 1.5, True, "17"],
        }.items():
            for value in invalid_values:
                arguments = dict(n_simulations=3, seed=17)
                arguments[parameter] = value
                with self.subTest(parameter=parameter, value=value):
                    with self.assertRaises(ValueError):
                        ck_bootstrap(states, **arguments)


if __name__ == "__main__":
    unittest.main()
