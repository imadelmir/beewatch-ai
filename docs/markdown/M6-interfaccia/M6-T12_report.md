# M6 - T12 · Pagina Report ed esportazione

> **Milestone** M6 · Interfaccia Streamlit
> **Task** M6-T12 (issue #58, P3)
> **Stato** completata
> **Commit** `feat(m6): add the Report page with three templates, an archive and CSV/XLSX/PDF export`
> **Collegati** → `app/pages/7_Report.py` · `beewatch/report.py` · `beewatch/services.py` · `sql/schema_04_report.sql`

## Obiettivo

Dalla issue: «pagina Report con tre modelli (mensile, analisi produzione, stato sanitario), archivio
dei report generati ed esportazione in CSV, XLSX e PDF tramite `st.download_button`». La issue non ha
caselle compilate: la Definition of Done usata è in fondo.

## Cosa c'è

**La pagina** (`app/pages/7_Report.py`, settima voce del menu):

- **Nuovo report**: il modello (con una riga che dice cosa contiene), mese e anno per il mensile, e il
  bottone; ogni report generato si salva subito nell'archivio;
- **Archivio**: quanti report ci sono, quale aprire (dal più recente; dopo un report nuovo si apre
  quello), la sintesi e le tabelle, tre bottoni **Scarica in CSV / Excel (XLSX) / PDF**, ed «Elimina»
  con la conferma esplicita (ricontrollata nel codice, come in Alveari).

**I tre modelli** (`Servizi.crea_report`, tabelle composte con pandas):

| Modello | Sintesi | Tabelle |
|---|---|---|
| **Report mensile** | ispezioni, alveari ispezionati («2 di 4»), ispezioni con rischio medio o alto, miele raccolto | ispezioni del mese, raccolti del mese |
| **Analisi della produzione** | miele in tutto, anni con raccolti, alveari, media per alveare, anno migliore | per anno e tipo di miele; per alveare (con «Intero apiario») |
| **Stato sanitario** | alveari, in salute, da controllare (mai o da oltre 30 giorni), con rischio medio o alto all'ultima ispezione | per alveare: stato, ultima ispezione, giorni, rischio, peso |

**Le esportazioni** (`beewatch/report.py`): un report è sintesi più sezioni, con valori grezzi (numeri
come numeri), e ogni formato li scrive a modo suo:

- **CSV**: separatore «;» e virgola decimale, come lo apre Excel in italiano, con il BOM UTF-8;
- **XLSX** (`openpyxl`): un foglio per la sintesi e uno per sezione, intestazioni in grassetto,
  **numeri veri** (si possono sommare); nomi dei fogli nelle regole di Excel (31 caratteri, unici);
- **PDF** (`fpdf2`): titolo, sintesi, tabelle, avvertenza; con i font standard del PDF, che coprono il
  latino-1: «— … ’ €» si traducono, gli accenti e «« »» restano.

**L'archivio** (`sql/schema_04_report.sql`, `ReportRepository`): il contenuto si salva come JSON
**com'era alla generazione**: riaprire un report un mese dopo dà gli stessi numeri. Cancellando
l'utente spariscono i suoi report (GDPR art. 17, `ON DELETE CASCADE`).

## Decisioni

**1. Un report è una fotografia, non una richiesta da rifare.** Per questo l'archivio salva il
contenuto, non i parametri: un report di ottobre resta quello anche dopo nuove ispezioni.

**2. Due dipendenze in Python puro, bloccate**: `openpyxl>=3.1,<4` e `fpdf2>=2.8,<3`. Provate prima su
questo PC (il controllo applicazioni di Windows può bloccare le estensioni compilate): nessuna delle
due ne ha, e Pillow (che `fpdf2` usa) resta la versione già installata.

**3. Niente font esterni nel PDF**, come per l'interfaccia (§13 della specifica): i font standard del
PDF non richiedono file. Il prezzo: i caratteri fuori dal latino-1 (emoji, lineette lunghe) si
traducono o diventano «?»; nei report ci sono solo testi nostri e codici degli alveari.

**4. Le etichette (stato, rischio, mesi) le ha anche `services.py`**, perché il report si scrive fuori
dall'interfaccia: un test controlla che coincidano con quelle di `ui.py`.

**5. Un difetto trovato dai test**: `mese=0` diventava «il mese corrente» (`mese or oggi.month`), invece
di essere rifiutato. Ora vale solo `None` come «non indicato».

## Come si prova

| Cosa | Dove |
|---|---|
| struttura (salva e rilegge, nome del file), CSV (BOM, «;», virgola decimale, sezioni, avvertenza), XLSX (fogli, grassetto, numeri veri, nomi dei fogli), PDF (valido, caratteri fuori dal latino-1), report vuoti, formato ignoto | `tests/test_report.py` |
| i tre modelli con i dati di prova calcolati a mano, apiario vuoto, errori con il campo (modello, apiario altrui, mese, anno), archivio (ordine, fotografia, altri utenti, eliminare), esportazione dal servizio | `tests/test_servizi_report.py` |
| su MySQL: archivio, JSON identico, cancellazione a cascata con l'utente; i tre report sull'apiario del seed in tutti e tre i formati | `tests/test_servizi_report.py` (integration) |
| la pagina: archivio vuoto, generare e scaricare, i tre modelli, riaprire un report precedente, eliminare con conferma, nessun apiario, database spento, salvataggio fallito | `tests/test_pagina_report.py` |

## File coinvolti

| File | Azione |
|---|---|
| `app/pages/7_Report.py` | creato |
| `app/Home.py` | la voce Report nel menu |
| `app/avvio.py` | letture in cache dell'archivio |
| `beewatch/report.py` | creato |
| `beewatch/services.py` | `crea_report`, `archivio_report`, `report_salvato`, `elimina_report`, `esporta_report` |
| `beewatch/repositories_riferimento.py` | `ReportRepository` |
| `sql/schema_04_report.sql` | creato |
| `requirements.txt`, `pyproject.toml` | `openpyxl`, `fpdf2` |
| `docs/markdown/M6-interfaccia/ui_spec.md` | §7: navigazione con l'accesso e la settima pagina |
| `tests/test_report.py`, `tests/test_servizi_report.py`, `tests/test_pagina_report.py`, `tests/report_finto.py` | creati |
| `tests/anagrafica_finta.py`, `tests/app_finta.py`, `tests/test_app_struttura.py`, `tests/test_app_streamlit.py` | adeguati |
| `README.md` | la pagina Report |

## Definition of Done (ricavata dalla descrizione della issue)

| Voce | Esito |
|---|---|
| tre modelli: mensile, analisi produzione, stato sanitario | fatto |
| archivio dei report generati | fatto, con riapertura ed eliminazione |
| esportazione in CSV, XLSX e PDF con `st.download_button` | fatto; i tre bottoni per ogni report |
