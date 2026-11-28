"""
Laesst die ganze Pruefung laufen und sagt am Ende, ob etwas fehlt.

Aufruf:  python3 tool/pruefung/alles.py [--schnell]
         xvfb-run -a python3 tool/pruefung/alles.py      (ohne Bildschirm)

--schnell laesst den Bildbestand aus. Der dauert mit ImageMagick ein paar
Minuten; alles andere ist in einer Minute durch.
"""

import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gemeinsam
import mach_bestand
import mach_bilder

HIER = os.path.dirname(os.path.abspath(__file__))
SCHNELL = "--schnell" in sys.argv


def lauf(skript, *args):
    print("\n" + "=" * 78)
    print(">>> {} {}".format(skript, " ".join(args)))
    print("=" * 78)
    t0 = time.time()
    e = subprocess.run([sys.executable, os.path.join(HIER, skript)] + list(args))
    print("({:.0f} Sekunden)".format(time.time() - t0))
    return skript, e.returncode


print("Pruefbestand liegt in:", gemeinsam.arbeitsordner())
print("(anderer Ort: Umgebungsvariable DATEIUMZUG_PRUEFUNG setzen)\n")

mach_bestand.baue()
if not SCHNELL:
    mach_bilder.baue()
else:
    print("Bildbestand übersprungen (--schnell)")

ergebnisse = [lauf("pruefe_gruppen.py", "20000"),
              lauf("pruefe_register.py"),
              lauf("pruefe_ausgaben.py")]
if not SCHNELL and mach_bilder.wahrheit_lesen():
    ergebnisse.append(lauf("pruefe_aehnliche.py", "alle"))

print("\n" + "=" * 78)
print("Zusammen:")
for skript, code in ergebnisse:
    print("  {}  {}".format("ok  " if code == 0 else "FEHL", skript))
print("=" * 78)
sys.exit(1 if any(c for _s, c in ergebnisse) else 0)
