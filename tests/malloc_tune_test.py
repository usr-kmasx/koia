#!/usr/bin/env python3
"""``koia/malloc_tune.py`` — o RSS não pode voltar a acumular.

Três provas, sem GUI e sem rede:

  1. o ``mallopt`` do glibc aceita o teto e ``instalar()`` é
     idempotente;
  2. ``run.py`` aplica o teto ANTES de importar app e tray (senão os
     primeiros blocos grandes já nascem no arena errado);
  3. a regressão: decodes simultâneos (6, o limite do ``ImageLoader``)
     com os tamanhos REAIS de imagem — corpo JPEG, pixbuf e textura
     vivos ao mesmo tempo e diferentes a cada visualização — não
     podem deixar memória retida no processo. Sem o teto, o glibc
     aloca esses blocos dentro de um arena por thread (o teto
     dinâmico sobe até 32 MB) e nenhum arena é devolvido ao sistema
     — o RSS subia a cada visualização e nunca descia (medido em
     produção: 1,1 GB de ``RssAnon`` com ~170 MB de texturas vivas
     de verdade).
"""
import gc
import os
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from koia import malloc_tune  # noqa: E402

PROJETO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _rss_kib():
    """``RssAnon`` do processo em KiB (Linux: /proc é o alvo do app)."""
    with open("/proc/self/status", encoding="utf-8") as handle:
        for linha in handle:
            if linha.startswith("RssAnon:"):
                return int(linha.split()[1])
    raise AssertionError("RssAnon sumiu do /proc/self/status")


def _tocar(buf):
    """Marca uma vez por página — memória não tocada não conta em RSS."""
    buf[::4096] = b"\x01" * len(buf[::4096])
    return buf


def teste_instalacao():
    assert malloc_tune.instalar(), \
        "mallopt não aceitou o teto (libc sem mallopt?)"
    assert malloc_tune.instalar(), "instalar() perdeu o estado na 2ª chamada"
    print("[malloc] mallopt aplicado e idempotente ok")


def teste_ligacao():
    """``run.py`` instala o teto antes de importar app/tray."""
    with open(os.path.join(PROJETO, "run.py"), encoding="utf-8") as handle:
        run_py = handle.read()
    assert "instalar()" in run_py, "run.py não chama malloc_tune.instalar()"
    assert run_py.index("instalar()") < run_py.index("from koia.main"), \
        "instalar() roda depois do import do app"
    assert run_py.index("instalar()") < run_py.index("from koia.tray"), \
        "instalar() roda depois do import do tray"
    print("[malloc] run.py aplica o teto antes do app e do tray ok")


def teste_regressao_rss():
    """Decodes simultâneos com tamanhos variados não retêm memória.

    Reproduz a carga real do app: até 6 decodes ao mesmo tempo (o
    limite do ``Semaphore(6)`` do ``ImageLoader``), cada um com corpo
    JPEG, pixbuf decodificado e textura escalada existindo **juntos**
    e de tamanhos diferentes a cada visualização. Mede o ``RssAnon``
    antes e depois de todo o trabalho ser liberado: com o teto, cada
    bloco grande vira ``mmap`` próprio e o ``free`` vira ``munmap``;
    sem ele, os blocos ≤ 32 MB ficam presos no arena da thread — que
    nunca é devolvido.
    """
    TRABALHADORES = 6       # igual ao Semaphore(6) do ImageLoader
    POR_TRABALHADOR = 8
    CORPOS = (1, 4, 9, 16)             # MiB — corpo do download
    PIXBUFS = (14, 24, 31, 42)         # MiB — decodificação completa
    TEXTURAS = (5, 14, 24, 35, 42)     # MiB — escalada p/ exibição
    TETO_RETENCAO = 64 * 1024         # KiB — prejuízo aceito (ruído)

    assert malloc_tune.instalar(), "sem o teto o teste mediria o defeito"

    def decodificar(repeticoes):
        for i in range(repeticoes):
            # os três blocos de um decode existem juntos, como no app
            corpo = _tocar(bytearray(CORPOS[i % len(CORPOS)] << 20))
            pixbuf = _tocar(bytearray(PIXBUFS[i % len(PIXBUFS)] << 20))
            textura = _tocar(bytearray(TEXTURAS[i % len(TEXTURAS)] << 20))
            del corpo, pixbuf, textura

    base = _rss_kib()
    trabalhadores = [
        threading.Thread(target=decodificar, args=(POR_TRABALHADOR,))
        for _ in range(TRABALHADORES)
    ]
    for t in trabalhadores:
        t.start()
    for t in trabalhadores:
        t.join()
    gc.collect()

    crescido = _rss_kib() - base
    assert crescido < TETO_RETENCAO, (
        f"{crescido // 1024} MiB retidos após {TRABALHADORES} threads "
        f"de decode liberarem tudo (teto {TETO_RETENCAO // 1024} MiB) — "
        "o RSS voltou a acumular: bloco grande dentro do arena "
        "sem munmap"
    )
    print(f"[malloc] {TRABALHADORES} decodes simultâneos sem "
          f"retenção de RSS ok")


if __name__ == "__main__":
    teste_instalacao()
    teste_ligacao()
    teste_regressao_rss()
    print("[malloc] todos os testes passaram")
