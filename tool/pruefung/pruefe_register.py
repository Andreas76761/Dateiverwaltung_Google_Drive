"""
Prueft jedes Register durch die echte Oberflaeche.

Felder fuellen, Knopf druecken, Ergebnis aus der Tabelle lesen -- und
gegen einen Bestand halten, bei dem fuer jede Datei vorher feststand, was
herauskommen muss. Wo es geht, wird zusaetzlich unabhaengig nachgezaehlt,
statt dem Programm seine eigene Zahl zu glauben.

Aufruf:  python3 tool/pruefung/pruefe_register.py
Vorher:  mach_bestand.py, gern auch mach_bilder.py
"""

import csv
import os
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gemeinsam
import mach_bestand
import mach_bilder

d = gemeinsam.werkzeug()
b = gemeinsam.Bericht("Register, durch die Oberfläche bedient")
W = mach_bestand.wahrheit_lesen()
QUELLE = W["wurzel"]
ARBEIT = gemeinsam.arbeitsordner("lauf")
BILDER_W = mach_bilder.wahrheit_lesen()

bedienung = gemeinsam.Bedienung(d)
warte = bedienung.warte


def csv_schreiben(pfad, kopf, zeilen):
    with open(pfad, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(kopf)
        for z in zeilen:
            w.writerow(z)


# ================================================================
print("Bestand vorbereiten …")
shutil.rmtree(ARBEIT, ignore_errors=True)
for u in ("ziel", "quarantaene", "bilder", "abbruch"):
    os.makedirs(os.path.join(ARBEIT, u))
ziel = os.path.join(ARBEIT, "ziel")
bilder = os.path.join(ARBEIT, "bilder")
quar = os.path.join(ARBEIT, "quarantaene")

vorher = gemeinsam.bestand(QUELLE)
grenze = W["grenze_mb"] * 1048576
junk, video = set(W["junk"]), set(W["video"])
# Unabhaengig aus der gesetzten Wahrheit, nicht aus den Regeln des
# Programms: alles ausser Abfall, Video und Uebergrossem faehrt mit.
# Von mach_bilder nachgelegte HEIC-Dateien fahren mit.
soll_mit = len(vorher) - len(junk) - len(video) - len(W["ueber_grenze"])
heic_jahre = {}
for rel in (BILDER_W or {}).get("im_bestand", []):
    heic_jahre[rel] = [2014, "exif"] if rel.endswith("mit_datum.heic") else [2019, "datei"]
W["jahre"].update(heic_jahre)
print("{} Dateien im Quellbestand, {} davon sollen mitfahren\n".format(
    len(vorher), soll_mit))

app = d.App()
app.var_limit.set(str(int(W["grenze_mb"])))
app.var_skip_video.set(True)
app.var_workers.set("4")
app.update()

# ================================================================
print("Register 1 · Inventur")
t = app.tab_inv
t.var_path.set(QUELLE)
t.var_id.set("PC1")
t.start()
warte(t, app)
b.prueft("1 Inventur", "Dateien gelesen", len(vorher), len(app.current_entries()))
b.prueft("1 Inventur", "Volumen in Bytes", sum(g for g, _m in vorher.values()),
         sum(e.size for e in app.current_entries()))
b.notiz("1 Inventur", "Zusammenfassung", t.summary.cget("text"))

# ================================================================
print("Register 2 · Regeln — Erprobung")
t = app.tab_reg
bedienung.ordner = QUELLE
t.probe()
warte(t, app)
b.notiz("2 Regeln", "Erprobung", t.summary.cget("text"))
b.prueft("2 Regeln", "Erprobung nennt die Zahl der Mitfahrer", True,
         d.fmt_count(soll_mit) in t.summary.cget("text"),
         "(erwartet {})".format(d.fmt_count(soll_mit)))

# ================================================================
print("Register 3 · Sammeln — Probelauf, dann Ausführung")
t = app.tab_sam
t.var_src.set(QUELLE)
t.var_dst.set(ziel)
t.start(True)
warte(t, app)
probelauf = t.summary.cget("text")
b.prueft("3 Sammeln", "Probelauf schreibt nichts", 0, len(gemeinsam.bestand(ziel)))
b.notiz("3 Sammeln", "Probelauf", probelauf)

t.start(False)
warte(t, app)
kopiert = gemeinsam.bestand(ziel)
b.prueft("3 Sammeln", "kopierte Dateien", soll_mit, len(kopiert))
b.prueft("3 Sammeln", "Probelauf und Ausführung gleich", probelauf, t.summary.cget("text"))
b.prueft("3 Sammeln", "Quelle unverändert", (0, 0, 0),
         gemeinsam.unterschied(vorher, gemeinsam.bestand(QUELLE)))
b.prueft("3 Sammeln", "kein Video mitgefahren", 0,
         sum(1 for r in kopiert if r.endswith(".mp4")))
b.prueft("3 Sammeln", "nichts über der Grenze", 0,
         sum(1 for r, (g, _m) in kopiert.items() if g > grenze))
b.prueft("3 Sammeln", "kein Abfall", 0, len([r for r in kopiert if r in junk]))
stichprobe = sorted(kopiert)[::137][:40]
b.prueft("3 Sammeln", "Stichproben byteweise gleich", len(stichprobe),
         sum(1 for r in stichprobe
             if gemeinsam.hashe(os.path.join(ziel, r)) == gemeinsam.hashe(
                 os.path.join(QUELLE, r))))
b.prueft("3 Sammeln", "Umlautnamen angekommen", len(W["umlaute"]),
         sum(1 for r in W["umlaute"] if r in kopiert))
b.prueft("3 Sammeln", "tiefer Pfad angekommen", True, W["tief"][0] in kopiert)

t0 = time.time()
t.start(False)
warte(t, app)
b.prueft("3 Sammeln", "Wiederholung ändert nichts", (0, 0, 0),
         gemeinsam.unterschied(kopiert, gemeinsam.bestand(ziel)))
b.prueft("3 Sammeln", "kein Register hat sich gesperrt", [],
         [m for m in bedienung.meldungen if "läuft noch" in m])
b.notiz("3 Sammeln", "Wiederholung", "{} · {:.1f}s".format(
    t.status.cget("text"), time.time() - t0))

# ================================================================
print("Register 4 · Dubletten")
t = app.tab_dup
t.var_root.set(QUELLE)
t.var_quar.set(quar)
t.var_prio.set("PC1, PC2, EXT1")
t.start()
warte(t, app)
gruppen = t.groups
gefunden = {tuple(sorted(e.rel.replace("\\", "/") for e in g)) for g in gruppen}

# Unabhaengige Wahrheit: alle inhaltsgleichen Dateien selbst zusammenstellen.
# Der Bestand enthaelt auch Dubletten, die beim Bauen nebenbei entstanden
# sind -- etwa Bilder aus derselben Vorlage.
nach_hash = {}
for rel in vorher:
    nach_hash.setdefault(gemeinsam.hashe(os.path.join(QUELLE, rel)), []).append(rel)
echte_gruppen = {tuple(sorted(v)) for v in nach_hash.values() if len(v) > 1}
dup_hashes = {h for h, v in nach_hash.items() if len(v) > 1}
b.prueft("4 Dubletten", "alle Gruppen gefunden", len(echte_gruppen),
         len(gefunden & echte_gruppen))
b.prueft("4 Dubletten", "keine erfundene Gruppe", 0, len(gefunden - echte_gruppen))
b.prueft("4 Dubletten", "gepflanzte Gruppen darin", len(W["dup_gruppen"]),
         len({tuple(sorted(g)) for g in W["dup_gruppen"]} & gefunden))
fallen_namen = {os.path.basename(a) for a, _b in W["fallen"]}
b.prueft("4 Dubletten", "keine Falle zugeschnappt", 0,
         sum(1 for g in gruppen if any(e.name in fallen_namen for e in g)))


def rang(rel):
    """Die Vorrangregel aus dem Programm, hier unabhaengig nachgebaut."""
    vorrang = ["pc1/", "pc2/", "ext1/"]
    low = rel.lower()
    r = len(vorrang)
    for i, v in enumerate(vorrang):
        if low.startswith(v):
            r = i
            break
    return (r, vorher[rel][1], rel.count("/"), -len(os.path.basename(rel)))


b.prueft("4 Dubletten", "Original nach der Vorrangregel", 0,
         sum(1 for g in gruppen
             if [e.rel.replace("\\", "/") for e in g][0]
             != min([e.rel.replace("\\", "/") for e in g], key=rang)))
b.notiz("4 Dubletten", "Zusammenfassung", t.summary.cget("text"))

dup_csv = os.path.join(ARBEIT, "dubletten.csv")
csv_schreiben(dup_csv,
              ["dup_gruppe", "dup_rolle", "original_pfad", "dateiname",
               "groesse_mb", "geaendert_am", "pruefsumme"],
              [["G-{:04d}".format(gi), "original" if j == 0 else "duplikat",
                e.reldir, e.name, "{:.2f}".format(e.size_mb).replace(".", ","),
                e.date, e.digest or ""]
               for gi, g in enumerate(gruppen, 1) for j, e in enumerate(g)])

# ================================================================
print("Register 5 · Bilder")
t = app.tab_img
t.var_src.set(QUELLE)
t.var_dst.set(bilder)
t.var_copy.set(True)
t.start(False)
warte(t, app)
rows = t.rows
falsch = [(e.rel, W["jahre"][e.rel.replace("\\", "/")], (jahr, quelle))
          for jahr, quelle, e, _z in rows
          if e.rel.replace("\\", "/") in W["jahre"]
          and [str(W["jahre"][e.rel.replace("\\", "/")][0]),
               W["jahre"][e.rel.replace("\\", "/")][1]] != [jahr, quelle]]
b.prueft("5 Bilder", "Aufnahmejahr und Herkunft", 0, len(falsch), str(falsch[:3]))
b.prueft("5 Bilder", "alle Bilder mit bekanntem Jahr dabei", len(W["jahre"]),
         sum(1 for _j, _q, e, _z in rows if e.rel.replace("\\", "/") in W["jahre"]))
angekommen = gemeinsam.bestand(bilder)
b.prueft("5 Bilder", "kein Bild verloren", len(rows), len(angekommen))
b.prueft("5 Bilder", "Quelle unverändert", (0, 0, 0),
         gemeinsam.unterschied(vorher, gemeinsam.bestand(QUELLE)))
b.notiz("5 Bilder", "Zusammenfassung", t.summary.cget("text"))
b.notiz("5 Bilder", "Statuszeile", t.status.cget("text"))

img_csv = os.path.join(ARBEIT, "bilder.csv")
csv_schreiben(img_csv,
              ["quelle_id", "herkunft_pfad", "dateiname", "ziel_name",
               "groesse_mb", "jahr", "jahr_quelle", "ziel_ordner"],
              [[e.rel.replace("\\", "/").split("/")[0], e.reldir, e.name, zn,
                "{:.2f}".format(e.size_mb).replace(".", ","), jahr, quelle, jahr]
               for jahr, quelle, e, zn in rows])

# ================================================================
print("Register 5b · Ähnliche")
t = app.tab_sim
t.var_root.set(bilder)
t.var_quar.set(quar)
t.var_schaerfe.current(1)
t.start()
warte(t, app)
sim_gruppen = t.gruppen
b.prueft("5b Ähnliche", "kein Mitglied weiter weg als die Schärfe", 0,
         sum(1 for g in sim_gruppen for _e, _w, _h, _q, ab in g if ab > 6))
if BILDER_W and BILDER_W.get("im_bestand"):
    heic_gruppen = [sorted(e.name for e, *_r in g) for g in sim_gruppen
                    if any(e.name.endswith(".heic") for e, *_r in g)]
    b.prueft("5b Ähnliche", "HEIC und JPEG desselben Motivs zusammen", 1,
             len(heic_gruppen), str(heic_gruppen))
else:
    b.notiz("5b Ähnliche", "HEIC", "übersprungen — mach_bilder.py nicht gelaufen")
b.notiz("5b Ähnliche", "Zusammenfassung", t.summary.cget("text"))
b.notiz("5b Ähnliche", "Statuszeile", t.status.cget("text"))

sim_csv = os.path.join(ARBEIT, "aehnliche.csv")
csv_schreiben(sim_csv,
              ["aehnlich_gruppe", "aehnlich_rolle", "herkunft_pfad", "dateiname",
               "breite", "hoehe", "groesse_mb", "abstand", "abdruck_quelle"],
              [["A-{:04d}".format(gi), "beste" if j == 0 else "fassung",
                e.reldir, e.name, bw, bh,
                "{:.2f}".format(e.size_mb).replace(".", ","), ab, woher]
               for gi, g in enumerate(sim_gruppen, 1)
               for j, (e, bw, bh, woher, ab) in enumerate(g)])
sim_wahrheit = {e.name: ("A-{:04d}".format(gi), "beste" if j == 0 else "fassung")
                for gi, g in enumerate(sim_gruppen, 1)
                for j, (e, *_r) in enumerate(g)}

# ================================================================
print("Register 7 · Kategorien")
t = app.tab_kat
t.var_root.set(QUELLE)
t.start()
warte(t, app)
treffer = 0
for ordner, kat in W["kategorie_ordner"].items():
    for r in t.rows:
        if r["pfad"].replace("\\", "/").rstrip("/").endswith(ordner):
            if kat in r["ziel"].lower():
                treffer += 1
            else:
                print("   Ordner {} -> {} (erwartet {})".format(ordner, r["ziel"], kat))
            break
b.prueft("7 Kategorien", "Ordner richtig eingeordnet", len(W["kategorie_ordner"]), treffer)
b.notiz("7 Kategorien", "Zusammenfassung", t.summary.cget("text"))

# ================================================================
print("Register 8 · Index")
t = app.tab_idx
t.var_root.set(bilder)
t.var_dup.set(dup_csv)
t.var_img.set(img_csv)
t.var_sim.set(sim_csv)
t.start()
warte(t, app)
index = t.index
b.prueft("8 Index", "eine Zeile je Datei", len(gemeinsam.bestand(bilder)), len(index))
schief = fehlend = unerwartet = 0
for r in index:
    soll = sim_wahrheit.get(r["dateiname"])
    ist = (r["aehnlich_gruppe"], r["aehnlich_rolle"])
    if soll is None:
        unerwartet += 1 if ist != ("", "") else 0
    elif ist == ("", ""):
        fehlend += 1
    elif ist != soll:
        schief += 1
b.prueft("8 Index", "Ähnlichkeitsangabe richtig", (0, 0, 0), (schief, fehlend, unerwartet))
# Eine Dubletten-Angabe darf nur an einer Datei stehen, deren Inhalt es
# wirklich mehrfach gibt -- gemessen am Hash der Datei im Archiv.
falsch_dup = 0
for r in index:
    if not r["dup_gruppe"]:
        continue
    p = os.path.join(bilder, r["ziel_pfad"], r["dateiname"])
    if not os.path.isfile(p) or gemeinsam.hashe(p) not in dup_hashes:
        falsch_dup += 1
b.prueft("8 Index", "keine fremde Dubletten-Angabe", 0, falsch_dup)
b.prueft("8 Index", "achtzehn Spalten", 18, len(index[0]) if index else 0)
b.notiz("8 Index", "Zusammenfassung", t.summary.cget("text"))

# ================================================================
print("Explorer")
t = app.tab_exp
bedienung.ordner = os.path.join(QUELLE, "PC1")
t.a.load()
bedienung.ordner = os.path.join(QUELLE, "PC2")
t.b.load()
bedienung.kurz_durchatmen(app)
a_alle = list(t.a.entries)
b.prueft("Explorer", "Seite A eingelesen",
         len([r for r in vorher if r.startswith("PC1/")]), len(a_alle))

t.preset()
t.var_junk.set(True)
t.refresh()
b.prueft("Explorer", "Voreinstellung Phase 2",
         sum(1 for e in a_alle if not d.is_junk(e) and e.size <= app.limit_bytes()),
         len(t.a.view))

t.var_ext.set("jpg")
t.var_junk.set(False)
t.var_max.set("")
t.refresh()
b.prueft("Explorer", "Filter nach Endung",
         sum(1 for e in a_alle if e.ext == "jpg"), len(t.a.view))

t.var_ext.set("")
t.var_name.set("akte_")
t.refresh()
b.prueft("Explorer", "Filter nach Name",
         sum(1 for e in a_alle if "akte_" in e.name.lower()), len(t.a.view))

t.var_name.set("")
t.var_min.set("0,5")
t.refresh()
b.prueft("Explorer", "Filter nach Grösse",
         sum(1 for e in a_alle if e.size >= 0.5 * 1048576), len(t.a.view))

t.var_min.set("")
t.var_cmp.set("nur hier vorhanden")
t.refresh()
b_rel = {e.rel.lower() for e in t.b.entries}
b.prueft("Explorer", "nur auf Seite A vorhanden",
         sum(1 for e in a_alle if e.rel.lower() not in b_rel), len(t.a.view))

t.var_cmp.set("Grösse weicht ab")
t.refresh()
b_idx = {e.rel.lower(): e for e in t.b.entries}
b.prueft("Explorer", "Grösse weicht ab",
         sum(1 for e in a_alle
             if e.rel.lower() in b_idx and b_idx[e.rel.lower()].size != e.size),
         len(t.a.view))
t.var_cmp.set("alle zeigen")
t.refresh()

# ================================================================
print("Abbrechen mitten im Lauf")
t = app.tab_sam
t.var_dst.set(os.path.join(ARBEIT, "abbruch"))
t.start(False)
t0 = time.time()
while time.time() - t0 < 0.25:
    app.update()
    time.sleep(0.01)
t.stop()
warte(t, app)
halb = gemeinsam.bestand(os.path.join(ARBEIT, "abbruch"))
b.prueft("Abbruch", "keine halbe Datei zurückgelassen", 0,
         len([r for r in list(halb)[:50]
              if halb[r][0] != vorher.get(r, (None,))[0]]))
b.prueft("Abbruch", "wirklich mitten im Lauf getroffen", True, len(halb) < soll_mit,
         "({} von {} Dateien)".format(len(halb), soll_mit))
b.prueft("Abbruch", "Quelle unverändert", (0, 0, 0),
         gemeinsam.unterschied(vorher, gemeinsam.bestand(QUELLE)))
b.notiz("Abbruch", "Stand", "{} von {} Dateien, dann abgebrochen".format(
    len(halb), soll_mit))

# ================================================================
print("Quarantäne — verschieben, nicht löschen")
t = app.tab_dup
t.var_root.set(ziel)          # auf der Sammelplatte, nicht in der Quelle
t.var_quar.set(quar)
t.start()
warte(t, app)
vor_quar = gemeinsam.bestand(ziel)
anzahl_dup = sum(len(g) - 1 for g in t.groups)
t.quarantine()
warte(t, app)
nach_quar = gemeinsam.bestand(ziel)
in_quar = gemeinsam.bestand(quar)
b.prueft("Quarantäne", "verschobene Dateien", anzahl_dup, len(vor_quar) - len(nach_quar))
b.prueft("Quarantäne", "alle wieder auffindbar", anzahl_dup, len(in_quar))
b.prueft("Quarantäne", "nichts verschwunden", len(vor_quar),
         len(nach_quar) + len(in_quar))

# ================================================================
print("Falscher Ordner im Feld")
bedienung.warnungen.clear()
t.var_root.set(os.path.join(ARBEIT, "gibtesnicht"))
t.quarantine()
warte(t, app)
b.prueft("Falscher Ordner", "Knopf verschiebt nichts", (0, 0, 0),
         gemeinsam.unterschied(nach_quar, gemeinsam.bestand(ziel)))
b.prueft("Falscher Ordner", "und sagt warum", True,
         any("anderen Ordner" in w for w in bedienung.warnungen),
         str(bedienung.warnungen)[:80])

app.destroy()
sys.exit(b.ausgeben())
