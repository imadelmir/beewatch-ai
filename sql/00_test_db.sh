#!/bin/bash
# ============================================================================
# BeeWatch AI - database dei test di integrazione
# ============================================================================
#
# Crea `<MYSQL_DATABASE>_test`, il database separato su cui girano i test del
# livello dati (regola 3 dell'architettura: MySQL vero, ma mai il database
# principale). Fa tre cose, e le fa root:
#
#   1. crea il database, in utf8mb4;
#   2. vi applica `schema.sql`, le estensioni `schema_*.sql` e `seed.sql`, gli stessi file
#      del database principale (non nominano mai il database: per questo si riusano
#      cosi' come sono). Il seed porta le tabelle di riferimento (stati dell'alveare, livelli
#      di rischio, tipi di miele, stati USA) che modelli, repository ed ETL danno
#      per scontate, e l'apiario dimostrativo;
#   3. concede all'utente applicativo SELECT, INSERT, UPDATE, DELETE e nient'altro.
#
# L'utente applicativo non puo' creare ne' cancellare tabelle, nemmeno qui: e' lo
# stesso principio di `privilegi.sql`. Per questo lo schema lo prepara root, e i
# test puliscono con DELETE (TRUNCATE richiederebbe il privilegio DROP).
#
# Il database principale non viene letto ne' modificato.
#
# Quando gira. Da solo, al primo avvio del contenitore MySQL (volume vuoto),
# prima degli altri script per ordine alfabetico. Su un volume che esiste gia'
# NON viene rieseguito: lo si lancia a mano, ed e' ripetibile senza danni.
#
#   docker compose exec mysql bash /docker-entrypoint-initdb.d/00_test_db.sh
#
# Perche' uno script di shell e non SQL come gli altri: il nome del database
# arriva da una variabile d'ambiente, e solo da qui si puo' applicare `schema.sql`
# a un database dal nome non fisso.
#
# L'immagine di MySQL ESEGUE gli script .sh che hanno il permesso di esecuzione e
# INCLUDE (con `source`) gli altri, dentro il proprio processo. Questo file
# funziona in entrambi i modi: tutto sta in una funzione con variabili locali, non
# usa `exit` (chiuderebbe l'avvio di MySQL) e non cambia le opzioni della shell.
# L'esito e' il valore di ritorno della funzione: se e' diverso da zero,
# l'inizializzazione si ferma e `docker compose up` fallisce.
#
# La password di root passa dalla variabile MYSQL_PWD, non dalla riga di comando,
# e non viene mai stampata.

beewatch_crea_db_test() {
    local variabile
    for variabile in MYSQL_ROOT_PASSWORD MYSQL_DATABASE MYSQL_USER; do
        if [ -z "${!variabile}" ]; then
            echo "BeeWatch: database di test NON creato: manca la variabile ${variabile}." >&2
            return 1
        fi
    done

    local cartella file_sql estensione
    cartella="$(dirname "${BASH_SOURCE[0]}")"
    # Lo schema, poi le sue estensioni (`schema_02_*.sql`, ... in ordine alfabetico: sono le
    # modifiche arrivate dopo M2, vedi il loro intestazione), poi il seed.
    local -a file_da_applicare=(schema.sql)
    for estensione in "${cartella}"/schema_*.sql; do
        if [ -e "${estensione}" ]; then
            file_da_applicare+=("$(basename "${estensione}")")
        fi
    done
    file_da_applicare+=(seed.sql)
    for file_sql in "${file_da_applicare[@]}"; do
        if [ ! -r "${cartella}/${file_sql}" ]; then
            echo "BeeWatch: database di test NON creato: ${cartella}/${file_sql} non si puo' leggere." >&2
            return 1
        fi
    done

    local nome="${MYSQL_DATABASE}_test"

    # Come identificatore (fra apici inversi): si raddoppia l'apice inverso.
    local identificatore="${nome//\`/\`\`}"
    # Nel GRANT il nome e' un modello: `_` e `%` sono caratteri jolly e vanno
    # preceduti da una barra rovesciata, altrimenti `bee_test` varrebbe anche per
    # `beeXtest`.
    local modello="${identificatore//\\/\\\\}"
    modello="${modello//_/\\_}"
    modello="${modello//\%/\\%}"
    # Come stringa (fra apici semplici): si raddoppiano barra rovesciata e apice.
    local apice="'"
    local utente="${MYSQL_USER//\\/\\\\}"
    utente="${utente//${apice}/${apice}${apice}}"

    # Sempre dal socket locale, come root: funziona sia durante l'inizializzazione
    # (quando MySQL non ascolta ancora sulla rete) sia a contenitore avviato.
    local -a client=(mysql --protocol=socket -uroot --batch --skip-column-names)

    if ! MYSQL_PWD="${MYSQL_ROOT_PASSWORD}" "${client[@]}" <<SQL
CREATE DATABASE IF NOT EXISTS \`${identificatore}\`
    CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
SQL
    then
        echo "BeeWatch: database di test NON creato: CREATE DATABASE e' fallito." >&2
        return 1
    fi

    # Prima lo schema e le sue estensioni, poi il seed. Sono tutti idempotenti: rilanciare
    # lo script non duplica nulla.
    for file_sql in "${file_da_applicare[@]}"; do
        if ! MYSQL_PWD="${MYSQL_ROOT_PASSWORD}" "${client[@]}" --database="${nome}" \
            < "${cartella}/${file_sql}" > /dev/null; then
            echo "BeeWatch: database di test incompleto: ${file_sql} non e' stato applicato." >&2
            return 1
        fi
    done

    # Prima si toglie tutto, poi si concede il necessario: cosi' il risultato e' lo
    # stesso anche se lo script viene rilanciato o se l'utente aveva altri privilegi.
    if ! MYSQL_PWD="${MYSQL_ROOT_PASSWORD}" "${client[@]}" <<SQL
REVOKE IF EXISTS ALL PRIVILEGES ON \`${modello}\`.* FROM '${utente}'@'%';
GRANT SELECT, INSERT, UPDATE, DELETE ON \`${modello}\`.* TO '${utente}'@'%';
SQL
    then
        echo "BeeWatch: database di test incompleto: i privilegi non sono stati concessi." >&2
        return 1
    fi

    echo "BeeWatch: database di test \`${nome}\` pronto (schema e seed applicati, solo privilegi DML)."
}

beewatch_crea_db_test
