"""Interfaz visual: servidor local con panel web (`futbol-ia web`)."""
from __future__ import annotations

import json
import os
import threading
import webbrowser
from datetime import date, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from . import data
from .backtest import backtest
from .mercados import marcadores_probables, mercados
from .modelo import DixonColes
from .valor import buscar_valor, kelly

ESTATICO = os.path.join(os.path.dirname(__file__), "static")


class Analizador:
    def __init__(self, carpeta="datos", temporadas=3, vida_media=240.0):
        self.carpeta, self.temporadas, self.vida_media = carpeta, temporadas, vida_media
        self._modelos: dict[str, DixonColes] = {}
        self._hist: dict[str, list] = {}
        self._lock = threading.Lock()

    def historial(self, liga: str) -> list:
        liga = liga.upper()
        with self._lock:
            if liga not in self._hist:
                self._hist[liga] = data.cargar_liga(liga, self.temporadas, self.carpeta)
            return self._hist[liga]

    def modelo(self, liga: str) -> DixonColes:
        liga = liga.upper()
        if liga not in self._modelos:
            m = DixonColes(vida_media_dias=self.vida_media).ajustar(self.historial(liga))
            self._modelos[liga] = m
        return self._modelos[liga]

    @staticmethod
    def analizar(modelo, local, visitante, c1x2=None, cou=None, peso=0.5, vmin=0.05) -> dict:
        m = modelo.matriz(local, visitante)
        pr = mercados(m)
        lam, mu = modelo.goles_esperados(local, visitante)
        desconocidos = [e for e in (local, visitante) if not modelo.conoce(e)]
        valor = [] if desconocidos else buscar_valor(pr, c1x2, cou, peso, vmin)
        return {
            "local": local, "visitante": visitante,
            "xg": [round(lam, 2), round(mu, 2)],
            "probs": {k: round(v, 4) for k, v in pr.items()},
            "marcadores": [[s, round(p, 4)] for s, p in marcadores_probables(m, 6)],
            "matriz": [[round(m[i][j], 4) for j in range(6)] for i in range(6)],
            "cuotas_1x2": c1x2, "cuotas_ou25": cou, "desconocidos": desconocidos,
            "valor": [{"mercado": a.mercado, "seleccion": a.seleccion, "cuota": a.cuota,
                       "prob": round(a.prob, 4), "prob_mercado": round(a.prob_mercado, 4),
                       "ve": round(a.valor, 4), "stake": round(kelly(a.prob, a.cuota), 4)} for a in valor],
        }

    # ------------------------------------------------------------------ API
    def api_ligas(self, q):
        return {"principales": data.LIGAS, "extra": data.LIGAS_EXTRA}

    def api_jornada(self, q):
        dias = int(q.get("dias", 7)); peso = float(q.get("peso", 0.5)); vmin = float(q.get("vmin", 0.05))
        hasta = date.today() + timedelta(days=dias)
        prox = [p for p in data.cargar_proximos(self.carpeta) if p.fecha <= hasta
                and (p.liga in data.LIGAS or p.liga in data.LIGAS_EXTRA)]
        if q.get("ligas"):
            filtro = {l.upper() for l in q["ligas"].split(",")}
            prox = [p for p in prox if p.liga in filtro]
        partidos, errores = [], {}
        for p in sorted(prox, key=lambda p: (p.fecha, p.extra.get("hora", ""), p.liga)):
            if p.liga in errores:
                continue
            try:
                mod = self.modelo(p.liga)
            except Exception as e:
                errores[p.liga] = str(e)
                continue
            a = self.analizar(mod, p.local, p.visitante, p.cuotas_1x2, p.cuotas_ou25, peso, vmin)
            a.update(fecha=p.fecha.isoformat(), hora=(p.extra.get("hora") or "").strip(), liga=p.liga,
                     liga_nombre=data.LIGAS.get(p.liga) or data.LIGAS_EXTRA.get(p.liga))
            partidos.append(a)
        return {"partidos": partidos, "errores": errores}

    def api_equipos(self, q):
        return {"equipos": sorted(self.modelo(q["liga"]).ataque)}

    def api_predecir(self, q):
        def nums(k, n):
            try:
                v = tuple(float(x) for x in q.get(k, "").split(","))
                return v if len(v) == n and all(x > 1 for x in v) else None
            except ValueError:
                return None
        return self.analizar(self.modelo(q["liga"]), q["local"], q["visitante"], nums("cuotas", 3),
                             nums("cuotas_goles", 2), float(q.get("peso", 0.5)), float(q.get("vmin", 0.05)))

    def api_ranking(self, q):
        m = self.modelo(q["liga"])
        return {"ventaja_local": round(m.ventaja_local, 3), "rho": m.rho, "partidos": m.n_partidos,
                "equipos": [{"equipo": e, "ataque": round(a, 3), "defensa": round(d, 3), "fuerza": round(f, 3)}
                            for e, a, d, f in m.ranking()]}

    def api_backtest(self, q):
        partidos = self.historial(q["liga"])
        desde = date.fromisoformat(q["desde"]) if q.get("desde") else \
            partidos[0].fecha + (partidos[-1].fecha - partidos[0].fecha) * 2 // 3
        r = backtest(partidos, desde, float(q.get("peso", 0.5)), float(q.get("vmin", 0.05)),
                     int(q.get("reajuste", 7)), staking=q.get("staking", "kelly"), vida_media_dias=self.vida_media)
        banca, serie = r.banca_inicial, [[desde.isoformat(), r.banca_inicial]]
        for d in r.detalle:
            banca += d[8]
            serie.append([d[0].isoformat(), round(banca, 2)])
        return {"desde": desde.isoformat(), "n_eval": r.n_eval, "apuestas": r.apuestas, "ganadas": r.ganadas,
                "apostado": round(r.apostado, 2), "beneficio": round(r.beneficio, 2), "roi": round(r.roi, 4),
                "banca_inicial": r.banca_inicial, "banca": round(r.banca, 2), "max_caida": round(r.max_caida, 4),
                "logloss": [round(r.logloss_modelo, 4), round(r.logloss_mercado, 4)],
                "brier": [round(r.brier_modelo, 4), round(r.brier_mercado, 4)], "serie": serie,
                "detalle": [[d[0].isoformat(), *d[1:]] for d in r.detalle[-200:]]}


