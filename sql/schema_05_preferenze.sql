-- ============================================================================
-- BeeWatch AI - estensione dello schema (M6-T13): le preferenze dell'utente
-- ============================================================================
--
-- Aggiunge la tabella `preferenze_utente`, una riga per utente, scritta dalla pagina
-- Impostazioni:
--
-- - `giorni_promemoria`: dopo quanti giorni senza ispezione un alveare «va controllato» (la Home
--   lo conta e lo elenca nei promemoria); 30 è il valore di sempre;
-- - `avvisi_rischio`: se la Home elenca le ispezioni recenti con rischio medio o alto;
-- - `assistente_esterno`: se le note delle ispezioni possono andare a un modello di linguaggio
--   esterno (OpenRouter). Con FALSE il servizio rifiuta di inviarle, qualunque cosa dica `.env`.
--
-- Un utente senza riga ha i valori predefiniti: la riga nasce al primo salvataggio. Cancellando
-- l'utente sparisce anche la sua riga (GDPR art. 17).
--
-- Perche' un file a parte e non una modifica a `schema.sql`: `schema.sql` gira solo al primo
-- avvio con il volume vuoto. Qui `CREATE TABLE IF NOT EXISTS` rende la modifica ripetibile e
-- applicabile anche a un database esistente. Il nome ordina questo file DOPO `schema.sql`
-- (serve `utenti`) e prima di `seed.sql`.
--
-- Esecuzione
-- ----------
-- Automatica: il contenitore MySQL esegue tutti gli .sql di `sql/` al primo avvio, in ordine
-- alfabetico. Lo stesso fa `00_test_db.sh` per il database dei test.
--
-- Su un volume gia' esistente non viene rieseguito: serve root (l'utente applicativo non ha
-- CREATE, e non deve averlo). E' ripetibile senza danni e non tocca i dati:
--
--   docker compose exec -T mysql sh -c \
--     'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" --database="$MYSQL_DATABASE"' \
--     < sql/schema_05_preferenze.sql

CREATE TABLE IF NOT EXISTS preferenze_utente (
    utente_id           INT UNSIGNED     NOT NULL,
    giorni_promemoria   TINYINT UNSIGNED NOT NULL DEFAULT 30,
    avvisi_rischio      BOOLEAN          NOT NULL DEFAULT TRUE,
    assistente_esterno  BOOLEAN          NOT NULL DEFAULT TRUE
                                         COMMENT 'FALSE: le note non vanno mai a un servizio esterno',
    aggiornato_il       DATETIME         NOT NULL DEFAULT CURRENT_TIMESTAMP
                                         ON UPDATE CURRENT_TIMESTAMP,

    PRIMARY KEY (utente_id),

    CONSTRAINT fk_preferenze_utenti
        FOREIGN KEY (utente_id) REFERENCES utenti (id)
        ON DELETE CASCADE ON UPDATE RESTRICT,

    CONSTRAINT chk_preferenze_giorni CHECK (giorni_promemoria BETWEEN 7 AND 90)
) ENGINE = InnoDB
  DEFAULT CHARSET = utf8mb4
  COLLATE = utf8mb4_unicode_ci
  COMMENT = 'Preferenze dell''utente scritte dalla pagina Impostazioni (M6-T13)';
