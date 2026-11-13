"""Interfaz de línea de comandos: `python -m futbol_ia <comando>`."""
from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from datetime import date, timedelta

from . import data
from .backtest import backtest
from .mercados import cuota_justa, marcadores_probables, mercados
from .modelo import DixonColes
from .valor import buscar_valor, kelly

AVISO = ("⚠  Aviso: ningún modelo garantiza ganancias. Las casas de apuestas tienen margen y el mercado es muy\n"
         "   eficiente. Usa esto como análisis, apuesta solo lo que puedas permitirte perder. Juega con responsabilidad.")


def _pct(x): return f"{100 * x:5.1f}%"


def _cargar(args) -> list[data.Partido]:
    if getattr(args, "archivo", None):
        return data.cargar_archivo(args.archivo, args.liga)
    print(f"Descargando {args.liga} ({args.temporadas} temporadas)...")
    return data.cargar_liga(args.liga, args.temporadas, args.datos)


def _modelo(args, partidos) -> DixonColes:
    return DixonColes(vida_media_dias=args.vida_media).ajustar(partidos)


def informe(modelo: DixonColes, local: str, visitante: str, cuotas_1x2=None, cuotas_ou25=None,
            peso=0.5, valor_min=0.05, banca=None, cabecera="") -> list:
    m = modelo.matriz(local, visitante)
    pr = mercados(m)
    lam, mu = modelo.goles_esperados(local, visitante)
    avisos = [e for e in (local, visitante) if not modelo.conoce(e)]
    print(f"\n━━ {cabecera}{local} vs {visitante} " + "━" * max(0, 50 - len(cabecera) - len(local) - len(visitante)))
    if avisos:
        print(f"   (sin historial para: {', '.join(avisos)} — predicción poco fiable)")
    print(f"   Goles esperados: {lam:.2f} - {mu:.2f}")
    print(f"   1X2:   1 {_pct(pr['1'])} (@{cuota_justa(pr['1']):.2f})   X {_pct(pr['X'])} "
          f"(@{cuota_justa(pr['X']):.2f})   2 {_pct(pr['2'])} (@{cuota_justa(pr['2']):.2f})")
    print(f"   Goles: +1.5 {_pct(pr['Más 1.5'])}  +2.5 {_pct(pr['Más 2.5'])}  +3.5 {_pct(pr['Más 3.5'])}"
          f"   Ambos marcan {_pct(pr['Ambos marcan: Sí'])}")
    print("   Marcadores: " + "  ".join(f"{s} {_pct(p).strip()}" for s, p in marcadores_probables(m, 5)))
    if cuotas_1x2:
        print(f"   Cuotas casa 1X2: {cuotas_1x2[0]:.2f} / {cuotas_1x2[1]:.2f} / {cuotas_1x2[2]:.2f}"
              + (f"   +2.5/-2.5: {cuotas_ou25[0]:.2f} / {cuotas_ou25[1]:.2f}" if cuotas_ou25 else ""))
    # sin historial de algún equipo no se señalan apuestas: la "ventaja" sería ruido del modelo
    valor = [] if avisos else buscar_valor(pr, cuotas_1x2, cuotas_ou25, peso, valor_min)
    for a in valor:
        st = kelly(a.prob, a.cuota)
        extra = f" → {banca * st:.2f} de {banca:.0f}" if banca else ""
        print(f"   ★ VALOR: {a.seleccion} @{a.cuota:.2f}  prob {_pct(a.prob)} vs mercado {_pct(a.prob_mercado)}"
              f"  VE {100 * a.valor:+.1f}%  stake {100 * st:.1f}% banca{extra}")
    return valor


# ----------------------------------------------------------------- comandos
def cmd_ligas(args):
    print("Ligas principales:")
    for k, v in data.LIGAS.items():
        print(f"  {k:5} {v}")
    print("Ligas extra (América, Asia, Escandinavia...):")
    for k, v in data.LIGAS_EXTRA.items():
        print(f"  {k:5} {v}")


def cmd_ranking(args):
    modelo = _modelo(args, _cargar(args))
    print(f"\nRanking {args.liga}  (ventaja local x{modelo.ventaja_local:.2f}, rho {modelo.rho:+.2f}, "
          f"{modelo.n_partidos} partidos)")
    print(f"  {'#':>2} {'Equipo':24} {'Ataque':>7} {'Defensa':>8} {'Fuerza':>7}")
    for i, (e, at, de, f) in enumerate(modelo.ranking(), 1):
        print(f"  {i:>2} {e:24} {at:7.2f} {de:8.2f} {f:+7.2f}")
    print("  (Ataque >1 marca más que la media; Defensa <1 concede menos que la media)")


