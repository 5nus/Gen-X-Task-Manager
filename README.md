# Gen X Task Manager

Ein kleiner Linux-Task-Manager im Windows-95-Look: Aufgaben erstellen, bearbeiten,
nach Priorität sortieren und nach Bestätigung dauerhaft löschen. Mit Kalender,
Uhrzeitauswahl und Harold P. Wiggins, einem grundsätzlich abwesenden Büroangestellten
in einem separaten Messenger.

Die Anwendung ist eine frühe Version. Erinnerungszeitpunkte werden gespeichert;
Erinnerungsbenachrichtigungen sind noch nicht implementiert. Harold antwortet nie
direkt, verwendet keine KI und benötigt keine Netzwerkverbindung.

Python 3.9 oder neuer, Tkinter und SQLite. Anwendung und Tests verwenden
ausschließlich die Python-Standardbibliothek. Bisher getestet unter Linux mit
Python 3.12 und Tk 8.6.

## Schnellstart

Python mit Tkinter muss installiert sein; unter Debian/Ubuntu heißen die
Systempakete `python3` und `python3-tk`.

```bash
git clone https://github.com/5nus/Gen-X-Task-Manager.git
cd Gen-X-Task-Manager
PYTHONPATH=src python3 -m task_manager
```

Es ist keine Installation über pip erforderlich. Weitere Startoptionen,
Datenbankpfade und Testbefehle stehen unten.

## Struktur

```text
src/task_manager/
    __init__.py
    models.py
    database.py
    repository.py
    service.py
    gui.py
    date_picker.py
    harold.py
    assets/
        harold.png
        harold.prompt.txt
    __main__.py
tests/
    test_persistence.py
    test_service.py
    test_gui.py
    test_date_picker.py
    test_harold.py
```

## Tests ausführen

Im Projektverzeichnis:

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

GUI-Tests benötigen ein X-Display und Tkinter. Ohne `DISPLAY` werden sie
übersprungen. Für eine vollständige Ausführung auf einem System ohne Desktop:

```bash
xvfb-run -a env PYTHONPATH=src python3 -m unittest discover -s tests -v
```

## Desktop-Anwendung starten

```bash
PYTHONPATH=src python3 -m task_manager
```

Tkinter gehört zur Python-Standardbibliothek; manche Linux-Distributionen liefern
es als separates Systempaket `python3-tk` aus. Es werden keine Python-Pakete
von Drittanbietern benötigt. Xvfb wird ausschließlich für GUI-Tests verwendet.

Die Datenbank liegt standardmäßig unter
`$XDG_DATA_HOME/task-manager/tasks.sqlite3`, ansonsten unter
`~/.local/share/task-manager/tasks.sqlite3`. Ein anderer Pfad ist möglich:

```bash
PYTHONPATH=src python3 -m task_manager --database ./tasks-v1.sqlite3
```

Die GUI erstellt das übergeordnete Verzeichnis bei Bedarf. Für das vereinfachte
V1-Schema ist eine neue Datenbank zu verwenden; vorhandene Entwicklungsdatenbanken
werden nicht migriert oder automatisch gelöscht.

## Verwendung

```python
from task_manager.database import Database
from task_manager.repository import TaskRepository
from task_manager.service import TaskService

with Database("tasks.sqlite3") as database:
    service = TaskService(TaskRepository(database))
    task = service.create(title="Einkaufen", priority=2)
    service.update_title(task.id, "Lebensmittel einkaufen")
    tasks = service.list_all()
    # Erledigen bedeutet dauerhaft löschen.
    service.delete(task.id)
```

Auch beim Ausführen eigener Skripte muss `src` im Python-Suchpfad liegen,
beispielsweise durch `PYTHONPATH=src`.

## Entscheidungen und Schnittstellen

- `Task` ist eine unveränderliche Dataclass. Für geänderte Modellwerte kann
  `dataclasses.replace` verwendet werden; gespeicherte Felder werden über gezielte
  Repository-Methoden geändert. IDs werden als UUID4 erzeugt und geprüft. Titel und
  Priorität sind Pflichtfelder; es gibt keinen impliziten Prioritätswert.
