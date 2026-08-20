"""Help topic registry — ids map to packaged markdown under ``content/``."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HelpTopic:
    """One help page shown in a dialog or the help browser."""

    id: str
    title: str
    summary: str
    filename: str

    @property
    def path_name(self) -> str:
        return self.filename


# Order is the sidebar order in HelpBrowser.
TOPICS: tuple[HelpTopic, ...] = (
    HelpTopic(
        "getting_started",
        "Getting started",
        "How to set up a project and run your first analysis.",
        "getting_started.md",
    ),
    HelpTopic(
        "project_structure",
        "Project directory layout",
        "Required folders, naming rules, and batch parent layout.",
        "project_structure.md",
    ),
    HelpTopic(
        "config_overview",
        "Config file overview",
        "What belongs in tracking_config.yaml and how to create one.",
        "config_overview.md",
    ),
    HelpTopic(
        "config_global",
        "Global settings",
        "Tracking type, rig, design factors, and optional overrides.",
        "config_global.md",
    ),
    HelpTopic(
        "config_regions",
        "Tracking and counting regions",
        "How regions map treatments and DTrack aliases.",
        "config_regions.md",
    ),
    HelpTopic(
        "hub_workflow",
        "Analysis Hub workflow",
        "Load, analyze, plots, stats, and reports in the Hub.",
        "hub_workflow.md",
    ),
    HelpTopic(
        "batch_experiments",
        "Batch experiments",
        "Run a batch script across every experiment subfolder.",
        "batch_experiments.md",
    ),
    HelpTopic(
        "batch_tools",
        "Batch tools",
        "Convert layouts, rename folders, copy YAML, combine CSVs.",
        "batch_tools.md",
    ),
    HelpTopic(
        "scripts_overview",
        "Scripts and Script Editor",
        "Saved recipes, the visual editor, and the special batch script.",
        "scripts_overview.md",
    ),
    HelpTopic(
        "ai_summary",
        "AI summary",
        "An optional AI-written one-page summary embedded in the report.",
        "ai_summary.md",
    ),
    HelpTopic(
        "qc_overview",
        "QC Viewer",
        "Data-quality table and per-tracker plots.",
        "qc_overview.md",
    ),
    HelpTopic(
        "outputs",
        "Outputs",
        "What appears under analysis/ and qc/.",
        "outputs.md",
    ),
)

_BY_ID = {t.id: t for t in TOPICS}


def get_topic(topic_id: str) -> HelpTopic:
    try:
        return _BY_ID[topic_id]
    except KeyError as exc:
        known = ", ".join(t.id for t in TOPICS)
        raise KeyError(f"Unknown help topic {topic_id!r}. Known: {known}") from exc


def topic_ids() -> list[str]:
    return [t.id for t in TOPICS]
