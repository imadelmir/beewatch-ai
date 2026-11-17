# Mockup · Blocco 5a · Impostazioni

> **Richiesta** il progetto come il mockup ad alta fedeltà, solo con le funzioni vere (2026-11-14)
> **Stato** completato
> **Tavole** 40–46 («Impostazioni»: Profilo, AI & Modelli, Database), chiaro e scuro
> **Collegati** → `app/pages/8_Impostazioni.py` · `app/schede.py` (`avatar_profilo`)

## Cosa c'è

| Scheda | Card del mockup | Nell'app |
|---|---|---|
| Profilo | Dati profilo (avatar, nome, ruolo, campi) | avatar con le iniziali, nome e «Apicoltore»; nome ed email |
| Profilo | Sicurezza | la password, conoscendo quella attuale |
| Profilo | Aspetto | l'interruttore **Scuro · Chiaro** |
| Profilo | — | **Cancella l'account** (password e spunta), con il bordo rosso della zona pericolosa |
| Notifiche | Notifiche (interruttori) | **promemoria ispezioni** (dopo quanti giorni) e **avvisi sanitari**; accanto, quanti alveari e ispezioni sono da guardare adesso |
| AI e Modelli | Impostazioni AI | assistente, dove gira, versione del prompt; l'interruttore del **consenso** a inviare le note fuori |
| AI e Modelli | Gestione modelli ML | versione, algoritmo, errore medio, righe di addestramento |
| Database | Connessione database | la **configurazione** da `.env`, in sola lettura, senza segreti |

Del mockup **non ci sono**: foto, telefono, azienda e ruolo; lingua e unità di misura;
autenticazione a due fattori; email di riepilogo; modello, temperatura, lunghezza e prompt
dell'assistente modificabili; spesa stimata; scelta e cronologia dei modelli; «Riaddestra
modello»; «Testa connessione»; backup, ripristino, attività recente, tabelle con i conteggi e
«svuota database». L'app non li ha: provider e modello si cambiano nel `.env`, il modello si
riaddestra con `python scripts/train_model.py`, il database si gestisce con Docker.

## Decisioni

**1. Niente «Salva modifiche» unico.** Ogni card ha il suo bottone: si salva quello che si vede,
e il messaggio dice che cosa è stato salvato.

**2. Interruttori al posto delle caselle**, come nel mockup, per notifiche e consenso: sono scelte
sì/no che restano. La cancellazione dell'account tiene la casella, perché è una conferma.

## Come si prova

| Cosa | Dove |
|---|---|
| le quattro schede, profilo e nome nella sidebar, email già usata, password giusta e sbagliata, cancellazione dell'account, notifiche e consenso salvati, configurazione senza segreti, senza configurazione, database spento | `tests/test_pagina_impostazioni.py` |
| nel browser: le card della scheda Profilo in tema scuro | a mano, con uno stack MySQL isolato |
