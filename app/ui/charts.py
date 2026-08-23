from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QCursor, QPainter
from PySide6.QtWidgets import QLabel, QToolTip


def _chart_supported() -> bool:
    try:
        from PySide6 import QtCharts  # noqa: F401

        return True
    except Exception:
        return False


def bar_chart(
    categories: list[str],
    series: dict[str, list[float]],
    title: str,
    height: int = 340,
):
    if not _chart_supported():
        return QLabel("图表组件不可用")
    from PySide6.QtCharts import QChart, QChartView

    chart = QChart()
    chart.setAnimationOptions(QChart.NoAnimation)
    chart.setTitle(title)
    chart.setBackgroundVisible(False)
    chart.legend().setVisible(True)
    chart.legend().setAlignment(Qt.AlignBottom)
    view = QChartView(chart)
    view.setRenderHint(QPainter.Antialiasing)
    view.setMinimumHeight(height)
    chart.setMinimumHeight(height - 40)
    _fill_bar_chart(chart, categories, series)
    return view


def update_bar_chart(view, categories: list[str], series: dict[str, list[float]], title: str) -> None:
    if not _chart_supported() or not hasattr(view, "chart"):
        return
    chart = view.chart()
    chart.setTitle(title)
    chart.removeAllSeries()
    for axis in list(chart.axes()):
        chart.removeAxis(axis)
    _fill_bar_chart(chart, categories, series)


def _fill_bar_chart(chart, categories: list[str], series: dict[str, list[float]]) -> None:
    from PySide6.QtCore import Qt as _Qt
    from PySide6.QtCharts import (
        QBarCategoryAxis,
        QBarSeries,
        QBarSet,
        QValueAxis,
    )

    axis_x = QBarCategoryAxis()
    axis_x.append(categories)
    chart.addAxis(axis_x, _Qt.AlignBottom)
    axis_y = QValueAxis()
    chart.addAxis(axis_y, _Qt.AlignLeft)

    bar_series = QBarSeries()
    for name, values in series.items():
        bar_set = QBarSet(name)
        for value in values:
            bar_set.append(value)
        bar_set.hovered.connect(
            lambda status, index, bar_set=bar_set: _bar_tooltip(
                status, index, bar_set, categories
            )
        )
        bar_series.append(bar_set)
    chart.addSeries(bar_series)
    bar_series.attachAxis(axis_x)
    bar_series.attachAxis(axis_y)


def pie_chart(
    labels: list[str],
    values: list[float],
    title: str,
    height: int = 300,
):
    if not _chart_supported():
        return QLabel("图表组件不可用")
    from PySide6.QtCharts import QChart, QChartView

    chart = QChart()
    chart.setAnimationOptions(QChart.NoAnimation)
    chart.setTitle(title)
    chart.setBackgroundVisible(False)
    chart.legend().setVisible(True)
    chart.legend().setAlignment(Qt.AlignRight)
    view = QChartView(chart)
    view.setRenderHint(QPainter.Antialiasing)
    view.setMinimumHeight(height)
    chart.setMinimumHeight(height - 40)
    _fill_pie_chart(chart, labels, values)
    return view


def update_pie_chart(view, labels: list[str], values: list[float], title: str) -> None:
    if not _chart_supported() or not hasattr(view, "chart"):
        return
    chart = view.chart()
    chart.setTitle(title)
    chart.removeAllSeries()
    _fill_pie_chart(chart, labels, values)


def _fill_pie_chart(chart, labels: list[str], values: list[float]) -> None:
    from PySide6.QtCharts import QPieSeries

    series = QPieSeries()
    total = sum(values) or 1.0
    for label, value in zip(labels, values):
        if value <= 0:
            continue
        piece = series.append(f"{label}\n{value / total * 100:.1f}%", value)
        piece.hovered.connect(
            lambda state, piece=piece, label=label, value=value: _pie_tooltip(
                state, piece, label, value
            )
        )
    chart.addSeries(series)


def _bar_tooltip(status: bool, index: int, bar_set, categories: list[str]) -> None:
    if not status or index < 0 or index >= len(categories):
        return
    QToolTip.showText(
        QCursor.pos(),
        f"{bar_set.label()} {categories[index]}: {bar_set.at(index):,.2f}",
    )


def _pie_tooltip(state: bool, piece, label: str, value: float) -> None:
    if not state:
        return
    QToolTip.showText(QCursor.pos(), f"{label}: {value:,.2f}")
