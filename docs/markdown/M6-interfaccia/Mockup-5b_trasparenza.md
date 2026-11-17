# Mockup · Blocco 5b · Trasparenza e stati dell'interfaccia

> **Richiesta** il progetto come il mockup ad alta fedeltà, solo con le funzioni vere (2026-11-14)
> **Stato** completato
> **Tavole** 47–56 («Stati dell'interfaccia» e «Trasparenza e limiti»), chiaro e scuro
> **Collegati** → `app/pages/6_Trasparenza.py` · `app/stile/beewatch.css` · `app/tema.py`

## Trasparenza e limiti

Come la tavola 56: titolo «Trasparenza e limiti», «Cosa fa questo sistema, con quali dati, e cosa
non è in grado di fare.», e **sei card in una griglia 3×2**, ognuna con il titolo in una pastiglia
colorata e il riferimento in fondo:

| Card | Colore | Riferimento |
|---|---|---|
| Che cosa fa BeeWatch AI | neutro | docs/etica.md |
| Quali dati tratta e dove li conserva | blu | GDPR art. 5, 6, 17 |
| Un'intelligenza artificiale generativa scrive i riepiloghi | verde | AI Act art. 50 |
| I limiti del modello di previsione | giallo | docs/model_card.md |
| Non sostituisce un veterinario | rosso | non è uno strumento diagnostico |
| Le regole che valgono per i tuoi dati | blu | Reg. (UE) 2016/679 e 2024/1689 |

I testi restano **parola per parola** quelli di `docs/etica.md` (un test lo controlla). Restano
anche, sotto le card, le due parti che dipendono da questa installazione: dove gira l'assistente
(le note escono dal PC o no) e il modello di previsione in uso, con i suoi numeri. L'avvertenza sul
veterinario resta in cima, prima delle card.

Il blu dei riquadri informativi ha ora una variante per tema (`informazione` in `tema.PALETTE`): il
blu scuro sul nero non si leggeva.

## Stati dell'interfaccia (tavole 47–53)

| Stato del mockup | Nell'app |
|---|---|
| Vuoto («Nessun alveare registrato», con «Nuovo alveare») | sì nella pagina Alveari (blocco 3b); nelle altre pagine il riquadro «Cosa puoi fare» di `blocco_vuoto` |
| Caricamento (sagome grigie) | gli indicatori di Streamlit e gli `st.spinner` delle operazioni lunghe (previsione, riepilogo, report) |
| Errore («Impossibile caricare i dati», Riprova, Vedi log) | il messaggio di `mostra_errore`: che cosa è successo e che cosa fare; il dettaglio tecnico va nel file di log |

Il bottone «Riprova» non c'è: la pagina si riprova da sola al giro successivo (dopo la pausa
dell'interruttore del database, M6-T9), e aggiungerlo a ogni errore cambierebbe il comportamento
verificato di tutte le pagine col database spento.

## Come si prova

| Cosa | Dove |
|---|---|
| ogni paragrafo uguale a `docs/etica.md`, i cinque punti obbligatori, niente gergo non spiegato, avvertenza in cima, ogni sezione con titolo e paragrafi, assistente locale / esterno / non configurato, il modello con i suoi numeri, senza modello | `tests/test_pagina_trasparenza.py` |
| nel browser a 1440×900: la griglia 3×2 e il colore di ogni pastiglia, misurati nel DOM | a mano, con uno stack MySQL isolato |
