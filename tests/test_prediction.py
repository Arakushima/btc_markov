"""Independent synthetic checks for Part A; never load market-data cells."""
import ast
import json
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
if not (ROOT / "notebooks/01_states_and_first_passage.ipynb").exists():
    ROOT = ROOT / "prepared"


def _load_functions():
    path = ROOT / "notebooks/01_states_and_first_passage.ipynb"
    notebook = json.loads(path.read_text(encoding="utf-8"))
    required = {"make_features", "count_transitions", "first_passage_probabilities",
                "make_event_labels", "rolling_forecasts", "score_forecasts",
                "evaluate_asset", "stationary_bootstrap_indices"}
    trees, names = [], set()
    for number, cell in enumerate(notebook["cells"]):
        tags = set(cell.get("metadata", {}).get("tags", []))
        if cell.get("cell_type") != "code" or "part-a-functions" not in tags:
            continue
        source = cell["source"]
        source = source if isinstance(source, str) else "".join(source)
        tree = ast.parse(source, filename=f"{path}#cell-{number}")
        for node in tree.body:
            if not isinstance(node, ast.FunctionDef):
                raise ValueError("Tagged research cells may contain only function definitions")
            if node.name in names:
                raise ValueError(f"Duplicate function definition: {node.name}")
            names.add(node.name)
        trees.append((number, tree))
    if not required.issubset(names):
        raise ValueError(f"Missing functions: {sorted(required - names)}")
    namespace = {"np": np, "pd": pd}
    for number, tree in trees:
        exec(compile(tree, f"{path}#cell-{number}", "exec"), namespace)
    return {name: namespace[name] for name in required}


globals().update(_load_functions())
CONFIG = json.loads((ROOT / "research/part_a_config.json").read_text(encoding="utf-8"))


def daily(values, *, tz=None):
    return pd.Series(values, index=pd.date_range("2020-01-01", periods=len(values), freq="D", tz=tz), dtype="Int64")


def state_sample():
    states = daily(np.random.default_rng(805).choice([0, 1, 2], size=600, p=[.23, .44, .33]))
    states.iloc[[35, 97, 210, 315]] = pd.NA
    return states


def manual_forecast(states, date, config):
    """Explicit date/label loops, with no calls to notebook math helpers."""
    start = date - pd.Timedelta(days=config["window_days"] - 1)
    history = states.loc[(states.index >= start) & (states.index <= date)]
    counts = np.zeros((3, 3), dtype=int)
    for position in range(len(history) - 1):
        source, destination = history.iloc[position:position + 2]
        if pd.notna(source) and pd.notna(destination):
            counts[int(source), int(destination)] += 1
    labels = []
    horizon = config["horizon"]
    for position in range(len(history) - horizon):
        source = history.iloc[position]
        future = history.iloc[position + 1:position + 1 + horizon]
        if pd.notna(source) and int(source) in (1, 2) and future.notna().all():
            labels.append((history.index[position], int(source), int((future == 0).any())))
    source_counts = counts.sum(axis=1)
    group_sizes = {state: sum(source == state for _, source, _ in labels) for state in (1, 2)}
    current = states.loc[date]
    eligible = bool(pd.notna(current) and int(current) in (1, 2)
                    and counts.sum() >= config["min_pairs"]
                    and min(source_counts[1:]) >= config["min_source_pairs"]
                    and len(labels) >= config["min_labels"]
                    and min(group_sizes.values()) >= config["min_state_labels"])
    result = {
        "history_start": start, "n_pairs": int(counts.sum()),
        "n_source_1": int(source_counts[1]), "n_source_2": int(source_counts[2]),
        "n_labels": len(labels), "n_labels_1": group_sizes[1], "n_labels_2": group_sizes[2],
        "latest_label_origin": labels[-1][0] if labels else pd.NaT,
        "latest_label_end": labels[-1][0] + pd.Timedelta(days=horizon) if labels else pd.NaT,
        "eligible": eligible,
    }
    if eligible:
        smoothed = counts.astype(float) + config["dirichlet_alpha"]
        transition = smoothed / smoothed.sum(axis=1)[:, None]
        q_power = np.eye(2)
        for _ in range(horizon):
            q_power = q_power @ transition[1:, 1:]
        current_group = [target for _, source, target in labels if source == int(current)]
        alpha, beta = config["beta_alpha"], config["beta_beta"]
        result.update(q_markov=1. - q_power[int(current) - 1].sum(),
                      q_pooled=(sum(target for _, _, target in labels) + alpha) / (len(labels) + alpha + beta),
                      q_state=(sum(current_group) + alpha) / (len(current_group) + alpha + beta))
    return result


