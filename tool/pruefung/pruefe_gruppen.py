"""
Prueft das Suchverfahren hinter Register 5b -- ohne Bilder, ohne Fenster.

Der Vergleich jedes mit jedem waere bei zwanzigtausend Fotos eine
Viertelmilliarde Paare. Das Programm zerlegt die Fingerabdruecke darum in
Streifen und vergleicht nur, wer sich einen Streifen teilt. Diese
Abkuerzung darf nichts uebersehen. Hier wird sie gegen den vollen
Vergleich gehalten: dieselben Paare, oder es ist ein Fehler.

Geprueft wird ausserdem, was zwei gefundene Fehler waren: dass es je
Schaerfe wirklich einen Streifen mehr gibt als erlaubte Abweichungen --
sonst traegt der Satz oben nicht --, und dass viele voellig gleiche
Bilder nicht durchfallen, weil ihr Eimer zu voll wird.

Laeuft in zweieinhalb Minuten -- die meiste Zeit geht fuer den vollen
Vergleich drauf, gegen den geprueft wird -- und braucht weder ImageMagick
noch eine Anzeige.

Aufruf:  python3 tool/pruefung/pruefe_gruppen.py [anzahl]
"""

import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gemeinsam

d = gemeinsam.werkzeug()
b = gemeinsam.Bericht("Streifensuche gegen den vollen Vergleich")

ANZAHL = int(sys.argv[1]) if len(sys.argv) > 1 else 20000
SCHWELLE = 6
VORLAGEN = ANZAHL // 10

rng = random.Random(20261025)
items = []
wahrheit = {}
for g in range(VORLAGEN):
    basis = rng.getrandbits(64)
    for v in range(3):
        bits = basis
        for _ in range(rng.randint(0, 4)):
            bits ^= 1 << rng.randrange(64)
        name = "g{}_{}".format(g, v)
        wahrheit[name] = g
        items.append((name, bits))
while len(items) < ANZAHL:
    items.append(("fremd{}".format(len(items)), rng.getrandbits(64)))
rng.shuffle(items)
print("{} Abdrücke, davon {} aus {} Vorlagen".format(
    len(items), len(wahrheit), VORLAGEN))

t0 = time.time()
paare = d.find_similar_pairs(items, SCHWELLE)
dauer_streifen = time.time() - t0

t0 = time.time()
bits = [x for _n, x in items]
voll = set()
for i in range(len(items)):
    bi = bits[i]
    for j in range(i + 1, len(items)):
        if bin(bi ^ bits[j]).count("1") <= SCHWELLE:
            voll.add((i, j))
dauer_voll = time.time() - t0

b.prueft("Paare", "dieselben Paare wie beim vollen Vergleich", voll, set(paare))
b.notiz("Paare", "gefunden", "{} Paare · Streifen {:.1f}s · voll {:.1f}s · {:.0f}× schneller"
        .format(len(voll), dauer_streifen, dauer_voll,
                dauer_voll / max(dauer_streifen, 0.001)))

# Gruppen: keine darf Fremdes enthalten
gruppen, _ab = d.group_similar(items, SCHWELLE)
vermischt = 0
for g in gruppen:
    namen = [items[i][0] for i, _dd in g]
    vorlagen = {wahrheit.get(n) for n in namen}
    if len(vorlagen) > 1 or None in vorlagen:
        vermischt += 1
b.prueft("Gruppen", "keine Gruppe mit Fremdem darin", 0, vermischt)
b.prueft("Gruppen", "kein Mitglied weiter weg als die Schwelle", 0,
         sum(1 for g in gruppen for _i, ab in g if ab > SCHWELLE))
b.notiz("Gruppen", "gebildet", "{} Gruppen aus {} Vorlagen".format(
    len(gruppen), VORLAGEN))

