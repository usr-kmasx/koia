#!/usr/bin/env python3
"""Instalador e desinstalador — lógica, sem tocar no sistema real.

O que cobre:

  1. a tabela de pacotes das três famílias (apt / dnf / pacman)
  2. --dry-run não escreve nada
  3. a árvore instalada (DESTDIR falso): código, .desktop, ícones
  4. o wrapper /usr/bin/koia — shebang + exec, porque run.py usa
     os.path.abspath(__file__), que NÃO resolve symlink: com um
     `ln -s` o sys.path viraria /usr/bin e o import quebraria
  5. o Icon= do .desktop aponta para um PNG que existe no hicolor, e
     cada PNG tem exatamente o tamanho declarado no nome do diretório
  6. nada de __pycache__, tests/ ou arquivos do repo na instalação
  7. a bandeja é opcional: pacote indisponível → avisa e o install
     instala o núcleo mesmo assim
  8. o uninstall remove programa + dados do usuário e NUNCA toca em
     ~/Pictures/Wallpapers (decisão explícita: pasta intocável)
  9. o uninstall é idempotente (segunda rodada: nada a remover, exit 0)
 10. o smoke check usa o runtime de verdade quando o gi existe

Nada de gerenciador de pacotes real: um PATH com shims de apt-get,
apt-cache, dpkg, dnf, rpm, pacman, gdbus e pkill registra as chamadas
e responde falso.

Uso: python3 tests/installer_test.py
"""

import os
import shutil
import struct
import subprocess
import sys
import tempfile

PROJETO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# espelho da tabela do install.sh — se o script mudar, isto acusa
TABELA = {
    "apt": (
        ["python3", "python3-gi", "gir1.2-gtk-4.0", "gir1.2-adw-1",
         "gir1.2-soup-3.0", "gir1.2-gdkpixbuf-2.0"],
        ["gir1.2-gtk-3.0", "gir1.2-ayatanaappindicator3-0.1"],
        "python3",
    ),
    "dnf": (
        ["python3", "python3-gobject", "gtk4", "libadwaita", "libsoup3",
         "gdk-pixbuf2"],
        ["gtk3", "libayatana-appindicator-gtk3"],
        "python3",
    ),
    "pacman": (
        ["python", "python-gobject", "gtk4", "libadwaita", "libsoup3",
         "gdk-pixbuf2"],
        ["gtk3", "libayatana-appindicator"],
        "python",
    ),
}

TAMANHOS = (16, 24, 32, 48, 64, 96, 128, 256, 512)

# shim único, gravado com nomes diferentes; consultas respondem falso,
# instalações são registradas em KOIA_SHIM_LOG
SHIM = """#!/bin/sh
last=""
for a in "$@"; do last="$a"; done
case "$1" in
    -s | -q | -Qi | -qi)
        # "está instalado?" — só o que a lista de teste manda
        grep -qx "$last" "$KOIA_FAKE_INSTALLED" 2>/dev/null && exit 0 || exit 1
        ;;
    show | -Si | info)
        # "existe no repositório?" — falso só para KOIA_FAKE_UNAVAILABLE
        grep -qx "$last" "$KOIA_FAKE_UNAVAILABLE" 2>/dev/null && exit 1 || exit 0
        ;;
    *)
        printf '%s %s\\n' "$(basename "$0")" "$*" >> "$KOIA_SHIM_LOG"
        exit 0
        ;;
esac
"""

SHIMS = ("apt-get", "apt-cache", "dpkg", "dnf", "rpm", "pacman",
         "gdbus", "pkill", "update-desktop-database", "gtk-update-icon-cache")


def rodar(script, env_extra, *args):
    """Roda um script do repo com os shims no PATH; devolve CompletedProcess."""
    env = dict(os.environ)
    env.update(env_extra)
    cmd = [os.path.join(PROJETO, script), *args]
    return subprocess.run(cmd, env=env, capture_output=True, text=True,
                          timeout=180)


