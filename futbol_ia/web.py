"""Panel visual en local: genera la app y la sirve en http://127.0.0.1:<puerto>."""
from __future__ import annotations

import functools
import threading
import webbrowser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

from .exportar import exportar


class _Silencioso(SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


def crear_servidor(carpeta: str, host="127.0.0.1", puerto=8765) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, puerto), functools.partial(_Silencioso, directory=carpeta))


def ejecutar(salida="sitio", ligas=None, carpeta="datos", temporadas=3, vida_media=240.0, puerto=8765,
             abrir=True, con_backtest=True):
    print("Preparando datos (la primera vez descarga todo y tarda unos minutos)...")
    exportar(salida, ligas, carpeta, temporadas, vida_media, con_backtest=con_backtest)
    srv = crear_servidor(salida, puerto=puerto)
    url = f"http://127.0.0.1:{srv.server_address[1]}"
    print(f"Panel de Futbol IA en {url}  (Ctrl+C para salir)")
    if abrir:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
