"""Un server HTTP locale che imita Ollama e OpenRouter, per provare i client senza rete.

Non è un test: lo usano `test_llm.py` (M5-T1), e M5-T2 e M5-T6 per timeout e limiti di richieste.
Gira su una porta libera di 127.0.0.1, in un thread, con **socket veri**: il timeout, la
connessione rifiutata e lo stato HTTP sono quelli di `requests`, non di un mock.

    with ServerFinto() as server:
        server.rispondi(200, {"message": {"content": "ciao"}})
        ...
        server.richieste[0].json      # ciò che il client ha inviato
        server.richieste[0].intestazioni["authorization"]

Le risposte si preparano in coda: la prima richiesta riceve la prima, e così via; finita la coda si
ripete l'ultima. Una risposta può avere un ritardo (per far scadere il timeout del client).
"""

from __future__ import annotations

import json
import socket
import threading
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


@dataclass
class Richiesta:
    percorso: str
    intestazioni: dict[str, str]  # chiavi in minuscolo
    corpo: bytes
    ricevuta_il: float = field(default_factory=time.monotonic)

    @property
    def json(self) -> Any:
        return json.loads(self.corpo)


@dataclass
class Risposta:
    stato: int = 200
    corpo: Any = None  # dict/list -> JSON; str -> testo; bytes -> grezzo
    ritardo: float = 0.0
    intestazioni: dict[str, str] = field(default_factory=dict)


class ServerFinto:
    def __init__(self) -> None:
        self.richieste: list[Richiesta] = []
        self._coda: list[Risposta] = []
        self._blocco = threading.Lock()
        server = self

        class Gestore(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802 - nome richiesto da http.server
                lunghezza = int(self.headers.get("Content-Length") or 0)
                corpo = self.rfile.read(lunghezza)
                intestazioni = {k.lower(): v for k, v in self.headers.items()}
                risposta = server._prossima(Richiesta(self.path, intestazioni, corpo))
                if risposta.ritardo:
                    time.sleep(risposta.ritardo)
                dati = risposta.corpo
                if isinstance(dati, bytes):
                    grezzo, tipo = dati, "application/octet-stream"
                elif isinstance(dati, str):
                    grezzo, tipo = dati.encode("utf-8"), "text/plain"
                else:
                    grezzo, tipo = (
                        json.dumps(dati if dati is not None else {}).encode(),
                        "application/json",
                    )
                try:
                    self.send_response(risposta.stato)
                    self.send_header("Content-Type", tipo)
                    self.send_header("Content-Length", str(len(grezzo)))
                    for nome, valore in risposta.intestazioni.items():
                        self.send_header(nome, valore)
                    self.end_headers()
                    self.wfile.write(grezzo)
                except OSError:  # il client ha già chiuso (timeout): non è un errore del server
                    pass

            def log_message(self, *argomenti: Any) -> None:  # niente rumore nei test
                pass

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Gestore)
        self._server.daemon_threads = True
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    # ----------------------------------------------------------------------- #

    def _prossima(self, richiesta: Richiesta) -> Risposta:
        with self._blocco:
            self.richieste.append(richiesta)
            if len(self._coda) > 1:
                return self._coda.pop(0)
            return (
                self._coda[0]
                if self._coda
                else Risposta(500, {"error": "nessuna risposta preparata"})
            )

    def rispondi(
        self,
        stato: int = 200,
        corpo: Any = None,
        *,
        ritardo: float = 0.0,
        intestazioni: dict[str, str] | None = None,
    ) -> ServerFinto:
        """Aggiunge una risposta in coda."""
        with self._blocco:
            self._coda.append(Risposta(stato, corpo, ritardo, intestazioni or {}))
        return self

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self._server.server_address[1]}"

    def __enter__(self) -> ServerFinto:
        self._thread.start()
        return self

    def __exit__(self, *argomenti: Any) -> None:
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=5)


def porta_chiusa() -> str:
    """L'indirizzo di una porta su cui non ascolta nessuno: la connessione viene rifiutata."""
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        porta = s.getsockname()[1]
    return f"http://127.0.0.1:{porta}"
