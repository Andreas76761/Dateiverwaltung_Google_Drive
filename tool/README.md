# Dateiumzug 2026 — Werkzeug

Ein Windows-Programm für den Ablauf aus dem Vorgehensplan. Kein Browser,
keine Internetverbindung, keine Installation von Zusatzsoftware.

## Das Programm holen

**Direkter Link, immer die neueste Fassung:**

<https://github.com/Andreas76761/Dateiverwaltung_Google_Drive/releases/download/werkzeug-neueste/Dateiumzug2026.exe>

Anklicken, speichern, doppelklicken. Kein Entpacken, keine Anmeldung. Der Link bleibt
über alle künftigen Bauten derselbe — es liegt dort immer die aktuelle Fassung.

Alternativ über **Actions → Windows-Programm bauen → Artifacts**; dort kommt sie als ZIP
und nur für angemeldete Nutzer.

Beim ersten Start meldet Windows möglicherweise „Der Computer wurde geschützt".
Das erscheint bei jedem Programm ohne gekaufte Signatur. Auf **Weitere Informationen**
klicken, dann auf **Trotzdem ausführen**.

## Die Grundregel

**Das Programm löscht nichts.** Es kennt keine Löschfunktion. Es kann drei Dinge:

- kopieren — die Quelle bleibt unverändert
- in die Quarantäne verschieben — die Dateien bleiben vollständig erhalten
- in Jahresordner verschieben — innerhalb desselben Bestands

Jede Aktion, die etwas auf der Platte verändert, fragt vorher nach. Für die beiden
grossen Vorgänge gibt es einen Probelauf, der nur zählt und rechnet.

## Die Register

| Register | Phase | Was es tut |
|---|---|---|
| **Inventur** | 1 | Ordner einlesen, Aufteilung nach Art zeigen, Inventur und Register der Übergrossen als CSV sichern |
| **Regeln** | 2 | Grössengrenze, Video, Ausschlusslisten — bearbeitbar, gespeichert, an einem Ordner erprobbar |
| **Sammeln** | 3 | Aus einer Quelle auf die Sammelplatte kopieren, mit Grössengrenze und Ausschlussliste |
| **Dubletten** | 4 | Inhaltsgleiche Dateien über die Prüfsumme finden, Original bestimmen, Rest in Quarantäne |
| **Bilder** | 5 | Bilder nach Aufnahmejahr einsortieren — EXIF, sonst Dateiname, sonst Dateidatum |
| **Ähnliche** | 5b | Dieselbe Aufnahme in anderer Grösse oder Qualität finden — über den Bildinhalt, nicht über die Prüfsumme |
| **Kategorien** | 7 | Ordner statt Einzeldateien einsortieren, mit Vorschlag je Ordner |
| **Index** | 8 | Archiv und die Listen der Register 4 und 5 zu einer Index-Datei verbinden |
| **Explorer** | — | Zwei Ordner nebeneinander, filtern, vergleichen, Auswahl kopieren |

Oben im Fenster stehen drei Einstellungen, die für alle Register gelten: die
**Grössengrenze in MB** (voreingestellt 120), ob **Video übernommen** wird
(voreingestellt: nein), und die Zahl der **Fäden** — gleichzeitige Kopiervorgänge.
Alle drei lassen sich auch in Register 2 setzen und bleiben dort gespeichert.

## Tempo

Kopieren läuft über mehrere Fäden gleichzeitig, weil ein einzelner die meiste Zeit auf
die Platte wartet. Auf dem Prüfstand mit 20.000 Dateien und 2,3 GB:

| | vorher | jetzt |
|---|---|---|
| Ordner einlesen | 0,27 s | **0,07 s** |
| Kopieren | 15,0 s | **5,9 s** |
| Nochmals kopieren (alles vorhanden) | 15,0 s | **0,8 s** |

