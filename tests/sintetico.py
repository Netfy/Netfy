"""Genera una liga sintética con fuerzas conocidas, en formato CSV de football-data."""
import math
import random
from datetime import date, timedelta


def _poisson(rng, lam):
    l, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= l:
            return k
        k += 1


def generar(n_equipos=20, temporadas=3, semilla=1, margen=0.05):
    rng = random.Random(semilla)
    equipos = [f"Equipo{i:02d}" for i in range(n_equipos)]
    fuerza = {e: 0.5 - i / n_equipos for i, e in enumerate(equipos)}  # Equipo00 el mejor
    filas = ["Div,Date,HomeTeam,AwayTeam,FTHG,FTAG,FTR,B365H,B365D,B365A,B365>2.5,B365<2.5"]
    inicio, n = date(2023, 8, 1), 0
    from futbol_ia.mercados import mercados
    from futbol_ia.modelo import _poisson as pois
    for _ in range(temporadas):
        for loc in equipos:
            for vis in equipos:
                if loc == vis:
                    continue
                lam = 1.35 * math.exp(fuerza[loc] - fuerza[vis]) * 1.15
                mu = 1.35 * math.exp(fuerza[vis] - fuerza[loc]) / 1.15
                gl, gv = _poisson(rng, lam), _poisson(rng, mu)
                m = [[pois(i, lam) * pois(j, mu) for j in range(11)] for i in range(11)]
                pr = mercados(m)
                c = [round(1 / (pr[s] * (1 + margen)), 2) for s in ("1", "X", "2", "Más 2.5", "Menos 2.5")]
                r = "H" if gl > gv else "D" if gl == gv else "A"
                dia = inicio + timedelta(days=n // 5); n += 1
                filas.append(f"SP1,{dia:%d/%m/%Y},{loc},{vis},{gl},{gv},{r},{c[0]},{c[1]},{c[2]},{c[3]},{c[4]}")
    return "\n".join(filas), fuerza
