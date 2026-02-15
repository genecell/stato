"""Test fixtures — all module source strings from the spec."""

VALID_QC_SKILL = '''
class QualityControl:
    """QC filtering for scRNA-seq data."""
    name = "qc_filtering"
    version = "1.2.0"
    depends_on = ["scanpy"]
    default_params = {
        "min_genes": 200,
        "max_genes": 5000,
        "max_pct_mito": 20,
        "min_cells": 3,
    }
    lessons_learned = """
    - Cortex tissue: max_pct_mito=20 retains ~85% of cells
    - FFPE samples: increase to max_pct_mito=40
    - Mouse data: use mt- prefix (lowercase). Human: MT-
    - If retention < 60%, thresholds are probably too aggressive
    """
    @staticmethod
    def run(adata_path, **kwargs):
        params = {**QualityControl.default_params, **kwargs}
        return params
'''

VALID_NORMALIZE_SKILL = '''
class Normalization:
    """Normalization for scRNA-seq data."""
    name = "normalize"
    version = "1.1.0"
    depends_on = ["scanpy", "qc_filtering"]
    default_params = {"method": "scran"}
    lessons_learned = """
    - scran outperforms log-normalize for heterogeneous tissues
    - For < 200 cells, fall back to simple normalization
    """
    @staticmethod
    def run(adata_path, **kwargs):
        return kwargs
'''

VALID_CLUSTER_SKILL = '''
class Clustering:
    """Cell clustering for scRNA-seq data."""
    name = "clustering"
    version = "1.0.0"
    depends_on = ["scanpy"]
    default_params = {"resolution": 0.6, "method": "leiden"}
    lessons_learned = """
    - Resolution 0.6 gives biologically meaningful clusters for cortex
    - Leiden outperforms Louvain for datasets > 5000 cells
    """
    @staticmethod
    def run(**kwargs): pass
'''

VALID_PLAN = '''
class AnalysisPlan:
    name = "cortex_analysis"
    objective = "Complete scRNA-seq analysis pipeline"
    steps = [
        {"id": 1, "action": "load_data", "status": "complete",
         "output": "loaded 15000 cells x 20000 genes"},
        {"id": 2, "action": "qc_filtering", "status": "complete",
         "output": "filtered to 12500 cells using max_pct_mito=20"},
        {"id": 3, "action": "normalize", "status": "complete",
         "output": "scran normalization applied"},
        {"id": 4, "action": "find_hvg", "status": "pending"},
        {"id": 5, "action": "dim_reduction", "status": "pending", "depends_on": [4]},
        {"id": 6, "action": "clustering", "status": "pending", "depends_on": [5]},
        {"id": 7, "action": "marker_genes", "status": "pending", "depends_on": [6]},
    ]
    decision_log = """
    - Chose scran over log-normalize based on benchmark results
    - Will use leiden clustering based on dataset size > 5000 cells
    """
'''

VALID_MEMORY = '''
class AnalysisState:
    phase = "analysis"
    tasks = ["find_hvg", "dim_reduction", "clustering", "markers"]
    known_issues = {"batch_effect": "plates 1 and 2 show batch effect"}
    reflection = """
    QC and normalization complete. Data quality is good.
    Batch effect between plates needs correction before clustering.
    """
'''

VALID_CONTEXT = '''
class ProjectContext:
    project = "cortex_scrna"
    description = "scRNA-seq analysis of mouse cortex P14"
    datasets = ["data/raw/cortex_p14.h5ad"]
    environment = {"scanpy": "1.10.0", "python": "3.11"}
    conventions = [
        "Use scanpy for all analysis",
        "Save figures to figures/ directory",
        "Use .h5ad format for all intermediate files",
    ]
'''

CORRUPTED_SKILL_MISSING_FIELDS = '''
class QC:
    # missing name
    # missing run()
    depends_on = "scanpy"
'''

CORRUPTED_SKILL_BAD_TYPES = '''
class QC:
    name = "qc"
    version = "1.0.0"
    depends_on = 42
    default_params = "not a dict"
    @staticmethod
    def run(**kwargs): pass
'''

FIXABLE_SKILL = '''
class QC:
    name = "qc"
    version = "1.0"
    depends_on = "scanpy"
    @staticmethod
    def run(**kwargs): pass
'''
