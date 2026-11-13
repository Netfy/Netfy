"""Modelo Dixon-Coles (Poisson bivariado con corrección de marcadores bajos y decaimiento temporal).

Goles esperados:
    λ_local     = ataque[local]     * defensa[visitante] * ventaja_local
    μ_visitante = ataque[visitante] * defensa[local]
`defensa` mide cuánto concede un equipo (mayor = peor defensa).
Se ajusta por máxima verosimilitud ponderada (actualizaciones iterativas en forma cerrada) y
`rho` (dependencia en 0-0, 1-0, 0-1, 1-1) por búsqueda en rejilla. Solo usa la librería estándar.
"""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import date

from .data import Partido

MAX_GOLES = 10


def _poisson(k: int, lam: float) -> float:
    return math.exp(-lam) * lam ** k / math.factorial(k)


def _tau(x: int, y: int, lam: float, mu: float, rho: float) -> float:
    if x == 0 and y == 0:
        return 1 - lam * mu * rho
    if x == 0 and y == 1:
        return 1 + lam * rho
    if x == 1 and y == 0:
        return 1 + mu * rho
    if x == 1 and y == 1:
        return 1 - rho
    return 1.0


class DixonColes:
    def __init__(self, vida_media_dias: float = 240.0, previa_partidos: float = 4.0,
                 iteraciones: int = 200):
        self.xi = math.log(2) / vida_media_dias if vida_media_dias > 0 else 0.0
        self.previa = previa_partidos  # pseudo-partidos "de media" para estabilizar equipos con pocos datos
        self.iteraciones = iteraciones
        self.ataque: dict[str, float] = {}
        self.defensa: dict[str, float] = {}
        self.ventaja_local = 1.3
        self.rho = 0.0
        self.media_goles = 1.35
        self.n_partidos = 0
        self.fecha_ref: date | None = None

    # ------------------------------------------------------------------ ajuste
    def ajustar(self, partidos: list[Partido], hasta: date | None = None) -> "DixonColes":
        jugados = [p for p in partidos if p.jugado and (hasta is None or p.fecha < hasta)]
        if len(jugados) < 20:
            raise ValueError(f"Datos insuficientes para ajustar el modelo ({len(jugados)} partidos).")
        ref = hasta or max(p.fecha for p in jugados)
        self.fecha_ref = ref
        self.n_partidos = len(jugados)
        datos = [(p.local, p.visitante, p.goles_local, p.goles_visitante,
                  math.exp(-self.xi * max(0, (ref - p.fecha).days))) for p in jugados]

        equipos = sorted({d[0] for d in datos} | {d[1] for d in datos})
        sw = sum(d[4] for d in datos)
        m_loc = sum(d[2] * d[4] for d in datos) / sw
        m_vis = sum(d[3] * d[4] for d in datos) / sw
        self.media_goles = (m_loc + m_vis) / 2
        a = {e: 1.0 for e in equipos}
        b = {e: self.media_goles for e in equipos}
        g = m_loc / max(m_vis, 1e-6)
        k = self.previa

        for _ in range(self.iteraciones):
            num, den = defaultdict(float), defaultdict(float)
            for loc, vis, gl, gv, w in datos:
                num[loc] += w * gl; den[loc] += w * b[vis] * g
                num[vis] += w * gv; den[vis] += w * b[loc]
            # previa: k partidos contra un rival medio marcando la media
            nuevo_a = {e: (num[e] + k * self.media_goles) / (den[e] + k * self.media_goles) for e in equipos}
            ma = sum(nuevo_a.values()) / len(equipos)
            nuevo_a = {e: v / ma for e, v in nuevo_a.items()}

            num, den = defaultdict(float), defaultdict(float)
            for loc, vis, gl, gv, w in datos:
                num[vis] += w * gl; den[vis] += w * nuevo_a[loc] * g
                num[loc] += w * gv; den[loc] += w * nuevo_a[vis]
            nuevo_b = {e: (num[e] + k * self.media_goles) / (den[e] + k) for e in equipos}

            ng = sum(w * gl for _, _, gl, _, w in datos) / sum(
                w * nuevo_a[l] * nuevo_b[v] for l, v, _, _, w in datos)
            cambio = max(abs(nuevo_a[e] - a[e]) for e in equipos) + abs(ng - g)
            a, b, g = nuevo_a, nuevo_b, ng
            if cambio < 1e-7:
                break

        self.ataque, self.defensa, self.ventaja_local = a, b, g
        self.rho = self._ajustar_rho(datos)
        return self

    def _ajustar_rho(self, datos) -> float:
        bajos = [(self.ataque[l] * self.defensa[v] * self.ventaja_local, self.ataque[v] * self.defensa[l], x, y, w)
                 for l, v, x, y, w in datos if x <= 1 and y <= 1]
        mejor, mejor_ll = 0.0, -math.inf
        for i in range(-25, 26):
            rho = i / 100
            ll = 0.0
            for lam, mu, x, y, w in bajos:
                t = _tau(x, y, lam, mu, rho)
                if t <= 0:
                    ll = -math.inf; break
                ll += w * math.log(t)
            if ll > mejor_ll:
                mejor, mejor_ll = rho, ll
        return mejor

    # -------------------------------------------------------------- predicción
    def conoce(self, equipo: str) -> bool:
        return equipo in self.ataque

    def goles_esperados(self, local: str, visitante: str) -> tuple[float, float]:
        a_l = self.ataque.get(local, 0.85)  # equipo desconocido (p.ej. recién ascendido): algo por debajo de la media
        a_v = self.ataque.get(visitante, 0.85)
        d_l = self.defensa.get(local, self.media_goles * 1.15)
        d_v = self.defensa.get(visitante, self.media_goles * 1.15)
        return a_l * d_v * self.ventaja_local, a_v * d_l

    def matriz(self, local: str, visitante: str) -> list[list[float]]:
        lam, mu = self.goles_esperados(local, visitante)
        pl = [_poisson(i, lam) for i in range(MAX_GOLES + 1)]
        pv = [_poisson(j, mu) for j in range(MAX_GOLES + 1)]
        m = [[pl[i] * pv[j] * _tau(i, j, lam, mu, self.rho) for j in range(MAX_GOLES + 1)]
             for i in range(MAX_GOLES + 1)]
        total = sum(map(sum, m))
        return [[v / total for v in fila] for fila in m]

    def ranking(self) -> list[tuple[str, float, float, float]]:
        """(equipo, ataque, defensa, fuerza neta) ordenado por fuerza."""
        filas = [(e, self.ataque[e], self.defensa[e] / self.media_goles,
                  math.log(self.ataque[e]) - math.log(self.defensa[e] / self.media_goles)) for e in self.ataque]
        return sorted(filas, key=lambda r: -r[3])
