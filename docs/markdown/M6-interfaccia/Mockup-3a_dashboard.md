# Mockup · Blocco 3a · Dashboard

> **Richiesta** il progetto come il mockup ad alta fedeltà, solo con le funzioni vere (2026-11-14)
> **Stato** completato
> **Tavole** 13–15 («Area operativa»: Dashboard), chiaro e scuro
> **Collegati** → `app/schermate/home.py` · `app/schede.py` · `app/tema.py` (icone) ·
> `app/stile/beewatch.css`

## Obiettivo

La prima pagina dopo l'accesso diventa la **Dashboard** del mockup. Nel menu prende il nome
«Dashboard»; la vecchia pagina Dashboard (raccolti per alveare e modello previsto/reale) si chiama
per ora «Statistiche», e il suo contenuto andrà in Previsioni nel blocco 4, come nel mockup.

## Cosa c'è

| Parte del mockup | Nell'app | Da dove vengono i dati |
|---|---|---|
| «Dashboard» e «Benvenuto Mario, ecco il riepilogo della tua attività.» | sì, con il nome di chi ha fatto l'accesso | sessione |
| la data nel riquadro con il calendario | sì, la data di oggi | — |
| «＋ Nuova ispezione» | sì: porta alla pagina Ispezioni | — |
| card Alveari totali, Ispezioni, Produzione stimata, Stato generale, con le icone | Alveari attivi, Ispezioni (30 giorni), Produzione stagione, Stato generale | `panoramica`, stati degli alveari |
| «+2 questo mese», «+12% rispetto al mese scorso» | una riga vera: «in 1 apiario», «negli ultimi 30 giorni», «miele raccolto nel 2026» | — |
| Produzione stimata (prossimi 3 mesi) | **Produzione registrata (per anno)**, linea gialla con l'area sfumata | raccolti dell'apiario |
| Stato alveari: ciambella con il totale e la legenda Sani / Attenzione / Critici | sì, con numeri e percentuali | alveari dell'apiario attivo |
| Ultime notifiche | sì: ispezioni a rischio e alveari da ricontrollare | promemoria (M6-T13) |
| Prossime scadenze | sì: «Ispezione alveare A1 · scaduta il …» o «da fare» | promemoria e soglia scelta |
| Visualizza tutte / Visualizza calendario | «Visualizza le ispezioni» e «Cambia la soglia»: il calendario non c'è | — |
| «Hai bisogno di aiuto? Chiedi al tuo assistente AI!» in basso a destra | sì: apre AI Assistant | — |

**Stato generale.** «Buono» se tutti gli alveari attivi sono in salute e nessuno va ricontrollato;
«Attenzione» se ce ne sono in osservazione, deboli, sciamati o da ricontrollare; «Critico» se ce
ne sono di persi. Il valore è nel giallo del tema, come nel mockup; il perché è nell'aiuto (?).

## Decisioni

**1. Nessun numero inventato.** Il mockup mostra una produzione «stimata nei prossimi 3 mesi» e
delle variazioni mensili: l'app non ha una stima mensile (il modello stima la resa annuale per
colonia) né uno storico mese per mese degli alveari. Al loro posto ci sono i numeri veri, e la riga
sotto ogni card dice da dove vengono.

**2. Le card sono `st.metric` veri.** L'icona in alto a destra la mette il CSS sul contenitore con
chiave (`bw_kpi_alveare`…), con le icone a linea del mockup in `tema.ICONE`. Così la card si legge
anche senza stile, con lo screen reader e nei test.

**3. Un modulo per le card del mockup.** `app/schede.py` (testata con le azioni, card KPI, pillola
della data, elenchi, ciambella, area): le prossime pagine le riusano. L'HTML ha solo testi fissi o
passati da `html.escape`.

**4. Lo stato del sistema resta, in piccolo.** In fondo alla pagina una riga dice quale modello e
quale assistente sono in uso, con l'avvertenza del progetto. Se il modello manca compare un avviso:
è un problema vero, e il resto della Dashboard funziona lo stesso.

## Come si prova

| Cosa | Dove |
|---|---|
| data in italiano, testata, card KPI (valore, riga sotto, parte verde), elenchi protetti dall'HTML, ciambella (totale, fette vuote saltate, sfondo trasparente), legenda con le percentuali, area della produzione | `tests/test_schede.py` |
| la Dashboard: titolo, benvenuto, le quattro card, le quattro sezioni, i bottoni; lo stato generale; «Nuova ispezione» porta alle Ispezioni | `tests/test_schede.py` |
| i numeri della panoramica, l'apiario attivo, il modello e l'avviso se manca | `tests/test_app_streamlit.py` |
| notifiche e scadenze dai promemoria | `tests/test_pagina_impostazioni.py` |
| nel browser a 1440×900: proporzioni delle colonne, card allineate, aiuto fisso in basso a destra | a mano, con uno stack MySQL isolato |
