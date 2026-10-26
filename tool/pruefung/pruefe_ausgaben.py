"""
Prueft, was der erste Teil nicht anfasst: gesicherte Listen, geaenderte
Regeln, das Kopieren im Explorer und die Einstellungen ueber einen
Neustart hinweg.

Aufruf:  python3 tool/pruefung/pruefe_ausgaben.py
Vorher:  mach_bestand.py
"""

import csv
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gemeinsam
import mach_bestand

d = gemeinsam.werkzeug()
b = gemeinsam.Bericht("Listen, Regeln, Explorer, Einstellungen")
W = mach_bestand.wahrheit_lesen()
QUELLE = W["wurzel"]
ARBEIT = gemeinsam.arbeitsordner("ausgaben")

bedienung = gemeinsam.Bedienung(d)
warte = bedienung.warte


def zeilen(pfad):
    with open(pfad, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f, delimiter=";"))


shutil.rmtree(ARBEIT, ignore_errors=True)
os.makedirs(os.path.join(ARBEIT, "kopierziel"))

# Gezaehlt wird, was wirklich dasteht, nicht was beim Bauen notiert wurde:
# mach_bilder.py legt hinterher noch HEIC-Proben in den Bestand. Wer der
# alten Zahl glaubt, prueft an der Wirklichkeit vorbei.
da = gemeinsam.bestand(QUELLE)
soll_alle = len(da)
soll_mit = soll_alle - len(W["junk"]) - len(W["video"]) - len(W["ueber_grenze"])

app = d.App()
app.var_limit.set(str(int(W["grenze_mb"])))
app.var_skip_video.set(True)
app.update()

# ================================================================
print("Register 1 · Listen sichern")
t = app.tab_inv
t.var_path.set(QUELLE)
t.start()
warte(t, app)
bedienung.speichern = os.path.join(ARBEIT, "inventur.csv")
t.export()
inv = zeilen(bedienung.speichern)
b.prueft("1 Inventur", "CSV hat eine Zeile je Datei", soll_alle, len(inv))
b.prueft("1 Inventur", "Spalte faehrt_mit stimmt", soll_mit,
         sum(1 for r in inv if r.get("faehrt_mit") == "ja"))

bedienung.speichern = os.path.join(ARBEIT, "nicht_uebernommen.csv")
t.export_register()
# Das Register listet alles, was nicht mitfaehrt, mit Grund -- nicht nur
# die zu grossen Dateien. So steht es auch im Vorgehensplan.
nicht = zeilen(bedienung.speichern)
b.prueft("1 Inventur", "Register der Nichtübernommenen",
         len(W["ueber_grenze"]) + len(W["junk"]) + len(W["video"]), len(nicht))
gruende = {}
for r in nicht:
    gruende[r["grund"]] = gruende.get(r["grund"], 0) + 1
b.prueft("1 Inventur", "Gründe stimmen",
         {"ausschlussliste": len(W["junk"]), "video": len(W["video"]),
          "zu gross": len(W["ueber_grenze"])}, gruende)

# ================================================================
print("Register 2 · Regeln ändern und zurücknehmen")
t = app.tab_reg
vorher_exts = set(d.JUNK_EXTS)
t.boxes["exts"].insert("1.0", "mp3\n")
t.apply()
b.prueft("2 Regeln", "neue Endung greift", True, "mp3" in d.JUNK_EXTS)
bedienung.ordner = QUELLE
t.probe()
warte(t, app)
mit_mp3 = t.summary.cget("text")
b.notiz("2 Regeln", "mit mp3 als Abfall", mit_mp3)
t.reset()
b.prueft("2 Regeln", "Auslieferungszustand stellt wieder her",
         vorher_exts, set(d.JUNK_EXTS))
t.probe()
warte(t, app)
b.notiz("2 Regeln", "wieder im Auslieferungszustand", t.summary.cget("text"))
b.prueft("2 Regeln", "Erprobung ändert sich mit der Regel", True,
         mit_mp3 != t.summary.cget("text"))

# ================================================================
print("Register 4 · Liste sichern")
t = app.tab_dup
t.var_root.set(os.path.join(QUELLE, "PC1"))
t.var_quar.set(os.path.join(ARBEIT, "quarantaene"))
t.start()
warte(t, app)
bedienung.speichern = os.path.join(ARBEIT, "dubletten.csv")
t.export()
dub = zeilen(bedienung.speichern)
b.prueft("4 Dubletten", "CSV so lang wie die Gruppen",
         sum(len(g) for g in t.groups), len(dub))
b.prueft("4 Dubletten", "jede Gruppe hat genau ein Original", len(t.groups),
         sum(1 for r in dub if r["dup_rolle"] == "original"))

# ================================================================
print("Explorer · auswählen und kopieren")
t = app.tab_exp
quelle_a = os.path.join(QUELLE, "EXT1", "Musik")
bedienung.ordner = quelle_a
t.a.load()
bedienung.ordner = os.path.join(ARBEIT, "kopierziel")
t.b.load()
bedienung.kurz_durchatmen(app)
t.preset()
t.var_max.set("")
t.refresh()
t.a.tree.selection_set(t.a.tree.get_children()[:5])
app.update()
vorher_quelle = sorted(os.listdir(quelle_a))
t.copy("a", "b")
warte(t, app)
kopiert = [n for _o, _u, dateien in os.walk(os.path.join(ARBEIT, "kopierziel"))
           for n in dateien]
b.prueft("Explorer", "markierte Dateien kopiert", 5, len(kopiert))
b.prueft("Explorer", "Quelle unverändert", vorher_quelle, sorted(os.listdir(quelle_a)))

# ================================================================
print("Einstellungen über einen Neustart")
alt_grenze = app.var_limit.get()
alt_faeden = app.var_workers.get()
app.var_limit.set("77")
app.var_workers.set("6")
app.persist()
gespeichert = d.load_settings()
b.prueft("Einstellungen", "Grenze gemerkt", 77.0, gespeichert.get("limit_mb"))
b.prueft("Einstellungen", "Fäden gemerkt", 6, gespeichert.get("workers"))
app.var_limit.set(alt_grenze)
app.var_workers.set(alt_faeden)
app.persist()

app.destroy()
sys.exit(b.ausgeben())
