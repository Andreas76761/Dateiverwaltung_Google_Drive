"""
Baut den Bildbestand fuer Register 5b und die HEIC-Proben.

Fuer die Bilder wird ImageMagick (`convert`) gebraucht -- es ist das
einzige fremde Werkzeug in der ganzen Pruefung. Fehlt es, meldet dieses
Skript das und die Bildpruefungen werden uebersprungen; alle uebrigen
laufen ohne.

Wichtig an den drei Fassungen: sie entstehen aus EINER Datei. Werden sie
je einzeln aus "plasma:" gerechnet, sind es drei verschiedene Bilder --
ein Wolkenmuster ist bei jedem Aufruf neu, "-seed" dahinter aendert daran
nichts.

Aufruf:  python3 tool/pruefung/mach_bilder.py [anzahl_vorlagen]
"""

import json
import os
import shutil
import struct
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gemeinsam

VORLAGEN = 120
EINZELNE = 240


def hat_imagemagick():
    try:
        subprocess.run(["convert", "-version"], capture_output=True, check=True)
        return True
    except (OSError, subprocess.CalledProcessError):
        return False


def convert(*args):
    return subprocess.run(["convert"] + list(args), capture_output=True, check=True).stdout


def grundbild(zahl, ziel):
    convert("-size", "600x450", "plasma:fractal", "-blur", "0x1",
            "-fill", "white", "-stroke", "black", "-strokewidth", "2",
            "-pointsize", "150", "-annotate", "+30+260", str(zahl),
            "-swirl", str((zahl * 37) % 300), ziel)


# ------------------------------------------------------------
#  HEIC von Hand: der Behaelter ist einfach, nur das Bild darin
#  waere ein Videoeinzelbild -- und genau das braucht hier niemand.
# ------------------------------------------------------------

def kasten(typ, inhalt):
    return struct.pack(">I", len(inhalt) + 8) + typ + inhalt


def voll(typ, version, merker, inhalt):
    return kasten(typ, bytes([version]) + merker.to_bytes(3, "big") + inhalt)


def tiff_mit_vorschau(thumb, datum=None):
    """TIFF-Block mit IFD0, IFD1 und angehaengtem Vorschaubild."""
    eintraege = [struct.pack("<HHI", 0x0112, 3, 1) + struct.pack("<HH", 1, 0)]
    if datum:
        eintraege.append(struct.pack("<HHII", 0x8769, 4, 1, 0))
    ifd0 = struct.pack("<H", len(eintraege)) + b"".join(eintraege)
    ifd1_pos = 8 + len(ifd0) + 4
    ifd0 += struct.pack("<I", ifd1_pos)
    thumb_pos = ifd1_pos + 2 + 24 + 4
    ifd1 = (struct.pack("<H", 2)
            + struct.pack("<HHII", 0x0201, 4, 1, thumb_pos)
            + struct.pack("<HHII", 0x0202, 4, 1, len(thumb))
            + struct.pack("<I", 0))
    anhang = b""
    if datum:
        roh = datum.encode("ascii") + b"\x00"
        unter_pos = thumb_pos + len(thumb)
        datum_pos = unter_pos + 2 + 12 + 4
        anhang = (struct.pack("<H", 1)
                  + struct.pack("<HHII", 0x9003, 2, len(roh), datum_pos)
                  + struct.pack("<I", 0) + roh)
        ifd0 = ifd0.replace(struct.pack("<HHII", 0x8769, 4, 1, 0),
                            struct.pack("<HHII", 0x8769, 4, 1, unter_pos))
    return b"II" + struct.pack("<HI", 42, 8) + ifd0 + ifd1 + thumb + anhang


