# Prüfung

Diese Skripte prüfen das Werkzeug **durch die echte Oberfläche**: Felder füllen,
Knopf drücken, Ergebnis aus der Tabelle lesen. Nicht die Funktionen darunter —
die Fehler, die zuletzt gefunden wurden, sassen genau dazwischen.

Geprüft wird gegen einen Bestand, bei dem für **jede einzelne Datei vorher
feststeht**, was herauskommen muss: Dubletten in bekannten Gruppen, Bilder mit
hinterlegtem Aufnahmejahr, Fallen mit gleichem Namen und gleicher Grösse bei
verschiedenem Inhalt, Ordner mit bekannter Kategorie.

## Loslegen

```
python3 tool/pruefung/alles.py --schnell
```

Das baut den Bestand, lässt drei Prüfungen laufen und braucht knapp drei
Minuten. Ohne `--schnell` kommt der Bildbestand dazu (ein paar Minuten mehr,
siehe unten).

Der Bestand landet in einem Ordner im Temp-Verzeichnis; etwa ein halbes
Gigabyte. Woanders hin:

```
DATEIUMZUG_PRUEFUNG=/pfad/zum/pruefstand python3 tool/pruefung/alles.py
```

## Was wozu gehört

| Skript | Was es tut | Braucht |
|---|---|---|
| `mach_bestand.py` | baut 2.910 Dateien mit bekannter Wahrheit und schreibt sie als JSON daneben | nichts |
| `mach_bilder.py` | baut 120 Vorlagen à drei Fassungen, 240 Einzelbilder und vier HEIC-Proben | ImageMagick |
| `pruefe_gruppen.py` | hält die Streifensuche aus Register 5b gegen den vollen Vergleich | nichts |
| `pruefe_register.py` | fährt jedes Register durch die Oberfläche | Tk, Anzeige |
| `pruefe_ausgaben.py` | gesicherte Listen, Regeländerungen, Kopieren im Explorer, Einstellungen | Tk, Anzeige |
| `pruefe_aehnliche.py` | Register 5b am Bildbestand, alle drei Schärfen, dazu HEIC | Tk, Anzeige, Bildbestand |
| `alles.py` | ruft alles der Reihe nach auf | — |

Jedes Skript lässt sich einzeln starten und endet mit Rückgabewert 0, wenn
alles stimmt. Fehlt etwas — ImageMagick, der Bildbestand —, sagt das Skript das
und überspringt den Teil, statt zu scheitern.

**Ohne Bildschirm** (Server, CI) braucht Tk eine Anzeige. Unter Linux genügt:

```
xvfb-run -a python3 tool/pruefung/alles.py
```

`xvfb-run` startet die Anzeige für die Dauer des Aufrufs und räumt sie danach
weg. Ein von Hand gestarteter `Xvfb` geht auch, muss dann aber den ganzen Lauf
über stehen bleiben — stirbt er mittendrin, scheitern alle Prüfungen mit
*couldn't connect to display*, und das sieht nach einem Fehler im Programm aus,
ist aber keiner.

## Was geprüft wird

**Register 1 · Inventur** — Anzahl und Volumen gegen eine unabhängige Zählung;
die Spalte `faehrt_mit` in der CSV; das Register der Nichtübernommenen samt
Grund je Zeile.

**Register 2 · Regeln** — eine Endung ergänzen, erproben, auf den
Auslieferungszustand zurücksetzen; die Zahl der Mitfahrer muss sich mit der
Regel ändern und danach wieder stimmen.

**Register 3 · Sammeln** — Probelauf schreibt nichts; Ausführung kopiert genau
die erwarteten Dateien; Quelle danach unverändert; Stichproben byteweise
verglichen; Umlaute und ein neun Ebenen tiefer Pfad; die Wiederholung
überspringt alles Vorhandene.

**Register 4 · Dubletten** — die Wahrheit wird hier **selbst ausgerechnet**
(alle inhaltsgleichen Dateien über ihre Prüfsumme), nicht bloss den gepflanzten
Gruppen geglaubt: der Bestand enthält auch Dubletten, die beim Bauen nebenbei
entstehen. Keine Gruppe darf fehlen, keine erfunden sein, keine Falle
zuschnappen, und das Original muss überall der Vorrangregel folgen.

**Register 5 · Bilder** — jedes Aufnahmejahr und woher es stammt: EXIF muss ein
widersprechendes Dateidatum schlagen, ein Datum im Namen muss greifen, wenn
EXIF fehlt. Namensgleiche aus zwei Quellen müssen nummeriert werden, keine
darf verloren gehen.

**Register 5b · Ähnliche** — am Bildbestand mit bekannter Wahrheit: mindestens
95 von 100 Vorlagen finden ihre Fassungen, höchstens jede zwanzigste Gruppe
enthält Fremdes, kein Mitglied liegt weiter von der besten Fassung entfernt als
die Schärfe erlaubt, und die grösste Fassung führt jede Gruppe an. Dazu die
HEIC-Proben: eine mit eingebettetem JPEG, eine mit Vorschaubild, eine mit
Aufnahmedatum, eine verschlossene — die muss draussen bleiben und als solche
genannt werden.

**Register 7 · Kategorien** — Ordner, deren Kategorie feststeht; das Volumen
muss die Anzahl schlagen.

**Register 8 · Index** — jede Dubletten- und jede Ähnlichkeitsangabe muss an
der richtigen Datei stehen und an keiner unbeteiligten. Geprüft wird über die
Prüfsumme der Datei im Archiv, nicht über ihren Namen.

**Explorer** — sieben Filter- und Vergleichsproben, jede gegen eine unabhängige
Nachzählung; Markieren und Kopieren, Quelle unverändert.

**Abbrechen** — mitten im Lauf gestoppt: keine halbe Datei, Quelle unverändert.

**Quarantäne** — verschieben, nicht löschen: alles wieder auffindbar, nichts
verschwunden. Und: steht ein anderer Ordner im Feld als der, in dem gesucht
wurde, darf der Knopf nichts tun und muss sagen warum.

**Einstellungen** — Grenze und Fäden über einen Neustart hinweg.

## Warum die Oberfläche und nicht die Funktionen darunter

Weil die Fehler dort sassen. Drei Beispiele aus dem letzten Durchgang:

- Jedes Register verweigerte den **zweiten** Vorgang — also genau den Weg
  *Probelauf, dann Ausführen*. Eine Prüfung, die jedes Register nur einmal
  startet, sieht das nie.
- Register 8 brach am Ende jedes Laufs mit einer Fehlermeldung ab, weil beim
  Umbau ein alter Name stehen geblieben war. Die Logik darunter war in Ordnung.
- Der Quarantäne-Knopf hätte auf die Treffer des vorigen Ordners gewirkt.

## Was die Skripte mit der Oberfläche anstellen

Rückfragen werden mit Ja beantwortet, Ordner- und Speichern-Dialoge liefern,
was vorher hineingelegt wurde — sonst bliebe jede Prüfung an einem Fenster
stehen, das niemand sieht. Gewartet wird nicht über eine feste Zeit, sondern
bis das Register seine Knöpfe wieder freigibt.

Die Prüfung **löscht nichts ausserhalb ihres eigenen Ordners**. Der Bestand
wird vor jedem Lauf neu gebaut, alles andere bleibt, wo es ist.