**Vier Fäden** sind die Voreinstellung und meist die beste Wahl. Auf dem Prüfstand waren
8 und 16 Fäden wieder langsamer — die Platte kommt nicht hinterher. Bei einer einzelnen
älteren USB-Platte kann sogar 1 oder 2 schneller sein. Der Wert steht oben im Fenster,
probier ihn an einem kleinen Ordner aus.

Ein abgebrochener Lauf lässt sich einfach wiederholen: vorhandene Dateien werden
übersprungen, nicht überschrieben — und das geht sehr schnell.

## Wie es arbeitet

**Dubletten** werden über SHA-256 erkannt, nicht über Namen oder Grösse. Um Rechenzeit
zu sparen, wird zuerst nach Dateigrösse vorgruppiert — nur wo mehrere Dateien exakt
gleich gross sind, wird überhaupt gerechnet. Bei gewachsenen Beständen fällt damit der
grösste Teil der Arbeit weg.

Welche Kopie als **Original** gilt, entscheidet in dieser Reihenfolge: der Vorrang des
Quellordners (im Feld *Vorrang* eintragen, z. B. `PC1, PC2, EXT1`), dann das ältere
Änderungsdatum, dann der kürzere Pfad, dann der längere und damit sprechendere Dateiname.

**Aufnahmejahre** kommen aus dem EXIF-Feld *DateTimeOriginal* bei JPEG und TIFF. Fehlt es,
greift ein Datum im Dateinamen (`IMG_20190812_…`, `PXL_20230704_…`, `Screenshot 2022-01-03`).
Fehlt auch das, gilt das Änderungsdatum der Datei. Unplausible Jahre — vor 1995 oder in
der Zukunft — landen in `_Jahr_unklar`.

**HEIC-Dateien** tragen ihr EXIF in einem Format, das dieses Programm nicht liest; für sie
greifen Dateiname und Dateidatum. Das trifft fast nur iPhone-Aufnahmen, die praktisch immer
ein Datum im Namen haben.

**Ähnliche Bilder** in Register 5b sind etwas anderes als Dubletten. Eine Prüfsumme sagt nur
*gleich* oder *ungleich*: dasselbe Foto einmal in voller Grösse und einmal für WhatsApp
verkleinert sind für sie zwei fremde Dateien. Register 5b vergleicht darum den Bildinhalt.
Jedes Bild bekommt einen **Fingerabdruck** aus 64 Bit: das Bild wird auf ein winziges
Graubild heruntergerechnet, und für jedes Feld wird nur notiert, ob es heller ist als sein
rechter Nachbar. Diese Hell-Dunkel-Verhältnisse überstehen Verkleinern und Nachkomprimieren;
die Farben und die Schärfe tun das nicht. Zwei Bilder gehören zusammen, wenn sich ihre
Fingerabdrücke in höchstens so vielen Bits unterscheiden, wie die **Schärfe** erlaubt.

Das Herunterrechnen geht bei JPEG fast umsonst: in einer JPEG-Datei steht für jeden
8×8-Block bereits dessen Mittelwert. Wer nur diese Werte liest, hat das Bild in einem Achtel
der Kantenlänge vorliegen, ohne je ein Bild aufgebaut zu haben. Dazu kommt eine Abkürzung:
Kameras und Telefone legen in jedes Foto ein kleines **Vorschaubild**. Passt es zum Bild,
wird es genommen — aus drei Millisekunden statt anderthalb Sekunden bei einem
Zwölf-Megapixel-Foto. Passt es nicht (anderes Seitenverhältnis, aufgefüllte Ränder), rechnet
das Programm von sich aus das ganze Bild durch. Geprüft wurde, dass beide Wege denselben
Fingerabdruck ergeben.

Gelesen werden **JPEG und PNG**. HEIC, TIFF, WebP, BMP und GIF werden gezählt und genannt,
aber nicht geprüft. Einmal berechnete Fingerabdrücke merkt sich das Programm
(`bildabdruecke.csv` neben den Einstellungen); ein zweiter Lauf über denselben Ordner ist
dadurch um ein Vielfaches schneller.