def baue_heic(ziel, teile, breite, hoehe):
    """
    teile: Liste (art, nutzdaten); der erste Teil ist das Hauptbild.

    Zuerst entsteht der Beschreibungsteil mit Platzhaltern, dann sind die
    Laengen bekannt, dann werden die Fundstellen eingetragen. Die Breite
    der Zahlen ist fest, darum aendert sich dabei keine Laenge mehr.
    """
    def meta_mit(orte):
        hdlr = voll(b"hdlr", 0, 0, struct.pack(">I", 0) + b"pict" + b"\x00" * 13)
        pitm = voll(b"pitm", 0, 0, struct.pack(">H", 1))
        infes = b"".join(voll(b"infe", 2, 0, struct.pack(">HH", i, 0) + art + b"\x00")
                         for i, (art, _d) in enumerate(teile, 1))
        iinf = voll(b"iinf", 0, 0, struct.pack(">H", len(teile)) + infes)
        eintraege = b"".join(
            struct.pack(">HHHII", i, 0, 1, orte[i - 1][0], orte[i - 1][1])
            for i in range(1, len(teile) + 1))
        iloc = voll(b"iloc", 0, 0, bytes([0x44, 0x00])
                    + struct.pack(">H", len(teile)) + eintraege)
        ispe = voll(b"ispe", 0, 0, struct.pack(">II", breite, hoehe))
        ipma = voll(b"ipma", 0, 0, struct.pack(">I", 1)
                    + struct.pack(">H", 1) + bytes([1, 1]))
        iprp = kasten(b"iprp", kasten(b"ipco", ispe) + ipma)
        return voll(b"meta", 0, 0, hdlr + pitm + iinf + iloc + iprp)

    ftyp = kasten(b"ftyp", b"heic" + struct.pack(">I", 0) + b"heic" + b"mif1")
    platzhalter = [(0, len(d)) for _art, d in teile]
    kopflaenge = len(ftyp) + len(meta_mit(platzhalter)) + 8
    orte, p = [], kopflaenge
    for _art, d in teile:
        orte.append((p, len(d)))
        p += len(d)
    datei = ftyp + meta_mit(orte) + kasten(b"mdat", b"".join(d for _art, d in teile))
    os.makedirs(os.path.dirname(ziel), exist_ok=True)
    with open(ziel, "wb") as f:
        f.write(datei)
    return len(datei)


