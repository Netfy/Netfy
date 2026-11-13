"""Probabilidades de mercados de apuestas a partir de la matriz de marcadores."""
from __future__ import annotations


def mercados(m: list[list[float]]) -> dict[str, float]:
    n = len(m)
    p1 = sum(m[i][j] for i in range(n) for j in range(n) if i > j)
    px = sum(m[i][i] for i in range(n))
    p2 = 1 - p1 - px
    res = {"1": p1, "X": px, "2": p2, "1X": p1 + px, "X2": px + p2, "12": p1 + p2}
    for linea in (0.5, 1.5, 2.5, 3.5, 4.5):
        mas = sum(m[i][j] for i in range(n) for j in range(n) if i + j > linea)
        res[f"Más {linea}"] = mas
        res[f"Menos {linea}"] = 1 - mas
    btts = sum(m[i][j] for i in range(1, n) for j in range(1, n))
    res["Ambos marcan: Sí"] = btts
    res["Ambos marcan: No"] = 1 - btts
    res["Local marca"] = 1 - sum(m[0][j] for j in range(n))
    res["Visitante marca"] = 1 - sum(m[i][0] for i in range(n))
    return res


def marcadores_probables(m: list[list[float]], top: int = 5) -> list[tuple[str, float]]:
    n = len(m)
    todos = [(f"{i}-{j}", m[i][j]) for i in range(n) for j in range(n)]
    return sorted(todos, key=lambda t: -t[1])[:top]


def cuota_justa(p: float) -> float:
    return 1 / p if p > 0 else float("inf")
