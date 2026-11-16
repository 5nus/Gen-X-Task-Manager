# Gen X Task Manager — V1

Ein Linux-Task-Manager im Windows-95-Look: Aufgaben erstellen, bearbeiten, nach
Priorität sortieren und nach Bestätigung dauerhaft löschen. Mit Kalender,
Uhrzeitauswahl, Linux-Desktop-Erinnerungen und Harold P. Wiggins, einem grundsätzlich
abwesenden Büroangestellten in einem separaten Messenger.

Erinnerungen laufen unabhängig vom Hauptfenster. Harold bleibt davon getrennt:
keine Aufgabenkommentare, keine direkten Antworten, keine KI oder Netzwerkverbindung.

## Voraussetzungen und Start

- Python 3.9 oder neuer mit Tkinter und SQLite; getestet mit Python 3.12 und Tk 8.6.
- Für Erinnerungen: systemd mit User-Manager, ein D-Bus-Session-Bus, `notify-send`
  und ein Desktop-Benachrichtigungsdienst, beispielsweise von GNOME, KDE oder Xfce.
- Anwendung und Tests verwenden ausschließlich Python-Standardbibliothek.
  Auf Debian/Ubuntu liefern `python3-tk` und `libnotify-bin` die benötigten Werkzeuge.
  Es ist keine Installation über pip erforderlich.

```bash
git clone https://github.com/5nus/Gen-X-Task-Manager.git
cd Gen-X-Task-Manager
PYTHONPATH=src python3 -m task_manager
```

Ohne aktivierten Reminder-Dienst funktioniert die GUI weiterhin. Das alleinige
Eintragen einer Erinnerung aktiviert keinen Hintergrundprozess.

## Datenbankpfad

GUI und Reminder verwenden dieselbe Pfadermittlung, in dieser Reihenfolge:

1. Expliziter Parameter `--database`.
2. Umgebungsvariable `TASK_MANAGER_DATABASE`.
3. `$XDG_DATA_HOME/task-manager/tasks.sqlite3`, ansonsten
   `~/.local/share/task-manager/tasks.sqlite3`.

```bash
PYTHONPATH=src python3 -m task_manager --database /absolute/path/tasks.sqlite3
PYTHONPATH=src python3 -m task_manager.reminder --database /absolute/path/tasks.sqlite3
```

Die GUI erstellt Verzeichnis und Schema bei Bedarf. Der Reminder erstellt keine
leere Ersatzdatenbank: Fehlt die Datei, protokolliert er den Pfad und wartet auf
seinen nächsten Aufruf. Alte Entwicklungsschemas werden nicht migriert oder
ungefragt gelöscht. Das kompatible V1-Schema erhält automatisch einen Index für
noch offene Erinnerungen.

**Bei einem eigenen GUI-Pfad muss derselbe absolute Pfad auch im Reminder
konfiguriert werden.** Ein `--database`-Argument der GUI wird nicht automatisch an
einen unabhängig gestarteten systemd-Prozess übertragen.

## Erinnerungen aktivieren

### 1. User-Units installieren

Diese Befehle im Repository-Verzeichnis als normaler Desktop-Benutzer ausführen,
**ohne sudo**:

```bash
mkdir -p "$HOME/.config/systemd/user" "$HOME/.config/gen-x-task-manager"
install -m 644 systemd/gen-x-task-reminder.service "$HOME/.config/systemd/user/"
install -m 644 systemd/gen-x-task-reminder.timer "$HOME/.config/systemd/user/"
```

Beim ersten Einrichten den tatsächlichen Repository-Pfad konfigurieren:

```bash
printf 'PYTHONPATH="%s/src"\n' "$PWD" > "$HOME/.config/gen-x-task-manager/reminder.env"
```

Die Datei ist eine systemd-EnvironmentFile, kein Shell-Skript. Wird das Repository
verschoben, muss `PYTHONPATH` dort angepasst werden. Bereits vorhandene eigene
Konfigurationen stattdessen bearbeiten, damit sie erhalten bleiben.

Für eine benutzerdefinierte Datenbank diese zusätzliche Zeile in
`~/.config/gen-x-task-manager/reminder.env` eintragen:

