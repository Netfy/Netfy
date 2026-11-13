"""Genera la app (PWA estática): copia la interfaz y escribe `datos.json` con modelos, partidos y backtests.

La app del móvil calcula todo en el navegador a partir de los parámetros del modelo, así que no
necesita servidor: basta con publicar la carpeta (GitHub Pages lo hace solo cada día).
"""
from __future__ import annotations

import json
import os
import shutil
import time
from datetime import date, datetime, timedelta, timezone

from . import data
from .backtest import backtest
from .modelo import DixonColes

ESTATICO = os.path.join(os.path.dirname(__file__), "static")


def _modelo_json(m: DixonColes) -> dict:
    return {"ventaja_local": round(m.ventaja_local, 5), "rho": m.rho, "media_goles": round(m.media_goles, 5),
            "n_partidos": m.n_partidos,
            "ataque": {e: round(v, 5) for e, v in m.ataque.items()},
            "defensa": {e: round(v, 5) for e, v in m.defensa.items()}}


def _backtest_json(partidos, vida_media) -> dict | None:
    if len(partidos) < 200:
        return None
    desde = partidos[0].fecha + (partidos[-1].fecha - partidos[0].fecha) * 2 // 3
    r = backtest(partidos, desde, reajuste_dias=14, vida_media_dias=vida_media)
    banca, serie = r.banca_inicial, [[desde.isoformat(), r.banca_inicial]]
    for d in r.detalle:
        banca += d[8]
        serie.append([d[0].isoformat(), round(banca, 2)])
    if len(serie) > 300:  # aligerar la gráfica
        paso = len(serie) / 300
        serie = [serie[int(i * paso)] for i in range(300)] + [serie[-1]]
    return {"desde": desde.isoformat(), "n_eval": r.n_eval, "apuestas": r.apuestas, "ganadas": r.ganadas,
            "apostado": round(r.apostado, 2), "beneficio": round(r.beneficio, 2), "roi": round(r.roi, 4),
            "banca_inicial": r.banca_inicial, "banca": round(r.banca, 2), "max_caida": round(r.max_caida, 4),
            "logloss": [round(r.logloss_modelo, 4), round(r.logloss_mercado, 4)], "serie": serie,
            "detalle": [[d[0].isoformat(), *d[1:]] for d in r.detalle[-40:]]}


def exportar(salida: str = "sitio", ligas: list[str] | None = None, carpeta: str = "datos", temporadas: int = 3,
             vida_media: float = 240.0, dias: int = 10, con_backtest: bool = True, log=print) -> str:
    os.makedirs(salida, exist_ok=True)
    for f in os.listdir(ESTATICO):
        shutil.copy2(os.path.join(ESTATICO, f), os.path.join(salida, f))

    todas = list(data.LIGAS) + list(data.LIGAS_EXTRA)
    ligas = [l.upper() for l in ligas] if ligas else todas
    hasta = date.today() + timedelta(days=dias)
    proximos = [p for p in data.cargar_proximos(carpeta)
                if p.liga in ligas and date.today() - timedelta(days=1) <= p.fecha <= hasta]

    res = {"generado": datetime.now(timezone.utc).isoformat(timespec="seconds"), "ligas": {}, "partidos": [],
           "errores": {}}
    for liga in ligas:
        t = time.time()
        try:
            hist = data.cargar_liga(liga, temporadas, carpeta)
            modelo = DixonColes(vida_media_dias=vida_media).ajustar(hist)
        except Exception as e:
            res["errores"][liga] = str(e)
            log(f"  {liga}: error — {e}")
            continue
        info = {"nombre": data.LIGAS.get(liga) or data.LIGAS_EXTRA.get(liga),
                "region": "Europa" if liga in data.LIGAS else "Resto del mundo",
                "modelo": _modelo_json(modelo), "backtest": None}
        if con_backtest:
            try:
                info["backtest"] = _backtest_json(hist, vida_media)
            except Exception as e:
                log(f"  {liga}: backtest falló — {e}")
        res["ligas"][liga] = info
        log(f"  {liga}: {modelo.n_partidos} partidos ({time.time() - t:.1f}s)")

    for p in sorted(proximos, key=lambda p: (p.fecha, p.extra.get("hora", ""))):
        if p.liga in res["ligas"]:
            res["partidos"].append({"fecha": p.fecha.isoformat(), "hora": (p.extra.get("hora") or "").strip(),
                                    "liga": p.liga, "local": p.local, "visitante": p.visitante,
                                    "cuotas_1x2": p.cuotas_1x2, "cuotas_ou25": p.cuotas_ou25})
    with open(os.path.join(salida, "datos.json"), "w", encoding="utf-8") as fh:
        json.dump(res, fh, ensure_ascii=False, separators=(",", ":"))
    log(f"App generada en {salida}/ — {len(res['ligas'])} ligas, {len(res['partidos'])} próximos partidos")
    return salida