- Das Modell prüft Feldtypen, Priorität 1–3 und zeitzonenbewusste Zeitstempel.
  Zeitstempel ohne Zeitzone werden mit `ValueError` abgewiesen. Alle gültigen
  Zeitstempel werden nach UTC normalisiert. `created_at` entsteht standardmäßig
  in UTC. Optionale Felder sind standardmäßig `None`, `reminder_sent` ist `False`.
- SQLite ist die einzige persistente Datenquelle. UUIDs liegen als Text,
  Boolean-Werte als 0/1 und Zeitstempel als ISO-8601-Text mit Mikrosekunden und
  explizitem UTC-Offset `+00:00` vor. Optionale Werte werden als SQL-`NULL` gespeichert.
- `Database(path)` öffnet eine Verbindung und erstellt das Schema, falls es fehlt.
  Ein vorhandenes Schema wird nicht migriert. Der Aufrufer bestimmt den Dateipfad;
  das übergeordnete Verzeichnis muss existieren. Der Kontextmanager schließt die
  Verbindung. Jede Instanz besitzt eine Verbindung und wird im erzeugenden Thread
  verwendet.
- `TaskRepository` übernimmt SQL und Serialisierung. Jede Schreiboperation führt
  eine eigene Transaktion aus: Commit bei Erfolg, Rollback bei Fehlern.
  SQL-Werte werden ausschließlich über Platzhalter übergeben.
- `create(task)` liefert die gespeicherte Aufgabe. `get(id)` liefert eine Aufgabe
  oder `None`. `list_all()` sortiert nach Priorität absteigend (3 zuerst).
  Bei gleicher Priorität folgen Erstellungszeit und ID aufsteigend.
  `delete(id)` löscht eine Aufgabe. `create()` speichert alle Anfangswerte.
- `update_title(id, title)`, `update_description(id, description)`,
  `update_priority(id, priority)` und
  `update_due_at(id, due_at)` schreiben ausschließlich das genannte Feld.
  `id` und `created_at` bleiben nach Erstellung unverändert. Ein vollständiges
  `update(task)` gibt es nicht mehr. So überschreiben veraltete Task-Objekte keine
  anderen Felder. Bei konkurrierenden Änderungen desselben Feldes gewinnt der
  letzte Schreibzugriff.
- `update_reminder(id, remind_at, *, reminder_sent)` schreibt Zeitpunkt und Status
  atomar mit einem SQL-UPDATE. Der Status ist ein expliziter Pflichtparameter.
  Der `TaskService` entscheidet, wann zurückgesetzt wird: Bei geändertem
  Zeitpunkt übergibt er `reminder_sent=False`. Das Repository trifft diese
  Geschäftsentscheidung nicht selbst. `remind_at=None` entfernt den Zeitpunkt.
- `mark_reminder_sent(id, *, expected_remind_at)` markiert ausschließlich den
  Versandstatus. Das bedingte UPDATE greift nur, wenn der gespeicherte Zeitpunkt
  dem erwarteten entspricht, der Status noch `False` ist und die Aufgabe noch
  existiert. Die Prüfung erfolgt atomar im selben UPDATE. Eine verspätete
  Markierung für einen inzwischen geänderten oder entfernten Zeitpunkt bleibt
  wirkungslos. Gezielte Schreibmethoden normalisieren Zeitstempel vor SQL nach UTC.
- Updates und `delete()` liefern `False`, wenn keine passende Zeile existiert.
  Beim Markieren bedeutet `False` auch: Zeitpunkt stimmt nicht mehr überein oder
  Erinnerung ist bereits als versendet markiert oder die Aufgabe wurde gelöscht.
  Jede Methode schreibt in einer
  eigenen Transaktion; mehrere Methoden bilden keine gemeinsame Transaktion.
- Ungültige Modellwerte erzeugen `TypeError` oder `ValueError`. SQLite-Fehler
  werden unverändert weitergegeben, beispielsweise `sqlite3.IntegrityError` bei
  doppelten IDs. Keine eigenen Fehlerklassen oder zusätzlichen Abstraktionen.

