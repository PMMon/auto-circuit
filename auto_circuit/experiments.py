#%%
from collections import defaultdict
from pathlib import Path
from typing import List
import torch as t

from auto_circuit.metrics.completeness_metrics.same_under_knockouts import (
    run_same_under_knockouts,
)
from auto_circuit.metrics.completeness_metrics.test_same_under_knockouts import TaskCompletenessScores, same_under_knockouts_fig, test_same_under_knockout, test_completeness
from auto_circuit.metrics.official_circuits.measure_roc import measure_roc
from auto_circuit.metrics.official_circuits.roc_plot import roc_plot
from auto_circuit.metrics.prune_metrics.measure_prune_metrics import (
    measure_prune_metrics,
    measurement_figs,
)
from auto_circuit.metrics.prune_metrics.prune_metrics import (
    ANSWER_LOGIT_METRIC,
    ANSWER_PROB_METRIC,
    CLEAN_KL_DIV_METRIC,
    CORRUPT_KL_DIV_METRIC,
    LOGIT_DIFF_METRIC,
    LOGIT_DIFF_PERCENT_METRIC,
    WRONG_ANSWER_LOGIT_METRIC,
    PruneMetric,
)
from auto_circuit.metrics.prune_scores_similarity import prune_score_similarities_plotly
from auto_circuit.prune_algos.prune_algos import (
    CIRCUIT_TREE_PROBING_PRUNE_ALGO,
    GROUND_TRUTH_PRUNE_ALGO,
    INTEGRATED_EDGE_GRADS_LOGIT_DIFF_PRUNE_ALGO,
    LOGIT_DIFF_GRAD_PRUNE_ALGO,
    OPPOSITE_TREE_PROBING_PRUNE_ALGO,
    PRUNE_ALGO_DICT,
    RANDOM_PRUNE_ALGO,
    SUBNETWORK_TREE_PROBING_PRUNE_ALGO,
    PruneAlgo,
    run_prune_algos,
)
from auto_circuit.tasks import (
    DOCSTRING_TOKEN_CIRCUIT_TASK,
    IOI_TOKEN_CIRCUIT_TASK,
    SPORTS_PLAYERS_TOKEN_CIRCUIT_TASK,
    TASK_DICT,
    Task,
)
from auto_circuit.types import (
    PatchType,
    TaskMeasurements,
    TaskPruneScores,
)
from auto_circuit.utils.misc import load_cache, repo_path_to_abs_path, save_cache
from auto_circuit.utils.tensor_ops import prune_scores_threshold
from auto_circuit.visualize import draw_seq_graph

TASKS: List[Task] = [
    # Token Circuits
    # SPORTS_PLAYERS_TOKEN_CIRCUIT_TASK,
    # IOI_TOKEN_CIRCUIT_TASK,
    DOCSTRING_TOKEN_CIRCUIT_TASK,
    # Component Circuits
    # SPORTS_PLAYERS_COMPONENT_CIRCUIT_TASK,
    # IOI_COMPONENT_CIRCUIT_TASK,
    # DOCSTRING_COMPONENT_CIRCUIT_TASK,
    # GREATERTHAN_COMPONENT_CIRCUIT_TASK,
    # Autoencoder Component Circuits
    # IOI_GPT2_AUTOENCODER_COMPONENT_CIRCUIT_TASK,
    # GREATERTHAN_GPT2_AUTOENCODER_COMPONENT_CIRCUIT_TASK
    # ANIMAL_DIET_GPT2_AUTOENCODER_COMPONENT_CIRCUIT_TASK,
    # CAPITAL_CITIES_PYTHIA_70M_AUTOENCODER_COMPONENT_CIRCUIT_TASK,
]

PRUNE_ALGOS: List[PruneAlgo] = [
    GROUND_TRUTH_PRUNE_ALGO,
    # ACT_MAG_PRUNE_ALGO,
    RANDOM_PRUNE_ALGO,
    # EDGE_ATTR_PATCH_PRUNE_ALGO,
    # ACDC_PRUNE_ALGO,
    INTEGRATED_EDGE_GRADS_LOGIT_DIFF_PRUNE_ALGO,
    # LOGPROB_GRAD_PRUNE_ALGO,
    # LOGPROB_DIFF_GRAD_PRUNE_ALGO,
    LOGIT_DIFF_GRAD_PRUNE_ALGO,  # Fast implementation of Edge Attribution Patching
    # LOGIT_MSE_GRAD_PRUNE_ALGO,
    # SUBNETWORK_EDGE_PROBING_PRUNE_ALGO,
    # CIRCUIT_PROBING_PRUNE_ALGO,
    SUBNETWORK_TREE_PROBING_PRUNE_ALGO,
    CIRCUIT_TREE_PROBING_PRUNE_ALGO,
    # MSE_CIRCUIT_TREE_PROBING_PRUNE_ALGO,
]

