"""
Baut einen Pruefbestand, bei dem fuer jede Datei vorher feststeht, was
herauskommen muss -- und schreibt diese Wahrheit als JSON daneben.

Nichts hier ist zufaellig gewachsen: jede Dublettengruppe, jede Falle,
jedes Aufnahmejahr ist gesetzt. Nur so laesst sich hinterher sagen, ob
das Programm recht hat oder bloss plausibel aussieht.

Aufruf:  python3 tool/pruefung/mach_bestand.py
"""

import json
import os
import random
import shutil
import struct
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gemeinsam

GRENZE_MB = 1.0
QUELLEN = ("PC1", "PC2", "EXT1")


def inhalt(n, schluessel):
    """Eindeutiger Inhalt fester Laenge."""
    r = random.Random(schluessel)
    kern = bytes(r.getrandbits(8) for _ in range(min(n, 1024)))
    return (kern * (n // len(kern) + 1))[:n]


def jpeg_mit_datum(roh, datum):
    """Haengt einen EXIF-Block mit Aufnahmedatum in ein vorhandenes JPEG."""
    text = datum.encode("ascii") + b"\x00"
    ifd0_laenge = 2 + 12 + 4
    unter_pos = 8 + ifd0_laenge
    datum_pos = unter_pos + 2 + 12 + 4
    ifd0 = (struct.pack("<H", 1)
            + struct.pack("<HHII", 0x8769, 4, 1, unter_pos)
            + struct.pack("<I", 0))
    unter = (struct.pack("<H", 1)
             + struct.pack("<HHII", 0x9003, 2, len(text), datum_pos)
             + struct.pack("<I", 0) + text)
    tiff = b"II" + struct.pack("<HI", 42, 8) + ifd0 + unter
    koerper = b"Exif\x00\x00" + tiff
    app1 = b"\xff\xe1" + struct.pack(">H", len(koerper) + 2) + koerper
    return roh[:2] + app1 + roh[2:]


def kleines_jpeg():
    """
    Ein winziges JPEG ohne fremde Werkzeuge.

    Gebraucht wird nur ein Traeger fuer EXIF-Daten; wie das Bild aussieht,
    ist fuer Register 5 gleichgueltig. Ein Grauverlauf von acht mal acht
    Punkten reicht und laesst sich von Hand zusammensetzen.
    """
    quant = bytes([16] * 64)
    dqt = b"\xff\xdb" + struct.pack(">H", 67) + b"\x00" + quant
    sof = (b"\xff\xc0" + struct.pack(">H", 11) + b"\x08"
           + struct.pack(">HH", 8, 8) + b"\x01" + bytes([1, 0x11, 0]))
    # eine Huffman-Tabelle fuer Gleich- und eine fuer Wechselanteile
    dc_counts = bytes([0, 1] + [0] * 15)
    dht_dc = b"\xff\xc4" + struct.pack(">H", 2 + 1 + 16 + 1) + b"\x00" + dc_counts + b"\x00"
    ac_counts = bytes([0, 1] + [0] * 15)
    dht_ac = b"\xff\xc4" + struct.pack(">H", 2 + 1 + 16 + 1) + b"\x10" + ac_counts + b"\x00"
    sos = b"\xff\xda" + struct.pack(">H", 8) + b"\x01" + bytes([1, 0x00]) + bytes([0, 63, 0])
    # ein Block: Gleichanteil null, danach Blockende
    daten = bytes([0b01000000])
    return (b"\xff\xd8" + dqt + sof + dht_dc + dht_ac + sos + daten + b"\xff\xd9")


def baue(wurzel=None, melden=True):
    wurzel = wurzel or gemeinsam.arbeitsordner("bestand")
    shutil.rmtree(wurzel, ignore_errors=True)
    wahrheit = {
        "wurzel": wurzel, "grenze_mb": GRENZE_MB,
        "dup_gruppen": [], "fallen": [], "jahre": {}, "video": [],
        "junk": [], "ueber_grenze": [], "kategorie_ordner": {},
        "umlaute": [], "tief": [],
    }
    alle = []

    def schreibe(rel, daten, jahr=None):
        pfad = os.path.join(wurzel, rel)
        os.makedirs(os.path.dirname(pfad), exist_ok=True)
        with open(pfad, "wb") as f:
            f.write(daten)
        if jahr:
            t = time.mktime(datetime(jahr, 6, 15, 12, 0).timetuple())
            os.utime(pfad, (t, t))
        alle.append((rel, len(daten)))

    # -- 1. gewoehnliche Dateien, jede fuer sich einmalig ----------
    endungen = ["pdf", "docx", "txt", "xlsx", "mp3", "zip", "js", "csv", "odt", "wav"]
    for i in range(1800):
        q = QUELLEN[i % 3]
        ordner = ["Dokumente", "Arbeit", "Privat", "Downloads"][i % 4]
        rel = "{}/{}/datei_{:05d}.{}".format(q, ordner, i, endungen[i % len(endungen)])
        schreibe(rel, inhalt(2000 + (i * 37) % 40000, 10000 + i))

    # -- 2. Dubletten in bekannten Gruppen -------------------------
    # 120 Gruppen zu dritt, die Haelfte mit gleichem Namen in allen
    # Quellen, die andere Haelfte mit verschiedenen Namen.
    for g in range(120):
        daten = inhalt(5000 + g * 11, 500000 + g)
        gruppe = []
        for k, q in enumerate(QUELLEN):
            if g % 2 == 0:
                rel = "{}/Gemeinsam/akte_{:04d}.pdf".format(q, g)
            else:
                rel = "{}/Gemeinsam/akte_{:04d}_{}.pdf".format(q, g, "abc"[k])
            schreibe(rel, daten)
            gruppe.append(rel)
        wahrheit["dup_gruppen"].append(gruppe)

    # -- 3. Fallen: gleicher Name, gleiche Groesse, anderer Inhalt --
    for i in range(150):
        n = 7000 + i
        a = "PC1/Fallen/bericht_{:04d}.pdf".format(i)
        b = "PC2/Fallen/bericht_{:04d}.pdf".format(i)
        schreibe(a, inhalt(n, 900000 + i))
        schreibe(b, inhalt(n, 950000 + i))
        wahrheit["fallen"].append([a, b])

    # -- 4. Bilder mit bekanntem Aufnahmejahr ----------------------
    traeger = kleines_jpeg()
    for i in range(120):
        jahr = 2008 + i % 12
        roh = jpeg_mit_datum(traeger, "{}:0{}:1{} 1{}:00:00".format(
            jahr, 1 + i % 9, i % 10, i % 10))
        rel = "{}/Fotos/aufnahme_{:04d}.jpg".format(QUELLEN[i % 3], i)
        schreibe(rel, roh, jahr=2024)      # Dateidatum anders: EXIF muss gewinnen
        wahrheit["jahre"][rel] = [jahr, "exif"]
    for i in range(80):
        jahr = 2011 + i % 9
        rel = "{}/Fotos/IMG_{}{:02d}{:02d}_{:04d}.jpg".format(
            QUELLEN[i % 3], jahr, 1 + i % 12, 1 + i % 28, i)
        schreibe(rel, traeger + inhalt(80 + i, 400000 + i), jahr=2023)
        wahrheit["jahre"][rel] = [jahr, "name"]   # Name muss gewinnen
    for i in range(60):
        jahr = 2015 + i % 8
        rel = "{}/Fotos/ohne_hinweis_{:04d}.png".format(QUELLEN[i % 3], i)
        schreibe(rel, inhalt(3000 + i, 300000 + i), jahr=jahr)
        wahrheit["jahre"][rel] = [jahr, "datei"]

    # -- 5. Namensgleiche Bilder aus zwei Quellen ------------------
    # Beide wollen in denselben Jahresordner; keines darf verloren gehen.
    for i in range(40):
        a = "PC1/Fotos/IMG_{:04d}.jpg".format(i)
        b = "PC2/Fotos/IMG_{:04d}.jpg".format(i)
        schreibe(a, jpeg_mit_datum(traeger, "2017:03:0{} 09:00:00".format(1 + i % 9)),
                 jahr=2024)
        schreibe(b, jpeg_mit_datum(traeger + inhalt(40 + i, 450000 + i),
                                   "2017:03:0{} 10:00:00".format(1 + i % 9)), jahr=2024)
        wahrheit["jahre"][a] = [2017, "exif"]
        wahrheit["jahre"][b] = [2017, "exif"]

    # -- 6. Video: faehrt nicht mit ---------------------------------
    for i in range(30):
        rel = "{}/Filme/urlaub_{:03d}.mp4".format(QUELLEN[i % 3], i)
        schreibe(rel, inhalt(60000 + i * 13, 200000 + i))
        wahrheit["video"].append(rel)

    # -- 7. Abfall: muss durch die Listen fallen --------------------
    abfall = [("PC1/Programme/bibliothek_{:02d}.dll".format(i), 4000 + i) for i in range(12)]
    abfall += [("PC2/Setup/aufbau_{:02d}.exe".format(i), 9000 + i) for i in range(8)]
    abfall += [("EXT1/Kram/zwischen_{:02d}.tmp".format(i), 1200 + i) for i in range(6)]
    abfall += [("PC1/Dokumente/Thumbs.db", 300), ("PC2/Arbeit/desktop.ini", 220),
               ("PC1/Projekte/node_modules/paket/index.js", 1500),
               ("PC2/AppData/Roaming/notiz.txt", 900),
               ("EXT1/Temp/rest.csv", 800)]
    for rel, n in abfall:
        schreibe(rel, inhalt(n, 700000 + len(rel)))
        wahrheit["junk"].append(rel)

    # -- 8. Ueber der Grenze ----------------------------------------
    for i in range(10):
        rel = "{}/Gross/abbild_{:02d}.zip".format(QUELLEN[i % 3], i)
        schreibe(rel, inhalt(int(GRENZE_MB * 1048576) + 50000 + i, 800000 + i))
        wahrheit["ueber_grenze"].append(rel)

    # -- 9. Ordner mit eindeutiger Kategorie ------------------------
    # Entscheiden soll das Volumen, nicht die Anzahl.
    for i in range(3):
        schreibe("EXT1/Vertraege/vertrag_{}.pdf".format(i), inhalt(400000 + i, 600000 + i))
    for i in range(20):
        schreibe("EXT1/Vertraege/skript_{:02d}.js".format(i), inhalt(600 + i, 610000 + i))
    wahrheit["kategorie_ordner"]["EXT1/Vertraege"] = "dokument"
    for i in range(12):
        schreibe("EXT1/Musik/lied_{:02d}.mp3".format(i), inhalt(90000 + i, 620000 + i))
    wahrheit["kategorie_ordner"]["EXT1/Musik"] = "audio"

    # -- 10. Umlaute und ein tiefer Pfad ----------------------------
    for name in ["PC1/Büro/Jahresübersicht_Grün.docx",
                 "PC2/Größe/straße_maß.txt",
                 "EXT1/Öffentlich/Prüfung_Ähnlich.pdf"]:
        schreibe(name, inhalt(2500, 650000 + len(name)))
        wahrheit["umlaute"].append(name)
    tief = "PC1/" + "/".join("ebene_{:02d}".format(i) for i in range(9)) + "/ganz_unten.txt"
    schreibe(tief, inhalt(1700, 660000))
    wahrheit["tief"].append(tief)

    # -- Zusammenzaehlen --------------------------------------------
    wahrheit["dateien_gesamt"] = len(alle)
    wahrheit["bytes_gesamt"] = sum(n for _r, n in alle)
    wahrheit["alle"] = dict(alle)
    wahrheit["faehrt_mit"] = (len(alle) - len(wahrheit["junk"])
                              - len(wahrheit["video"]) - len(wahrheit["ueber_grenze"]))
    pfad = gemeinsam.arbeitsordner("bestand_wahrheit.json")
    os.makedirs(os.path.dirname(pfad), exist_ok=True)
    with open(pfad, "w", encoding="utf-8") as f:
        json.dump(wahrheit, f, indent=1, ensure_ascii=False)
    if melden:
        print("{} Dateien, {:.1f} MB in {}".format(
            wahrheit["dateien_gesamt"], wahrheit["bytes_gesamt"] / 1048576, wurzel))
        print("davon Abfall {} · Video {} · über der Grenze {} · fährt mit {}".format(
            len(wahrheit["junk"]), len(wahrheit["video"]),
            len(wahrheit["ueber_grenze"]), wahrheit["faehrt_mit"]))
        print("{} Dublettengruppen, {} Fallen, {} Bilder mit bekanntem Jahr".format(
            len(wahrheit["dup_gruppen"]), len(wahrheit["fallen"]), len(wahrheit["jahre"])))
    return wahrheit


def wahrheit_lesen():
    with open(gemeinsam.arbeitsordner("bestand_wahrheit.json"), encoding="utf-8") as f:
        return json.load(f)


if __name__ == "__main__":
    baue()
