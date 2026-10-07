"""Synthetic orchestration checks; execute tagged definitions, never data cells."""
import ast
import json
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

import numpy as np
import pandas as pd


def load_functions():
    here = Path(__file__).resolve().parent
    candidates = [here / "prepared/01_states_and_first_passage.ipynb",
                  here.parent / "notebooks/01_states_and_first_passage.ipynb"]
    path = next(candidate for candidate in candidates if candidate.is_file())
    notebook = json.loads(path.read_text(encoding="utf-8"))
    trees, names = [], set()
    for index, cell in enumerate(notebook["cells"]):
        if cell.get("cell_type") != "code" or "research-functions" not in cell.get("metadata", {}).get("tags", []):
            continue
        source = cell["source"]
        tree = ast.parse("".join(source) if isinstance(source, list) else source)
        for node in tree.body:
            if not isinstance(node, ast.FunctionDef) or node.name in names:
                raise ValueError("Tagged cells must contain unique function definitions only")
            names.add(node.name)
        trees.append((index, tree))
    required = {"run_development_diagnostic", "residence_bootstrap", "holm_adjust"}
    if not required.issubset(names):
        raise ValueError("Required Part B definitions are missing")
    namespace = {"np": np, "pd": pd}
    for index, tree in trees:
        exec(compile(tree, f"{path}#cell-{index}", "exec"), namespace)
    return namespace


FUNCTIONS = load_functions()
run_development_diagnostic = FUNCTIONS["run_development_diagnostic"]
residence_bootstrap = FUNCTIONS["residence_bootstrap"]
holm_adjust = FUNCTIONS["holm_adjust"]
CONFIG = {"ck_lag": 5, "max_duration": 20, "min_runs": 5,
          "n_simulations": 7, "seed": 20261004}


def states(repeats):
    return pd.Series([0, 1, 2] * repeats,
                     index=pd.date_range("2021-01-01", periods=3 * repeats, freq="D"), dtype="Int64")


class PartBAvailabilityTests(unittest.TestCase):
    def test_sparse_observed_residence_is_retained_without_simulation_and_withholds_family(self):
        path = states(4)
        simulator = Mock(side_effect=AssertionError("An unavailable observed path must not be simulated"))
        with patch.dict(FUNCTIONS, {"simulate_markov_paths": simulator}):
            result = run_development_diagnostic(path, str(path.index[0].date()),
                                               str(path.index[-1].date()), "Residence", CONFIG)
        simulator.assert_not_called()
        self.assertIsNone(result["observed"])
        self.assertTrue(np.isnan(result["p_value"]))
        self.assertEqual(result["n_simulations"], 0)
        self.assertEqual(len(result["simulated_statistics"]), 0)
        self.assertIn("Too few complete runs", result["unavailable_reason"])
        family = holm_adjust(pd.Series({"CK": .01, "Residence": result["p_value"]}))
        self.assertTrue(family["holm_p"].isna().all())
        self.assertTrue(family["reject"].isna().all())
        self.assertFalse(family["family_available"].any())

    def test_missing_state_or_date_records_both_diagnostics_unavailable_before_estimation(self):
        complete = states(10)
        missing_state = complete.copy()
        missing_state.iloc[7] = pd.NA
        missing_date = complete.drop(complete.index[7])
        estimator = Mock(side_effect=AssertionError("An incomplete window must not reach estimation"))
        with patch.dict(FUNCTIONS, {"ck_bootstrap": estimator, "residence_bootstrap": estimator}):
            for path in [missing_state, missing_date]:
                for diagnostic in ["CK", "Residence"]:
                    with self.subTest(diagnostic=diagnostic, rows=len(path)):
                        result = run_development_diagnostic(path, "2021-01-01", "2021-01-30", diagnostic, CONFIG)
                        self.assertIsNone(result["observed"])
                        self.assertTrue(np.isnan(result["p_value"]))
                        self.assertEqual(result["n_simulations"], 0)
                        self.assertIn("complete prespecified development window", result["unavailable_reason"])
        estimator.assert_not_called()

    def test_available_path_matches_direct_result_and_unexpected_failures_propagate(self):
        path = states(10)
        wrapped = run_development_diagnostic(path, "2021-01-01", "2021-01-30", "Residence", CONFIG)
        direct = residence_bootstrap(path, max_duration=20, min_runs=5, n_simulations=7, seed=20261004)
        np.testing.assert_array_equal(wrapped["simulated_statistics"], direct["simulated_statistics"])
        np.testing.assert_array_equal(wrapped["observed"]["run_counts"], direct["observed"]["run_counts"])
        self.assertEqual(wrapped["p_value"], 1.0)
        self.assertEqual(wrapped["n_simulations"], 7)
        with patch.dict(FUNCTIONS, {"residence_bootstrap": Mock(side_effect=ValueError("unexpected implementation failure"))}):
            with self.assertRaisesRegex(ValueError, "unexpected implementation failure"):
                run_development_diagnostic(path, "2021-01-01", "2021-01-30", "Residence", CONFIG)


if __name__ == "__main__":
    unittest.main()
