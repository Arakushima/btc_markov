"""Independent synthetic residence-time and Holm checks; no market data read.

Set BTC_PART_B_NOTEBOOK to test a staged notebook. Installed in tests/, the
default loads only function definitions from the project's canonical notebook.
"""
import ast
from fractions import Fraction
from itertools import groupby
import json
import os
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

import numpy as np
import pandas as pd


def _load_notebook_functions():
    default = Path(__file__).resolve().parents[1] / "notebooks/01_states_and_first_passage.ipynb"
    path = Path(os.environ.get("BTC_PART_B_NOTEBOOK", str(default)))
    notebook = json.loads(path.read_text(encoding="utf-8"))
    expected = {"extract_complete_runs", "residence_statistic", "residence_bootstrap", "holm_adjust", "development_window"}
    trees, names = [], set()
    for index, cell in enumerate(notebook["cells"]):
        if cell.get("cell_type") != "code" or "research-functions" not in cell.get("metadata", {}).get("tags", []):
            continue
        source = cell.get("source", [])
        source = source if isinstance(source, str) else "".join(source)
        tree = ast.parse(source, filename=f"{path}#cell-{index}")
        for node in tree.body:
            if not isinstance(node, ast.FunctionDef):
                raise ValueError("research-functions cells must contain only function definitions")
            if node.name in names:
                raise ValueError(f"Duplicate notebook function: {node.name}")
            names.add(node.name)
        trees.append((index, tree))
    if not expected.issubset(names):
        raise ValueError(f"Missing notebook functions: {sorted(expected - names)}")
    namespace = {"np": np, "pd": pd}
    # Validate all selected cells first. Never execute loading, analysis, or
    # display cells, and never inspect saved notebook outputs.
    for index, tree in trees:
        exec(compile(tree, f"{path}#cell-{index}", "exec"), namespace)
    return {name: namespace[name] for name in expected}


globals().update(_load_notebook_functions())


def daily(values, *, tz=None):
    return pd.Series(values, index=pd.date_range("2020-01-01", periods=len(values), freq="D", tz=tz))


def expand_runs(pairs):
    return [state for state, length in pairs for _ in range(length)]


MANUAL_RUNS = [(0, 2), (1, 1), (2, 3), (0, 2), (1, 2),
               (2, 1), (0, 1), (1, 1), (2, 2), (1, 4)]


def manual_statistic(sequence, max_duration=20, min_runs=5, fixed_matrix=None):
    """Independent loop/groupby oracle, also used to detect failure to refit."""
    values = [int(value) for value in sequence]
    counts = np.zeros((3, 3), dtype=int)
    for left, right in zip(values[:-1], values[1:]):
        counts[left, right] += 1
    if (counts.sum(axis=1) == 0).any():
        raise ValueError("Missing source row")
    matrix = counts / counts.sum(axis=1)[:, None]
    grouped = [(state, len(list(items))) for state, items in groupby(values)]
    complete = grouped[1:-1]
    lengths = [[length for state, length in complete if state == wanted] for wanted in range(3)]
    run_counts = np.array([len(items) for items in lengths])
    if (run_counts < min_runs).any():
        raise ValueError("Too few complete runs")
    if fixed_matrix is not None:
        matrix = fixed_matrix
    total = 0.0
    for state in range(3):
        squared_errors = []
        for duration in range(2, max_duration + 1):
            empirical = sum(length >= duration for length in lengths[state]) / len(lengths[state])
            geometric = float(matrix[state, state]) ** (duration - 1)
            squared_errors.append((empirical - geometric) ** 2)
        total += (len(lengths[state]) / len(complete)) * sum(squared_errors) / len(squared_errors)
    return float(total), counts / counts.sum(axis=1)[:, None], run_counts


