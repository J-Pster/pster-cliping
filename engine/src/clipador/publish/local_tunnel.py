"""Expoe o clipe numa URL HTTPS publica TEMPORARIA via servidor HTTP local + tunel ngrok,
para o Buffer conseguir buscar o video (a API do Buffer nao aceita upload binario, so URL).

Decisao do usuario: nada de S3/infra de nuvem pra isso, 100% local. O tunel so precisa ficar
de pe durante a janela curta entre criar o post (`mode: addToQueue`, publicacao imediata) e
confirmar status `sent` via polling - depois disso o servidor e o tunel sao derrubados
(mesmo ciclo de vida que a staging em S3 tinha: sobe -> publica -> confirma -> limpa).

Risco conhecido: o plano gratuito do ngrok so permite 1 agente por vez nessa maquina. Por
isso a consulta na API local do ngrok (`/api/tunnels`) SEMPRE filtra pelo `config.addr`
batendo com a porta local escolhida aqui - nunca assume "o primeiro tunnel da lista", que
pode pertencer a outro processo ngrok do usuario.
"""

from __future__ import annotations

import http.server
import secrets
import socket
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import requests

from clipador.publish.models import PublishError

NGROK_API_URL = "http://127.0.0.1:4040/api/tunnels"
DEFAULT_TUNNEL_STARTUP_TIMEOUT_SECONDS = 20.0
DEFAULT_TUNNEL_POLL_INTERVAL_SECONDS = 0.3


def _pick_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _make_handler(video_path: Path, url_path: str) -> type[http.server.BaseHTTPRequestHandler]:
    file_size = video_path.stat().st_size

    class SingleFileHandler(http.server.BaseHTTPRequestHandler):
        def _send_headers(
            self, status: int, content_length: int, extra: dict[str, str] | None = None
        ) -> None:
            self.send_response(status)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Content-Length", str(content_length))
            self.send_header("Accept-Ranges", "bytes")
            for key, value in (extra or {}).items():
                self.send_header(key, value)
            self.end_headers()

        def _serve(self, write_body: bool) -> None:
            if self.path != url_path:
                self.send_error(404)
                return

            range_header = self.headers.get("Range")
            if range_header and range_header.startswith("bytes="):
                start_str, _, end_str = range_header.removeprefix("bytes=").partition("-")
                start = int(start_str) if start_str else 0
                end = int(end_str) if end_str else file_size - 1
                end = min(end, file_size - 1)
                length = end - start + 1
                self._send_headers(
                    206, length, {"Content-Range": f"bytes {start}-{end}/{file_size}"}
                )
                if write_body:
                    with video_path.open("rb") as handle:
                        handle.seek(start)
                        self.wfile.write(handle.read(length))
                return

            self._send_headers(200, file_size)
            if write_body:
                with video_path.open("rb") as handle:
                    self.wfile.write(handle.read())

        def do_GET(self) -> None:  # noqa: N802
            self._serve(write_body=True)

        def do_HEAD(self) -> None:  # noqa: N802
            self._serve(write_body=False)

        def log_message(self, *_args: object) -> None:  # silencia log padrao do stdlib
            pass

    return SingleFileHandler


@dataclass
class StagedTunnel:
    server: http.server.ThreadingHTTPServer
    server_thread: threading.Thread
    ngrok_process: subprocess.Popen
    url: str


def _wait_for_ngrok_tunnel(
    port: int,
    api_url: str,
    timeout_seconds: float,
    poll_interval_seconds: float,
    ngrok_process: subprocess.Popen,
) -> str:
    deadline = time.monotonic() + timeout_seconds
    local_addr_suffix = f":{port}"
    while time.monotonic() < deadline:
        if ngrok_process.poll() is not None:
            output = ngrok_process.stdout.read() if ngrok_process.stdout else ""
            raise PublishError(
                f"ngrok encerrou antes de abrir o tunel (exit code {ngrok_process.returncode}). "
                f"Saida: {output.strip()[:500]}"
            )
        try:
            response = requests.get(api_url, timeout=2)
            response.raise_for_status()
            tunnels = response.json().get("tunnels", [])
        except requests.RequestException:
            tunnels = []
        for tunnel in tunnels:
            addr = tunnel.get("config", {}).get("addr", "")
            if addr.endswith(local_addr_suffix) and tunnel.get("proto") == "https":
                return tunnel["public_url"]
        time.sleep(poll_interval_seconds)
    raise PublishError(
        "Timeout esperando o ngrok abrir o tunel. O plano gratuito do ngrok so permite 1 "
        "agente por vez nessa maquina - feche outras sessoes de ngrok abertas e tente de novo."
    )


def stage_video(
    video_path: str | Path,
    *,
    ngrok_binary: str = "ngrok",
    startup_timeout_seconds: float = DEFAULT_TUNNEL_STARTUP_TIMEOUT_SECONDS,
    poll_interval_seconds: float = DEFAULT_TUNNEL_POLL_INTERVAL_SECONDS,
) -> tuple[StagedTunnel, str]:
    """Sobe um servidor HTTP local servindo `video_path` + tunel ngrok apontando pra ele.

    Retorna (handle pra limpar depois via `delete_staged`, URL publica https)."""
    video_path = Path(video_path)
    if not video_path.is_file():
        raise PublishError(f"Video nao encontrado pra staging: {video_path}")

    port = _pick_free_port()
    url_path = f"/{secrets.token_urlsafe(24)}.mp4"
    handler_cls = _make_handler(video_path, url_path)

    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), handler_cls)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    ngrok_process = subprocess.Popen(
        [ngrok_binary, "http", str(port), "--log=stdout", "--log-format=json"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    try:
        public_base = _wait_for_ngrok_tunnel(
            port, NGROK_API_URL, startup_timeout_seconds, poll_interval_seconds, ngrok_process
        )
    except PublishError:
        server.shutdown()
        thread.join(timeout=5)
        ngrok_process.terminate()
        raise

    staged = StagedTunnel(
        server=server, server_thread=thread, ngrok_process=ngrok_process, url=public_base + url_path
    )
    return staged, staged.url


def delete_staged(staged: StagedTunnel) -> None:
    """Derruba o tunel ngrok e o servidor HTTP local. Chamado sempre num `finally`."""
    staged.ngrok_process.terminate()
    try:
        staged.ngrok_process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        staged.ngrok_process.kill()
    staged.server.shutdown()
    staged.server_thread.join(timeout=5)
