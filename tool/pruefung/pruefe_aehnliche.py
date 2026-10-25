"""
Prueft Register 5b am Bildbestand mit bekannter Wahrheit.

Jede Vorlage liegt in drei Fassungen vor -- voll, halb, viertel. Die
muessen zusammenfinden; die Einzelbilder duerfen keine Gruppe bilden.
Zusaetzlich die drei Schaerfen im Vergleich und der HEIC-Weg.

Aufruf:  python3 tool/pruefung/pruefe_aehnliche.py [schaerfe 0|1|2|alle]
Vorher:  mach_bilder.py
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gemeinsam
import mach_bilder

d = gemeinsam.werkzeug()
b = gemeinsam.Bericht("Ähnliche Bilder")
BW = mach_bilder.wahrheit_lesen()
if not BW or not os.path.isdir(BW["bilder"]):
    print("Kein Bildbestand da — erst mach_bilder.py laufen lassen.")
    sys.exit(0)

wahl = sys.argv[1] if len(sys.argv) > 1 else "1"
schaerfen = [0, 1, 2] if wahl == "alle" else [int(wahl)]

bedienung = gemeinsam.Bedienung(d)
app = d.App()
app.update()


def vorlage_von(name):
    return name.split("_")[1] if name.startswith("vorlage_") else None


for s in schaerfen:
    name, bits = d.SCHAERFEN[s]
    t = app.tab_sim
    t.var_root.set(BW["bilder"])
    t.var_schaerfe.current(s)
    t.var_thumb.set(True)
    t0 = time.time()
    t.start()
    bedienung.warte(t, app)
    dauer = time.time() - t0

    sauber = vermischt = 0
    gefunden = set()
    for g in t.gruppen:
        namen = [e.name for e, *_r in g]
        vorlagen = {vorlage_von(n) for n in namen}
        if len(vorlagen) == 1 and None not in vorlagen:
            sauber += 1
            gefunden.add(vorlagen.pop())
        else:
            vermischt += 1
    bereich = "Schärfe {}".format(bits)
    anteil = 100.0 * len(gefunden) / BW["vorlagen"]
    b.prueft(bereich, "kein Mitglied weiter weg als erlaubt", 0,
             sum(1 for g in t.gruppen for _e, _w, _h, _q, ab in g if ab > bits))
    b.prueft(bereich, "die beste Fassung führt jede Gruppe", 0,
             sum(1 for g in t.gruppen
                 if g[0][1] * g[0][2] != max(m[1] * m[2] for m in g)))
    if s == 1:
        # Bei der empfohlenen Einstellung sollen fast alle Vorlagen
        # zusammenfinden und fast keine Gruppe Fremdes enthalten.
        b.prueft(bereich, "mindestens 95 von 100 Vorlagen gefunden", True, anteil >= 95,
                 "({:.0f} Prozent)".format(anteil))
        b.prueft(bereich, "höchstens jede zwanzigste Gruppe vermischt", True,
                 vermischt <= 0.05 * max(1, len(t.gruppen)),
                 "({} von {})".format(vermischt, len(t.gruppen)))
    b.notiz(bereich, "{} von {} Vorlagen, {} vermischt".format(
        len(gefunden), BW["vorlagen"], vermischt),
        "{} · {:.0f}s · {}".format(name, dauer, t.summary.cget("text")))

# ================================================================
heic = BW.get("heic")
if heic and os.path.isdir(heic):
    print("HEIC-Proben")
    t = app.tab_sim
    t.var_root.set(heic)
    t.var_schaerfe.current(1)
    t.start()
    bedienung.warte(t, app)
    beisammen = [sorted(e.name for e, *_r in g) for g in t.gruppen]
    alle_namen = sorted(n for g in beisammen for n in g)
    b.prueft("HEIC", "eine Gruppe aus HEIC und JPEG", 1, len(beisammen), str(beisammen))
    b.prueft("HEIC", "die Fassung mit eingebettetem JPEG ist dabei", True,
             "mit_jpeg.heic" in alle_namen)
    b.prueft("HEIC", "die Fassung mit Vorschaubild ist dabei", True,
             "mit_vorschau.heic" in alle_namen)
    b.prueft("HEIC", "die JPEG-Fassungen sind dabei", True,
             "dasselbe_voll.jpg" in alle_namen and "dasselbe_halb.jpg" in alle_namen)
    b.prueft("HEIC", "die verschlossene Datei bleibt draussen", True,
             "ohne_alles.heic" not in alle_namen)
    b.prueft("HEIC", "und wird als solche genannt", True,
             "ohne Vorschau" in t.status.cget("text"), t.status.cget("text"))
    b.notiz("HEIC", "Statuszeile", t.status.cget("text"))

    # Das Aufnahmedatum aus dem Behaelter
    jahr = d.year_from_exif(os.path.join(heic, "mit_datum.heic"))
    b.prueft("HEIC", "Aufnahmejahr aus dem EXIF-Teil", 2014, jahr)
    b.prueft("HEIC", "ohne EXIF kein erfundenes Jahr", None,
             d.year_from_exif(os.path.join(heic, "ohne_alles.heic")))

app.destroy()
sys.exit(b.ausgeben())