class CompleteRunTests(unittest.TestCase):
    def test_all_runs_dates_and_boundary_flags_match_manual_oracle(self):
        states = daily(expand_runs(MANUAL_RUNS), tz="UTC")
        runs = extract_complete_runs(states)
        self.assertEqual(set(runs.columns), {"state", "length", "start_date", "end_date",
                                             "left_truncated", "right_truncated", "complete"})
        self.assertEqual(list(zip(runs["state"], runs["length"])), MANUAL_RUNS)
        offset = 0
        for position, (_, length) in enumerate(MANUAL_RUNS):
            row = runs.iloc[position]
            self.assertEqual(row["start_date"], states.index[offset])
            self.assertEqual(row["end_date"], states.index[offset + length - 1])
            self.assertEqual(bool(row["left_truncated"]), position == 0)
            self.assertEqual(bool(row["right_truncated"]), position == len(MANUAL_RUNS) - 1)
            self.assertEqual(bool(row["complete"]), 0 < position < len(MANUAL_RUNS) - 1)
            offset += length
        self.assertEqual(int(runs["length"].sum()), len(states))

    def test_one_run_is_both_left_and_right_truncated_even_for_one_observation(self):
        for length in [1, 7]:
            with self.subTest(length=length):
                runs = extract_complete_runs(daily([2] * length))
                self.assertEqual(len(runs), 1)
                self.assertEqual(int(runs.iloc[0]["length"]), length)
                self.assertTrue(bool(runs.iloc[0]["left_truncated"]))
                self.assertTrue(bool(runs.iloc[0]["right_truncated"]))
                self.assertFalse(bool(runs.iloc[0]["complete"]))

    def test_two_distinct_runs_have_no_complete_run(self):
        runs = extract_complete_runs(daily([0, 0, 1, 1, 1]))
        self.assertEqual(len(runs), 2)
        self.assertFalse(runs["complete"].any())
        np.testing.assert_array_equal(runs["left_truncated"], [True, False])
        np.testing.assert_array_equal(runs["right_truncated"], [False, True])

    def test_missing_or_invalid_states_are_rejected_without_bridging(self):
        for invalid in [pd.NA, np.nan, np.inf, -1, 3, .5, "invalid"]:
            with self.subTest(value=invalid):
                with self.assertRaises(ValueError):
                    extract_complete_runs(daily([0, 0, invalid, 0, 1, 2]))

    def test_missing_duplicate_unsorted_and_nondaily_dates_are_rejected(self):
        states = daily([0, 1, 2, 0, 1, 2])
        index = states.index
        bad_indexes = [index.delete(2).append(pd.DatetimeIndex([index[-1] + pd.Timedelta(days=1)])),
                       pd.DatetimeIndex([index[0], index[0], *index[2:]]),
                       index[::-1], index + pd.Timedelta(hours=1), pd.RangeIndex(len(states))]
        for bad in bad_indexes:
            with self.subTest(index=bad):
                with self.assertRaises(ValueError):
                    extract_complete_runs(pd.Series(states.to_numpy(), index=bad))


class ResidenceStatisticTests(unittest.TestCase):
    def test_weighted_statistic_matches_exact_rational_hand_calculation(self):
        states = daily(expand_runs(MANUAL_RUNS))
        result = residence_statistic(states, max_duration=4, min_runs=2)
        self.assertTrue({"P1", "counts_1", "runs", "run_counts", "run_weights", "durations",
                         "empirical_survival", "geometric_survival", "statistic"}.issubset(result))
        counts = np.array([[2, 3, 0], [0, 4, 3], [2, 1, 3]])
        np.testing.assert_array_equal(result["counts_1"], counts)
        np.testing.assert_allclose(result["P1"], counts / np.array([5, 7, 6])[:, None])
        np.testing.assert_array_equal(result["run_counts"], [2, 3, 3])
        np.testing.assert_allclose(result["run_weights"], [2 / 8, 3 / 8, 3 / 8])
        np.testing.assert_array_equal(result["durations"], [2, 3, 4])
        empirical = [[Fraction(1, 2), Fraction(0), Fraction(0)],
                     [Fraction(1, 3), Fraction(0), Fraction(0)],
                     [Fraction(2, 3), Fraction(1, 3), Fraction(0)]]
        diagonal = [Fraction(2, 5), Fraction(4, 7), Fraction(1, 2)]
        geometric = [[probability ** exponent for exponent in [1, 2, 3]] for probability in diagonal]
        expected = sum(Fraction(n, 8) * sum((a - b) ** 2 for a, b in zip(actual, fitted)) / 3
                       for n, actual, fitted in zip([2, 3, 3], empirical, geometric))
        np.testing.assert_allclose(result["empirical_survival"], np.array(empirical, dtype=float))
        np.testing.assert_allclose(result["geometric_survival"], np.array(geometric, dtype=float))
        self.assertAlmostEqual(result["statistic"], float(expected), places=14)
        pd.testing.assert_frame_equal(result["runs"], extract_complete_runs(states))

    def test_default_duration_range_is_two_through_twenty_and_cycle_has_zero_error(self):
        result = residence_statistic(daily([0, 1, 2] * 6))
        np.testing.assert_array_equal(result["durations"], np.arange(2, 21))
        self.assertEqual(result["empirical_survival"].shape, (3, 19))
        self.assertEqual(result["geometric_survival"].shape, (3, 19))
        np.testing.assert_array_equal(result["run_counts"], [5, 6, 5])
        self.assertEqual(result["statistic"], 0.0)
        with self.assertRaises(ValueError):
            residence_statistic(daily([0, 1, 2] * 5))

    def test_two_is_valid_max_duration_and_uses_survival_not_cdf(self):
        result = residence_statistic(daily(expand_runs(MANUAL_RUNS)), max_duration=2, min_runs=2)
        np.testing.assert_array_equal(result["durations"], [2])
        np.testing.assert_allclose(result["empirical_survival"], [[.5], [1 / 3], [2 / 3]])
        expected, _, _ = manual_statistic(expand_runs(MANUAL_RUNS), max_duration=2, min_runs=2)
        self.assertAlmostEqual(result["statistic"], expected, places=14)

    def test_sparse_one_step_rows_or_any_sparse_complete_run_group_are_unavailable(self):
        for states, minimum in [(daily([0, 1] * 12), 1),
                                (daily([0, 1, 0, 1, 2]), 1),
                                (daily([0, 1, 2, 1, 2, 0, 1, 2, 0]), 2)]:
            with self.subTest(values=states.to_list(), min_runs=minimum):
                with self.assertRaises(ValueError):
                    residence_statistic(states, min_runs=minimum)

    def test_statistic_rejects_missing_states_and_gapped_calendar(self):
        values = daily([0, 1, 2] * 8)
        missing = values.astype("Int64")
        missing.iloc[5] = pd.NA
        for states in [missing, values.drop(values.index[5])]:
            with self.assertRaises(ValueError):
                residence_statistic(states)

    def test_duration_and_minimum_are_integers_with_explicit_lower_bounds(self):
        states = daily([0, 1, 2] * 8)
        invalid_by_parameter = {"max_duration": [0, 1, -1, 2.5, True, False, "20"],
                                "min_runs": [0, -1, 1.5, True, False, "5"]}
        for name, invalids in invalid_by_parameter.items():
            for value in invalids:
                with self.subTest(parameter=name, value=value):
                    with self.assertRaises(ValueError):
                        residence_statistic(states, **{name: value})
        # NumPy integer parameters remain ordinary integer values.
        result = residence_statistic(states, max_duration=np.int64(2), min_runs=np.int64(1))
        self.assertEqual(result["statistic"], 0.0)


