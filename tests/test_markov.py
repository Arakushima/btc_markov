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
        "count_transitions",
        "estimate_transition_matrix",
        "count_lagged_transitions",
        "ck_statistic",
        "simulate_markov_paths",
        "ck_bootstrap",
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


class RawTransitionMLETests(unittest.TestCase):
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