def cmd_predecir(args):
    modelo = _modelo(args, _cargar(args))
    c1x2 = tuple(args.cuotas) if args.cuotas else None
    cou = tuple(args.cuotas_goles) if args.cuotas_goles else None
    informe(modelo, args.local, args.visitante, c1x2, cou, args.peso_modelo, args.valor_minimo, args.banca)
    print("\n" + AVISO)


def cmd_jornada(args):
    """Analiza TODOS los próximos partidos publicados (con cuotas) de las ligas elegidas."""
    proximos = data.cargar_proximos(args.datos)
    hasta = date.today() + timedelta(days=args.dias)
    proximos = [p for p in proximos if p.fecha <= hasta]
    ligas = {l.upper() for l in args.ligas} if args.ligas else None
    por_liga = defaultdict(list)
    for p in proximos:
        if (ligas is None or p.liga in ligas) and (p.liga in data.LIGAS or p.liga in data.LIGAS_EXTRA):
            por_liga[p.liga].append(p)
    if not por_liga:
        print("No hay próximos partidos publicados para esas ligas.")
        return
    todas, filas = [], []
    for liga, partidos in sorted(por_liga.items()):
        nombre = data.LIGAS.get(liga) or data.LIGAS_EXTRA.get(liga)
        print(f"\n################ {nombre} ({liga}) — {len(partidos)} partidos ################")
        try:
            hist = data.cargar_liga(liga, args.temporadas, args.datos)
            modelo = DixonColes(vida_media_dias=args.vida_media).ajustar(hist)
        except Exception as e:
            print(f"  no se pudo modelar {liga}: {e}")
            continue
        for p in partidos:
            hora = (p.extra.get("hora") or "").strip()
            valor = informe(modelo, p.local, p.visitante, p.cuotas_1x2, p.cuotas_ou25,
                            args.peso_modelo, args.valor_minimo, args.banca,
                            cabecera=f"{p.fecha:%d/%m} {hora + ' ' if hora else ''}| ")
            pr = mercados(modelo.matriz(p.local, p.visitante))
            filas.append([p.fecha, liga, p.local, p.visitante] + [round(pr[k], 4) for k in
                         ("1", "X", "2", "Más 2.5", "Ambos marcan: Sí")] +
                         ["; ".join(f"{a.seleccion}@{a.cuota} VE{100 * a.valor:+.1f}%" for a in valor)])
            todas += [(p, a) for a in valor]
    print("\n================ RESUMEN: APUESTAS CON VALOR ================")
    if not todas:
        print("  Ninguna supera el umbral de valor. (No apostar también es una decisión correcta.)")
    for p, a in sorted(todas, key=lambda t: -t[1].valor):
        print(f"  {p.fecha:%d/%m} {p.liga:4} {p.local} - {p.visitante}: {a.seleccion} @{a.cuota:.2f} "
              f"VE {100 * a.valor:+.1f}%  stake {100 * kelly(a.prob, a.cuota):.1f}%")
    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["fecha", "liga", "local", "visitante", "p1", "pX", "p2", "p_mas25", "p_ambos", "valor"])
            w.writerows(filas)
        print(f"\nCSV guardado en {args.csv}")
    print("\n" + AVISO)


def cmd_backtest(args):
    partidos = _cargar(args)
    desde = date.fromisoformat(args.desde) if args.desde else \
        partidos[0].fecha + (partidos[-1].fecha - partidos[0].fecha) * 2 // 3
    print(f"Backtest desde {desde} (entrena solo con el pasado, reajuste cada {args.reajuste} días)...")
    r = backtest(partidos, desde, args.peso_modelo, args.valor_minimo, args.reajuste,
                 staking=args.staking, vida_media_dias=args.vida_media)
    print(f"\n  Partidos evaluados: {r.n_eval}")
    print(f"  Log-loss 1X2  modelo {r.logloss_modelo:.4f}  |  mercado {r.logloss_mercado:.4f}  (menor = mejor)")
    print(f"  Brier 1X2     modelo {r.brier_modelo:.4f}  |  mercado {r.brier_mercado:.4f}")
    print(f"  Apuestas: {r.apuestas}  acertadas: {r.ganadas} ({_pct(r.ganadas / r.apuestas) if r.apuestas else '-'})")
    print(f"  Apostado: {r.apostado:.2f}  Beneficio: {r.beneficio:+.2f}  ROI: {100 * r.roi:+.2f}%")
    print(f"  Banca: {r.banca_inicial:.0f} → {r.banca:.2f}   Máxima caída: {_pct(r.max_caida)}")
    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            w.writerow(["fecha", "local", "visitante", "apuesta", "cuota", "prob", "stake", "resultado", "ganancia"])
            w.writerows(r.detalle)
        print(f"  Detalle guardado en {args.csv}")
    print("\n" + AVISO)


