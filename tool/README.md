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

Geprüft an 34.521 Dateien mit 2,8 GB über fünf Quellen, mit Dubletten über Rechnergrenzen,
Umlauten, 164 Zeichen langen Pfaden, Videos, Übergrossen und Programmordnern:

| Schritt | Menge | Dauer |
|---|---|---|
| Inventur über alle fünf Quellen | 34.521 Dateien | 0,5 s |
| Regeln erproben | 88 % fahren mit | 0,05 s |
| Sammeln | 30.273 Dateien, 1,8 GB | 9,2 s |
| Sammeln wiederholt | alles vorhanden | 1,1 s |
| Dubletten über Prüfsummen | 1.898 Gruppen | 2,4 s |
| Bilder nach Jahr | 20.129 Bilder | 1,7 s |
| Kategorien | 21 Ordner beurteilt | 0,1 s |
| Index | 30.273 Zeilen | 0,3 s |

Die Quelle war danach unverändert, Umlaute und lange Pfade heil.

## Selbst starten, ohne den Build abzuwarten

Wenn Python auf dem Rechner ist, geht es auch direkt:

```
python tool/dateiumzug.py
```

Es werden nur Module der Standardbibliothek verwendet, es ist nichts nachzuinstallieren.

## Wenn etwas schiefgeht

Stürzt das Programm ab, schreibt es `dateiumzug-fehler.txt` in dein Benutzerverzeichnis
(`C:\Users\<Name>\`). Diese Datei enthält den Grund.