def crear_servidor(analizador: Analizador, host="127.0.0.1", puerto=8765) -> ThreadingHTTPServer:
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _enviar(self, codigo, cuerpo: bytes, tipo):
            self.send_response(codigo)
            self.send_header("Content-Type", tipo)
            self.send_header("Content-Length", str(len(cuerpo)))
            self.end_headers()
            self.wfile.write(cuerpo)

        def do_GET(self):
            u = urlparse(self.path)
            if u.path.startswith("/api/"):
                fn = getattr(analizador, "api_" + u.path[5:], None)
                if fn is None:
                    return self._enviar(404, b'{"error":"no existe"}', "application/json")
                q = {k: v[0] for k, v in parse_qs(u.query).items()}
                try:
                    res, codigo = fn(q), 200
                except Exception as e:
                    res, codigo = {"error": str(e)}, 400
                return self._enviar(codigo, json.dumps(res, ensure_ascii=False).encode(), "application/json; charset=utf-8")
            with open(os.path.join(ESTATICO, "index.html"), "rb") as fh:
                self._enviar(200, fh.read(), "text/html; charset=utf-8")

    return ThreadingHTTPServer((host, puerto), H)


def ejecutar(carpeta="datos", temporadas=3, vida_media=240.0, puerto=8765, abrir=True):
    srv = crear_servidor(Analizador(carpeta, temporadas, vida_media), puerto=puerto)
    url = f"http://127.0.0.1:{srv.server_address[1]}"
    print(f"Panel de Futbol IA en {url}  (Ctrl+C para salir)")
    if abrir:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