def baue(vorlagen=VORLAGEN, einzelne=EINZELNE):
    if not hat_imagemagick():
        print("ImageMagick (convert) fehlt — der Bildbestand wird nicht gebaut.")
        return None

    bilder = gemeinsam.arbeitsordner("bilder")
    heic = gemeinsam.arbeitsordner("heic")
    shutil.rmtree(bilder, ignore_errors=True)
    shutil.rmtree(heic, ignore_errors=True)
    for jahr in ("2019", "2020", "2021", "_Jahr_unklar"):
        os.makedirs(os.path.join(bilder, jahr))
    quellen = os.path.join(bilder, "_quellen")
    os.makedirs(quellen)

    print("baue {} Vorlagen à drei Fassungen und {} Einzelbilder …".format(
        vorlagen, einzelne))
    for i in range(1, vorlagen + 1):
        jahr = "{}".format(2019 + i % 3)
        grund = os.path.join(quellen, "{}.png".format(i))
        grundbild(i, grund)
        convert(grund, "-quality", "92", os.path.join(bilder, jahr, "vorlage_{}_voll.jpg".format(i)))
        convert(grund, "-resize", "50%", "-quality", "88",
                os.path.join(bilder, jahr, "vorlage_{}_halb.jpg".format(i)))
        convert(grund, "-resize", "25%", "-quality", "80",
                os.path.join(bilder, "_Jahr_unklar", "vorlage_{}_viertel.jpg".format(i)))
    for i in range(1001, 1001 + einzelne):
        jahr = "{}".format(2019 + i % 3)
        grund = os.path.join(quellen, "e{}.png".format(i))
        grundbild(i, grund)
        convert(grund, "-quality", "90", os.path.join(bilder, jahr, "einzeln_{}.jpg".format(i)))
        os.remove(grund)

    # Formate, die das Programm nicht vergleicht, und Abfall
    convert("-size", "300x200", "plasma:fractal", os.path.join(bilder, "2020", "nicht_lesbar.gif"))
    convert("-size", "300x200", "plasma:fractal", os.path.join(bilder, "2020", "nicht_lesbar.bmp"))
    with open(os.path.join(bilder, "2020", "Thumbs.db"), "wb") as f:
        f.write(b"x")
    with open(os.path.join(bilder, "2020", "beschaedigt.jpg"), "wb") as f:
        f.write(b"x")

    # -- HEIC-Proben ------------------------------------------------
    print("baue HEIC-Proben …")
    vorlage_png = os.path.join(quellen, "1.png")
    gross = convert(vorlage_png, "-quality", "92", "jpg:-")
    thumb = convert(vorlage_png, "-resize", "160x120!", "-quality", "70", "jpg:-")
    leeres_tiff = b"II" + struct.pack("<HI", 42, 8) + struct.pack("<H", 0) + struct.pack("<I", 0)
    baue_heic(os.path.join(heic, "mit_vorschau.heic"),
              [(b"hvc1", b"\x00" * 4096),
               (b"Exif", struct.pack(">I", 0) + tiff_mit_vorschau(thumb))], 600, 450)
    baue_heic(os.path.join(heic, "mit_jpeg.heic"),
              [(b"jpeg", gross), (b"Exif", struct.pack(">I", 0) + leeres_tiff)], 600, 450)
    baue_heic(os.path.join(heic, "ohne_alles.heic"),
              [(b"hvc1", b"\x00" * 4096)], 600, 450)
    baue_heic(os.path.join(heic, "mit_datum.heic"),
              [(b"hvc1", b"\x00" * 4096),
               (b"Exif", struct.pack(">I", 0)
                + tiff_mit_vorschau(thumb, "2014:07:19 16:02:11"))], 600, 450)
    # dieselbe Aufnahme als JPEG daneben -- die muessen zusammenfinden
    convert(vorlage_png, "-quality", "92", os.path.join(heic, "dasselbe_voll.jpg"))
    convert(vorlage_png, "-resize", "50%", "-quality", "88",
            os.path.join(heic, "dasselbe_halb.jpg"))
    shutil.rmtree(quellen, ignore_errors=True)

    # In den Dateibestand legen, falls es ihn gibt: dann pruefen die
    # Register 5, 5b und 8 den HEIC-Weg gleich mit.
    bestand = gemeinsam.arbeitsordner("bestand")
    fotos = os.path.join(bestand, "PC1", "Fotos")
    gelegt = []
    if os.path.isdir(fotos):
        import time
        for n in sorted(os.listdir(heic)):
            ziel = os.path.join(fotos, n)
            shutil.copy2(os.path.join(heic, n), ziel)
            t = time.mktime((2019, 5, 5, 12, 0, 0, 0, 0, -1))
            os.utime(ziel, (t, t))
            gelegt.append("PC1/Fotos/" + n)
    wahrheit = {
        "bilder": bilder, "heic": heic, "vorlagen": vorlagen, "einzelne": einzelne,
        "im_bestand": gelegt,
    }
    with open(gemeinsam.arbeitsordner("bilder_wahrheit.json"), "w", encoding="utf-8") as f:
        json.dump(wahrheit, f, indent=1, ensure_ascii=False)
    anzahl = sum(len(d) for _r, _u, d in os.walk(bilder))
    print("{} Bilder in {}".format(anzahl, bilder))
    print("{} HEIC-Proben in {}{}".format(
        4, heic, ", auch in den Dateibestand gelegt" if gelegt else ""))
    return wahrheit


def wahrheit_lesen():
    pfad = gemeinsam.arbeitsordner("bilder_wahrheit.json")
    if not os.path.isfile(pfad):
        return None
    with open(pfad, encoding="utf-8") as f:
        return json.load(f)


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else VORLAGEN
    baue(n, n * 2)