def scoring_fixture():
    index = pd.date_range("2020-01-01", periods=12, freq="D")
    state = pd.Series([1, 2] * 6, index=index, dtype="Int64")
    state.iloc[8] = 0
    forecasts = pd.DataFrame({"state": state,
        "q_markov": [0., 1., .25, .75, .4, .1, .8, .2, .65, .3, .55, .9],
        "q_pooled": [.5] * 12,
        "q_state": [.1, .9, .4, .7, .6, .3, .6, .4, .7, .4, .5, .8],
        "eligible": True, "exclusion_reason": "",
        "n_pairs": 300, "n_source_1": 140, "n_source_2": 100,
        "n_labels": 200, "n_labels_1": 110, "n_labels_2": 90,
        "history_start": index - pd.Timedelta(days=364),
        "latest_label_origin": index - pd.Timedelta(days=5),
        "latest_label_end": index}, index=index)
    forecasts.loc[index[[4, 8]], "eligible"] = False
    forecasts.loc[index[[4, 8]], "exclusion_reason"] = "synthetic_exclusion"
    forecasts.loc[index[[4, 8]], ["q_markov", "q_pooled", "q_state"]] = np.nan
    labels = pd.DataFrame({"state": state,
        "target": pd.Series([1, 0, 0, 1, 1, 0, 1, pd.NA, pd.NA, 1, 0, 1], index=index, dtype="Int64"),
        "target_end_date": index + pd.Timedelta(days=5),
        "label_status": pd.Series(["available"] * 12, index=index, dtype="string")}, index=index)
    labels.loc[index[7], "label_status"] = "incomplete_future"
    labels.loc[index[8], "label_status"] = "risk_origin"
    config = dict(CONFIG, bootstrap_samples=31)
    return forecasts, labels, config


