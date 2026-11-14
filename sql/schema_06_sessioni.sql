-- ============================================================================
-- BeeWatch AI - estensione dello schema: le sessioni ricordate («Ricordami»)
-- ============================================================================
--
-- Aggiunge la tabella `sessioni`: una riga per ogni browser in cui un utente ha fatto l'accesso.
-- Il browser tiene un token casuale in un cookie; qui si salva solo la sua impronta SHA-256, così
-- chi leggesse la tabella non potrebbe usare le sessioni. Serve a due cose:
--
-- - con «Ricordami» l'accesso resta valido 30 giorni, anche chiudendo il browser;
-- - senza, l'accesso dura finché il browser resta aperto (al massimo un giorno): ricaricare la
--   pagina, o cambiare tema (l'interruttore Scuro/Chiaro ricarica la pagina), non fa uscire.
--
-- «Esci» cancella la riga. Cancellando l'utente spariscono le sue sessioni (GDPR art. 17).
--
-- File a parte e non una modifica a `schema.sql` per lo stesso motivo di `schema_05`: si applica
-- anche a un database esistente ed e' ripetibile. Il nome lo ordina dopo `schema.sql` (serve
-- `utenti`) e prima di `seed.sql`.
--
-- Su un volume gia' esistente (serve root, l'utente applicativo non ha CREATE):
--
--   docker compose exec -T mysql sh -c \
--     'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" --database="$MYSQL_DATABASE"' \
--     < sql/schema_06_sessioni.sql

CREATE TABLE IF NOT EXISTS sessioni (
    id            INT UNSIGNED NOT NULL AUTO_INCREMENT,
    utente_id     INT UNSIGNED NOT NULL,
    impronta      CHAR(64)     NOT NULL COMMENT 'SHA-256 del token del cookie: mai il token',
    creata_il     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
    scade_il      DATETIME     NOT NULL,

    PRIMARY KEY (id),
    UNIQUE KEY uq_sessioni_impronta (impronta),
    KEY idx_sessioni_utente (utente_id),

    CONSTRAINT fk_sessioni_utenti
        FOREIGN KEY (utente_id) REFERENCES utenti (id)
        ON DELETE CASCADE ON UPDATE RESTRICT
) ENGINE = InnoDB
  DEFAULT CHARSET = utf8mb4
  COLLATE = utf8mb4_unicode_ci
  COMMENT = 'Sessioni ricordate da un cookie del browser («Ricordami»)';
