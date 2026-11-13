"""Backtest walk-forward: el modelo solo ve partidos anteriores a cada jornada y apuesta a cuotas reales."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, timedelta

from .data import Partido
from .mercados import mercados
from .modelo import DixonColes
from .valor import buscar_valor, kelly, quitar_margen


@dataclass
class Resultado:
    apuestas: int = 0
    ganadas: int = 0
    apostado: float = 0.0
    beneficio: float = 0.0
    banca_inicial: float = 1000.0
    banca: float = 1000.0
    max_banca: float = 1000.0
    max_caida: float = 0.0
    logloss_modelo: float = 0.0
    logloss_mercado: float = 0.0
    brier_modelo: float = 0.0
    brier_mercado: float = 0.0
    n_eval: int = 0
    detalle: list = field(default_factory=list)

    @property
    def roi(self) -> float:
        return self.beneficio / self.apostado if self.apostado else 0.0


def _gana(sel: str, gl: int, gv: int) -> bool:
    return {"1": gl > gv, "X": gl == gv, "2": gl < gv,
            "Más 2.5": gl + gv > 2.5, "Menos 2.5": gl + gv < 2.5}[sel]


def backtest(partidos: list[Partido], desde: date, peso_modelo: float = 0.5, valor_minimo: float = 0.05,
             reajuste_dias: int = 7, staking: str = "kelly", **kw_modelo) -> Resultado:
    r = Resultado()
    prueba = [p for p in partidos if p.jugado and p.fecha >= desde]
    modelo, siguiente = None, None
    for p in prueba:
        if modelo is None or p.fecha >= siguiente:
            try:
                modelo = DixonColes(**kw_modelo).ajustar(partidos, hasta=p.fecha)
            except ValueError:
                continue
            siguiente = p.fecha + timedelta(days=reajuste_dias)
        probs = mercados(modelo.matriz(p.local, p.visitante))
        gl, gv = p.goles_local, p.goles_visitante
        real = "1" if gl > gv else "X" if gl == gv else "2"

        if p.cuotas_1x2:  # calidad de la predicción frente al mercado
            pm = dict(zip("1X2", quitar_margen(p.cuotas_1x2)))
            r.n_eval += 1
            r.logloss_modelo -= math.log(max(probs[real], 1e-12))
            r.logloss_mercado -= math.log(max(pm[real], 1e-12))
            r.brier_modelo += sum((probs[s] - (s == real)) ** 2 for s in "1X2")
            r.brier_mercado += sum((pm[s] - (s == real)) ** 2 for s in "1X2")

        for a in buscar_valor(probs, p.cuotas_1x2, p.cuotas_ou25, peso_modelo, valor_minimo)[:1]:
            stake = r.banca * kelly(a.prob, a.cuota) if staking == "kelly" else 10.0
            if stake <= 0:
                continue
            gano = _gana(a.seleccion, gl, gv)
            ganancia = stake * (a.cuota - 1) if gano else -stake
            r.apuestas += 1; r.ganadas += gano; r.apostado += stake
            r.beneficio += ganancia; r.banca += ganancia
            r.max_banca = max(r.max_banca, r.banca)
            r.max_caida = max(r.max_caida, 1 - r.banca / r.max_banca)
            r.detalle.append((p.fecha, p.local, p.visitante, a.seleccion, a.cuota, round(a.prob, 3),
                              round(stake, 2), f"{gl}-{gv}", round(ganancia, 2)))
    if r.n_eval:
        for k in ("logloss_modelo", "logloss_mercado", "brier_modelo", "brier_mercado"):
            setattr(r, k, getattr(r, k) / r.n_eval)
    return r