def cmd_web(args):
    from .web import ejecutar
    ejecutar(args.salida, args.ligas, args.datos, args.temporadas, args.vida_media, args.puerto,
             not args.no_abrir, not args.sin_backtest)


def cmd_exportar(args):
    from .exportar import exportar
    exportar(args.salida, args.ligas, args.datos, args.temporadas, args.vida_media, args.dias,
             not args.sin_backtest)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="futbol-ia", description="IA de análisis de partidos de fútbol para apuestas.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    def comunes(p, liga=True):
        if liga:
            p.add_argument("--liga", default="SP1", help="código de liga (ver `ligas`). Por defecto SP1")
            p.add_argument("--archivo", help="usar un CSV local en lugar de descargar")
        p.add_argument("--temporadas", type=int, default=3)
        p.add_argument("--datos", default="datos", help="carpeta de caché de CSVs")
        p.add_argument("--vida-media", type=float, default=240, help="días para que un partido pese la mitad")
        p.add_argument("--peso-modelo", type=float, default=0.5, help="0..1: mezcla modelo/mercado")
        p.add_argument("--valor-minimo", type=float, default=0.05, help="VE mínimo para señalar apuesta (0.05=5%%)")

    sub.add_parser("ligas", help="lista las ligas disponibles").set_defaults(f=cmd_ligas)

    p = sub.add_parser("ranking", help="fuerza de ataque/defensa de cada equipo"); comunes(p)
    p.set_defaults(f=cmd_ranking)

    p = sub.add_parser("predecir", help="analiza un partido concreto"); comunes(p)
    p.add_argument("local"); p.add_argument("visitante")
    p.add_argument("--cuotas", type=float, nargs=3, metavar=("1", "X", "2"))
    p.add_argument("--cuotas-goles", type=float, nargs=2, metavar=("MAS25", "MENOS25"))
    p.add_argument("--banca", type=float)
    p.set_defaults(f=cmd_predecir)

    p = sub.add_parser("jornada", help="analiza todos los próximos partidos y busca valor"); comunes(p, liga=False)
    p.add_argument("--ligas", nargs="*", help="limitar a estas ligas (por defecto todas)")
    p.add_argument("--dias", type=int, default=7)
    p.add_argument("--banca", type=float)
    p.add_argument("--csv", help="exportar resultados a CSV")
    p.set_defaults(f=cmd_jornada)

    p = sub.add_parser("backtest", help="evalúa la estrategia con datos pasados"); comunes(p)
    p.add_argument("--desde", help="fecha AAAA-MM-DD de inicio (por defecto último tercio)")
    p.add_argument("--reajuste", type=int, default=7)
    p.add_argument("--staking", choices=["kelly", "plano"], default="kelly")
    p.add_argument("--csv")
    p.set_defaults(f=cmd_backtest)

    p = sub.add_parser("web", help="abre el panel visual en el navegador"); comunes(p, liga=False)
    p.add_argument("--ligas", nargs="*", help="solo estas ligas (por defecto todas; menos ligas = más rápido)")
    p.add_argument("--salida", default="sitio")
    p.add_argument("--puerto", type=int, default=8765)
    p.add_argument("--sin-backtest", action="store_true", help="arranca más rápido, sin pestaña de backtest")
    p.add_argument("--no-abrir", action="store_true", help="no abrir el navegador automáticamente")
    p.set_defaults(f=cmd_web)

    p = sub.add_parser("exportar", help="genera la app para el móvil (carpeta lista para publicar)")
    comunes(p, liga=False)
    p.add_argument("--ligas", nargs="*")
    p.add_argument("--salida", default="sitio")
    p.add_argument("--dias", type=int, default=10)
    p.add_argument("--sin-backtest", action="store_true")
    p.set_defaults(f=cmd_exportar)

    args = ap.parse_args(argv)
    try:
        args.f(args)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    return 0
