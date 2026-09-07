"""Rebrand: reaproveita a thumbnail + outro do pipeline principal em um video curto que
JA EXISTE fora dele.

Diferente da geracao de clipes ponta a ponta (`clipador.pipeline`), aqui o usuario ja
tem um arquivo de video pronto (nao passou por download, transcricao, selecao nem
reenquadramento) e so quer "re-brandear" ele: gerar a mesma thumbnail composta usada no
pipeline principal, prende-la como primeiro frame do video (mesma logica de previa
automatica de plataforma), e adicionar um outro/encerramento estatico de alguns
segundos no final. Continua restrito ao formato curto/vertical.
"""

from __future__ import annotations
