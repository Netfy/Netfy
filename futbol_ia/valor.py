"""Detección de apuestas de valor y gestión de banca (Kelly fraccionado)."""
from __future__ import annotations

from dataclasses import dataclass


def quitar_margen(cuotas) -> list[float]:
    """Probabilidades implícitas sin el margen de la casa (normalización proporcional)."""
    inv = [1 / c for c in cuotas]
    s = sum(inv)
    return [x / s for x in inv]


def margen(cuotas) -> float:
    return sum(1 / c for c in cuotas) - 1


def kelly(p: float, cuota: float, fraccion: float = 0.25, maximo: float = 0.05) -> float:
    """Fracción de banca recomendada. Kelly completo es demasiado agresivo: se usa 1/4 y tope del 5 %."""
    b = cuota - 1
    if b <= 0:
        return 0.0
    f = (p * b - (1 - p)) / b
    return max(0.0, min(f * fraccion, maximo))


@dataclass
class Apuesta:
    mercado: str
    seleccion: str
    prob: float
    cuota: float
    prob_mercado: float

    @property
    def valor(self) -> float:  # valor esperado por unidad apostada
        return self.prob * self.cuota - 1


def buscar_valor(probs: dict[str, float], cuotas_1x2=None, cuotas_ou25=None, peso_modelo: float = 0.5,
                 valor_minimo: float = 0.05, cuota_max: float = 6.0) -> list[Apuesta]:
    """Compara el modelo con las cuotas. La probabilidad final mezcla modelo y mercado
    (el mercado de cierre es muy eficiente: mezclarlo reduce falsas señales)."""
    res = []
    grupos = []
    if cuotas_1x2:
        grupos.append(("1X2", ["1", "X", "2"], cuotas_1x2))
    if cuotas_ou25:
        grupos.append(("Goles 2.5", ["Más 2.5", "Menos 2.5"], cuotas_ou25))
    for nombre, sels, cuotas in grupos:
        justas = quitar_margen(cuotas)
        for sel, c, pm in zip(sels, cuotas, justas):
            p = peso_modelo * probs[sel] + (1 - peso_modelo) * pm
            a = Apuesta(nombre, sel, p, c, pm)
            if a.valor >= valor_minimo and c <= cuota_max:
                res.append(a)
    return sorted(res, key=lambda a: -a.valor)
