"""Servidor loopback minimo pra capturar o `code` de um redirect OAuth.

Instagram e TikTok nao tem um flow "installed app" pronto como o do Google
(InstalledAppFlow), entao a captura do redirect e feita a mao aqui: sobe um
HTTPServer na porta fixa configurada no app da plataforma, espera o unico
request do redirect, guarda o `code` da query string e desliga.
"""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

from clipador.publish.models import PublishError


def wait_for_redirect_code(port: int, timeout_seconds: int = 300) -> str:
    captured: dict[str, str] = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 (nome exigido pela stdlib)
            query = parse_qs(urlparse(self.path).query)
            if "code" in query:
                captured["code"] = query["code"][0]
                body = b"Autorizado, pode fechar esta aba e voltar ao terminal."
            else:
                captured["error"] = query.get("error_description", ["autorizacao negada"])[0]
                body = b"Falha na autorizacao, veja o terminal."
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args: object) -> None:  # silencia log padrao do stdlib
            pass

    server = HTTPServer(("127.0.0.1", port), Handler)
    server.timeout = timeout_seconds
    server.handle_request()
    server.server_close()

    if "code" not in captured:
        raise PublishError(f"Nao recebeu o redirect de autorizacao: {captured.get('error', 'timeout')}")
    return captured["code"]