class ResidenceBootstrapTests(unittest.TestCase):
    def test_deterministic_cycle_counts_ties_and_returns_p_one(self):
        result = residence_bootstrap(daily([0, 1, 2] * 8), n_simulations=7, seed=321)
        self.assertEqual(result["observed"]["statistic"], 0.0)
        np.testing.assert_array_equal(result["simulated_statistics"], np.zeros(7))
        self.assertEqual(result["invalid_simulations"], 0)
        self.assertEqual(result["n_simulations"], 7)
        self.assertEqual(result["exceedances"], 7)
        self.assertEqual(result["p_value"], 1.0)
        self.assertEqual(result["seed"], 321)

    def test_each_simulation_refits_matrix_runs_and_weights_against_loop_oracle(self):
        states = daily(expand_runs(MANUAL_RUNS) * 20)
        duration, minimum, n_simulations, seed = 7, 5, 11, 203
        observed, fitted, _ = manual_statistic(states, duration, minimum)
        uniforms = np.random.default_rng(seed).random((n_simulations, len(states) - 1))
        paths = np.empty((n_simulations, len(states)), dtype=int)
        paths[:, 0] = int(states.iloc[0])
        for row in range(n_simulations):
            for step in range(1, len(states)):
                cumulative = np.cumsum(fitted[paths[row, step - 1]])
                cumulative[-1] = 1.0
                paths[row, step] = np.searchsorted(cumulative, uniforms[row, step - 1], side="right")
        expected = np.array([manual_statistic(path, duration, minimum)[0] for path in paths])
        incorrectly_fixed = np.array([manual_statistic(path, duration, minimum, fixed_matrix=fitted)[0]
                                      for path in paths])
        self.assertGreater(float(np.max(np.abs(expected - incorrectly_fixed))), 1e-5)
        result = residence_bootstrap(states, max_duration=duration, min_runs=minimum,
                                     n_simulations=n_simulations, seed=seed)
        self.assertAlmostEqual(result["observed"]["statistic"], observed, places=14)
        np.testing.assert_allclose(result["simulated_statistics"], expected, rtol=1e-12, atol=1e-14)
        self.assertEqual(result["invalid_simulations"], 0)
        exceedances = int((expected >= observed).sum())
        self.assertEqual(result["exceedances"], exceedances)
        self.assertEqual(result["p_value"], (1 + exceedances) / (n_simulations + 1))
        repeat = residence_bootstrap(states, max_duration=duration, min_runs=minimum,
                                     n_simulations=n_simulations, seed=seed)
        np.testing.assert_array_equal(result["simulated_statistics"], repeat["simulated_statistics"])

    def test_any_invalid_path_is_retained_without_drop_redraw_or_partial_p(self):
        states = daily([0, 1, 2] * 8)
        sparse_runs = np.repeat([0, 1, 2], 8)  # All source rows exist; complete runs are insufficient.
        absent_rows = np.zeros(len(states), dtype=int)
        paths = np.array([states.to_numpy(dtype=int), sparse_runs, absent_rows])
        simulator = Mock(return_value=paths)
        with patch.dict(residence_bootstrap.__globals__, {"simulate_markov_paths": simulator}):
            result = residence_bootstrap(states, n_simulations=3, seed=77)
        simulator.assert_called_once()
        self.assertEqual(result["n_simulations"], 3)
        self.assertEqual(result["invalid_simulations"], 2)
        self.assertEqual(result["simulated_statistics"].shape, (3,))
        self.assertEqual(result["simulated_statistics"][0], 0.0)
        self.assertTrue(np.isnan(result["simulated_statistics"][1:]).all())
        self.assertTrue(np.isnan(result["p_value"]))
        self.assertIsNone(result["exceedances"])

    def test_bootstrap_validates_simulation_count_and_seed(self):
        states = daily([0, 1, 2] * 8)
        for name, invalids in {"n_simulations": [0, -1, 1.5, True, "3"],
                               "seed": [-1, 1.5, True, "17"]}.items():
            for value in invalids:
                arguments = {"n_simulations": 3, "seed": 17, name: value}
                with self.subTest(parameter=name, value=value):
                    with self.assertRaises(ValueError):
                        residence_bootstrap(states, **arguments)