Gruppen bildet Register 5b **um die beste Fassung herum** — die mit den meisten Bildpunkten.
Jedes Mitglied liegt höchstens die eingestellte Schärfe von ihr entfernt. Der erste Entwurf
hat stattdessen alles zusammengezogen, was irgendwie zusammenhing: A zu B, B zu C, also alle
drei in eine Gruppe. Das brachte im Versuch zwei völlig verschiedene Aufnahmen in dieselbe
Gruppe, weil eine kleine Fassung zufällig beiden nahe lag. Mit einer Anführerin je Gruppe
kann das nicht mehr passieren.

**Kategorievorschläge** in Register 7 entstehen aus dem **Volumen** je Ordner, nicht aus der
Anzahl der Dateien: ein Ordner mit einem grossen Vertrag und zwanzig winzigen Skripten ist ein
Dokumentenordner. Der Vorschlag ist nie bindend — Doppelklick auf eine Zeile schaltet zur
nächsten Kategorie weiter. Verschoben werden ganze Ordner, nicht einzelne Dateien.

**Der Index** in Register 8 entsteht aus einem frischen Durchlauf durch das fertige Archiv,
angereichert um die beiden CSV-Dateien aus Register 4 und 5. Register 4 liefert Prüfsumme,
Dublettengruppe und Rolle, Register 5 liefert die ursprüngliche Herkunft der Bilder — die im
Archiv nicht mehr am Pfad ablesbar ist, weil sie in Jahresordnern liegen. Beide sind freiwillig;
ohne sie bleiben die entsprechenden Spalten leer. Die vier Spalten für Handarbeit — Tags,
Aufbewahrung, Status und Notiz — füllst du danach in Sheets.

**Reihenfolge:** Register 5 vor Register 8 ausführen und dort **Liste sichern** nicht vergessen,
sonst lässt sich die Herkunft der Bilder später nicht mehr rekonstruieren.

**Lange Pfade** über 260 Zeichen werden auf Windows korrekt behandelt, ebenso Netzlaufwerke.

**Namenskollisionen** beim Einsortieren führen nie zum Überschreiben — es wird eine Nummer
angehängt (`IMG_0001_2.jpg`). Das gilt auch für Kollisionen *innerhalb desselben Laufs*:
`PC1/Bilder/2014/IMG_0064.jpg` und `PC2/Bilder/2014/IMG_0064.jpg` wollen beide nach
`80_Bilder/2014/IMG_0064.jpg` — die zweite bekommt `IMG_0064_2.jpg`. Wieviele Dateien so
umbenannt wurden, steht am Ende in der Statuszeile.

## Am grossen Bestand erprobt

Jedes Register wurde an einem Bestand geprüft, bei dem für jede Datei vorher feststand,
was herauskommen muss — Dubletten in bekannten Gruppen, Bilder mit hinterlegtem
Aufnahmejahr, Ordner mit bekannter Kategorie, Fallen mit gleichem Namen und gleicher
Grösse bei verschiedenem Inhalt.

| Register | Prüfung | Ergebnis |
|---|---|---|
| 1 · Inventur | 12.542 Dateien, Aufteilung und CSV | Ausschlüsse, Übergrosse und Spalte `faehrt_mit` exakt |
| 2 · Regeln | Grenze, Videoschalter, Listen ändern | jede Datei genau einmal einsortiert; Regeländerung greift sofort |
| 3 · Sammeln | 11.227 Dateien kopiert | Probelauf = Ausführung, Quelle unverändert, 40 Stichproben byteweise gleich |
| 4 · Dubletten | 2.000 bekannte Gruppen, 6.800 Fallen | 2.000 von 2.000 getroffen, 0 übersehen, 0 Falle zugeschnappt |
| 5 · Bilder | 3.620 Bilder mit bekanntem Jahr | alle richtig; EXIF schlägt widersprechenden Dateinamen |
| 5b · Ähnliche | 200 Vorlagen à drei Fassungen, 400 Einzelbilder | bei *normal* 198 von 200 gefunden, 7 Gruppen mit Fremdem — siehe unten |
| 7 · Kategorien | 5 Ordner mit bekannter Kategorie | alle 5 richtig, Volumen schlägt Anzahl |
| 8 · Index | 27.785 Zeilen, 800 Fallen | jede Dubletten-Angabe an der richtigen Datei |
| Explorer | 8 Filterproben, 4 Vergleichsarten | jede Zahl mit unabhängiger Nachzählung deckungsgleich |

