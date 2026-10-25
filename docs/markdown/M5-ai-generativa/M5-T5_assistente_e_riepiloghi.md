# M5 - T5 · Assistente e persistenza dei report

> **Milestone** M5 · Componente AI generativa
> **Task** M5-T5
> **Stato** completata (con il modello di linguaggio finto: la prova con un modello vero dipende da #26)
> **Commit** `feat(m5): add the inspection assistant and persist the AI summaries`
> **Collegati** → [`M5-T3_schema_e_parser.md`](M5-T3_schema_e_parser.md) · [`M5-T4_prompt.md`](M5-T4_prompt.md) · `beewatch/ai/assistant.py` · `beewatch/services.py`

## Obiettivo

Dall'id di un'ispezione al riepilogo AI salvato, con tutta la tracciabilità: chi l'ha prodotto (provider,
modello, versione del prompt), quanto è costato (durata, token), e con quali dati. La logica dell'AI sta
in `beewatch/`, non nelle pagine Streamlit: la pagina chiama `Servizi.genera_riepilogo_ispezione` e
mostra il risultato.

## Il flusso

```
Servizi.genera_riepilogo_ispezione(utente_id, ispezione_id)
  1. carica l'ispezione, solo se è dell'utente          (IspezioniRepository.trova)
  2. senza note → ValidationError, il modello non viene chiamato
  3. carica alveare e apiario, le 3 ispezioni precedenti, i raccolti fino a quella data
  4. AssistenteIspezioni.riassumi(contesto)               (beewatch/ai/assistant.py)
       costruisce la richiesta dai file di prompt (M5-T4), logga il contesto,
       chiama il modello con un tentativo correttivo al massimo (M5-T3)
  5. riepilogo valido → INSERT in riepiloghi_ispezione    (RiepiloghiRepository.salva)
  6. restituisce RiepilogoGenerato
```

## Cosa entra nel prompt

Alveare (codice, stato, data di installazione, anno della regina), ispezione (data, rischio valutato
dall'apicoltore, peso, telaini, regina vista, sciamatura), fino a **3 ispezioni precedenti** (con le loro
note accorciate a 200 caratteri) e fino a **5 raccolti** dell'apiario: quelli dell'apiario intero e quelli
di questo alveare, non successivi all'ispezione. Il nome dell'apiario sì; **coordinate e località no**
(un test lo verifica). **Le previsioni di produzione non entrano**: sono stime per uno stato USA e non
dicono nulla di questa famiglia; un consiglio operativo derivato da lì sarebbe un errore. Un valore
mancante si scrive «non registrato», non zero.

## Quando qualcosa va storto

| Guasto | Conseguenza | Salvato? |
|---|---|---|
| ispezione inesistente o di un altro utente | `ValidationError` (stesso messaggio nei due casi) | no, nessuna chiamata al modello |
| ispezione senza note | `ValidationError`, campo `note` | no, nessuna chiamata |
| provider spento, chiave rifiutata, timeout (dopo i tentativi di M5-T2) | `LLMError` si propaga | no |
| nessun provider configurato | `ConfigError` | no |
| risposta malformata, anche dopo il tentativo correttivo | `RiepilogoGenerato(valido=False)` con il «non disponibile» onesto e un messaggio | no |
| database che non salva | `RiepilogoGenerato(valido=True, salvato=False)` con un messaggio: il lavoro del modello non si butta | no, e l'errore è nel log con lo stack |
| qualunque altra eccezione | non viene nascosta | — |

## Decisioni

**1. Tabella nuova `riepiloghi_ispezione` (DA-03, opzione A), non `messaggi`.** Un riepilogo appartiene a
un'ispezione e ha una struttura: `stato_salute` e `confidenza` stanno in colonne proprie per filtrarli, il
resto nel JSON. File `sql/schema_03_riepiloghi_ispezione.sql`, ripetibile (`CREATE TABLE IF NOT EXISTS`),
che si ordina dopo `schema.sql`. Su un volume esistente si applica come root (comando nel README).