class PredictionTests(unittest.TestCase):
    def test_config_records_the_agreed_values(self):
        expected = dict(horizon=5, window_days=365, dirichlet_alpha=1, beta_alpha=1,
                        beta_beta=1, min_pairs=250, min_source_pairs=20,
                        min_labels=100, min_state_labels=20, log_clip=1e-12,
                        calibration_bins=10, bootstrap_samples=2000,
                        bootstrap_mean_block=10, bootstrap_seed=20261007, ci_level=.95)
        for name, value in expected.items():
            with self.subTest(parameter=name):
                self.assertEqual(CONFIG[name], value)

    def test_rolling_forecasts_match_independent_counts_mature_labels_and_probabilities(self):
        states = state_sample()
        dates = states.index[390:405]
        actual = rolling_forecasts(states, dates[0], dates[-1], CONFIG)
        pd.testing.assert_index_equal(actual.index, dates, check_names=False)
        for date in dates:
            expected = manual_forecast(states, date, CONFIG)
            with self.subTest(date=date):
                for name, value in expected.items():
                    if name.startswith("q_"):
                        self.assertAlmostEqual(actual.at[date, name], value, places=13)
                    else:
                        self.assertEqual(actual.at[date, name], value)
                if not expected["eligible"]:
                    self.assertTrue(actual.loc[date, ["q_markov", "q_pooled", "q_state"]].isna().all())

    def test_future_state_changes_leave_all_earlier_forecast_fields_unchanged(self):
        states = state_sample()
        cutoff = states.index[415]
        changed = states.copy()
        changed.loc[changed.index > cutoff] = 0
        original = rolling_forecasts(states, states.index[390], cutoff, CONFIG)
        perturbed = rolling_forecasts(changed, states.index[390], cutoff, CONFIG)
        pd.testing.assert_frame_equal(original, perturbed)
        self.assertTrue((original["latest_label_end"].dropna() <= original["latest_label_end"].dropna().index).all())

    def test_mature_label_ends_at_origin_and_early_hit_cannot_enter_history(self):
        states = daily([0, 1, 2] * 200)
        origin = states.index[400]
        states.iloc[395] = 1  # The label ending exactly at the forecast origin is eligible.
        states.iloc[398] = 1
        states.iloc[399] = 0  # Early hit, but this origin's five-day label is still immature.
        result = rolling_forecasts(states, origin, origin, CONFIG).loc[origin]
        expected = manual_forecast(states, origin, CONFIG)
        self.assertEqual(result["latest_label_origin"], states.index[395])
        self.assertEqual(result["latest_label_end"], origin)
        self.assertEqual(result["n_labels"], expected["n_labels"])
        self.assertEqual(result["n_labels_1"], expected["n_labels_1"])
        changed = states.copy()
        changed.iloc[401:] = 0
        pd.testing.assert_series_equal(result, rolling_forecasts(changed, origin, origin, CONFIG).loc[origin])

    def test_window_excludes_the_cross_boundary_transition_and_older_labels(self):
        states = state_sample()
        origin = states.index[450]
        states.loc[origin] = 1
        earliest = origin - pd.Timedelta(days=364)
        before = rolling_forecasts(states, origin, origin, CONFIG)
        changed = states.copy()
        changed.loc[changed.index < earliest] = 2
        after = rolling_forecasts(changed, origin, origin, CONFIG)
        pd.testing.assert_frame_equal(before, after)
        self.assertEqual(before.at[origin, "history_start"], earliest)
        self.assertLessEqual(before.at[origin, "n_pairs"], 364)

    def test_every_minimum_threshold_has_an_inclusive_boundary_and_shared_eligibility(self):
        states = state_sample()
        origin = states.index[450]
        states.loc[origin] = 1
        permissive = dict(CONFIG, min_pairs=1, min_source_pairs=1, min_labels=1, min_state_labels=1)
        counts = manual_forecast(states, origin, permissive)
        boundaries = {"min_pairs": counts["n_pairs"],
                      "min_source_pairs": min(counts["n_source_1"], counts["n_source_2"]),
                      "min_labels": counts["n_labels"],
                      "min_state_labels": min(counts["n_labels_1"], counts["n_labels_2"])}
        for name, boundary in boundaries.items():
            with self.subTest(parameter=name):
                allowed = rolling_forecasts(states, origin, origin, dict(permissive, **{name: boundary})).iloc[0]
                excluded = rolling_forecasts(states, origin, origin, dict(permissive, **{name: boundary + 1})).iloc[0]
                self.assertTrue(allowed["eligible"])
                self.assertTrue(allowed[["q_markov", "q_pooled", "q_state"]].notna().all())
                self.assertFalse(excluded["eligible"])
                self.assertTrue(excluded[["q_markov", "q_pooled", "q_state"]].isna().all())
                self.assertTrue(str(excluded["exclusion_reason"]))
        for current in [0, pd.NA]:
            with self.subTest(current=current):
                changed = states.copy()
                changed.loc[origin] = current
                row = rolling_forecasts(changed, origin, origin, permissive).iloc[0]
                self.assertFalse(row["eligible"])
                self.assertTrue(row[["q_markov", "q_pooled", "q_state"]].isna().all())

    def test_rolling_rejects_missing_calendar_dates_and_invalid_states(self):
        states = state_sample()
        broken = states.drop(states.index[300])
        with self.assertRaises(ValueError):
            rolling_forecasts(broken, states.index[400], states.index[410], CONFIG)
        for invalid in [-1, 3, .5, np.inf]:
            with self.subTest(state=invalid):
                changed = states.astype(object)
                changed.iloc[300] = invalid
                with self.assertRaises(ValueError):
                    rolling_forecasts(changed, states.index[400], states.index[410], CONFIG)

    def test_stationary_indices_match_seeded_restart_rule_and_calendar_continuity(self):
        n, resamples, mean_block, seed = 12, 9, 3, 73
        rng = np.random.default_rng(seed)
        expected = np.zeros((resamples, n), dtype=int)
        expected[:, 0] = rng.integers(0, n, size=resamples)
        for position in range(1, n):
            restart = rng.random(resamples) < 1 / mean_block
            fresh = rng.integers(0, n, size=resamples)
            expected[:, position] = np.where(restart, fresh, (expected[:, position - 1] + 1) % n)
        actual = stationary_bootstrap_indices(n, resamples, mean_block, seed)
        np.testing.assert_array_equal(actual, expected)
        np.testing.assert_array_equal(actual, stationary_bootstrap_indices(n, resamples, mean_block, seed))
        self.assertTrue(np.issubdtype(actual.dtype, np.integer))
        self.assertTrue(((actual >= 0) & (actual < n)).all())
        continuous = stationary_bootstrap_indices(n, resamples, 1e12, seed)
        np.testing.assert_array_equal(continuous, (continuous[:, :1] + np.arange(n)) % n)

    def test_score_uses_shared_rows_unclipped_brier_clipped_log_and_endpoint_bins(self):
        forecasts, labels, config = scoring_fixture()
        result = score_forecasts(forecasts, labels, config)
        daily_losses = result["daily_losses"]
        pd.testing.assert_index_equal(daily_losses.index, forecasts.index)
        common = forecasts["eligible"] & labels["target"].notna()
        np.testing.assert_array_equal(daily_losses["scorable"], common)
        y = labels.loc[common, "target"].astype(float)
        for model in ["markov", "pooled", "state"]:
            probability = forecasts.loc[common, "q_" + model]
            expected_brier = (probability - y) ** 2
            clipped = probability.clip(config["log_clip"], 1 - config["log_clip"])
            expected_log = -y * np.log(clipped) - (1 - y) * np.log1p(-clipped)
            np.testing.assert_allclose(daily_losses.loc[common, "brier_" + model], expected_brier)
            np.testing.assert_allclose(daily_losses.loc[common, "log_" + model], expected_log)
            self.assertTrue(daily_losses.loc[~common, ["brier_" + model, "log_" + model]].isna().all().all())
            summary = result["summary"].loc[model]
            self.assertEqual(summary["n"], int(common.sum()))
            self.assertAlmostEqual(summary["brier"], expected_brier.mean())
            self.assertAlmostEqual(summary["log_loss"], expected_log.mean())
            self.assertAlmostEqual(summary["event_rate"], y.mean())
            self.assertAlmostEqual(summary["mean_forecast"], probability.mean())
            bins = result["calibration"].loc[lambda frame: frame["model"] == model]
            self.assertEqual(int(bins["n"].sum()), int(common.sum()))
        self.assertEqual(daily_losses["brier_markov"].iloc[0], 1.0)
        self.assertEqual(daily_losses["brier_markov"].iloc[1], 1.0)
        bins = result["calibration"].loc[lambda frame: frame["model"] == "markov"]
        self.assertGreaterEqual(int(bins.loc[np.isclose(bins["lower"], 0), "n"].sum()), 1)
        self.assertGreaterEqual(int(bins.loc[np.isclose(bins["upper"], 1), "n"].sum()), 1)
        coverage = result["coverage"].iloc[0]
        self.assertEqual(coverage["calendar_origins"], 12)
        self.assertEqual(coverage["forecast_eligible"], 10)
        self.assertEqual(coverage["scorable"], 9)
        self.assertEqual(coverage["forecast_excluded"], 2)
        self.assertEqual(coverage["label_unavailable"], 1)

    def test_bootstrap_uses_one_paired_calendar_index_matrix_for_every_comparison(self):
        forecasts, labels, config = scoring_fixture()
        result = score_forecasts(forecasts, labels, config)
        losses = result["daily_losses"]
        indices = stationary_bootstrap_indices(len(forecasts), config["bootstrap_samples"],
                                               config["bootstrap_mean_block"], config["bootstrap_seed"])
        pairs = {"markov_vs_state": ("markov", "state"),
                 "markov_vs_pooled": ("markov", "pooled"),
                 "state_vs_pooled": ("state", "pooled")}
        for name, (first, baseline) in pairs.items():
            difference = (losses["brier_" + baseline] - losses["brier_" + first]).to_numpy(dtype=float)
            expected = np.array([np.nanmean(difference[draw]) for draw in indices])
            np.testing.assert_allclose(result["bootstrap"][name], expected)
            comparison = result["comparisons"].loc[name]
            self.assertAlmostEqual(comparison["delta_brier"], np.nanmean(difference))
            alpha = (1 - config["ci_level"]) / 2
            lower, upper = np.quantile(expected, [alpha, 1 - alpha])
            self.assertAlmostEqual(comparison["ci_lower"], lower)
            self.assertAlmostEqual(comparison["ci_upper"], upper)
            self.assertEqual(comparison["invalid_resamples"], 0)
            self.assertEqual(comparison["n"], 9)
            expected_decision = "supports_improvement" if lower > 0 else "supports_worse" if upper < 0 else "uncertain"
            self.assertEqual(comparison["decision"], expected_decision)

    def test_identical_forecasts_have_zero_paired_deltas_and_uncertain_decision(self):
        forecasts, labels, config = scoring_fixture()
        forecasts["q_state"] = forecasts["q_markov"]
        result = score_forecasts(forecasts, labels, config)
        np.testing.assert_array_equal(result["bootstrap"]["markov_vs_state"], np.zeros(config["bootstrap_samples"]))
        comparison = result["comparisons"].loc["markov_vs_state"]
        self.assertEqual(comparison["delta_brier"], 0)
        self.assertEqual(comparison["ci_lower"], 0)
        self.assertEqual(comparison["ci_upper"], 0)
        self.assertEqual(comparison["decision"], "uncertain")

    def test_one_resample_with_no_scorable_dates_is_retained_and_withholds_all_intervals(self):
        forecasts, labels, config = scoring_fixture()
        config["bootstrap_samples"] = 2
        draws = np.array([np.arange(12), np.full(12, 7)])
        sampler = Mock(return_value=draws)
        with patch.dict(score_forecasts.__globals__, {"stationary_bootstrap_indices": sampler}):
            result = score_forecasts(forecasts, labels, config)
        sampler.assert_called_once()
        self.assertEqual(result["bootstrap"].shape, (2, 3))
        self.assertTrue(result["bootstrap"].iloc[1].isna().all())
        self.assertTrue(result["bootstrap"].iloc[0].notna().all())
        self.assertTrue((result["comparisons"]["invalid_resamples"] == 1).all())
        self.assertTrue(result["comparisons"][["ci_lower", "ci_upper"]].isna().all().all())
        self.assertTrue((result["comparisons"]["decision"] == "unavailable").all())

    def test_score_rejects_invalid_probabilities_targets_states_and_end_dates(self):
        forecasts, labels, config = scoring_fixture()
        for model in ["markov", "pooled", "state"]:
            for invalid in [np.nan, np.inf, -.01, 1.01]:
                with self.subTest(model=model, value=invalid):
                    changed = forecasts.copy()
                    changed.loc[changed.index[0], "q_" + model] = invalid
                    with self.assertRaises(ValueError):
                        score_forecasts(changed, labels, config)
        for invalid in [2, -.5]:
            with self.subTest(target=invalid):
                changed = labels.copy()
                changed["target"] = changed["target"].astype(object)
                changed.loc[changed.index[0], "target"] = invalid
                with self.assertRaises(ValueError):
                    score_forecasts(forecasts, changed, config)
        mismatched_state = labels.copy()
        mismatched_state.loc[mismatched_state.index[0], "state"] = 2
        with self.assertRaises(ValueError):
            score_forecasts(forecasts, mismatched_state, config)
        wrong_end = labels.copy()
        wrong_end.loc[wrong_end.index[0], "target_end_date"] += pd.Timedelta(days=1)
        with self.assertRaises(ValueError):
            score_forecasts(forecasts, wrong_end, config)

    def test_evaluate_asset_preserves_causal_forecasts_when_later_prices_change(self):
        rng = np.random.default_rng(331)
        close = pd.Series(100 * np.cumprod(1 + rng.normal(.0002, .01, 550)),
                          index=pd.date_range("2020-01-01", periods=550, freq="D"))
        start, end = close.index[420], close.index[439]
        changed = close.copy()
        changed.loc[changed.index > end] *= 1.5
        config = dict(CONFIG, bootstrap_samples=7)
        first = evaluate_asset(close, start, end, config)
        second = evaluate_asset(changed, start, end, config)
        pd.testing.assert_frame_equal(first["forecasts"], second["forecasts"])
        pd.testing.assert_index_equal(first["forecasts"].index, close.loc[start:end].index, check_names=False)
        pd.testing.assert_frame_equal(first["labels"].loc[:end - pd.Timedelta(days=5)],
                                      second["labels"].loc[:end - pd.Timedelta(days=5)])
        self.assertTrue({"daily_losses", "summary", "calibration", "comparisons", "coverage", "bootstrap",
                         "forecasts", "labels"}.issubset(first))


if __name__ == "__main__":
    unittest.main()
