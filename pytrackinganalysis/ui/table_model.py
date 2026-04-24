"""Tiny ``pandas.DataFrame`` → ``QAbstractTableModel`` adapter.

Handles ``DisplayRole``, ``BackgroundRole`` via a user-supplied
``row_color(row_index)`` callback, and header labels from the DataFrame.
"""

from __future__ import annotations

from typing import Any, Callable

import pandas as pd
from PyQt6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PyQt6.QtGui import QBrush, QColor


class DataFrameModel(QAbstractTableModel):
    """Read-only model backed by a pandas DataFrame."""

    def __init__(
        self,
        df: pd.DataFrame | None = None,
        row_color: Callable[[int], QColor | None] | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._df = df if df is not None else pd.DataFrame()
        self._row_color = row_color

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_dataframe(self, df: pd.DataFrame) -> None:
        self.beginResetModel()
        self._df = df if df is not None else pd.DataFrame()
        self.endResetModel()

    def set_row_color(self, row_color: Callable[[int], QColor | None] | None) -> None:
        self._row_color = row_color
        # Trigger a background-role refresh without rebuilding the whole model.
        top = self.index(0, 0)
        bottom = self.index(max(self.rowCount() - 1, 0), max(self.columnCount() - 1, 0))
        self.dataChanged.emit(top, bottom, [Qt.ItemDataRole.BackgroundRole])

    def dataframe(self) -> pd.DataFrame:
        return self._df

    # ------------------------------------------------------------------
    # Qt model API
    # ------------------------------------------------------------------

    def rowCount(self, _parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return len(self._df.index)

    def columnCount(self, _parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return len(self._df.columns)

    def headerData(  # noqa: N802
        self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole
    ) -> Any:
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            if 0 <= section < len(self._df.columns):
                return str(self._df.columns[section])
            return None
        if 0 <= section < len(self._df.index):
            return str(self._df.index[section])
        return None

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid():
            return None
        row, col = index.row(), index.column()
        if not (0 <= row < len(self._df.index) and 0 <= col < len(self._df.columns)):
            return None
        if role == Qt.ItemDataRole.DisplayRole:
            value = self._df.iat[row, col]
            if isinstance(value, float):
                if pd.isna(value):
                    return ""
                return f"{value:.3f}"
            return str(value)
        if role == Qt.ItemDataRole.BackgroundRole and self._row_color is not None:
            col_ = self._row_color(row)
            if col_ is not None:
                return QBrush(col_)
        if role == Qt.ItemDataRole.TextAlignmentRole:
            value = self._df.iat[row, col]
            if isinstance(value, (int, float)) and not pd.isna(value):
                return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return None