# ================================================================
#  Die Abkuerzung traegt nur, wenn es mehr Streifen gibt als erlaubte
#  Abweichungen. Hier stand einmal eine Obergrenze von acht Streifen,
#  bei einer Schaerfe von neun: gemessen gingen dann 1,6 Prozent der
#  Paare im Abstand 9 verloren -- genau die, fuer die man "weit"
#  einschaltet. Darum wird jede Schaerfe einzeln nachgerechnet.
# ================================================================
print("\nStreifen und Vollständigkeit je Schärfe")
PROBEN = 3000
for _name, s in d.SCHAERFEN:
    b.prueft("Schärfe {}".format(s), "ein Streifen mehr als erlaubte Bits",
             s + 1, len(d._baender(s)))
    verfehlt = zuviel = 0
    for abstand in (s - 1, s, s + 1):
        for _ in range(PROBEN):
            a = rng.getrandbits(64)
            c = a
            for pos in rng.sample(range(64), abstand):
                c ^= 1 << pos
            hat = bool(d.find_similar_pairs([("a", a), ("c", c)], s))
            if abstand <= s and not hat:
                verfehlt += 1
            elif abstand > s and hat:
                zuviel += 1
    b.prueft("Schärfe {}".format(s), "kein Paar bis zur Schwelle verfehlt",
             0, verfehlt, "(je {} Proben im Abstand {}, {} und {})".format(
                 PROBEN, s - 1, s, s + 1))
    b.prueft("Schärfe {}".format(s), "kein Paar jenseits der Schwelle dabei",
             0, zuviel)

# Der volle Vergleich auch bei der weitesten Einstellung -- oben laeuft
# er nur bei der empfohlenen. Mit weniger Abdruecken, sonst dauert das
# Jedes-mit-jedem zu lange.
print("Voller Vergleich bei Schärfe 9")
klein = items[:4000]
paare9 = d.find_similar_pairs(klein, 9)
bits9 = [x for _n, x in klein]
voll9 = set()
for i in range(len(klein)):
    bi = bits9[i]
    for j in range(i + 1, len(klein)):
        if bin(bi ^ bits9[j]).count("1") <= 9:
            voll9.add((i, j))
b.prueft("Schärfe 9", "dieselben Paare wie beim vollen Vergleich",
         voll9, set(paare9))
b.notiz("Schärfe 9", "gefunden", "{} Paare unter {} Abdrücken".format(
    len(voll9), len(klein)))

# ================================================================
#  Viele voellig gleiche Bilder. Das ist der Fall, der vorher still
#  verloren ging: sie landen zwangslaeufig im selben Eimer, und der
#  wurde ab 4000 Eintraegen uebersprungen -- ohne ein Wort. Aus 4001
#  gleichen Abdruecken wurden null Paare.
# ================================================================
print("Viele gleiche Bilder")
for anzahl in (3000, 4001, 6000):
    gleiche = [("gl{}".format(i), 0xABCDEF0123456789) for i in range(anzahl)]
    p = d.find_similar_pairs(gleiche, 6)
    g, uebergangen = d.group_similar(gleiche, 6)
    b.prueft("Gleiche", "{} gleiche: alle Paare".format(anzahl),
             anzahl * (anzahl - 1) // 2, len(p))
    b.prueft("Gleiche", "{} gleiche: eine Gruppe mit allen".format(anzahl),
             (1, anzahl), (len(g), sum(len(x) for x in g)))
    b.prueft("Gleiche", "{} gleiche: nichts übergangen".format(anzahl),
             0, uebergangen)

# Und dieselbe Menge mit einem Nachbarn daneben: der muss mit in die
# Gruppe, nicht an ihr vorbeilaufen.
nah = 0xABCDEF0123456789 ^ 0b111
gemischt = ([("gl{}".format(i), 0xABCDEF0123456789) for i in range(5000)]
            + [("nah", nah)])
g, _ueb = d.group_similar(gemischt, 6)
b.prueft("Gleiche", "der nahe Nachbar kommt mit in die Gruppe",
         (1, 5001), (len(g), sum(len(x) for x in g)))

sys.exit(b.ausgeben())
