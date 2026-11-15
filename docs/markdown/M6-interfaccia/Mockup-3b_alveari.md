# Mockup · Blocco 3b · Alveari

> **Richiesta** il progetto come il mockup ad alta fedeltà, solo con le funzioni vere (2026-11-14)
> **Stato** completato
> **Tavole** 16–24 («Gestione alveari»: elenco, dettaglio Alveare A12, Nuovo alveare, Eliminare
> l'alveare), chiaro e scuro
> **Collegati** → `app/pages/1_Alveari.py` · `app/schede.py` · `app/avvio.py` (finestre) ·
> `beewatch/services.py` (`elenco_alveari`, Forza e Scorte)

## Cosa c'è

**L'elenco (tavola 18).** Titolo, «Apiari» e «＋ Nuovo alveare» in alto a destra; una card con:

| Parte del mockup | Nell'app |
|---|---|
| Cerca alveare… | sì, sul codice |
| Stato: Tutti | sì, per stato |
| Posizione: Tutte | sì, per apiario: la tabella ha gli alveari di **tutti** gli apiari |
| Esporta | sì: la tabella filtrata in CSV per Excel in italiano («;», virgola decimale, BOM) |
| ID alveare, Posizione, Stato (pastiglia), Forza, Scorte di miele, Ultima ispezione | sì |
| le tre azioni: vedi, modifica, elimina (rossa) | sì |
| «Mostrando 10 di 24 alveari» e le pagine | sì, dieci righe per pagina |

**Forza e Scorte di miele** vengono dai telaini contati all'ultima ispezione che li ha registrati
(un'arnia da 10): forza Alta da 6 telaini di covata, Media da 3, Bassa sotto; scorte Buone da 4
telaini, Medie da 2, Scarse sotto. Le soglie sono una regola pratica, scritta sotto la tabella e
nell'aiuto delle card. Se i telaini non sono mai stati contati compare «—».

**Il dettaglio (tavola 20).** «← Alveari», «Alveare A1», apiario e ultima ispezione, «Modifica» e
«＋ Nuova ispezione»; card Stato, Forza, Scorte (valori preoccupanti in arancio o rosso) e Peso;
**Andamento del peso** alle ispezioni (il mockup ha «produzione kg/mese», che l'app non registra
alveare per alveare e mese per mese); **Storico ispezioni** con data, rischio e note, e «Vedi tutte»;
**Dettagli alveare** (posizione, installazione, regina, note); **Salute e rischi** con tre barre
ricavate dall'ultima ispezione (rischio rilevato, sciamatura, carenza di scorte), ognuna anche a
parole; **Assistente AI**, che apre la pagina dell'assistente.

**Le finestre (tavole 22 e 24).** «Nuovo alveare» e «Modifica alveare» su due colonne (ID,
posizione, stato, data d'installazione, anno della regina, note) con Annulla e Salva; «Elimina
alveare» con il punto esclamativo rosso, la domanda e Annulla / Elimina. «Apiari» apre la gestione
degli apiari (aggiungere, modificare, eliminare), che il mockup non mostra ma senza la quale non si
può creare un alveare.

Del mockup mancano **tipo d'arnia, numero di telaini dell'arnia, origine della regina e
operatore**: l'app non li registra.

## Decisioni

**1. La finestra aperta è nello stato.** `avvio.apri_finestra` / `chiudi_finestra`: la X chiama
`chiudi_finestra` (`on_dismiss`), e un clic dentro una finestra che deve chiuderla (Annulla, Salva)
chiude e riesegue tutta la pagina con `st.rerun()`. Il motivo: un clic dentro una finestra riesegue
solo la finestra, che altrimenti resterebbe aperta. Trovato nel browser: in AppTest non si vede.

**2. Una cancellazione è una seconda azione esplicita.** Prima serviva una spunta; ora c'è la
finestra con la domanda e il bottone rosso, come nel mockup. Eliminare resta logico: le ispezioni
restano nello storico (lo dice la finestra). Per gli apiari, che portano via anche i loro alveari,
resta la spunta.

**3. L'HTML resta negli helper.** Pastiglie, testata della tabella, barre dei rischi, icone: tutto in
`schede.py`, con i testi passati da `html.escape`. La pagina non scrive HTML.

**4. AppTest e le finestre.** AppTest disegna le finestre ma, dopo una chiusura, ne conserva gli
elementi; i test controllano lo stato (`finestra_aperta`) e, dove serve, riaprono la pagina da capo.

## Come si prova

| Cosa | Dove |
|---|---|
| Forza e Scorte dai telaini (soglie), l'elenco di tutti gli apiari con l'ultima ispezione contata | `tests/test_pagina_alveari.py` |
| la tabella (intestazioni, pastiglie, azioni), ricerca e filtri, Esporta e il CSV per Excel, dieci righe per pagina, stato vuoto, nessun apiario, database spento | `tests/test_pagina_alveari.py` |
| finestre: nuovo alveare, codice vuoto, codice già usato, Annulla, modifica e spostamento, eliminazione e suo errore; apiari: aggiungere, controlli, modificare, eliminare | `tests/test_pagina_alveari.py` |
| il dettaglio: card, sezioni, peso, sciamatura, valori preoccupanti colorati, tornare all'elenco, modificare | `tests/test_pagina_alveari.py` |
| nel browser a 1440×900: colonne della testata allineate alle righe, finestre aperte e chiuse con X e Annulla, valori delle card non tagliati | a mano, con uno stack MySQL isolato |