## TaskService

`TaskService(repository)` übernimmt Geschäftsregeln und verwendet ausschließlich
die vorhandenen Repository-Methoden. Er besitzt keine eigene Datenbankverbindung
und führt kein SQL aus.

- `create(title, priority, *, description=None, due_at=None, remind_at=None)`
  erzeugt eine neue Aufgabe mit UUID4, aktueller UTC-Erstellungszeit und
  `reminder_sent=False`.
- Der TaskService entfernt führenden und nachfolgenden Leerraum mit `strip()`.
  Danach müssen Titel 1 bis einschließlich 200 Zeichen enthalten. Leere Titel,
  Titel aus ausschließlich Leerraum und längere Titel werden abgewiesen.
  Die Länge wird mit Python-`len()` gezählt. Längere Inhalte gehören in das
  separate Beschreibungsfeld. Die Validierung erfolgt beim Erstellen und Bearbeiten
  im TaskService, unabhängig von einer späteren GUI.
- `get(id)` liefert eine Aufgabe; `list_all()` liefert die nach Priorität sortierte
  Liste des Repositorys.
- `update_title`, `update_description`, `update_priority` und `update_due_at`
  erhalten jeweils ID und neuen Feldwert. Sie ändern ausschließlich dieses Feld.
  Optionale Werte lassen sich mit `None` entfernen.
- `update_reminder(id, remind_at)` validiert den Zeitpunkt über das Modell und
  vergleicht ihn in UTC mit dem gespeicherten Wert. Bei Änderungen, auch beim
  Hinzufügen oder Entfernen, speichert das Repository Zeitpunkt und
  `reminder_sent=False` atomar. Bei unverändertem Zeitpunkt erfolgt kein Update;
  der Versandstatus bleibt erhalten. Verschiedene Zeitzonenangaben desselben
  Zeitpunkts gelten als unverändert.
- Erledigen bedeutet in Version 1 dauerhaft löschen. Es gibt keinen separaten
  Erledigt-Status. `delete(id)` löscht den vollständigen Datensatz einschließlich
  der Erinnerungsdaten. Veraltete Updates oder Versandmarkierungen können ihn
  nicht wiederherstellen. Ändernde Methoden liefern bei Erfolg `None`.
  Fehlende Aufgaben erzeugen `KeyError(id)`, auch wenn das Repository bei einem
  Schreibversuch keine passende Zeile mehr findet. Ungültige Werte erzeugen
  `TypeError` oder `ValueError`. SQLite-Fehler werden unverändert weitergegeben.

Mehrere Service-Aufrufe bilden keine gemeinsame Transaktion. Gezielte Updates
verhindern das Überschreiben anderer Felder; bei Änderungen desselben Feldes gilt
weiterhin der letzte Schreibzugriff.

## GUI

- Klassische Tkinter-Widgets mit grauem Hintergrund `#C0C0C0`, dunkelblauen
  Titelleisten, erhabenen Schaltflächen und vertieften Eingabefeldern erhalten
  den Windows-95-Stil. Beschriftungen und Dialoge sind kurz und englisch.
- „Add task“ und „Edit task“ öffnen Titel, Beschreibung, Priorität, Fälligkeit
  und Erinnerungszeitpunkt. Low, Normal und High entsprechen Priorität 1, 2 und 3.
  Aufgaben mit hoher Priorität stehen zuerst. Lange Titel umbrechen.
- Fälligkeit und Erinnerung besitzen je einen anklickbaren Kalender mit
  Monatsnavigation und Today-Schaltfläche. Datumeingaben akzeptieren
  `MM/DD/YYYY`, `MM-DD-YYYY` und ISO-Daten. Monat steht beim US-Format zuerst.
- Stunden und Minuten lassen sich über klassische Spinboxen auswählen oder
  eintippen. Neue Eingaben verwenden die lokale Linux-Zeitzone, einschließlich
  Sommerzeit, und das Repository speichert weiterhin UTC. Ungültige Daten,
  Uhrzeiten und lokale Uhrzeiten in einer Sommerzeitlücke werden abgelehnt.
