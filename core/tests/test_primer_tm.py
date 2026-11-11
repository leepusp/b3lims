import json
import shutil
import subprocess
from pathlib import Path

from django.test import SimpleTestCase

from core.services.primer_tm import free_magnesium, melting_temperature

CALC = Path(__file__).resolve().parents[1] / "static" / "internal" / "lab_tools" / "molecular_inspector_calc.js"
PANEL = CALC.with_name("molecular_primer_panel.js")
SEQ = "AGCTTGCATGCCTGCAGGTC"


class MeltingTemperatureTests(SimpleTestCase):
    def test_reference_values(self):
        # Checked against Biopython (SantaLucia 1998 and Owczarzy 2008); the two agree within 0.5 C.
        self.assertAlmostEqual(melting_temperature(SEQ), 60.0, delta=0.5)
        self.assertAlmostEqual(
            melting_temperature(SEQ, monovalent_mM=50, magnesium_mM=1.5, dntp_mM=0.8, primer_uM=0.25, method="owczarzy"), 65.4, delta=0.5
        )

    def test_conditions_move_tm_in_the_expected_direction(self):
        base = melting_temperature(SEQ)

        self.assertGreater(melting_temperature(SEQ, monovalent_mM=150), base)
        self.assertGreater(melting_temperature(SEQ, magnesium_mM=2), base)
        self.assertLess(melting_temperature(SEQ, magnesium_mM=2, dntp_mM=2), melting_temperature(SEQ, magnesium_mM=2))
        self.assertGreater(melting_temperature(SEQ, primer_uM=2.5), base)
        self.assertAlmostEqual(melting_temperature(SEQ, dmso_percent=5), base - 3.0, delta=0.11)
        self.assertAlmostEqual(melting_temperature(SEQ, formamide_percent=10), base - 6.5, delta=0.11)
        self.assertGreater(melting_temperature(SEQ, primer_excess=True), base)

    def test_unusable_sequences_give_none(self):
        for seq in ("ACGT", "ACGTNACGTACGT", "", "A" * 121):
            self.assertIsNone(melting_temperature(seq))

        self.assertEqual(melting_temperature("agcttgcatgcctgcaggtc"), melting_temperature(SEQ))
        self.assertEqual(melting_temperature(SEQ.replace("T", "U")), melting_temperature(SEQ))

    def test_free_magnesium(self):
        self.assertEqual(free_magnesium(0, 0.8e-3), 0)
        self.assertAlmostEqual(free_magnesium(1.5e-3, 0), 1.5e-3)
        self.assertLess(free_magnesium(1.5e-3, 0.8e-3), 0.9e-3)
        self.assertGreaterEqual(free_magnesium(1e-3, 5e-3), 0)


class PrimerPanelFrontendTests(SimpleTestCase):
    def test_panel_has_the_calculator(self):
        text = PANEL.read_text()

        for needle in ("Tm calculator", "setTmConditions", "primerExcess", "dmsoPercent", "magnesiumMM"):
            self.assertIn(needle, text)

    def test_browser_calculator_matches_the_server_one(self):
        node = shutil.which("node")

        if not node:
            self.skipTest("node is not available")

        cases = [
            (SEQ, {}, {}),
            (SEQ, {"magnesiumMM": 1.5, "dntpMM": 0.8, "monovalentMM": 50, "primerUM": 0.5, "primerExcess": True},
             {"magnesium_mM": 1.5, "dntp_mM": 0.8, "monovalent_mM": 50, "primer_uM": 0.5, "primer_excess": True}),
            (SEQ, {"monovalentMM": 100, "dmsoPercent": 5}, {"monovalent_mM": 100, "dmso_percent": 5}),
            ("GAATTCGAATTCGAATTC", {"magnesiumMM": 3, "monovalentMM": 10}, {"magnesium_mM": 3, "monovalent_mM": 10}),
        ]
        script = (
            "const calc=require(process.argv[1]);const rows=JSON.parse(process.argv[2]);"
            "console.log(JSON.stringify(rows.map(([s,o])=>calc.meltingTemperature(s,o))));"
        )
        done = subprocess.run([node, "-e", script, str(CALC), json.dumps([[s, js] for s, js, _ in cases])], capture_output=True, text=True, timeout=30)

        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(json.loads(done.stdout), [melting_temperature(s, **py) for s, _, py in cases])
