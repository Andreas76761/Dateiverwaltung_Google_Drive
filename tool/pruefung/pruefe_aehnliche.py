"""
Prueft Register 5b am Bildbestand mit bekannter Wahrheit.

Jede Vorlage liegt in drei Fassungen vor -- voll, halb, viertel. Die
muessen zusammenfinden; die Einzelbilder duerfen keine Gruppe bilden.
Zusaetzlich die drei Schaerfen im Vergleich und der HEIC-Weg.

Aufruf:  python3 tool/pruefung/pruefe_aehnliche.py [schaerfe 0|1|2|alle]
Vorher:  mach_bilder.py
"""

import os
import subprocess
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

    sauber = vermischt = unvollstaendig = 0
    gefunden = set()
    for g in t.gruppen:
        namen = [e.name for e, *_r in g]
        vorlagen = {vorlage_von(n) for n in namen}
        if len(vorlagen) == 1 and None not in vorlagen:
            sauber += 1
            gefunden.add(vorlagen.pop())
            # Jede Vorlage liegt in drei Fassungen vor. Sind es weniger,
            # hat die Gruppe eine liegen gelassen -- bei "streng" meist
            # die viertelgrosse.
            if len(g) < 3:
                unvollstaendig += 1
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
    b.notiz(bereich, "{} von {} Vorlagen, {} vermischt, {} unvollständig".format(
        len(gefunden), BW["vorlagen"], vermischt, unvollstaendig),
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
    b.prueft("HEIC", "die PNG-Fassung ist dabei", True,
             "dasselbe_voll.png" in alle_namen)
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

    # ------------------------------------------------------------
    #  Die gemeldete Bildgroesse muss die wirkliche sein. Beim PNG
    #  stand hier einmal das Rechenraster mal acht, also auf das
    #  naechste Vielfache von acht aufgerundet: 450 Punkte Hoehe
    #  wurden als 456 gemeldet, in der Tabelle und in der CSV.
    # ------------------------------------------------------------
    print("Gemeldete Bildgröße")
    masse = {e.name: (bw, bh) for g in t.gruppen for e, bw, bh, _q, _d in g}
    soll = (BW.get("probe_breite"), BW.get("probe_hoehe"))
    b.prueft("Größe", "PNG wird mit seiner wirklichen Größe gemeldet",
             soll, masse.get("dasselbe_voll.png"))
    b.prueft("Größe", "JPEG desselben Bildes meldet dasselbe",
             soll, masse.get("dasselbe_voll.jpg"))

    # ------------------------------------------------------------
    #  Der Schalter "Vorschaubilder der Kamera nutzen" muss auch im
    #  zweiten Lauf greifen -- da liegen die Abdruecke schon im
    #  Zwischenspeicher. Vorher ging er dort unter, und bei HEIC
    #  ueberhaupt nicht ein.
    # ------------------------------------------------------------
    print("Schalter · ohne Vorschaubilder")
    t.var_thumb.set(False)
    t.start()
    bedienung.warte(t, app)
    ohne = sorted(e.name for g in t.gruppen for e, *_r in g)
    quellen = {e.name: q for g in t.gruppen for e, _w, _h, q, _d in g}
    b.prueft("Schalter", "kein Abdruck mehr aus einem Vorschaubild", [],
             sorted(n for n, q in quellen.items() if q == "vorschau"))
    b.prueft("Schalter", "die Datei mit nur Vorschaubild fällt heraus", True,
             "mit_vorschau.heic" not in ohne, str(ohne))
    b.prueft("Schalter", "und wird als ohne Vorschau genannt", True,
             "ohne Vorschau" in t.status.cget("text"), t.status.cget("text"))
    b.prueft("Schalter", "die Fassung mit ganzem JPEG bleibt dabei", True,
             "mit_jpeg.heic" in ohne, str(ohne))
    t.var_thumb.set(True)

# ================================================================
#  Die Abdruecke auf mehreren Kernen. Entscheidend ist nicht die Zeit,
#  sondern dass genau dasselbe herauskommt -- und dass es auch dann
#  herauskommt, wenn sich auf einem Rechner kein Hilfsprozess starten
#  laesst. Der eigene Abdruck-Speicher wird beiseitegelegt und
#  hinterher zurueckgeschrieben.
# ================================================================
print("Mehrere Kerne")
SPEICHER = d.fingerprint_file()
eigener = d.load_fingerprints()


def lauf_mit(kerne, ordner):
    if os.path.isfile(SPEICHER):
        os.remove(SPEICHER)
    t.var_root.set(ordner)
    t.var_schaerfe.current(1)
    t.var_thumb.set(True)
    t.var_kerne.set(kerne > 1)
    app.var_workers.set(str(kerne))
    app.update()
    t0 = time.time()
    t.start()
    bedienung.warte(t, app)
    return (time.time() - t0, {p: v[2:] for p, v in d.load_fingerprints().items()},
            [sorted(e.name for e, *_r in g) for g in t.gruppen])


t = app.tab_sim
dauer1, ab1, gr1 = lauf_mit(1, BW["bilder"])
dauer4, ab4, gr4 = lauf_mit(4, BW["bilder"])
b.prueft("Kerne", "auf vier Kernen dieselben Abdrücke", ab1, ab4)
b.prueft("Kerne", "und dieselben Gruppen", sorted(gr1), sorted(gr4))
b.notiz("Kerne", "Zeit", "{} Bilder: ein Kern {:.1f}s · vier Kerne {:.1f}s".format(
    len(ab1), dauer1, dauer4))

# Lohnt es sich nicht, darf gar kein Helfer gestartet werden: ein
# Jahresordner mit kleinen Bildern ist in Sekunden selbst gerechnet,
# und im gebauten Programm entpackt sich jeder Helfer erst selbst.
gezaehlt = {"n": 0}
echt_starten = d._starte_helfer


def zaehlend():
    gezaehlt["n"] += 1
    return echt_starten()


d._starte_helfer = zaehlend
try:
    lauf_mit(4, os.path.join(BW["bilder"], "2019"))
    wenig = gezaehlt["n"]
    gezaehlt["n"] = 0
    lauf_mit(4, BW["bilder"])
    viel = gezaehlt["n"]
finally:
    d._starte_helfer = echt_starten
b.prueft("Kerne", "für wenig Arbeit keine Hilfsprozesse", 0, wenig)
b.prueft("Kerne", "für viel Arbeit schon", True, viel > 0, "({})".format(viel))

# Lässt sich kein Hilfsprozess starten, muss trotzdem alles herauskommen.
echter_befehl = d.worker_befehl
d.worker_befehl = lambda: [gemeinsam.arbeitsordner("gibt-es-nicht"), "--abdruecke"]
try:
    _dauer, ab_zurueck, gr_zurueck = lauf_mit(4, BW["bilder"])
finally:
    d.worker_befehl = echter_befehl
b.prueft("Kerne", "ohne Hilfsprozesse rechnet es selbst weiter", ab1, ab_zurueck)
b.prueft("Kerne", "und kommt auf dieselben Gruppen", sorted(gr1), sorted(gr_zurueck))

# Antwortet ein Helfer nicht, darf das Register nicht haengen bleiben.
d.worker_befehl = lambda: [sys.executable, "-c", "import time; time.sleep(120)"]
alte_grenze = d.PROBE_SEKUNDEN
d.PROBE_SEKUNDEN = 2.0
try:
    t0 = time.time()
    leer = d.abdruecke_parallel(sorted(ab1)[:40], True, 4,
                                d.Job(d.queue.Queue()))
    gewartet = time.time() - t0
finally:
    d.worker_befehl = echter_befehl
    d.PROBE_SEKUNDEN = alte_grenze
b.prueft("Kerne", "ein stummer Helfer gibt nach der Probezeit auf", {}, leer)
b.prueft("Kerne", "und zwar nach der Probezeit, nicht später", True,
         gewartet < 20, "({:.1f}s)".format(gewartet))
offen = [z for z in subprocess.run(["ps", "-eo", "args"], capture_output=True,
                                   text=True).stdout.splitlines()
         if "time.sleep(120)" in z and "ps -eo" not in z]
b.prueft("Kerne", "und lässt keinen Prozess zurück", 0, len(offen))

# Der Hilfsprozess selbst, von Hand befragt
proben = [("1\t" + os.path.join(heic, "dasselbe_voll.jpg"), "ok"),
          ("1\t" + os.path.join(heic, "ohne_alles.heic"), "nicht"),
          ("1\t" + gemeinsam.arbeitsordner("gibt-es-nicht.jpg"), "fehler")]
fertig = subprocess.run(d.worker_befehl(), input="\n".join(p for p, _a in proben) + "\n",
                        capture_output=True, text=True)
antworten = [z.split("\t")[0] for z in fertig.stdout.splitlines()]
b.prueft("Hilfsprozess", "antwortet je Zeile mit dem richtigen Urteil",
         [a for _p, a in proben], antworten, fertig.stdout[:120])

d.save_fingerprints(eigener, set(eigener))
b.prueft("Kerne", "der eigene Abdruck-Speicher ist wieder da",
         len(eigener), len(d.load_fingerprints()))

app.destroy()
sys.exit(b.ausgeben())
