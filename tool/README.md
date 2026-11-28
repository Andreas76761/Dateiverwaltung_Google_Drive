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
| **Index** | 8 | Archiv und die Listen der Register 4, 5 und 5b zu einer Index-Datei verbinden |
| **Abgleich** | 9 | Sammelplatte gegen den Drive-Ordner halten — je Quelle zählen, Abweichung über ein Prozent anzeigen, Stichprobe nachrechnen |
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

**HEIC-Dateien vom iPhone** werden gelesen. Eine HEIC-Datei ist keine Bilddatei im gewohnten
Sinn, sondern ein Behälter nach demselben Muster wie ein Video: ineinander geschachtelte
Kästen, und das Bild darin ist ein Videoeinzelbild. Das Bild selbst bleibt deshalb
verschlossen — die **EXIF-Daten mit dem Aufnahmedatum** liegen aber als eigener Teil daneben
und werden jetzt direkt aus dem Behälter geholt. Damit bekommen iPhone-Fotos ihr echtes
Aufnahmejahr statt einer Schätzung aus Dateiname oder Dateidatum. Geprüft an einem echten
iPhone-Foto: Aufnahmedatum 11.05.2010, erkanntes Jahr 2010.

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

Verglichen werden **JPEG und PNG**, und **HEIC, soweit ein JPEG mit darin liegt** — viele
Geräte legen ein Vorschaubild in den EXIF-Block, manche ein ganzes JPEG daneben. Dann stimmt
der Fingerabdruck mit dem der JPEG-Fassung desselben Fotos überein; geprüft wurde genau das
(Abstand 0 beim eingebetteten JPEG, 2 beim Vorschaubild). Findet sich keines von beidem,
sagt das Programm es: solche Dateien erscheinen als *HEIC ohne Vorschau* und nicht als
Fehler. TIFF, WebP, BMP und GIF werden gezählt, aber nicht verglichen. Einmal berechnete
Fingerabdrücke merkt sich das Programm
(`bildabdruecke.csv` neben den Einstellungen); ein zweiter Lauf über denselben Ordner ist
dadurch um ein Vielfaches schneller. Nach einem vollständigen Lauf räumt es dort auf: was zu
einer Datei gehört, die im geprüften Ordner nicht mehr liegt, wird vergessen.

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
angereichert um die CSV-Dateien aus den Registern 4, 5 und 5b. Register 4 liefert Prüfsumme,
Dublettengruppe und Rolle, Register 5 liefert die ursprüngliche Herkunft der Bilder — die im
Archiv nicht mehr am Pfad ablesbar ist, weil sie in Jahresordnern liegen —, Register 5b die
Ähnlichkeitsgruppe. Wer darin nicht die beste Fassung ist, bekommt gleich `status:unklar`.
Alle drei sind freiwillig; ohne sie bleiben die entsprechenden Spalten leer. Die vier Spalten für Handarbeit — Tags,
Aufbewahrung, Status und Notiz — füllst du danach in Sheets.

**Reihenfolge:** Register 5 vor Register 8 ausführen und dort **Liste sichern** nicht vergessen,
sonst lässt sich die Herkunft der Bilder später nicht mehr rekonstruieren.

