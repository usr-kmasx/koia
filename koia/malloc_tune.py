"""Teto de ``mmap`` no glibc para a carga de decodificação do Koia.

Por que isto existe
-------------------

Cada imagem vista aloca blocos grandes de tamanhos **diferentes** a
cada vez: corpo JPEG baixado (1–20 MB), pixbuf decodificado (``largura
× altura × 4``, até ~56 MB) e textura escalada (5–42 MB). O glibc por
padrão sobe sozinho o ``M_MMAP_THRESHOLD`` até 32 MB conforme blocos
grandes são liberados — depois disso esses blocos deixam de ser
``mmap`` individual e passam a ser alocados **dentro dos arenas de
thread**, que nunca são devolvidos ao sistema (só o arena principal é
aparável, e ninguém chama ``malloc_trim``).

Num dia de uso isso vira um RSS que sobe a cada visualização e nunca
desce. Medido num processo real de 9 horas: 1,1 GB de ``RssAnon`` com
15 arenas de ~64 MB (o ``HEAP_MAX_SIZE`` do glibc em x86-64) quase
cheios, sendo que as texturas vivas de verdade somavam ~170 MB — o
LRU de 128 MB do ``ImageLoader`` estava correto o tempo todo; o que
não voltava era a memória já liberada, fragmentada dentro dos arenas.

O conserto é fixar o teto em ``TETO``: todo bloco maior vira
``mmap`` próprio e o ``free`` vira ``munmap`` de volta, então o RSS
acompanha o conjunto vivo. Custa um par de chamadas de sistema por
decode — irrelevante no ritmo de uma imagem por segundo. Passar valor
explícito ao ``mallopt`` desliga o ajuste dinâmico do glibc, então o
teto não sobe mais sozinho.

Chamar ``instalar()`` uma vez por processo, antes do trabalho pesado
(``run.py`` faz isso antes de importar app e tray).
"""

import ctypes

# malloc.h: M_MMAP_THRESHOLD = -3
_M_MMAP_THRESHOLD = -3

# 4 MB: acima disso os blocos do decode (corpos, pixbufs, texturas)
# viram mmap individual; abaixo, o arena continua valendo a pena
TETO = 4 * 1024 * 1024

_instalado = False


def instalar():
    """Aplica o teto. Idempotente; devolve ``True`` quando valeu.

    Em libc sem ``mallopt`` (musl) ou sem ctypes, devolve ``False`` e
    o comportamento segue o padrão do sistema — ajuste de memória não
    pode ser motivo para o app não subir.
    """
    global _instalado
    if _instalado:
        return True
    try:
        libc = ctypes.CDLL(None)
        resultado = libc.mallopt(_M_MMAP_THRESHOLD, TETO)
    except (AttributeError, OSError):
        return False
    _instalado = bool(resultado)
    return _instalado
