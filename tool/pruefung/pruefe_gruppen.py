"""
Prueft das Suchverfahren hinter Register 5b -- ohne Bilder, ohne Fenster.

Der Vergleich jedes mit jedem waere bei zwanzigtausend Fotos eine
Viertelmilliarde Paare. Das Programm zerlegt die Fingerabdruecke darum in
Streifen und vergleicht nur, wer sich einen Streifen teilt. Diese
Abkuerzung darf nichts uebersehen. Hier wird sie gegen den vollen
Vergleich gehalten: dieselben Paare, oder es ist ein Fehler.

Laeuft in Sekunden und braucht weder ImageMagick noch eine Anzeige.

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

sys.exit(b.ausgeben())
