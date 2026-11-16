# Mockup · Blocco 4b · AI Assistant

> **Richiesta** il progetto come il mockup ad alta fedeltà, solo con le funzioni vere (2026-11-14)
> **Stato** completato
> **Tavole** 33–34 («AI Assistant»), chiaro e scuro
> **Collegati** → `app/pages/4_Assistente_AI.py` · `app/schede.py` (`intestazione_chat`) ·
> `app/stile/beewatch.css`

## Obiettivo

Il mockup disegna l'assistente come una chat. L'assistente di BeeWatch fa una cosa precisa:
**riassume le note di campo di un'ispezione** (M5, M6-T6). La pagina prende il layout della chat
e lo usa per questo, senza fingere una conversazione libera che l'app non ha.

## Cosa c'è

| Parte del mockup | Nell'app |
|---|---|
| «AI Assistant», «Chiedi al tuo assistente AI…» | sì |
| Conversazioni (elenco a sinistra, la scelta in giallo) | **le ispezioni con le note** dell'apiario attivo, dalla più recente |
| «Assistente BeeWatch» con la pastiglia «Ollama» | sì: il provider configurato, e accanto il modello e dove gira |
| il messaggio dell'utente (fumetto giallo a destra) | **le note dell'ispezione**, come le leggerà il modello, in sola lettura |
| la risposta dell'assistente (fumetto a sinistra) | **il riepilogo strutturato**: stato di salute, confidenza, elementi, criticità, azioni per priorità, lacune |
| Rigenera | sì: «Genera il riepilogo», o «Rigenera il riepilogo» se ce n'è già uno |
| Contenuto generato da un'intelligenza artificiale (riquadro blu) | sì, **in cima alla pagina** (regola del §9 della specifica: sempre visibile, non richiudibile) |
| Copia · Salva nota · Domande suggerite · casella del messaggio · Nuova chat | **no**: l'app non ha una chat libera; ogni riepilogo si salva da solo |

Sotto la risposta restano i **riepiloghi già generati** per l'ispezione, ognuno con modello e
versione del prompt.

## Decisioni

**1. Niente chat finta.** Una casella «Scrivi il tuo messaggio…» che non risponde, o risponde
con il riepilogo qualunque cosa si scriva, ingannerebbe. Il layout della chat c'è; le domande
libere no.

**2. La risposta mostrata è l'ultima.** Se un riepilogo è appena stato generato si vede quello,
altrimenti l'ultimo salvato; tutti restano negli espansori sotto.

**3. Il testo del modello resta testo.** Le note sono in un campo di sola lettura; le frasi del
modello passano da `testo_semplice`, come prima: asterischi, cancelletti o link non diventano
formattazione.

## Come si prova

| Cosa | Dove |
|---|---|
| banner, elenco delle ispezioni con note, note da leggere, cambio d'ispezione, attesa dichiarata, riepilogo strutturato, storico, testo del modello senza formattazione, elenchi vuoti, risposta illeggibile, timeout, nessun provider, salvataggio fallito, note inviate fuori, senza apiari, senza note, database spento, storico illeggibile | `tests/test_pagina_assistente.py` |
| il consenso all'assistente esterno (Impostazioni) | `tests/test_pagina_impostazioni.py` |
| il banner subito dopo la testata | `tests/test_ui.py` |
