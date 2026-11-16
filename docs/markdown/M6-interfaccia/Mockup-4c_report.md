# Mockup · Blocco 4c · Report

> **Richiesta** il progetto come il mockup ad alta fedeltà, solo con le funzioni vere (2026-11-14)
> **Stato** completato
> **Tavole** 35–39 («Report»: archivio e Genera report), chiaro e scuro
> **Collegati** → `app/pages/7_Report.py` · `app/schede.py` (`scheda_modello_report`)

## Cosa c'è

| Parte del mockup | Nell'app |
|---|---|
| «Report», «Genera, consulta ed esporta i report del tuo apiario.», «＋ Genera Report» | sì |
| le tre card (Report mensile, Analisi produzione, Stato sanitario) con «▶ Genera» | sì: aprono la finestra con il modello già scelto |
| la finestra «Genera report»: tipo, alveari, dal / al, sezioni, formato | **tipo**, e **mese e anno** per il mensile; Annulla / Genera report |
| Report generati: ricerca, nome, tipo, periodo, creato il, formato, download | ricerca, **nome**, **tipo**, **creato il**, i **formati** (CSV · Excel · PDF) e le azioni: **apri** (sintesi, tabelle, i tre download) ed **elimina** con conferma |
| «Mostrando 7 di 18 report» e le pagine | sì |

Del mockup mancano il **periodo libero**, la **scelta degli alveari** e delle **sezioni**: i tre
modelli hanno contenuti fissi (M6-T12), e i report riguardano l'apiario attivo. Il **formato** non
si sceglie prima di generare: ogni report si scarica in tutti e tre, quando si vuole.

## Decisioni

**1. I download stanno nella finestra del report.** Un bottone di download per ogni riga e per ogni
formato vorrebbe dire preparare ogni PDF a ogni giro della pagina; si preparano solo aprendo il
report che serve.

**2. Generare non apre il report.** Il report nuovo compare in cima all'archivio con il messaggio di
conferma; si apre con l'occhio, come gli altri.

## Come si prova

| Cosa | Dove |
|---|---|
| le tre card e l'archivio vuoto; la card apre la finestra con il suo modello; generare (mensile con mese e anno, produzione, sanitario); aprire con sintesi e tre download; cercare; eliminare con conferma; senza apiari; database spento; salvataggio, riapertura ed eliminazione che falliscono | `tests/test_pagina_report.py` |
| nel browser: card, «Genera», archivio, finestra del report con i tre download | a mano, con uno stack MySQL isolato |