```ini
TASK_MANAGER_DATABASE="/absolute/path/tasks.sqlite3"
```

Kein `export`, keine Shell-Variablen wie `$HOME` und keine relative Pfadangabe in
dieser Datei verwenden. Die GUI anschließend mit demselben `--database`-Pfad
starten oder `TASK_MANAGER_DATABASE` auch in ihrer Umgebung setzen. Ohne eigene
Datenbankkonfiguration verwenden beide den Standardpfad.

### 2. Grafische Sitzung übernehmen und Timer starten

Im Terminal der tatsächlichen grafischen Sitzung:

```bash
systemctl --user import-environment DISPLAY WAYLAND_DISPLAY XAUTHORITY XDG_DATA_HOME
systemctl --user daemon-reload
systemctl --user enable --now gen-x-task-reminder.timer
systemctl --user start gen-x-task-reminder.service
```

Meldungen über nicht gesetzte Variablen sind bei der jeweils anderen Display-Art
normal: X11 braucht beispielsweise kein `WAYLAND_DISPLAY`. Mindestens `DISPLAY`
oder `WAYLAND_DISPLAY` muss im User-Manager gesetzt sein. Der Service verwendet
`unix:path=%t/bus`, also den D-Bus-Bus desselben Benutzers, ohne eine feste
Display-Nummer vorauszusetzen. `XDG_DATA_HOME` wird mit übernommen, damit ein eigener
Standard-Datenordner auch vom Dienst verwendet wird.

Die Units sind an `graphical-session.target` angebunden. Bei Desktops, die dieses
Target verwalten, startet der aktivierte Timer mit der grafischen Sitzung und
stoppt mit ihr. Prüfung:

```bash
systemctl --user is-active graphical-session.target
```

**Xfce und andere Sitzungen ohne aktives Target:** Zusätzlich den mitgelieferten
XDG-Autostart-Eintrag installieren:

```bash
mkdir -p "$HOME/.config/autostart"
install -m 644 systemd/gen-x-task-reminder.desktop "$HOME/.config/autostart/"
```

Er übernimmt beim nächsten grafischen Login die Sitzungsvariablen und startet
denselben Timer. Wiederholtes Starten erzeugt keinen zweiten Timer. In der
aktuellen Sitzung gelten die obigen Import-/Startbefehle. Ein reiner SSH-Login
ersetzt keine grafische Sitzung. `loginctl enable-linger` ist nicht erforderlich;
Benachrichtigungen während vollständiger Abmeldung sind kein Zustellziel.

### 3. Status und Logs prüfen

```bash
systemctl --user status gen-x-task-reminder.timer
systemctl --user list-timers --all gen-x-task-reminder.timer
systemctl --user status gen-x-task-reminder.service
journalctl --user -u gen-x-task-reminder.service -n 50 --no-pager
```

Der Service ist ein kurzer `Type=oneshot`-Prozess und zwischen erfolgreichen
Prüfläufen normalerweise `inactive (dead)`. Der Timer soll dagegen aktiv sein.
Fehler beim Benachrichtigen führen zu Exit-Code 1 und bleiben im Journal sichtbar;
der nächste Timer-Lauf versucht offene Erinnerungen erneut.

Zum manuellen Test außerhalb von systemd, mit dem gewählten Datenbankpfad:

```bash
PYTHONPATH=src python3 -m task_manager.reminder --database /absolute/path/tasks.sqlite3
```

Dieser Befehl läuft genau einmal und beendet sich danach. Er benötigt kein Tkinter.

### Fehler eingrenzen

- **Keine Datenbank gefunden:** Den im Journal genannten absoluten Pfad mit dem
  GUI-Aufruf und `reminder.env` vergleichen.
- **Python-Modul fehlt:** `PYTHONPATH` muss auf das vorhandene `src`-Verzeichnis
  des Repositorys zeigen. Nach einer Konfigurationsänderung den Service erneut starten.
- **Kein grafisches Display / kein D-Bus:** Die Sitzungsvariablen aus einem
  Desktop-Terminal erneut importieren; bei Xfce den Autostart-Eintrag verwenden.