**Der Abgleich** in Register 9 ist der Nachweis, dass der Upload aus Phase 6 vollständig war.
Links die Sammelplatte, rechts der Drive-Ordner, den *Google Drive für Desktop* als Laufwerk
in den Explorer hängt — meist `G:\`. Verglichen wird Datei für Datei über den Pfad, gezählt
wird je **Quelle**, also je Ordner der ersten Ebene. Jede Quelle bekommt eine Zeile mit
Anzahl hier, Anzahl in Drive und der Abweichung in Prozent; was über **einem Prozent** liegt
oder eine fehlende Datei enthält, wird mit `!` markiert — die Schwelle aus dem Vorgehensplan.
Dazu kommt die **Stichprobe**: fünf Dateien je Quelle werden auf beiden Seiten gelesen und
ihre Prüfsummen verglichen. Das ist der Teil, den reines Zählen nicht leisten kann — eine
Datei kann richtig heissen und die richtige Grösse haben und trotzdem eine leere Hülle sein.
Die Proben sind über die Unterordner verteilt, nicht die ersten fünf, und grosse Dateien
bleiben aussen vor, solange es kleine gibt: jede Probe muss aus Drive heruntergeladen werden.
Der Bericht als CSV nennt jede Fundstelle einzeln — fehlt in Drive, nur in Drive, Grösse
weicht ab, Stichprobe — und ist damit das Dokument für „fertig". Verändert wird nichts.

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

Die Prüfung bedient dabei die **echte Oberfläche** — Felder füllen, Knopf drücken,
Ergebnis aus der Tabelle lesen —, nicht die Funktionen darunter. Nur so fallen Fehler auf,
die zwischen Fenster und Logik sitzen; genau dort steckten die, die zuletzt gefunden wurden.
**137 Prüfungen, alle grün.**

Die Prüfung liegt im Repository und lässt sich jederzeit wiederholen:

```
python3 tool/pruefung/alles.py --schnell       # knapp fünf Minuten
xvfb-run -a python3 tool/pruefung/alles.py     # alles, ohne Bildschirm
```

Was sie im Einzelnen tut, steht in [tool/pruefung/README.md](pruefung/README.md).

| Register | Prüfung | Ergebnis |
|---|---|---|
| 1 · Inventur | 2.914 Dateien, Aufteilung, beide CSV-Listen | Anzahl und Volumen exakt; `faehrt_mit` 2.843; Register der Nichtübernommenen 71 mit richtigem Grund je Zeile |
| 2 · Regeln | Endung ergänzen, erproben, zurücksetzen | Regeländerung greift sofort (2.843 → 2.651), *Auslieferungszustand* stellt die Listen her |
| 3 · Sammeln | 2.843 Dateien kopiert | Probelauf = Ausführung, Quelle unverändert, Stichproben byteweise gleich, Umlaute und neun Ebenen tiefe Pfade heil, Wiederholung überspringt alle in 0,6 s |
| 4 · Dubletten | 139 Gruppen, 150 Fallen | alle 139 gefunden, keine erfunden, keine Falle zugeschnappt, Original überall nach der Vorrangregel |
| 5 · Bilder | 344 Bilder mit bekanntem Jahr | jedes Jahr und jede Herkunft richtig; EXIF schlägt widersprechendes Dateidatum; 40 Namensgleiche nummeriert, keine verloren |
| 5b · Ähnliche | 200 Vorlagen à drei Fassungen, 400 Einzelbilder | bei *normal* 196 von 200 gefunden, 5 Gruppen mit Fremdem — siehe unten |
| 5b · Streifensuche | 20.000 Fingerabdrücke gegen jeden-mit-jedem | dieselben Paare bei allen drei Schärfen; ein Streifen mehr als erlaubte Bits; 6.000 völlig gleiche Bilder bilden eine Gruppe mit allen |
| HEIC | 4 echte Dateien aus dem Netz, 4 selbst gebaute | Bildgrösse wie ImageMagick; Aufnahmedatum eines iPhone-Fotos richtig; HEIC, JPEG und PNG desselben Motivs in einer Gruppe, jedes mit seiner wirklichen Bildgrösse; der Schalter für die Vorschaubilder greift auch im zweiten Lauf |
| 7 · Kategorien | Ordner mit bekannter Kategorie | richtig, Volumen schlägt Anzahl |
| 8 · Index | 344 Zeilen, 18 Spalten | jede Dubletten- und jede Ähnlichkeitsangabe an der richtigen Datei, keine an einer unbeteiligten |
| 9 · Abgleich | Kopie des Archivs, erst unversehrt, dann mit bekannten Schäden | gleicher Baum: keine Abweichung, jede Probe nachgerechnet; zwei entfernte, eine beschnittene und eine fremde Datei werden genau benannt; gleich gross bei anderem Inhalt findet nur die Stichprobe |
| Mehrere Kerne | Abdrücke in Hilfsprozessen, dazu die drei Fälle, in denen es schiefgeht | bitgleiche Abdrücke und dieselben Gruppen wie auf einem Kern; keine Helfer, wenn es sich nicht lohnt; Weiterrechnen, wenn keiner startet; Aufgeben bei einem stummen Helfer, ohne Prozessleiche |
| Explorer | 7 Filter- und Vergleichsproben, Kopieren | jede Zahl mit unabhängiger Nachzählung deckungsgleich; 5 markierte Dateien kopiert, Quelle unverändert |
| Abbrechen | mitten im Lauf gestoppt | keine halbe Datei, Quelle unverändert |
| Quarantäne | 381 Duplikate verschoben | alle wieder auffindbar, nichts verschwunden |
| Einstellungen | Grenze und Fäden | über einen Neustart hinweg gemerkt |
| Abdruck-Speicher | Abschneiden, Aufräumen, Abbruch | beim Abschneiden bleiben die neu berechneten; nach einem vollständigen Lauf werden verschwundene Dateien vergessen, nach einem Abbruch nichts |

Tempo an diesem Bestand: Inventur 0,4 s · Sammeln 4,6 s · Wiederholung 0,6 s ·
Dubletten 2,1 s · Bilder 1,2 s · Index 0,4 s.

### Was diese Prüfung gefunden hat

Sechs Fehler, alle behoben. Zwei davon hätten beim ersten echten Lauf zugeschlagen:

- **Jedes Register verweigerte den zweiten Vorgang.** Nach einem beendeten Lauf meldete
  es „Es läuft noch ein Vorgang" und tat nichts mehr — also genau beim Weg
  *Probelauf, dann Ausführen*, der überall empfohlen wird. Ein fertiger Vorgang wurde nie
  aus der Hand gelegt und galt weiter als laufend. Dass es vorher nicht auffiel, liegt an
  den früheren Prüfungen: die starteten jedes Register nur einmal.
- **Der Quarantäne-Knopf konnte auf den vorigen Ordner wirken.** Wer den Ordner wechselt
  und sich vertippt, bekommt beim Suchen eine Warnung — der Knopf daneben hätte danach
  die Treffer des alten Ordners verschoben. Jetzt prüft er, woher die Treffer stammen, und
  sagt es, statt zu handeln.
- **Die Inventur ignorierte die Videoregel** in ihrer Zusammenfassung und in der Spalte
  `faehrt_mit` — und widersprach damit dem Register der Nichtübernommenen gleich daneben,
  das dieselben Dateien mit Grund *video* führte.
- **Der Knopf „Register der Übergrossen"** schrieb in Wahrheit alles, was nicht mitfährt,
  mit Begründung. Jetzt heisst er auch so.
- **Der Explorer meldete seine Knöpfe nicht an:** während des Kopierens blieb alles
  bedienbar, und einen Abbrechen-Knopf gab es dort gar nicht.
- **Drei Stellen lasen Eingabefelder aus dem Arbeitsfaden heraus** (die beiden
  Quarantäne-Knöpfe und das Kopieren im Explorer). In der Praxis geht das meist gut,
  zugesichert ist es nicht.

### Was das Durchsehen des Codes gefunden hat

Fünf weitere Fehler, alle behoben und alle mit einer eigenen Prüfung versehen. Sie hatten
eines gemeinsam: keiner meldete sich.

- **Viele gleiche Bilder fielen still durch.** Die Suche nach Ähnlichen zerlegt die
  Fingerabdrücke in Streifen und vergleicht nur, wer sich einen Streifen teilt. Enthielt
  ein Streifen mehr als 4.000 Einträge, wurde er übersprungen — ohne ein Wort. Gerade
  Fassungen derselben Aufnahme landen aber zwangsläufig im selben Streifen: gemessen
  ergaben 4.001 gleiche Fingerabdrücke **null Paare** statt acht Millionen, und Register 5b
  meldete „keine Gruppen". Jetzt werden völlig gleiche Abdrücke zuerst zusammengefasst und
  nur verschiedene gegeneinander gehalten; das ist nicht bloss richtig, sondern auch
  schneller. Bleibt ein Streifen trotzdem zu gross — dafür müssten einander über 20.000
  Bilder ähneln —, sagt das Programm es in einem Fenster und in der Statuszeile.
- **Die Schärfe *weit* war nicht vollständig.** Die Abkürzung trägt nur, wenn es einen
  Streifen mehr gibt als erlaubte Abweichungen; eingetragen war eine Obergrenze von acht
  Streifen, *weit* erlaubt aber neun Bit. Gemessen gingen dadurch 1,6 % der Paare im
  Abstand 9 und 0,5 % im Abstand 8 verloren — genau die weit entfernten Fassungen, für die
  man *weit* überhaupt einschaltet. Jetzt sind es zehn Streifen, und die Prüfung rechnet
  jede der drei Schärfen einzeln nach.
- **PNG meldete eine falsche Bildgrösse.** Gemeldet wurden die Masse des Rechenrasters mal
  acht, also die wirkliche Grösse aufgerundet auf das nächste Vielfache von acht: ein Bild
  mit 1200 × 900 Punkten stand als 1200 × 904 in der Tabelle und in der CSV. Bei JPEG
  stimmte es. Da die Pixelzahl auch darüber entscheidet, welche Fassung ihre Gruppe
  anführt, konnte ein PNG sich so an die Spitze schieben.
- **Der Schalter „Vorschaubilder der Kamera nutzen" blieb oft ohne Wirkung.** Der
  Zwischenspeicher wurde nur über Grösse und Datum geprüft. Wer den Schalter abwählte, weil
  er dem Ergebnis nicht traute, bekam für jede bereits berechnete Datei denselben
  Vorschau-Abdruck zurück — der Lauf dauerte gleich lang und meldete weiter *per
  Vorschaubild*. Bei HEIC ging der Schalter überhaupt nicht ein. Jetzt wird ein gemerkter
  Vorschau-Abdruck verworfen, sobald man ihn abwählt, und HEIC hält sich daran.
- **Der Speicher der Bildabdrücke hätte sich selbst blockiert.** Er merkt sich bis zu
  400.000 Abdrücke; war die Zahl erreicht, brach das Schreiben in der vorhandenen
  Reihenfolge ab — und das sind die aus der Datei geladenen alten Einträge. Die im Lauf eben
  berechneten fielen hinten herunter, und jeder weitere Lauf hätte dieselben Bilder wieder
  von Null gerechnet. Einträge zu gelöschten oder verschobenen Dateien wurden ausserdem nie
  entfernt, die Datei wuchs also nur. Jetzt fliegen zuerst die Einträge heraus, die der
  laufende Durchgang nicht gebraucht hat, und nach einem **vollständigen** Lauf werden
  unangetastete Einträge aus dem geprüften Ordner vergessen — die Dateien liegen dort nicht
  mehr. Nach einem Abbruch wird nichts vergessen: dort heisst *unangetastet* nur, dass es
  nicht weiterging. Bei 20.000 Fotos wäre das nie aufgefallen; über Jahre an vier Rechnern
  und mehreren Platten schon.

Nebenbei: die Paarsuche zählt die abweichenden Bits jetzt mit `int.bit_count` statt über den
Umweg `bin(...).count("1")`. Das ist siebenmal schneller und fängt die zusätzlichen Streifen
mehr als auf — 20.000 Fingerabdrücke bei *normal* in 0,3 statt 1,4 Sekunden.

### Welche Schärfe in Register 5b

An 1.000 Bildern — 200 Vorlagen in je drei Fassungen (voll, halb, viertel) und 400
Einzelbildern (`python3 tool/pruefung/mach_bilder.py 200`; im Standardlauf sind es 120
Vorlagen und 240 Einzelbilder):

| Schärfe | Vorlagen gefunden | Gruppen mit Fremdem darin | Fassungen unvollständig |
|---|---|---|---|
| streng (3 Bit) | 175 von 200 | **1** | 113 |
| **normal (6 Bit)** | **196 von 200** | 5 | 35 |
| weit (9 Bit) | 147 von 200 | 73 | 11 |

*normal* ist die Voreinstellung. *streng* lässt viertelgrosse Fassungen liegen, *weit* wirft
zu viel zusammen — und zwar seit der Korrektur der Streifenzahl noch etwas mehr als vorher,
weil es jetzt wirklich alles findet, was neun Bit entfernt liegt. Der Prüfbestand ist dabei
härter als echte Fotos: alle 1.000 Bilder sind nach demselben Muster erzeugt und sehen
einander von Haus aus ähnlich — ein Teil der beanstandeten Gruppen enthält Bilder, die auch
ein Mensch für Varianten desselben Motivs hielte. Bei Urlaubsfotos liegen fremde Aufnahmen
deutlich weiter auseinander. Die Zahlen stammen aus einem frisch gebauten Prüfbestand; ein
anderer Satz Zufallsbilder verschiebt sie um ein paar Zähler.

**Mehrere Kerne.** Das Rechnen der Abdrücke ist reine Rechenarbeit, und Python rechnet in
einem Prozess nur auf einem Kern — Fäden bringen hier nichts, Prozesse schon. Das Programm
startet sich deshalb selbst noch einmal als Hilfsprozess, so oft wie unter **Fäden**
eingestellt, schickt Pfade hinein und bekommt Abdrücke heraus. Gemessen: 600 Bilder in 15,7
statt 5,2 Sekunden, und 30 Zwölf-Megapixel-Fotos ohne Vorschaubild in **13,9 statt 42,4
Sekunden** — bei bitgleichen Abdrücken und denselben Gruppen.

Ob es sich lohnt, wird gemessen statt geschätzt: ein paar Bilder rechnet das Programm selbst
und rechnet die Zeit hoch. Liegt die Restzeit unter acht Sekunden, startet es gar keine
Hilfsprozesse — die gebaute Datei entpackt sich bei jedem Start selbst, und das kostet mehr
als es bringt. Aus demselben Grund bekommt jeder Helfer eine ganze Scheibe der Arbeit statt
einzelne Dateien. Antwortet der erste Helfer nicht innerhalb von 30 Sekunden, werden die
übrigen nicht mehr gestartet und das Programm rechnet allein weiter; dasselbe, wenn sich
überhaupt kein Hilfsprozess starten lässt. Wer es nicht will, nimmt das Häkchen *mehrere
Kerne nutzen* weg.

Tempo: 1.000 Bilder à 0,3 Megapixel in 26 Sekunden auf einem Kern, beim zweiten Lauf aus dem
Gedächtnis unter einer Sekunde. Ein Zwölf-Megapixel-Foto braucht auf einem Kern 0,3 bis 1,7
Sekunden, wenn das ganze Bild gerechnet werden muss — und 3 Millisekunden, wenn das
Vorschaubild der Kamera taugt. Das
Vergleichen selbst fällt kaum ins Gewicht: 20.000 Fingerabdrücke brauchen 0,3 Sekunden statt
113 Sekunden für jeden-mit-jedem, und finden dabei nachweislich dieselben Paare — bei allen
drei Schärfen, nicht nur bei *normal*.

Umlaute und 164 Zeichen lange Pfade blieben heil, die Quelle war nach jedem Lauf unverändert.

Früher gefunden und ebenfalls behoben: Register 8 brach am Ende jedes Laufs mit einer
Fehlermeldung ab, weil beim Umbau ein alter Name stehen geblieben war, und drei Register
lasen ihre Einstellungen aus dem Arbeitsfaden heraus direkt aus den Eingabefeldern.

Jedes Register wurde ausserdem in beiden Fenstergrössen angesehen — in voller Grösse und
auf dem kleinsten zulässigen Mass. Nichts wird abgeschnitten, jede Schaltfläche bleibt
erreichbar.

## Selbst starten, ohne den Build abzuwarten

Wenn Python auf dem Rechner ist, geht es auch direkt:

```
python tool/dateiumzug.py
```

Es werden nur Module der Standardbibliothek verwendet, es ist nichts nachzuinstallieren.

## Wenn etwas schiefgeht

Stürzt das Programm ab, schreibt es `dateiumzug-fehler.txt` in dein Benutzerverzeichnis
(`C:\Users\<Name>\`). Diese Datei enthält den Grund.
