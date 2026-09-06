# M1 - T1 · Repository e convenzioni di lavoro

> **Milestone** M1 · Fondamenta e setup
> **Stato** completata
> **Commit** `M1 - T1 : initialize repository, conventions and backlog`

## Obiettivo

Mettere in piedi l'infrastruttura di lavoro **prima** di scrivere codice:
repository, regole di collaborazione, backlog completo. Un gruppo di tre persone
senza convenzioni condivise produce tre stili diversi e una cronologia illeggibile.

## Cosa è stato fatto

### Repository

Repository pubblico `imadelmir/beewatch-ai` su GitHub, con licenza MIT.

### Protezione del ramo principale

Un *ruleset* su `main` impedisce di scrivere direttamente sul ramo principale:
ogni modifica passa da una pull request. Le impostazioni:

| Regola | Valore |
|---|---|
| Richiedi una pull request | sì |
| Approvazioni richieste | 0 |
| Blocca i push forzati | sì |
| Bypass | amministratore del repository |

**Perché zero approvazioni.** La regola che conta è "nessuno scrive su `main`
senza passare da una PR": è quella che rende la cronologia leggibile. Imporre
un'approvazione in un gruppo dove non tutti fanno review davvero produrrebbe
solo bypass a ripetizione, che è peggio della regola assente.

Dopo M1-T5 si è aggiunto un secondo vincolo: la pull request non si può
completare finché il controllo automatico `Lint e test` non è verde.

### Convenzioni di collaborazione

`CONTRIBUTING.md` fissa tre cose:

**Nomi dei rami**: `<tipo>/<codice-task>-<descrizione>`

```
feat/m1-t3-config        nuova funzionalita'
fix/m2-t5-charset        correzione di un errore
docs/m2-t4-schema        solo documentazione
```

**Messaggi di commit**: il codice della task, poi una descrizione in inglese.

```
M1 - T3 : add centralized configuration with startup validation
```

Con lo *squash merge* è il **titolo della pull request** a diventare il commit
su `main`: è lì che il codice della task deve comparire.

**Flusso di lavoro**: ramo dalla `main` aggiornata → commit → push → pull
request → attesa del controllo automatico → *squash and merge* → cancellazione
del ramo.

### Moduli per issue e pull request

In `.github/`:

- `ISSUE_TEMPLATE/task.yml` — modulo per una task del backlog: codice, obiettivo,
  Definition of Done a caselle, dipendenze
- `ISSUE_TEMPLATE/bug.yml` — modulo per un difetto: cosa succede, cosa dovrebbe
  succedere, come riprodurlo
- `pull_request_template.md` — task, `Closes #`, elenco delle verifiche fatte

Servono a non dover ricordare a memoria cosa scrivere: il modulo lo chiede.

### Backlog

**55 task** distribuite su **9 milestone**, con etichette, assegnatari, priorità,
date e dipendenze. Caricate su GitHub come issue e organizzate in una board
*Projects* con quattro campi personalizzati.

Le task sono state generate da un CSV tramite `gh` (GitHub CLI): scriverle a
mano avrebbe richiesto ore e prodotto disomogeneità.

| Milestone | Contenuto |
|---|---|
| M1 | Fondamenta e setup |
| M2 | Dati e database |
| M3 | Accesso ai dati ed ETL |
| M4 | Machine Learning |
| M5 | Componente AI generativa |
| M6 | Interfaccia Streamlit |
| M7 | Qualità, Docker, etica |
| M8 | Documentazione, demo e consegna |
| MX | Estensioni opzionali |

## File e artefatti prodotti

| Dove | Cosa |
|---|---|
| GitHub | repository, ruleset su `main`, 9 milestone, 22 etichette, 55 issue, board Projects |
| `CONTRIBUTING.md` | convenzioni di ramo, commit e flusso |
| `LICENSE` | MIT |
| `.github/ISSUE_TEMPLATE/task.yml` | modulo per le task |
| `.github/ISSUE_TEMPLATE/bug.yml` | modulo per i difetti |
| `.github/pull_request_template.md` | modulo per le pull request |

Gli script che hanno generato issue e board vivono **fuori dal repository**
(`beewatch-setup/`): sono strumenti usati una volta sola, non fanno parte del
prodotto.

## Decisioni progettuali

**Il backlog sta su GitHub, non in un foglio di calcolo.** Le issue si collegano
ai commit e alle pull request: scrivere `Closes #12` chiude la task da sola. Un
foglio separato va aggiornato a mano, e nessuno lo aggiorna.

**Ogni task ha una Definition of Done a caselle.** "Fatto" è un'opinione; una
lista di verifiche no. È anche ciò che permette di riprendere una task
interrotta senza ricostruire a memoria cosa mancava.

**La cronologia si legge dall'alto.** Con lo squash merge, ogni task diventa
**un solo commit** su `main`, con il proprio codice nel titolo. `git log`
diventa il registro di avanzamento del progetto.

## Definition of Done

| Verifica | Esito |
|---|---|
| Il repository esiste ed è clonabile | ✅ |
| `main` è protetto: nessun push diretto | ✅ |
| Le convenzioni sono scritte in `CONTRIBUTING.md` | ✅ |
| I moduli per issue e PR funzionano | ✅ |
| 55 issue create, con milestone ed etichette | ✅ |
| La board Projects mostra il backlog | ✅ |

## Miglioramenti futuri

- **Etichette di stato automatiche**: far spostare le card sulla board quando la
  PR viene aperta o mergiata. Si fa con un workflow GitHub Actions; oggi il
  movimento è manuale ed è un costo trascurabile.
- **`CODEOWNERS`**: avrebbe senso in un gruppo dove ognuno ha un'area di
  competenza esclusiva. Qui le aree si sovrappongono.