- **`notify-send` fehlt:** Das Systempaket installieren, unter Debian/Ubuntu
  `libnotify-bin`. Für dieses Problem ist keine Python-Bibliothek nötig.
- **Benachrichtigungsaufruf scheitert oder läuft in ein Timeout:** Den normalen
  Desktop-Dienst prüfen. Ein direkter Test im grafischen Terminal ist:

  ```bash
  notify-send -- "Task Reminder" "Manual notification test"
  ```

- **Aufruf erfolgreich, trotzdem kein sichtbares Banner:** Nicht-stören-Modus,
  Benachrichtigungseinstellungen und das Benachrichtigungszentrum des Desktops prüfen.
  Ein akzeptierter Aufruf ist kein Nachweis, dass jemand die Meldung gesehen hat.
- **`database is locked`:** Ein Schreibzugriff wartet auf einen anderen. Die GUI
  meldet einen Fehler ohne Teiländerungen; nach Ende des konkurrierenden Zugriffs
  erneut speichern. Der Reminder hält seine Schreibsperre während eines auf
  fünf Sekunden begrenzten Benachrichtigungsaufrufs.

### Deaktivieren

```bash
systemctl --user disable --now gen-x-task-reminder.timer
systemctl --user stop gen-x-task-reminder.service
```

Falls der XDG-Autostart-Eintrag installiert wurde, ihn in den
Autostart-Einstellungen des Desktops deaktivieren oder
`~/.config/autostart/gen-x-task-reminder.desktop` entfernen. Andernfalls würde er
beim nächsten Login den Timer wieder starten. Aufgaben und Erinnerungsdaten bleiben
beim Deaktivieren erhalten.

## Ablauf und Zustellgrenzen

Ein User-Timer startet ungefähr jede Minute einen kurzen Prüflauf. Zwischen den
Läufen läuft kein zusätzlicher Python-Prozess. Das ist für V1 einfacher als ein
ständig laufender Daemon mit eigener Schleife, Neustartlogik oder Threads.
`OnStartupSec=10s` sorgt für einen ersten Lauf; `OnUnitInactiveSec=60s` und
`AccuracySec=5s` für weitere Prüfungen. Es gibt keine sekundengenaue Termingarantie.
Der Timer weckt den Rechner nicht aus dem Standby.

1. Eine indexgestützte SQL-Abfrage wählt ausschließlich fällige, noch nicht
   versendete Aufgaben mit gesetztem `remind_at`. Vergleiche erfolgen in UTC.
2. Für jede Aufgabe beginnt eine kurze SQLite-Transaktion mit `BEGIN IMMEDIATE`.
   Darin werden Existenz, Zeitpunkt und Versandstatus erneut gelesen. Bereits
   gelöschte, verschobene oder inzwischen verarbeitete Erinnerungen werden übersprungen.
3. `notify-send` übergibt „Task Reminder“ und den aktuellen Aufgabentitel an den
   Desktop-Dienst. Argumente werden ohne Shell übergeben; Titel-Markup wird maskiert.
4. Erst nach erfolgreichem Aufruf wird `reminder_sent` für den erwarteten Zeitpunkt
   gesetzt und die Transaktion committed. Aufruf- oder Datenbankfehler lassen den
   Status offen. Andere Reminder-Prozesse und GUI-Schreiber werden dabei serialisiert.

