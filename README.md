# ⚽ Futbol IA — análisis de partidos para apuestas

Herramienta en Python (sin dependencias externas) que analiza **todos los próximos partidos** de
más de 30 ligas, calcula probabilidades de cada resultado y señala las apuestas en las que la
cuota de la casa está por encima de lo que dice el modelo (**apuestas de valor**).

> ⚠️ **Aviso importante.** Ningún modelo garantiza ganancias. Las casas tienen margen (5–8 %) y las cuotas de
> cierre ya incorporan casi toda la información pública. Esta herramienta te da probabilidades y una
> disciplina, no dinero fácil. Apuesta solo lo que puedas permitirte perder. Si el juego deja de ser
> diversión: [jugarbien.es](https://www.jugarbien.es) / línea de ayuda de tu país.

## Qué hace

| Función | Detalle |
|---|---|
| **Modelo** | Dixon-Coles: ataque y defensa de cada equipo, ventaja local, corrección de marcadores bajos y más peso a los partidos recientes (vida media configurable). |
| **Mercados** | 1X2, doble oportunidad, más/menos 0.5–4.5 goles, ambos marcan, marcadores exactos más probables, cuota justa. |
| **Valor** | Compara con las cuotas reales (Pinnacle de cierre, media del mercado o Bet365), quitando el margen. Mezcla modelo y mercado (`--peso-modelo`) para evitar falsas señales. |
| **Banca** | Stake por Kelly fraccionado (¼ Kelly, máximo 5 % de la banca por apuesta). |
| **Backtest** | Simulación *walk-forward*: el modelo solo ve el pasado y apuesta a las cuotas que había. Mide ROI, máxima caída, log-loss y Brier frente al mercado. |
| **Datos** | Descarga automática gratuita de [football-data.co.uk](https://www.football-data.co.uk) (resultados + cuotas), con caché local en `datos/`. |

## Instalación

Requiere Python 3.10+ y conexión a internet.

```bash
pip install -e .          # instala el comando `futbol-ia`
# o sin instalar:  python -m futbol_ia <comando>
```

## Uso

```bash
futbol-ia ligas                                   # lista de ligas (SP1, E0, I1, MEX, ARG, BRA...)

# Analizar TODOS los partidos de los próximos 7 días y buscar valor
futbol-ia jornada --banca 1000 --csv jornada.csv
futbol-ia jornada --ligas SP1 E0 MEX --dias 3     # solo algunas ligas

# Un partido concreto, con las cuotas de tu casa de apuestas
futbol-ia predecir --liga SP1 "Real Madrid" Barcelona --cuotas 2.10 3.60 3.40 --cuotas-goles 1.70 2.15 --banca 500

# Fuerza de cada equipo
futbol-ia ranking --liga E0

# ¿Habría ganado dinero la estrategia? (hazlo SIEMPRE antes de apostar en una liga)
futbol-ia backtest --liga SP1 --temporadas 5 --csv apuestas.csv
```

Ejemplo de salida:

```
━━ 14/11 20:00 | Equipo A vs Equipo B ━━━━━━━━━━━━━━━━━━━━
   Goles esperados: 1.82 - 0.97
   1X2:   1  56.1% (@1.78)   X  23.4% (@4.27)   2  20.5% (@4.88)
   Goles: +1.5  76.0%  +2.5  52.1%  +3.5  29.6%   Ambos marcan  47.8%
   Marcadores: 1-0 11.2%  2-0 10.4%  1-1 10.1%  2-1 9.5%  0-0 6.2%
   Cuotas casa 1X2: 1.95 / 3.50 / 4.00   +2.5/-2.5: 2.05 / 1.80
   ★ VALOR: 1 @1.95  prob  53.9% vs mercado  50.9%  VE +5.1%  stake 1.3% banca → 13.00 de 1000
```

Los nombres de equipos son los de football-data (p. ej. `Ath Madrid`, `Man City`); usa `ranking` para verlos.

### Parámetros útiles

| Opción | Por defecto | Significado |
|---|---|---|
| `--peso-modelo` | 0.5 | 1 = solo modelo, 0 = solo mercado. Valores altos dan más señales pero más falsas. |
| `--valor-minimo` | 0.05 | Valor esperado mínimo (5 %) para marcar una apuesta. |
| `--vida-media` | 240 | Días para que un partido pese la mitad. |
| `--temporadas` | 3 | Temporadas de historial usadas para entrenar. |

## Cómo usarlo con cabeza

1. **Haz backtest de cada liga** y quédate solo con las que muestren log-loss cercano al mercado y ROI positivo en varias temporadas.
2. **Apuesta pronto** (las cuotas tempranas son menos eficientes) y compara casas: la mejor cuota es la mitad de la ventaja.
3. El modelo **no sabe** de lesiones, rotaciones, sanciones, motivación ni del clima: revísalo tú antes de apostar.
4. Registra todas tus apuestas y respeta el stake. Las rachas negativas de 10–20 apuestas son normales.

## Estructura

```
futbol_ia/
  data.py      descarga y normalización de CSVs (ligas principales, extra y próximos partidos)
  modelo.py    modelo Dixon-Coles
  mercados.py  probabilidades por mercado
  valor.py     margen, valor esperado y Kelly
  backtest.py  simulación walk-forward
  cli.py       comandos
tests/         pruebas con una liga sintética de fuerzas conocidas
```

```bash
python -m unittest discover tests
```
