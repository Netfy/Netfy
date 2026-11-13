"""Descarga y normalización de datos de football-data.co.uk (resultados + cuotas)."""
from __future__ import annotations

import csv
import io
import os
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime

BASE = "https://www.football-data.co.uk"

# Ligas principales (formato mmz4281/<temporada>/<código>.csv)
LIGAS = {
    "E0": "Inglaterra - Premier League", "E1": "Inglaterra - Championship",
    "E2": "Inglaterra - League One", "E3": "Inglaterra - League Two",
    "SC0": "Escocia - Premiership", "D1": "Alemania - Bundesliga",
    "D2": "Alemania - 2. Bundesliga", "I1": "Italia - Serie A", "I2": "Italia - Serie B",
    "SP1": "España - LaLiga", "SP2": "España - Segunda", "F1": "Francia - Ligue 1",
    "F2": "Francia - Ligue 2", "N1": "Países Bajos - Eredivisie", "B1": "Bélgica - Pro League",
    "P1": "Portugal - Primeira Liga", "T1": "Turquía - Süper Lig", "G1": "Grecia - Super League",
}
# Ligas "extra" (un único CSV con todas las temporadas: new/<código>.csv)
LIGAS_EXTRA = {
    "ARG": "Argentina - Liga Profesional", "BRA": "Brasil - Serie A", "MEX": "México - Liga MX",
    "USA": "EE.UU. - MLS", "CHN": "China - Super League", "JPN": "Japón - J-League",
    "NOR": "Noruega - Eliteserien", "SWE": "Suecia - Allsvenskan", "FIN": "Finlandia - Veikkausliiga",
    "IRL": "Irlanda - Premier Division", "DNK": "Dinamarca - Superliga", "AUT": "Austria - Bundesliga",
    "SWZ": "Suiza - Super League", "POL": "Polonia - Ekstraklasa", "ROU": "Rumanía - Liga I",
    "RUS": "Rusia - Premier League",
}

PAIS_A_CODIGO = {"Argentina": "ARG", "Brazil": "BRA", "Mexico": "MEX", "USA": "USA", "China": "CHN",
                 "Japan": "JPN", "Norway": "NOR", "Sweden": "SWE", "Finland": "FIN", "Ireland": "IRL",
                 "Denmark": "DNK", "Austria": "AUT", "Switzerland": "SWZ", "Poland": "POL",
                 "Romania": "ROU", "Russia": "RUS"}

# Columnas de cuotas candidatas, por orden de preferencia (cierre de Pinnacle > media > Bet365)
CUOTAS_1X2 = [("PSCH", "PSCD", "PSCA"), ("PSH", "PSD", "PSA"), ("AvgCH", "AvgCD", "AvgCA"),
              ("AvgH", "AvgD", "AvgA"), ("B365CH", "B365CD", "B365CA"), ("B365H", "B365D", "B365A"),
              ("PH", "PD", "PA")]
CUOTAS_OU25 = [("PC>2.5", "PC<2.5"), ("P>2.5", "P<2.5"), ("AvgC>2.5", "AvgC<2.5"),
               ("Avg>2.5", "Avg<2.5"), ("B365C>2.5", "B365C<2.5"), ("B365>2.5", "B365<2.5")]


@dataclass
class Partido:
    fecha: date
    liga: str
    local: str
    visitante: str
    goles_local: int | None = None
    goles_visitante: int | None = None
    cuotas_1x2: tuple[float, float, float] | None = None
    cuotas_ou25: tuple[float, float] | None = None  # (más de 2.5, menos de 2.5)
    extra: dict = field(default_factory=dict)

    @property
    def jugado(self) -> bool:
        return self.goles_local is not None and self.goles_visitante is not None


def _fecha(txt: str) -> date | None:
    txt = (txt or "").strip()
    for fmt in ("%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d"):
        try:
            return datetime.strptime(txt, fmt).date()
        except ValueError:
            pass
    return None


def _num(txt) -> float | None:
    try:
        v = float(str(txt).strip())
        return v if v > 1.0 else None
    except (TypeError, ValueError):
        return None


def _int(txt) -> int | None:
    try:
        return int(float(str(txt).strip()))
    except (TypeError, ValueError):
        return None


def _primera(fila: dict, grupos):
    for g in grupos:
        vals = tuple(_num(fila.get(c)) for c in g)
        if all(vals):
            return vals
    return None


