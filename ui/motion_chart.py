"""График движения планеты: эклиптическая долгота и элонгация (matplotlib в Qt)."""
from __future__ import annotations

import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

from astronomy.planets import MotionSeries


class MotionChart(FigureCanvasQTAgg):
    def __init__(self) -> None:
        self.figure = Figure(figsize=(8, 3), tight_layout=True)
        super().__init__(self.figure)
        self.setMinimumHeight(180)
        self.set_message("Нет данных")

    def set_message(self, text: str) -> None:
        self.figure.clear()
        ax = self.figure.add_subplot(111)
        ax.axis("off")
        ax.text(0.5, 0.5, text, ha="center", va="center", wrap=True)
        self.draw_idle()

    def set_series(self, series: MotionSeries, tz) -> None:
        self.figure.clear()
        ax1 = self.figure.add_subplot(111)
        ax2 = ax1.twinx()
        local = [t.astimezone(tz).replace(tzinfo=None) for t in series.times]
        lon = np.asarray(series.longitude)
        retro = np.asarray(series.retrograde, dtype=bool)
        ax1.plot(local, lon, color="#4a78c2", lw=1.4, label="Долгота (эклиптическая)")
        if retro.any():
            ax1.plot(local, np.where(retro, lon, np.nan), color="#d9534f", lw=2.6, label="Попятное движение")
        ax2.plot(local, series.elongation, color="#999999", lw=1.0, ls="--", label="Элонгация")
        ax1.set_ylabel("Эклиптическая долгота, °")
        ax2.set_ylabel("Элонгация от Солнца, °")
        ax1.set_title(f"{series.name}: видимое движение на фоне звёзд")
        ax1.grid(alpha=0.25)
        handles = ax1.get_legend_handles_labels()
        extra = ax2.get_legend_handles_labels()
        ax1.legend(handles[0] + extra[0], handles[1] + extra[1], loc="upper left", fontsize=8)
        self.figure.autofmt_xdate()
        self.draw_idle()