Tempo an 34.521 Dateien mit 2,8 GB über fünf Quellen: Inventur 0,5 s · Sammeln 9,2 s ·
Wiederholung 1,1 s · Dubletten 2,4 s · Bilder 1,7 s · Index 0,3 s.

### Welche Schärfe in Register 5b

An 1.000 Bildern — 200 Vorlagen in je drei Fassungen (voll, halb, viertel) und 400
Einzelbildern:

| Schärfe | Vorlagen gefunden | Gruppen mit Fremdem darin | Fassungen unvollständig |
|---|---|---|---|
| streng (3 Bit) | 181 von 200 | **0** | 106 |
| **normal (6 Bit)** | **198 von 200** | 7 | 26 |
| weit (9 Bit) | 161 von 200 | 65 | 11 |

*normal* ist die Voreinstellung. *streng* lässt viertelgrosse Fassungen liegen, *weit* wirft
zu viel zusammen. Der Prüfbestand ist dabei härter als echte Fotos: alle 1.000 Bilder sind
nach demselben Muster erzeugt und sehen einander von Haus aus ähnlich — zwei der sieben
beanstandeten Gruppen enthalten Bilder, die auch ein Mensch für Varianten desselben Motivs
hielte. Bei Urlaubsfotos liegen fremde Aufnahmen deutlich weiter auseinander.

Tempo: 1.000 Bilder à 0,3 Megapixel in 27 Sekunden, beim zweiten Lauf aus dem Gedächtnis in
1 Sekunde. Ein Zwölf-Megapixel-Foto braucht 0,3 bis 1,7 Sekunden, wenn das ganze Bild
gerechnet werden muss — und 3 Millisekunden, wenn das Vorschaubild der Kamera taugt. Das
Vergleichen selbst fällt kaum ins Gewicht: 20.000 Fingerabdrücke brauchen 1,2 Sekunden statt
106 Sekunden für jeden-mit-jedem, und finden dabei nachweislich dieselben Paare.

Umlaute und 164 Zeichen lange Pfade blieben heil, die Quelle war nach jedem Lauf unverändert.

Register 5b wurde durch die Oberfläche selbst getrieben — Ordner eintragen, *Suchen*
drücken, Tabelle auslesen —, ebenso ein Durchlauf durch alle übrigen Register nacheinander.
Dabei kam ein Fehler ans Licht, der in der Logikprüfung nicht auffallen konnte: Register 8
brach am Ende jedes Laufs mit einer Fehlermeldung ab, weil beim letzten Umbau ein alter
Name stehen geblieben war. Behoben; der Durchlauf über alle Register gehört jetzt zur
Prüfung.

Ausserdem lasen drei Register ihre Einstellungen aus dem Arbeitsfaden heraus direkt aus den
Eingabefeldern. Das geht in der Praxis gut, ist aber nicht zugesichert; jetzt wird alles
vorher im Hauptfaden gelesen und als einfacher Wert weitergereicht.

## Selbst starten, ohne den Build abzuwarten

Wenn Python auf dem Rechner ist, geht es auch direkt:

```
python tool/dateiumzug.py
```

Es werden nur Module der Standardbibliothek verwendet, es ist nichts nachzuinstallieren.

## Wenn etwas schiefgeht

Stürzt das Programm ab, schreibt es `dateiumzug-fehler.txt` in dein Benutzerverzeichnis
(`C:\Users\<Name>\`). Diese Datei enthält den Grund.