def ler(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def pacotes_pedidos(linha):
    """Extrai os nomes de pacotes de uma linha de log de instalação.

    As flags (-y, --needed, --no-install-recommends) e o nome do próprio
    comando saem fora; sobra só o que foi pedido ao gerenciador.
    """
    ignora = {"apt-get", "install", "dnf", "pacman"}
    return {tok for tok in linha.split()
            if not tok.startswith("-") and tok not in ignora}


class Mundo:
    """Árvore temporária com shims, listas falsas e log de chamadas."""

    def __init__(self, raiz):
        self.shims = os.path.join(raiz, "shims")
        self.log = os.path.join(raiz, "chamadas.log")
        self.instalados = os.path.join(raiz, "instalados.txt")
        self.indisponiveis = os.path.join(raiz, "indisponiveis.txt")
        self.home = os.path.join(raiz, "home")
        os.makedirs(self.shims)
        os.makedirs(self.home)
        for nome in SHIMS:
            caminho = os.path.join(self.shims, nome)
            with open(caminho, "w", encoding="utf-8") as handle:
                handle.write(SHIM)
            os.chmod(caminho, 0o755)
        for caminho in (self.log, self.instalados, self.indisponiveis):
            open(caminho, "w", encoding="utf-8").close()

    def env(self, dest, pm, **extras):
        env = {
            "PATH": self.shims + os.pathsep + os.environ["PATH"],
            "DESTDIR": dest,
            "HOME": self.home,
            "KOIA_FORCE_PM": pm,
            "KOIA_SHIM_LOG": self.log,
            "KOIA_FAKE_INSTALLED": self.instalados,
            "KOIA_FAKE_UNAVAILABLE": self.indisponiveis,
            "KOIA_SKIP_DEPS": "1",   # layout não precisa do runtime real
        }
        env.update(extras)
        return env

    def env_sem_destdir(self, pm):
        """Env do caminho REAL: a variável DESTDIR nem existe.

        É a situação de produção (`./install.sh` à mão) — e a que faltava
        cobrir: `set -u` derrubava o script num "$DESTDIR" cru.
        """
        env = self.env("/tmp/koia-nunca-usado", pm)
        del env["DESTDIR"]
        return env

    def marcar_instalado(self, *pacotes):
        with open(self.instalados, "a", encoding="utf-8") as handle:
            handle.write("".join(f"{p}\n" for p in pacotes))

    def marcar_indisponivel(self, *pacotes):
        with open(self.indisponiveis, "a", encoding="utf-8") as handle:
            handle.write("".join(f"{p}\n" for p in pacotes))

    def chamadas(self):
        return ler(self.log).splitlines()

    def limpar_log(self):
        open(self.log, "w", encoding="utf-8").close()


# ---------------------------------------------------------------------------
def testar_dry_run(mundo, raiz):
    """--dry-run: sai 0 e não cria árvore nenhuma."""
    for pm in TABELA:
        dest = os.path.join(raiz, f"dry-{pm}")
        saida = rodar("install.sh", mundo.env(dest, pm), "--dry-run")
        assert saida.returncode == 0, saida.stderr
        assert not os.path.exists(dest), f"--dry-run escreveu algo em {pm}"
    print("[installer] --dry-run não escreve nada (3 famílias) ok")


def testar_caminho_real(mundo):
    """O caminho de produção: sem DESTDIR nenhum (é o `./install.sh` à mão).

    Regressão direta: o install.sh referenciava "$DESTDIR" cru em 8
    linhas e o `set -u` derrubava o script na PRIMEIRA escrita quando a
    variável não existia. Nenhum teste pegou, porque todos rodavam com
    DESTDIR (o prefixo era a razão de existirem).

    Os dois casos rodam SÓ com --dry-run: sem ele seria instalação de
    verdade na máquina de quem rodar o teste.
    """
    env = mundo.env_sem_destdir("pacman")
    mundo.limpar_log()

    saida = rodar("install.sh", env, "--dry-run")
    assert saida.returncode == 0, saida.stderr + saida.stdout
    assert "/opt/koia" in saida.stdout and "/usr/bin/koia" in saida.stdout, \
        "sem DESTDIR o install tem de mirar os caminhos do sistema"
    # --dry-run não toca no sistema: nem cache de desktop/ícone atualizado
    assert "update-desktop-database" not in " ".join(mundo.chamadas()) and \
        "gtk-update-icon-cache" not in " ".join(mundo.chamadas()), \
        "--dry-run atualizou cache no sistema real"

    saida = rodar("uninstall.sh", env, "--dry-run")
    assert saida.returncode == 0, saida.stderr + saida.stdout

    print("[installer] caminho real (sem DESTDIR, só --dry-run) ok")


def testar_simetria_sudo():
    """install.sh e uninstall.sh têm de exigir root do MESMO jeito.

    Regressão: o uninstall.sh saiu sem o root check que o install.sh
    tem — na prática, `./uninstall.sh` sem sudo morria no meio com
    "rm: Permission denied" e não removia nada (nem ~/.config/koia, que
    vem depois na ordem). O sudo de verdade não dá para exercitar sem
    root, então a regra é estática: os dois carregam o mesmo trecho.
    """
    install = ler(os.path.join(PROJETO, "install.sh"))
    uninstall = ler(os.path.join(PROJETO, "uninstall.sh"))

    # o re-exec com sudo, com a isenção de DESTDIR/--dry-run
    bloco = ('if [ "$DRY" -eq 0 ] && [ -z "$ROOT" ] && '
             '[ "$(id -u)" -ne 0 ]; then\n'
             '    if command -v sudo >/dev/null 2>&1; then\n'
             '        info "root is required — retrying with sudo"\n'
             '        exec sudo "$0" "$@"\n'
             '    fi\n'
             '    die "run as root: sudo $0"\n'
             'fi')
    for nome, conteudo in (("install.sh", install),
                           ("uninstall.sh", uninstall)):
        assert bloco in conteudo, f"{nome} sem o root check (ou divergente)"

    # ROOT é uma variável só; "$DESTDIR" cru derruba o set -u
    for nome, conteudo in (("install.sh", install),
                           ("uninstall.sh", uninstall)):
        assert 'ROOT="${DESTDIR:-}"' in conteudo, \
            f"{nome} sem ROOT=\"${{DESTDIR:-}}\""
        cruas = [linha for linha in conteudo.splitlines()
                 if "$DESTDIR" in linha and not linha.lstrip().startswith("#")]
        assert not cruas, f"{nome} referencia $DESTDIR cru: {cruas}"

    print("[installer] simetria sudo/ROOT dos dois scripts ok")


def testar_install(mundo, raiz):
    for pm, (nucleo, bandeja, ja_instalado) in TABELA.items():
        dest = os.path.join(raiz, f"inst-{pm}")
        mundo.limpar_log()
        # só o primeiro pacote do núcleo já veio da distro: o resto tem
        # de ser pedido. Prova que install.sh instala só o que falta.
        mundo.marcar_instalado(ja_instalado)

        saida = rodar("install.sh", mundo.env(dest, pm))
        assert saida.returncode == 0, saida.stderr + saida.stdout

        # --- pacotes: os que faltavam, nenhum a mais
        pedidos = set()
        for linha in mundo.chamadas():
            campos = linha.split()
            if len(campos) > 1 and campos[1] in ("install", "-S"):
                pedidos.update(pacotes_pedidos(linha))
        assert ja_instalado not in pedidos, f"{ja_instalado} já estava lá"
        assert pedidos == set(nucleo + bandeja) - {ja_instalado}, \
            f"pacotes errados em {pm}: {sorted(pedidos)}"

        # --- árvore de código
        for arquivo in ("run.py", "icon.png", "koia/main.py", "koia/i18n.py",
                        "koia/data/icons/koia-heart-symbolic.svg"):
            assert os.path.isfile(os.path.join(dest, "opt/koia", arquivo)), \
                f"{arquivo} não instalado em {pm}"
        copia = os.path.join(dest, "opt/koia")
        for raiz2, _dirs, arquivos in os.walk(copia):
            for nome in arquivos:
                assert not nome.endswith(".pyc"), f"{nome} foi instalado"
            assert "__pycache__" not in raiz2, f"{raiz2} foi instalado"
        for fora in ("tests", ".qa-tests", "install.sh", "uninstall.sh"):
            assert not os.path.exists(os.path.join(copia, fora)), \
                f"{fora} não pertence à instalação"

        # --- wrapper: shebang sh + exec, porque symlink não resolve
        wrapper = os.path.join(dest, "usr/bin/koia")
        assert os.access(wrapper, os.X_OK), "wrapper sem permissão de exec"
        conteudo = ler(wrapper)
        assert conteudo.startswith("#!/bin/sh\n"), "wrapper sem shebang"
        assert 'exec python3 /opt/koia/run.py "$@"' in conteudo, \
            "wrapper não faz exec com os argumentos passados"
        # o caminho final é o do sistema, não o do DESTDIR de teste
        assert dest not in conteudo, "wrapper vazou o caminho de teste"

        # --- .desktop: Exec=koia passa a valer pelo wrapper
        desktop = ler(os.path.join(
            dest, "usr/share/applications/com.koia.Koia.desktop"))
        assert "\nExec=koia\n" in desktop, "desktop sem Exec=koia"
        assert "\nIcon=com.koia.Koia\n" in desktop, "desktop sem o ícone"

        # --- ícones: existem, são PNG e o tamanho bate com o diretório
        for tamanho in TAMANHOS:
            caminho = os.path.join(
                dest, f"usr/share/icons/hicolor/{tamanho}x{tamanho}"
                      f"/apps/com.koia.Koia.png")
            with open(caminho, "rb") as handle:
                head = handle.read(24)
            assert head[:8] == b"\x89PNG\r\n\x1a\n", f"{caminho} não é PNG"
            largura, altura = struct.unpack(">II", head[16:24])
            assert (largura, altura) == (tamanho, tamanho), \
                f"{caminho} tem {largura}x{altura}"

        # --- o install NÃO cria autostart (o tray cria no 1º uso)
        assert not os.path.exists(os.path.join(
            mundo.home, ".config/autostart")), \
            "install.sh não pode criar autostart"

        print(f"[installer] install em {pm}: pacotes, árvore, wrapper, "
              f".desktop e ícones ok")


def testar_bandeja_opcional(mundo, raiz):
    """Fedora < 40: ayatana fora do repo → avisa e instala o núcleo."""
    dest = os.path.join(raiz, "inst-sem-ayatana")
    mundo.limpar_log()
    mundo.marcar_indisponivel("libayatana-appindicator-gtk3")
    saida = rodar("install.sh", mundo.env(dest, "dnf"))
    assert saida.returncode == 0, saida.stderr + saida.stdout
    assert "WARNING" in saida.stderr and \
        "libayatana-appindicator-gtk3" in saida.stderr, \
        "a ausência da bandeja precisa ser avisada"
    pedidos = set()
    for linha in mundo.chamadas():
        if linha.startswith("dnf install"):
            pedidos.update(linha.split()[2:])
    assert "libayatana-appindicator-gtk3" not in pedidos
    assert os.path.isfile(os.path.join(dest, "opt/koia/run.py")), \
        "o núcleo tinha de ser instalado mesmo sem a bandeja"
    mundo.marcar_indisponivel()   # limpa para os próximos testes
    open(mundo.indisponiveis, "w", encoding="utf-8").close()
    print("[installer] bandeja opcional: avisa e segue ok")


def testar_smoke_check(mundo, raiz):
    """Com o runtime real, o smoke check roda de verdade."""
    dest = os.path.join(raiz, "inst-smoke")
    mundo.limpar_log()
    # sem KOIA_SKIP_DEPS: o install importa o runtime de verdade
    extras = mundo.env(dest, "pacman")
    del extras["KOIA_SKIP_DEPS"]

    probe = subprocess.run(
        [sys.executable, "-c",
         "import gi\n"
         "gi.require_version('Gtk', '4.0')\n"
         "gi.require_version('Adw', '1')\n"
         "gi.require_version('Soup', '3.0')\n"
         "from gi.repository import Adw, GdkPixbuf, Gtk, Soup\n"],
        capture_output=True, text=True)

    # Gtk 3 e 4 não coexistem num processo: o smoke do install também os
    # separa, então o probe tem de ser dois processos (igual ao script)
    if probe.returncode == 0:
        probe = subprocess.run(
            [sys.executable, "-c",
             "import gi\n"
             "gi.require_version('Gtk', '3.0')\n"
             "gi.require_version('AyatanaAppIndicator3', '0.1')\n"
             "from gi.repository import AyatanaAppIndicator3, Gtk\n"],
            capture_output=True, text=True)

    saida = rodar("install.sh", extras)
    if probe.returncode == 0:
        assert saida.returncode == 0, saida.stderr + saida.stdout
        assert os.path.isfile(os.path.join(dest, "opt/koia/run.py"))
        print("[installer] smoke check com o runtime real ok")
    else:
        # sem runtime o install tem de ABORTAR antes de copiar arquivo
        assert saida.returncode != 0, "sem runtime o install não podia seguir"
        assert not os.path.exists(os.path.join(dest, "opt/koia")), \
            "o install copiou arquivo sem runtime"
        print("[installer] smoke check: runtime ausente → abortou antes "
              "de copiar (gi indisponível nesta máquina)")


def testar_uninstall(mundo, raiz):
    dest = os.path.join(raiz, "inst-para-remover")
    rodar("install.sh", mundo.env(dest, "pacman"))

    # dados do usuário de mentira, incluindo a pasta de downloads
    for pasta in (".config/koia", ".cache/koia", ".config/autostart",
                  "Pictures/Wallpapers"):
        os.makedirs(os.path.join(mundo.home, pasta), exist_ok=True)
    for arquivo in (".config/koia/settings.ini", ".cache/koia/tray.log",
                    ".config/autostart/com.koia.Tray.desktop",
                    "Pictures/Wallpapers/wall.png"):
        open(os.path.join(mundo.home, arquivo), "w", encoding="utf-8").close()

    # --dry-run: nada some
    mundo.limpar_log()
    saida = rodar("uninstall.sh", mundo.env(dest, "pacman"), "--dry-run")
    assert saida.returncode == 0, saida.stderr
    assert os.path.isfile(os.path.join(dest, "opt/koia/run.py")), \
        "--dry-run do uninstall apagou de verdade"

    # real
    mundo.limpar_log()
    saida = rodar("uninstall.sh", mundo.env(dest, "pacman"))
    assert saida.returncode == 0, saida.stderr + saida.stdout

    # parou o que estivesse rodando antes de apagar
    chamadas = " ".join(mundo.chamadas())
    assert "gdbus" in chamadas and "Quit" in chamadas, \
        "o uninstall tinha de pedir Quit() ao app pelo D-Bus"
    assert "pkill" in chamadas, \
        "o uninstall tinha de parar o tray (ele não expõe método no bus)"

    # programa e dados sumiram
    assert not os.path.exists(os.path.join(dest, "opt/koia")), \
        "/opt/koia continuou depois do uninstall"
    assert not os.path.exists(os.path.join(dest, "usr/bin/koia"))
    assert not os.path.exists(os.path.join(
        dest, "usr/share/applications/com.koia.Koia.desktop"))
    for tamanho in TAMANHOS:
        assert not os.path.exists(os.path.join(
            dest, f"usr/share/icons/hicolor/{tamanho}x{tamanho}"
                  f"/apps/com.koia.Koia.png")), "ícone sobrou"
    for arquivo in (".config/koia", ".cache/koia",
                    ".config/autostart/com.koia.Tray.desktop"):
        assert not os.path.exists(os.path.join(mundo.home, arquivo)), \
            f"dado do usuário {arquivo} sobrou"

    # a pasta de downloads NUNCA é tocada (decisão explícita)
    assert os.path.isfile(os.path.join(
        mundo.home, "Pictures/Wallpapers/wall.png")), \
        "o uninstall apagou os wallpapers baixados"
    assert "left untouched" in saida.stdout, \
        "o uninstall tinha de avisar que os wallpapers ficaram"

    # idempotente
    saida = rodar("uninstall.sh", mundo.env(dest, "pacman"))
    assert saida.returncode == 0
    assert "nothing to remove" in saida.stdout, \
        "segunda rodada devia dizer que não há nada a remover"

    print("[installer] uninstall: programa + dados fora, downloads "
          "intocados, idempotente ok")


# ---------------------------------------------------------------------------
def main():
    raiz = tempfile.mkdtemp(prefix="koia-installer-")
    try:
        mundo = Mundo(raiz)
        testar_dry_run(mundo, raiz)
        testar_caminho_real(mundo)
        testar_simetria_sudo()
        testar_install(mundo, raiz)
        testar_bandeja_opcional(mundo, raiz)
        testar_smoke_check(mundo, raiz)
        testar_uninstall(mundo, raiz)
    finally:
        shutil.rmtree(raiz, ignore_errors=True)
    print("[installer] todos os testes passaram")


if __name__ == "__main__":
    sys.exit(main())
