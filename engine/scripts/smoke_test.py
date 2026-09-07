"""Smoke test: verifica se as credenciais de API (Claude e YouTube) estao funcionando."""

import os
import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(override=True)  # .env do projeto sempre vence env var solta do sistema


def main() -> int:
    ok = True

    print("== Smoke test: Clipador ==\n")

    from clipador.llm.provider import TEXT_LLM_PROVIDER

    print(f"-- LLM de texto do motor ({TEXT_LLM_PROVIDER}) --")
    required_env_var = "GEMINI_API_KEY" if TEXT_LLM_PROVIDER == "gemini" else "ANTHROPIC_API_KEY"
    if TEXT_LLM_PROVIDER == "claude" and os.environ.get("CLIPADOR_LLM_AUTH_MODE", "oauth") == "oauth":
        required_env_var = "CLAUDE_CODE_OAUTH_TOKEN"
    if not os.environ.get(required_env_var):
        print(f"PENDENTE: {required_env_var} nao esta definida no ambiente (.env).")
        ok = False
    else:
        try:
            if TEXT_LLM_PROVIDER == "gemini":
                from clipador.llm.gemini_client import test_connection
            else:
                from clipador.llm.claude_client import test_connection

            if test_connection():
                print(f"OK: conexao com o provedor de texto ({TEXT_LLM_PROVIDER}) funcionando.")
            else:
                print(f"FALHA: nao foi possivel confirmar a conexao com o provedor de texto ({TEXT_LLM_PROVIDER}).")
                ok = False
        except Exception as exc:
            print(f"FALHA: erro ao testar o provedor de texto ({TEXT_LLM_PROVIDER}): {exc}")
            ok = False

    print("\n-- YouTube Data API --")
    if not os.environ.get("YOUTUBE_API_KEY"):
        print("PENDENTE: YOUTUBE_API_KEY nao esta definida no ambiente (.env).")
        ok = False
    else:
        try:
            from clipador.youtube.client import get_client

            get_client()
            print("OK: client da YouTube Data API criado com sucesso.")
        except Exception as exc:
            print(f"FALHA: erro ao criar o client da YouTube Data API: {exc}")
            ok = False

    print()
    if ok:
        print("Smoke test concluido: tudo OK.")
        return 0

    print("Smoke test concluido com pendencias/falhas (ver acima).")
    return 1


if __name__ == "__main__":
    sys.exit(main())