**2. Più riepiloghi per ispezione.** Rigenerare con un altro modello o prompt non cancella il vecchio, e
i due si possono confrontare. `ultimo()` restituisce il più recente.

**3. Le risposte non valide non si salvano.** Non sono un riepilogo, e un «non disponibile» in tabella
sarebbe rumore. Il fallimento è nel log (con provider, modello e numero di chiamate).

**4. Cascata sull'ispezione e sull'utente.** Il riepilogo contiene il contenuto delle note: sparisce con
loro (GDPR art. 17, come le previsioni).

**5. Log: il contesto sì, la nota solo a DEBUG.** Le quattro sezioni di contesto (alveare, ispezione,
storico, raccolti) vanno nel log a livello INFO, così come partono per il modello: è la prova richiesta
dalla DoD. La nota dell'ispezione corrente compare solo a DEBUG; a INFO se ne vede la lunghezza. Lo
storico può contenere note precedenti accorciate: il log è locale e gli stessi dati vanno al provider.

**6. Privacy.** `RiepilogoGenerato.in_locale` è `False` quando le note escono dal computer
(OpenRouter) e `True` con Ollama: l'interfaccia (M6) deve mostrare l'avviso. Il valore viene dal client
(`LLMClient.in_locale`), non dalla configurazione, quindi non può dissentire dal provider realmente usato.

**7. Il client del modello si crea alla prima richiesta**, come il predittore: un'app senza provider
configurato parte, e mostra il problema solo quando serve. Se la creazione fallisce non si ricorda il
fallimento.

**8. Niente consigli sanitari.** Il riepilogo non è un parere: il system prompt (M5-T4) vieta diagnosi,
farmaci e dosi, e l'interfaccia deve presentarlo come «generato automaticamente, da verificare».

## Cosa NON è provato

I test usano un modello **finto**: provano il flusso, i dati, il salvataggio e i guasti. **Non provano
cosa risponderebbe un modello vero** alle note (in particolare alla nota lunga di A3 del seed: confidenza
non alta, nessun farmaco, nessuna dose). Quella verifica richiede Ollama o una chiave OpenRouter (vedi
#26) e `scripts/prova_prompt.py` (vedi #29).

## File coinvolti

| File | Azione |
|---|---|
| `sql/schema_03_riepiloghi_ispezione.sql` | creato: la tabella |
| `beewatch/ai/assistant.py` | creato: contesto, sezioni di testo, `AssistenteIspezioni` |
| `beewatch/services.py` | `genera_riepilogo_ispezione`, `riepilogo_salvato`, `RiepilogoGenerato`, `assistente` |
| `beewatch/repositories.py` | `IspezioniRepository.trova`; query comuni delle ispezioni condivise |
| `beewatch/repositories_riferimento.py` | `RiepiloghiRepository` (`salva`, `ultimo`) |
| `beewatch/ai/llm.py` | `LLMClient.in_locale` |
| `docs/diagrams/er_diagram.dbml` | la tabella nuova (il `.png` va riesportato da dbdiagram.io) |
| `tests/test_assistente.py` | test unitari con repository e LLM finti |
| `tests/test_riepiloghi_repository.py` | test di integrazione su MySQL vero, servizio intero sul seed |
| `tests/test_schema_estensioni.py`, `tests/test_database.py` | l'estensione è ripetibile e crea la tabella su un volume vecchio; le tabelle sono 15 |

## Definition of Done

| Voce | Prova |
|---|---|
| report generato, validato e persistito con tracciabilità completa | `test_il_riepilogo_si_genera_valida_e_salva_con_la_tracciabilita_completa` (unitario); `test_servizio_intero_sulla_nota_lunga_di_a3_del_seed` (MySQL: riga con provider, modello, versione prompt, durata, token, tentativi) |
| testato con LLM mockato | `tests/test_assistente.py` e `tests/llm_fake.py`: nessuna rete, nessuna chiave |
| il contesto passato al prompt è visibile nei log | `test_il_contesto_e_visibile_nei_log_ma_la_nota_solo_in_debug` |
