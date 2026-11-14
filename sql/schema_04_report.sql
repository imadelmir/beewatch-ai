-- ============================================================================
-- BeeWatch AI - estensione dello schema (M6-T12): l'archivio dei report
-- ============================================================================
--
-- Aggiunge la tabella `report`: ogni report generato dalla pagina Report (mensile, analisi
-- della produzione, stato sanitario) resta nell'archivio, e si può riaprire e riscaricare in
-- CSV, XLSX o PDF anche dopo.
--
-- Il contenuto si salva com'era quando è stato generato (`contenuto_json`: sintesi e tabelle),
-- non come richiesta da rifare: un report è una fotografia, e riaprirlo un mese dopo deve dare
-- gli stessi numeri anche se nel frattempo sono arrivate ispezioni nuove.
--
-- Cancellando l'utente spariscono anche i suoi report (GDPR art. 17): contengono i suoi dati.
-- L'apiario invece si cancella in modo logico (`attivo = FALSE`): il riferimento resta, e se un
-- giorno la riga sparisse davvero il report resterebbe, senza apiario (`SET NULL`).
--
-- Perche' un file a parte e non una modifica a `schema.sql`: `schema.sql` gira solo al primo
-- avvio con il volume vuoto. Qui `CREATE TABLE IF NOT EXISTS` rende la modifica ripetibile e
-- applicabile anche a un database esistente. Il nome ordina questo file DOPO `schema.sql`
-- (servono `utenti` e `apiari`) e prima di `seed.sql`.
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
--     < sql/schema_04_report.sql

CREATE TABLE IF NOT EXISTS report (
    id              INT UNSIGNED  NOT NULL AUTO_INCREMENT,
    utente_id       INT UNSIGNED  NOT NULL,
    apiario_id      INT UNSIGNED  NULL,
    modello         ENUM('mensile', 'produzione', 'sanitario') NOT NULL,
    titolo          VARCHAR(200)  NOT NULL,
    contenuto_json  JSON          NOT NULL COMMENT 'Sintesi e tabelle, com''erano alla generazione',
    creato_il       DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (id),
    KEY idx_report_utente_data (utente_id, creato_il DESC),

    CONSTRAINT fk_report_utenti
        FOREIGN KEY (utente_id) REFERENCES utenti (id)
        ON DELETE CASCADE ON UPDATE RESTRICT,

    CONSTRAINT fk_report_apiari
        FOREIGN KEY (apiario_id) REFERENCES apiari (id)
        ON DELETE SET NULL ON UPDATE RESTRICT
) ENGINE = InnoDB
  DEFAULT CHARSET = utf8mb4
  COLLATE = utf8mb4_unicode_ci
  COMMENT = 'Archivio dei report generati dalla pagina Report (M6-T12)';