PRUNE_METRICS: List[PruneMetric] = [
    CLEAN_KL_DIV_METRIC,
    CORRUPT_KL_DIV_METRIC,
    ANSWER_PROB_METRIC,
    ANSWER_LOGIT_METRIC,
    WRONG_ANSWER_LOGIT_METRIC,
    LOGIT_DIFF_METRIC,
    LOGIT_DIFF_PERCENT_METRIC,
]
figs = []

# ------------------------------------ Prune Scores ------------------------------------

compute_prune_scores = False
save_prune_scores = False
load_prune_scores = True

task_prune_scores: TaskPruneScores = defaultdict(dict)
cache_folder_name = ".prune_scores_cache"
if compute_prune_scores:
    task_prune_scores = run_prune_algos(TASKS, PRUNE_ALGOS)
if load_prune_scores:
    # 2000 epoch IOI Docstring tensor prune_scores post-kv-cache-fix
    # batch_size=128, batch_count=2, default seed (for both)
    filename = "task-prune-scores-16-02-2024_23-27-49.pkl"

    # 1000 epoch Sport Players tensor prune_scores post-kv-cache-fix
    # batch_size=(10, 20), batch_count=(10, 5), default seed
    # filename = "task-prune-scores-16-02-2024_22-22-43.pkl"

    loaded_cache = load_cache(cache_folder_name, filename)
    task_prune_scores = {k: v | task_prune_scores[k] for k, v in loaded_cache.items()}
if save_prune_scores:
    base_filename = "task-prune-scores"
    save_cache(task_prune_scores, cache_folder_name, base_filename)

for task, algo_prune_scores in task_prune_scores.items():
    for algo, prune_scores in algo_prune_scores.items():
        for module_name, scores in prune_scores.items():
            # Convert dtype to float32
            task_prune_scores[task][algo][module_name] = scores.float()

for task_key in list(task_prune_scores.keys()):
    if not task_key in [DOCSTRING_TOKEN_CIRCUIT_TASK.key]:
        del task_prune_scores[task_key]

# -------------------------------- Draw Circuit Graphs ---------------------------------

if False:
    for task_key, algo_prune_scores in task_prune_scores.items():
        # if not task_key.startswith("Docstring"):
        #     continue
        task = TASK_DICT[task_key]
        if task.key != SPORTS_PLAYERS_TOKEN_CIRCUIT_TASK.key or task.true_edge_count is None:
            continue
        for algo_key, ps in algo_prune_scores.items():
            algo = PRUNE_ALGO_DICT[algo_key]
            # keys = [GROUND_TRUTH_PRUNE_ALGO.key, CIRCUIT_TREE_PROBING_PRUNE_ALGO.key]
            keys = [GROUND_TRUTH_PRUNE_ALGO.key]
            if not algo_key in keys:
                continue
            th = prune_scores_threshold(ps, task.true_edge_count)
            circ_edges = dict([(d, (m >= th).float()) for d, m in ps.items()])
            print("circ_edge_count", sum([m.sum() for m in circ_edges.values()]))
            circ = dict([(d, t.where(m >= th, m, t.zeros_like(m))) for d, m in ps.items()])
            print("task:", task.name, "algo:", algo.name)
            draw_seq_graph(
                model=task.model,
                input=next(iter(task.test_loader)).clean,
                prune_scores=circ,
                seq_labels=task.test_loader.seq_labels,
                show_all_edges=False,
            )

# ------------------------------ Prune Scores Similarity -------------------------------

if False:
    prune_scores_similartity_fig = prune_score_similarities_plotly(
        task_prune_scores, [], ground_truths=True
    )
    figs.append(prune_scores_similartity_fig)

# ------------------------------------ Completeness ------------------------------------

compute_task_completeness_scores = True
save_task_completeness_scores = False
load_task_completeness_scores = False
completeness_prune_scores: TaskPruneScores = {}
algo_keys = ["Official Circuit", "Random"]

if compute_task_completeness_scores:
    completeness_prune_scores: TaskPruneScores = run_same_under_knockouts(
        task_prune_scores,
        algo_keys=algo_keys,
        learning_rate=0.1,
        epochs=50,
        regularize_lambda=0,
    )

