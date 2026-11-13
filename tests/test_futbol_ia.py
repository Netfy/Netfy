import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from futbol_ia import data
from futbol_ia.backtest import backtest
from futbol_ia.cli import main
from futbol_ia.mercados import mercados
from futbol_ia.modelo import DixonColes
from futbol_ia.valor import buscar_valor, kelly, quitar_margen
from sintetico import generar


class TestFutbolIA(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.csv, cls.fuerza = generar()
        cls.partidos = data.parsear_csv(cls.csv)
        cls.modelo = DixonColes().ajustar(cls.partidos)

    def test_parseo(self):
        self.assertEqual(len(self.partidos), 3 * 20 * 19)
        p = self.partidos[0]
        self.assertTrue(p.jugado)
        self.assertEqual(len(p.cuotas_1x2), 3)
        self.assertEqual(len(p.cuotas_ou25), 2)

    def test_formato_extra(self):
        txt = ("Country,League,Season,Date,Time,Home,Away,HG,AG,Res,PSCH,PSCD,PSCA\n"
               "Argentina,Liga Profesional,2025,01/02/2025,20:00,Boca,River,2,1,H,2.1,3.2,3.6\n")
        p = data.parsear_csv(txt)[0]
        self.assertEqual((p.liga, p.local, p.goles_local, p.cuotas_1x2), ("ARG", "Boca", 2, (2.1, 3.2, 3.6)))

    def test_recupera_orden_de_fuerza(self):
        top = [e for e, *_ in self.modelo.ranking()[:5]]
        cola = [e for e, *_ in self.modelo.ranking()[-5:]]
        self.assertIn("Equipo00", top)
        self.assertIn("Equipo19", cola)
        self.assertGreater(self.modelo.ventaja_local, 1.1)

    def test_probabilidades_coherentes(self):
        pr = mercados(self.modelo.matriz("Equipo00", "Equipo19"))
        self.assertAlmostEqual(pr["1"] + pr["X"] + pr["2"], 1, places=9)
        self.assertGreater(pr["1"], 0.6)
        self.assertAlmostEqual(pr["Más 2.5"] + pr["Menos 2.5"], 1, places=9)

    def test_valor_y_kelly(self):
        self.assertAlmostEqual(sum(quitar_margen([2.0, 3.4, 3.8])), 1)
        self.assertEqual(kelly(0.4, 2.0), 0)
        self.assertGreater(kelly(0.6, 2.0), 0)
        self.assertLessEqual(kelly(0.99, 10), 0.05)
        pr = {"1": 0.6, "X": 0.25, "2": 0.15}
        v = buscar_valor(pr, (2.2, 3.4, 4.0), peso_modelo=1.0)
        self.assertEqual(v[0].seleccion, "1")

    def test_backtest(self):
        desde = self.partidos[int(len(self.partidos) * 0.8)].fecha
        r = backtest(self.partidos, desde, reajuste_dias=30)
        self.assertGreater(r.n_eval, 100)
        # las cuotas sintéticas son "perfectas": el modelo no debería ser mucho peor que el mercado
        self.assertLess(r.logloss_modelo, r.logloss_mercado + 0.03)

    def test_cli(self):
        import tempfile
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as fh:
            fh.write(self.csv)
        try:
            self.assertEqual(main(["predecir", "--archivo", fh.name, "Equipo00", "Equipo10",
                                   "--cuotas", "1.9", "3.6", "4.5", "--banca", "500"]), 0)
            self.assertEqual(main(["ranking", "--archivo", fh.name]), 0)
        finally:
            os.unlink(fh.name)

    def test_jornada(self):
        from datetime import date, timedelta
        from unittest import mock
        hoy = date.today()
        prox = [data.Partido(hoy + timedelta(days=1), "SP1", "Equipo00", "Equipo19", cuotas_1x2=(1.5, 4.5, 8.0),
                             cuotas_ou25=(1.8, 2.0)),
                data.Partido(hoy + timedelta(days=2), "SP1", "Equipo05", "Nuevo FC", cuotas_1x2=(2.0, 3.4, 3.9))]
        with mock.patch.object(data, "cargar_proximos", return_value=prox), \
             mock.patch.object(data, "cargar_liga", return_value=self.partidos):
            self.assertEqual(main(["jornada", "--banca", "1000"]), 0)


if __name__ == "__main__":
    unittest.main()