`notify-send` verwendet den üblichen Linux-Benachrichtigungsdienst und erspart
eine zusätzliche D-Bus-Python-Bibliothek. Die Schnittstelle ist in der
[Desktop Notifications Specification](https://specifications.freedesktop.org/notification/latest/protocol.html)
beschrieben; Optionen dokumentiert die [notify-send-Manpage](https://manpages.debian.org/trixie/libnotify-bin/notify-send.1.en.html).
Timer und Sitzungseinbindung folgen der
[systemd-Timer-Dokumentation](https://www.freedesktop.org/software/systemd/man/latest/systemd.timer.html)
und den [Hinweisen zu Desktop-Sitzungen](https://github.com/systemd/systemd/blob/main/docs/DESKTOP_ENVIRONMENTS.md).

Während Ausschalten oder Standby überfällige Erinnerungen werden beim nächsten
geeigneten Lauf nachgeholt. Erfolgreich gespeicherte Versandstatus verhindern
erneute Meldungen bei normalen Neustarts. Fehlt die Sitzungsumgebung oder schlägt
der Benachrichtigungsaufruf fehl, bleibt die Zustellung offen. V1 richtet sich an eine grafische
Sitzung pro Benutzer; die Auswahl zwischen mehreren parallelen Desktops wird
nicht verwaltet.

**Keine Exactly-once-Garantie:** Datenbank und Desktop-Dienst besitzen keine gemeinsame
Transaktion. Ein Absturz nach Annahme der Benachrichtigung, aber vor dem Commit,
kann bei erneutem Versuch eine doppelte Meldung verursachen. Auch ein Timeout
kann auftreten, nachdem der Desktop eine Anfrage bereits angenommen hat.
Nicht-stören-Modus und andere Desktop-Regeln können sichtbare Meldungen unterdrücken.
Eine bereits abgesendete Benachrichtigung lässt sich durch späteres Löschen oder
Ändern der Aufgabe nicht zurücknehmen.

## Aufgabenbearbeitung und Persistenz

`TaskService` validiert Titel und Modellwerte vor dem Schreiben. Titel werden
getrimmt und müssen 1–200 Zeichen enthalten. `TaskService.update(id, **changes)`
übernimmt ausschließlich explizit geänderte Felder: Titel, Beschreibung, Priorität,
Fälligkeit und Erinnerungszeitpunkt. Ein Formular speichert diese gemeinsam mit
einem einzigen parametrisierten SQL-UPDATE in einer Transaktion. Bei einem Fehler
bleibt keine Teiländerung bestehen. `id` und `created_at` sind unveränderlich.

Die Service-Schicht fordert bei Änderungen des Erinnerungsfeldes einen bedingten
Reset an. Das Repository vergleicht dafür den tatsächlich gespeicherten Zeitpunkt
atomar im SQL-UPDATE. Nur ein geänderter Zeitpunkt setzt `reminder_sent=False`.
Unveränderte Erinnerungszeiten und andere Feldänderungen erhalten einen inzwischen
vom Reminder gesetzten Status. Konkurrierende Änderungen desselben Aufgabenfeldes
folgen weiterhin dem letzten Schreibzugriff. Mehrere getrennte Service-Aufrufe
bilden keine gemeinsame Formulartransaktion.

SQLite ist die einzige persistente Datenquelle. UUID4-IDs und zeitzonenbewusste
ISO-Zeitstempel liegen als Text vor; Zeitstempel sind auf UTC mit Mikrosekunden
normalisiert. Boolean-Werte liegen als 0/1 vor. Fehlende Aufgaben erzeugen im
Service `KeyError`, ungültige Werte `TypeError` oder `ValueError`. SQLite-Fehler
werden weitergegeben. Das Repository enthält keine GUI- oder Benachrichtigungslogik.

Erledigen bedeutet dauerhaft löschen. Eine Bestätigung in der GUI ist erforderlich.
Gelöschte Aufgaben erscheinen nicht mehr in der Reminder-Abfrage und veraltete
Schreibzugriffe können sie nicht wiederherstellen.

## Kalender und GUI

Die englische Oberfläche behält graue Fenster, dunkelblaue Titel, 3D-Schaltflächen
und mehrzeilige Titel. Aufgaben mit hoher Priorität stehen zuerst; Low, Normal
und High entsprechen 1, 2 und 3.

Fälligkeit und Erinnerung besitzen einen Kalender mit Monatsnavigation und Today.
Die Eingabe akzeptiert `MM/DD/YYYY`, `MM-DD-YYYY` und ISO-Daten; im US-Format steht
der Monat zuerst. Stunden und Minuten werden mit Spinboxen gewählt oder eingegeben.
Neue Eingaben verwenden die lokale Linux-Zeitzone einschließlich Sommerzeit;
Zeitpunkte in einer Sommerzeitlücke werden abgelehnt. Clear entfernt den Zeitpunkt.
Vollständige ISO-Zeitpunkte mit Offset bleiben einfügbar. Unveränderte Zeitpunkte
behalten Sekunden und Mikrosekunden.

## Harold Messenger

Harold bleibt ein separater, nicht modaler Messenger mit Pixel-Avatar, „Away“,
„Last seen: Unknown“, scrollbarem Verlauf und lokalen Uhrzeiten. Mehrfaches Öffnen
zeigt dasselbe Fenster. Der Avatar und sein Generierungsprompt liegen in
`src/task_manager/assets/` und benötigen keine zusätzliche Bildbibliothek.

Harold schreibt unabhängig von Benutzernachrichten höchstens drei belanglose
Nachrichten pro Anwendungssitzung, in zufälligen Abständen von 3–10 Minuten.
Jeder Sendeversuch öffnet einen separaten „Messenger Service“-Dialog. Diese Meldung
landet niemals im Chatverlauf; direkte Antworten von Harold gibt es nicht.
OK, Escape und das Schließen-Kreuz schließen den Systemdialog.

Verlauf und Nachrichtenlimit bleiben beim Schließen des Chats im Arbeitsspeicher.
`after()`-Timer laufen ohne Threads und werden beim Beenden der GUI abgebrochen.
Harold hat keinen Zugriff auf den Reminder-Prozess und sendet keine Desktop-Meldungen.

## Tests und Struktur

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Ohne `DISPLAY` werden GUI-Tests übersprungen. Mit Xvfb alle Tests ausführen:

```bash
xvfb-run -a env PYTHONPATH=src python3 -m unittest discover -s tests -v
systemd-analyze --user verify systemd/gen-x-task-reminder.service systemd/gen-x-task-reminder.timer
desktop-file-validate systemd/gen-x-task-reminder.desktop
```

Die automatisierten Reminder-Tests mocken alle Desktop-Benachrichtigungen. Sie
prüfen Fälligkeit, Nachholen, Fehler und Wiederholung, benutzerdefinierte Pfade,
veraltete Daten, zwei echte parallele Prozesse auf SQLite sowie vollständigen
Rollback. GUI-, Kalender-, Service-, Persistenz- und Harold-Tests laufen mit.

Prüfstand für dieses V1-Review: 103 Tests bestanden, einschließlich GUI unter
Xvfb. User-Units und XDG-Autostart-Datei bestehen ihre jeweiligen Validatoren.
Zusätzlich wurde der echte GUI-Kommandozeilenstart mit einer separaten Datenbank
geprüft. Ein temporärer systemd-User-Service konnte bei geschlossener GUI eine
echte Benachrichtigung an den Xfce-Notification-Daemon übergeben und den Status
speichern; sein zweiter Lauf sendete dieselbe Erinnerung nicht erneut.

Nicht praktisch durch Herunterfahren oder Suspend getestet wurden reale
Neustarts, Standby und der automatische Start nach erneutem Desktop-Login.
Nachholen und Wiederanlauf sind automatisiert über überfällige Daten und neue
Prozesse geprüft. Eine sichtbare Wahrnehmung durch den Benutzer wurde nicht
nachgewiesen. Der dauerhafte Reminder-Dienst wurde im Entwicklungsbenutzerkonto
nicht installiert oder aktiviert; die Praxistests verwendeten temporäre Dienste.

```text
src/task_manager/
    __main__.py          GUI-Start
    database.py          Pfadermittlung, Verbindung, Schema, Transaktionen
    models.py            Datenmodell
    repository.py        SQL und Serialisierung
    service.py           Geschäftsregeln und atomare Aufgabenbearbeitung
    reminder.py          Unabhängiger einmaliger Reminder-Lauf
    gui.py               Tkinter-Oberfläche
    date_picker.py       Kalender und Uhrzeitfelder
    harold.py            Harold Messenger, unverändert
    assets/              Harold-Avatar und Prompt
systemd/
    gen-x-task-reminder.service
    gen-x-task-reminder.timer
    gen-x-task-reminder.desktop   Optionaler XDG-Autostart
tests/                   unittest-Tests
```

Nicht Teil von V1: wiederkehrende Aufgaben, Cloud-Synchronisierung, Benutzerkonten,
Statistiken, IPC und neue GUI-Frameworks.