def parsear_csv(texto: str, liga: str | None = None) -> list[Partido]:
    """Convierte un CSV de football-data (formato principal, extra o fixtures) en Partidos."""
    texto = texto.lstrip("﻿")
    partidos = []
    for fila in csv.DictReader(io.StringIO(texto)):
        local = (fila.get("HomeTeam") or fila.get("Home") or "").strip()
        visit = (fila.get("AwayTeam") or fila.get("Away") or "").strip()
        f = _fecha(fila.get("Date", ""))
        if not local or not visit or f is None:
            continue
        gl = _int(fila.get("FTHG", fila.get("HG")))
        gv = _int(fila.get("FTAG", fila.get("AG")))
        partidos.append(Partido(
            fecha=f,
            liga=(fila.get("Div") or PAIS_A_CODIGO.get((fila.get("Country") or "").strip())
                  or liga or "?").strip(),
            local=local, visitante=visit, goles_local=gl, goles_visitante=gv,
            cuotas_1x2=_primera(fila, CUOTAS_1X2),
            cuotas_ou25=_primera(fila, CUOTAS_OU25),
            extra={"hora": fila.get("Time", ""), "temporada": fila.get("Season", "")},
        ))
    partidos.sort(key=lambda p: p.fecha)
    return partidos


def codigo_temporada(anio_inicio: int) -> str:
    """2025 -> '2526'."""
    return f"{anio_inicio % 100:02d}{(anio_inicio + 1) % 100:02d}"


def temporada_actual(hoy: date | None = None) -> int:
    hoy = hoy or date.today()
    return hoy.year if hoy.month >= 7 else hoy.year - 1


def _descargar(url: str, destino: str, refrescar: bool) -> str:
    if os.path.exists(destino) and not refrescar:
        with open(destino, encoding="latin-1") as fh:
            return fh.read()
    req = urllib.request.Request(url, headers={"User-Agent": "futbol-ia/0.1"})
    with urllib.request.urlopen(req, timeout=60) as r:
        crudo = r.read()
    texto = crudo.decode("utf-8-sig", errors="replace") if crudo[:3] == b"\xef\xbb\xbf" else crudo.decode("latin-1")
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    with open(destino, "w", encoding="latin-1", errors="replace") as fh:
        fh.write(texto)
    return texto


def cargar_liga(liga: str, temporadas: int = 3, carpeta: str = "datos",
                refrescar_actual: bool = True) -> list[Partido]:
    """Descarga (con caché) las últimas `temporadas` temporadas de una liga."""
    liga = liga.upper()
    if liga in LIGAS_EXTRA:
        texto = _descargar(f"{BASE}/new/{liga}.csv", os.path.join(carpeta, f"{liga}.csv"), refrescar_actual)
        partidos = parsear_csv(texto, liga)
        if partidos:
            limite = partidos[-1].fecha.replace(year=partidos[-1].fecha.year - temporadas)
            partidos = [p for p in partidos if p.fecha >= limite]
        return partidos
    if liga not in LIGAS:
        raise ValueError(f"Liga desconocida: {liga}. Usa `futbol-ia ligas` para ver las disponibles.")
    actual = temporada_actual()
    partidos: list[Partido] = []
    for anio in range(actual - temporadas + 1, actual + 1):
        cod = codigo_temporada(anio)
        try:
            texto = _descargar(f"{BASE}/mmz4281/{cod}/{liga}.csv",
                               os.path.join(carpeta, cod, f"{liga}.csv"),
                               refrescar_actual and anio == actual)
        except Exception as e:  # temporada aún no publicada, etc.
            print(f"  aviso: no se pudo obtener {liga} {cod}: {e}")
            continue
        partidos.extend(parsear_csv(texto, liga))
    partidos.sort(key=lambda p: p.fecha)
    return partidos


def cargar_proximos(carpeta: str = "datos") -> list[Partido]:
    """Próximos partidos (con cuotas) de las ligas principales y extra."""
    res = []
    for nombre in ("fixtures.csv", "new_league_fixtures.csv"):
        try:
            res += parsear_csv(_descargar(f"{BASE}/{nombre}", os.path.join(carpeta, nombre), True))
        except Exception as e:
            print(f"  aviso: no se pudo obtener {nombre}: {e}")
    return [p for p in res if not p.jugado]


def cargar_archivo(ruta: str, liga: str | None = None) -> list[Partido]:
    with open(ruta, encoding="latin-1") as fh:
        return parsear_csv(fh.read(), liga)