cache_folder_name = ".completeness_scores"
if save_task_completeness_scores:
    base_filename = "task-completeness-prune-scores"
    save_cache(completeness_prune_scores, cache_folder_name, base_filename)

if load_task_completeness_scores:
    completeness_prune_scores = load_cache(cache_folder_name, filename)

if completeness_prune_scores:
    task_completeness_scores: TaskCompletenessScores = test_completeness(
        task_prune_scores=task_prune_scores,
        knockout_prune_scores=completeness_prune_scores,
        algo_keys=algo_keys,
    )
    completeness_fig = same_under_knockouts_fig(task_completeness_scores)
    figs.append(completeness_fig)

# ----------------------------- Opposite Task Prune Scores -----------------------------

compute_opposite_task_prune_scores = False
save_opposite_task_prune_scores = False
load_opposite_task_prune_scores = False
opposite_task_prune_scores: TaskPruneScores = {}
opposite_prune_scores_cache_folder_name = ".opposite_prune_scores_cache"
if compute_opposite_task_prune_scores:
    opposite_task_prune_scores = run_prune_algos(
        TASKS, [OPPOSITE_TREE_PROBING_PRUNE_ALGO]
    )
if save_opposite_task_prune_scores:
    base_filename = "opposite-task-prune-scores"
    save_cache(
        opposite_task_prune_scores,
        opposite_prune_scores_cache_folder_name,
        base_filename,
    )
if load_opposite_task_prune_scores:
    filename = "opposite-task-prune-scores-07-02-2024_17-34-33.pkl"
    opposite_task_prune_scores = load_cache(
        opposite_prune_scores_cache_folder_name, filename
    )
if opposite_task_prune_scores:
    opposite_prune_metric_measurements = measure_prune_metrics(
        [ANSWER_PROB_METRIC, LOGIT_DIFF_METRIC],
        opposite_task_prune_scores,
        PatchType.TREE_PATCH,
    )
    figs += list(measurement_figs(opposite_prune_metric_measurements, auc_plots=False))

# ---------------------------------------- ROC -----------------------------------------

compute_roc_measurements = False
save_roc_measurements = False
load_roc_measurements = False
roc_measurements: TaskMeasurements = {}
roc_cache_folder_name = ".roc_measurements"
if compute_roc_measurements:
    roc_measurements: TaskMeasurements = measure_roc(task_prune_scores)
if save_roc_measurements:
    base_filename = "roc-measurements"
    save_cache(roc_measurements, cache_folder_name, base_filename)
if load_roc_measurements:
    filename = "lala.pkl"
    roc_measurements = load_cache(roc_cache_folder_name, filename)
if roc_measurements:
    roc_fig = roc_plot(roc_measurements)
    figs.append(roc_fig)


# ----------------------------- Prune Metric Measurements ------------------------------

compute_prune_metric_measurements = False
save_prune_metric_measurements = False
load_prune_metric_measurements = False

cache_folder_name = ".measurement_cache"
prune_metric_measurements = None
if compute_prune_metric_measurements:
    prune_metric_measurements = measure_prune_metrics(
        PRUNE_METRICS,
        task_prune_scores,
        PatchType.TREE_PATCH,
        reverse_clean_corrupt=False,
    )
    if save_prune_metric_measurements:
        base_filename = "seq-circuit"
        save_cache(prune_metric_measurements, cache_folder_name, base_filename)
if load_prune_metric_measurements:
    # 2000 epoch IOI Docstring tensor prune_scores post-kv-cache-fix
    # filename = "seq-circuit-17-02-2024_03-34-58.pkl"
    # filename = "seq-circuit-18-02-2024_17-20-57.pkl"

    # 1000 epoch Sport Players tensor prune_scores post-kv-cache-fix
    # batch_size=(10, 20), batch_count=(10, 5), default seed
    filename="seq-circuit-18-02-2024_22-09-26.pkl"

    prune_metric_measurements = load_cache(cache_folder_name, filename)

if prune_metric_measurements is not None:
    figs += list(measurement_figs(prune_metric_measurements))

# -------------------------------------- Figures ---------------------------------------

for i, fig in enumerate(figs):
    fig.show()
    folder: Path = repo_path_to_abs_path("figures-12")
    # Save figure as pdf in figures folder
    # fig.write_image(str(folder / f"new {i}.pdf"))

#%%
