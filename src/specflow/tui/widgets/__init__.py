"""TUI widgets for SpecFlow."""

from specflow.tui.widgets.agents import AgentsPanel
from specflow.tui.widgets.spec_editor import SpecEditor
from specflow.tui.widgets.specs import SpecsPanel
from specflow.tui.widgets.swimlanes import (
    SwimlaneBoard,
    SwimlaneScreen,
    SwimLane,
    TaskCard,
    TaskDetailModal,
)

__all__ = [
    "AgentsPanel",
    "SpecEditor",
    "SpecsPanel",
    "SwimlaneBoard",
    "SwimlaneScreen",
    "SwimLane",
    "TaskCard",
    "TaskDetailModal",
]