class HolmTests(unittest.TestCase):
    def test_unsorted_values_preserve_labels_use_stepdown_monotonicity_and_clip(self):
        raw = pd.Series([.04, .008, .03, .8], index=["fourth", "first", "third", "second"], name="input")
        result = holm_adjust(raw)
        self.assertEqual(set(result.columns), {"raw_p", "holm_p", "reject", "family_available"})
        pd.testing.assert_index_equal(result.index, raw.index)
        np.testing.assert_array_equal(result["raw_p"], raw)
        np.testing.assert_allclose(result["holm_p"], [.09, .032, .09, .8])
        np.testing.assert_array_equal(result["reject"].to_numpy(dtype=bool), [False, True, False, False])
        self.assertTrue(result["family_available"].all())
        clipped = holm_adjust(pd.Series([.7, .8, 1.], index=["a", "b", "c"]))
        np.testing.assert_array_equal(clipped["holm_p"], [1., 1., 1.])

    def test_ties_have_equal_adjusted_values_and_exact_alpha_boundary_rejects(self):
        raw = pd.Series([.025, .025], index=["CK", "residence"])
        result = holm_adjust(raw, alpha=.05)
        np.testing.assert_allclose(result["holm_p"], [.05, .05])
        self.assertTrue(result["reject"].all())
        result = holm_adjust(raw, alpha=.049)
        self.assertFalse(result["reject"].any())

    def test_zero_and_one_are_valid_probabilities(self):
        result = holm_adjust(pd.Series([1., 0.], index=["CK", "residence"]))
        np.testing.assert_array_equal(result["holm_p"], [1., 0.])
        np.testing.assert_array_equal(result["reject"].to_numpy(dtype=bool), [False, True])

    def test_missing_p_withholds_entire_family_without_shrinking_or_false_decisions(self):
        for raw in [pd.Series([.001, np.nan], index=["CK", "residence"]),
                    pd.Series([pd.NA, .001], index=["CK", "residence"], dtype="Float64")]:
            with self.subTest(values=raw.to_list()):
                result = holm_adjust(raw)
                pd.testing.assert_index_equal(result.index, raw.index)
                self.assertTrue(result["holm_p"].isna().all())
                self.assertTrue(result["reject"].isna().all())
                self.assertEqual(str(result["reject"].dtype), "boolean")
                self.assertFalse(result["family_available"].any())
                np.testing.assert_array_equal(result["raw_p"].isna(), raw.isna())



class DevelopmentWindowTests(unittest.TestCase):
    def test_fixed_window_preserves_precomputed_states(self):
        states = daily([0, 1, 2, 1, 0, 2])
        actual = development_window(states, "2020-01-02", "2020-01-05")
        pd.testing.assert_series_equal(actual, states.iloc[1:5])

    def test_holdout_or_incomplete_window_is_rejected(self):
        states = daily([0, 1, 2, 1, 0, 2])
        for start, end in [("2020-01-01", "2024-01-01"),
                           ("2019-12-31", "2020-01-03"),
                           ("2020-01-01", "2020-01-07")]:
            with self.subTest(start=start, end=end), self.assertRaises(ValueError):
                development_window(states, start, end)
        states.iloc[2] = np.nan
        with self.assertRaises(ValueError):
            development_window(states, "2020-01-01", "2020-01-06")

if __name__ == "__main__":
    unittest.main()
