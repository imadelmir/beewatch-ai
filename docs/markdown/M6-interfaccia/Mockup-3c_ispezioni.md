# Mockup · Blocco 3c · Ispezioni

> **Richiesta** il progetto come il mockup ad alta fedeltà, solo con le funzioni vere (2026-11-14)
> **Stato** completato
> **Tavole** 25–29 («Ispezioni»: storico e Nuova ispezione), chiaro e scuro
> **Collegati** → `app/pages/2_Ispezioni.py` · `beewatch/services.py` (`elenco_ispezioni`,
> `elimina_ispezione`) · `app/schede.py`

## Cosa c'è

**Lo storico (tavola 27).** Titolo, la data di oggi e «＋ Nuova ispezione»; una card con:

| Parte del mockup | Nell'app |
|---|---|
| Cerca ispezione… | sì: nel codice dell'alveare e nelle note |
| Alveare: Tutti | sì |
| Stato: Tutti | sì, per rischio rilevato |
| Ultimi 30 giorni (giallo) | sì: Tutto, Ultimi 30 / 90 giorni, Ultimo anno |
| Esporta | sì: le ispezioni filtrate in CSV per Excel, con le note intere |
| Data, Alveare, Stato (pastiglia), Forza, Scorte, Regina | sì: lo «stato» è il rischio rilevato; forza e scorte dai telaini contati in quell'ispezione |
| Operatore | **al suo posto il Peso**: l'app non registra chi ha fatto l'ispezione |
| vedi / modifica / elimina | **vedi** (l'ispezione intera, con le note) ed **elimina**; modificare non è previsto |
| «Mostrando 10 di 15 ispezioni» e le pagine | sì |

La tabella ha le ispezioni di **tutti** gli alveari, non solo dell'apiario attivo, come nel mockup.

**La nuova ispezione (tavola 29)** si apre a tutta pagina: alveare, data, stato (rischio rilevato),
forza (telaini di covata), scorte (telaini di scorte), presenza della regina, sciamatura, peso e
note, con Annulla e Salva ispezione. «Nuova ispezione» della Dashboard e del dettaglio di un alveare
apre direttamente questo modulo; dal dettaglio, con l'alveare già scelto.

Del mockup mancano **temperatura**, **operatore**, **«Salva bozza»** e **«Compila con AI»**: l'app non
registra la temperatura né chi ispeziona, non ha bozze, e l'assistente riassume le note dopo il
salvataggio (pagina AI Assistant), non riempie il modulo.

**Le finestre.** «Ispezione»: tutti i campi e le note intere in sola lettura (asterischi e trattini
restano come sono stati scritti), con «Vai all'alveare» e «Riepilogo con l'assistente». «Elimina
ispezione»: la domanda e Annulla / Elimina. La cancellazione è **definitiva**, con il riepilogo AI
a cascata, e la finestra lo dice.

## Decisioni

**1. Due servizi nuovi.** `elenco_ispezioni` (tutte le ispezioni degli alveari attivi dell'utente)
ed `elimina_ispezione`, che espone il `IspezioniRepository.elimina` già esistente. Modificare
un'ispezione richiederebbe un metodo nuovo in `repositories.py`, che è al limite delle 400 righe:
non c'è, e la tabella non mostra la matita.

**2. La nuova ispezione è una vista, non una finestra.** Come nel mockup, a tutta pagina: il modulo
è lungo e le note vanno scritte con calma. Si apre e si chiude con lo stesso stato delle finestre
(`apri_finestra("nuova_ispezione", alveare)`), così può aprirla anche un'altra pagina.

**3. Il periodo parte da «Tutto».** Il mockup evidenzia «Ultimi 30 giorni»; qui il filtro parte da
tutto lo storico, perché con un apiario poco ispezionato la tabella sarebbe vuota all'apertura.

## Come si prova

| Cosa | Dove |
|---|---|
| l'elenco di tutti gli apiari dalla più recente; un'ispezione altrui non si elimina | `tests/test_pagina_ispezioni.py` |
| la tabella, i filtri (alveare, rischio, note), il periodo da oggi, Esporta, nessuna ispezione, database spento | `tests/test_pagina_ispezioni.py` |
| leggere un'ispezione intera, le note non formattate, eliminare con conferma | `tests/test_pagina_ispezioni.py` |
| la nuova ispezione: il modulo, il salvataggio, il rifiuto del modello sul campo, Annulla, Torna, l'alveare già scelto, il salvataggio fallito | `tests/test_pagina_ispezioni.py` |
| «Nuova ispezione» della Dashboard apre il modulo | `tests/test_schede.py` |
| nel browser a 1440×900: tabella con i dati del seed, pagine, modulo a tutta pagina | a mano, con uno stack MySQL isolato |