- Vollständige ISO-Zeitpunkte mit UTC-Offset können weiterhin eingefügt werden;
  beim Verlassen des Feldes werden sie in lokale Datum- und Uhrzeitfelder
  übernommen. Unveränderte bestehende Zeitpunkte behalten Sekunden und
  Mikrosekunden. Clear oder ein leeres Datumsfeld entfernt den Zeitpunkt.
- „Delete“ verlangt eine Bestätigung. Cancel, Escape und das Schließen des
  Dialogs brechen ab. Erfolgreiches Löschen benötigt keinen weiteren Dialog.
- Validierungsfehler, fehlende Aufgaben und Datenbankfehler werden angezeigt.
  Das Formular bleibt bei Speicherfehlern offen. Änderungen mehrerer Felder
  verwenden weiterhin einzelne Repository-Transaktionen; zuvor gespeicherte
  Felder können bei einem späteren Datenbankfehler bereits geändert sein.
- „Refresh“ lädt den aktuellen Datenbankstand. Datenmodell, SQLite-Persistenz
  und TaskService bleiben unverändert.

## Harold Messenger

- „Harold Messenger“ öffnet ein separates, nicht modales Fenster mit Pixel-Avatar,
  Harold P. Wiggins, Status „Away“, „Last seen: Unknown“, scrollbarem Verlauf,
  Eingabe und Send-Button. Absender und lokale Uhrzeit stehen über jeder Nachricht;
  die Uhrzeit bleibt beim erneuten Öffnen erhalten.
  Wiederholtes Öffnen bringt dasselbe Fenster nach vorn.
- Das Avatar-Asset liegt unter `src/task_manager/assets/harold.png`: ein älterer
  Büroangestellter mit Halbglatze, grauem Haar, Brille und kariertem Hemd.
  Es wurde mit dem eingebauten Bildgenerator anhand der Vorlage erstellt;
  der verwendete Prompt liegt daneben in `harold.prompt.txt`.
  Tkinter lädt das PNG direkt, ohne zusätzliche Bibliotheken.
- Ab dem Anwendungsstart plant Tkinter mit `after()` in zufälligen Abständen von
  3 bis 10 Minuten belanglose Nachrichten. Harold schreibt höchstens drei
  Nachrichten pro Anwendungssitzung. Es gibt keine Threads oder Netzwerkzugriffe.
- Harold schreibt unabhängig von Benutzernachrichten. Er antwortet niemals direkt
  und kommentiert weder Aufgaben noch Benutzerverhalten.
- Nicht leere Benutzernachrichten erscheinen im Verlauf. Jeder Sendeversuch,
  einschließlich leerer Eingaben, öffnet ein separates „Messenger Service“-Fenster:
  „The user you are trying to contact has not been at their desk for some time.“
  Diese Meldung wird niemals im Chat angezeigt oder gespeichert.
- OK, Escape und das Schließen-Kreuz schließen nur den Systemdialog. Er bleibt
  auch beim Schließen des Chatfensters bestehen und blockiert keine anderen Fenster.
- Der Chatverlauf und Harolds Nachrichtenlimit bleiben beim Schließen und erneuten
  Öffnen des Chats erhalten. Auch bei geschlossenem Chat laufen die Timer weiter,
  ohne Fenster automatisch zu öffnen. Beim Beenden der Anwendung werden offene
  Timer abgebrochen. Eine neue Sitzung startet ohne Verlauf.
- Harold-Daten liegen ausschließlich im Arbeitsspeicher. Es gibt keine Änderungen
  an der Datenbank, keine KI, API, Desktop-Benachrichtigungen oder zusätzlichen Bibliotheken.

Reminder-Prozess, IPC, Aufgabenbenachrichtigungen und wiederkehrende Aufgaben
gehören nicht zu dieser Implementierung. Erinnerungszeitpunkte werden nur gespeichert.
