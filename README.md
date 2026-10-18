# Koia

**Koia** é um visualizador de wallpapers GTK4 para Linux, movido pela API pública do
[wallhaven.cc](https://wallhaven.cc). Explore, favorite e baixe wallpapers com uma
interface limpa e nativa do GNOME.

## Funcionalidades

- 🔍 **Busca** — filtros por categoria, pureza (SFW / sketchy / NSFW), resolução e cores
- ❤️ **Favoritos** — listinha local, sincroniza com os favoritos da sua conta wallhaven
- ⬇️ **Downloads** — fila de download com progresso e visual dedicado
- ▶️ **Visor de página** — grade navegável das páginas de resultados
  (‹ › e campo de página no rodapé); a foto carregada fica destacada e
  clicar em outra salta direto pra ela
- 🖼️ **Definir wallpaper** — para GNOME e derivados, direto da galeria
- 🌐 **Idioma** — inglês por padrão, com português (Brasil) nas
  Configurações; a troca vale na hora, sem reiniciar
- 🏷️ **Tags e metadados** — veja os detalhes de cada wallpaper antes de baixar
- 📌 **Bandeja (tray)** — daemon em segundo plano com slideshow e navegação
  pelos wallpapers já baixados

> A API key do wallhaven é opcional (só para conteúdo NSFW e favoritos da conta).
> Ela é salva localmente, nas configurações do app — nunca vai para o código.

## Requisitos

- Python 3.10+
- GTK 4 + **libadwaita**
- **libsoup 3**
- PyGObject (`python3-gobject`)
- Para a bandeja: GTK 3 + **libayatana-appindicator3** (`python3-gi`); no GNOME,
  a extensão **AppIndicator and KStatusNotifierItem Support**

## Como rodar

```bash
python3 run.py
```

O app sobe junto um daemon de bandeja, se ainda não estiver rodando. Para
rodar só o daemon (é o que o autostart usa):

```bash
python3 run.py --tray
```

## Idioma

O código usa o **inglês como língua-fonte** e a opção **Idioma** das
Configurações (no fim do painel) troca para português (Brasil).

- A troca vale **na hora**: a janela é reconstruída e mantém o que estava
  na tela (imagem, página, tela cheia); o painel de configurações fecha e
  reabre no idioma novo
- A bandeja é outro processo e acompanha sozinha, observando o
  `settings.ini` — sem reiniciar nada
- Um texto sem tradução aparece em inglês em vez de quebrar a interface;
  `tests/i18n_test.py` falha antes disso acontecer

## Bandeja e slideshow

A bandeja é um processo separado (GTK3 e GTK4 não coexistem no mesmo
processo); app e tray conversam por D-Bus.

- **Abrir / Fechar** — abre e esconde a janela (fechar com X só esconde)
- **Próximo / Anterior** — navega pelos wallpapers **já baixados**; a bandeja
  nunca baixa nada
- **Slide koia** — troca automática: desligado, 5/10/15/30/60 s ou
  1/3/5/30/60 min
- **Pausar / Retomar** — congela o slide sem desligá-lo
- **Sair** — encerra a bandeja **e** o app; não sobra nada rodando

Detalhes:

- A opção de slide fica em `~/.config/koia/settings.ini`, grupo `[tray]`
- No primeiro uso o tray cria o autostart discreto
  `~/.config/autostart/com.koia.Tray.desktop` (apague o arquivo para
  desativar)
- Erros do daemon são logados em `~/.cache/koia/tray.log`
- A janela não tem botão de fechar de verdade: o X só esconde — quem mata
  o app é o **Sair** da bandeja

## Instalação

Um instalador/desinstalador que detecta a distro e instala tudo
(dependências, código, atalho e ícone):

```bash
git clone https://github.com/usr-kmasx/koia
cd koia
sudo ./install.sh      # instala em /opt/koia + /usr/bin/koia + ícones
sudo ./uninstall.sh    # remove o programa E os dados (~/.config/koia, ~/.cache/koia)
```

Suporta **Debian/Ubuntu** (apt), **Fedora** (dnf) e **Arch** (pacman) — a
deteção é pelo `/etc/os-release`. Instala só o que falta (rodar de novo é
atualização), e `./install.sh --dry-run` mostra tudo que faria sem escrever.

| | Pacotes |
|---|---|
| **apt** (Debian 12+, Ubuntu 22.04+) | `python3 python3-gi gir1.2-gtk-4.0 gir1.2-adw-1 gir1.2-soup-3.0 gir1.2-gdkpixbuf-2.0` + bandeja `gir1.2-gtk-3.0 gir1.2-ayatanaappindicator3-0.1` |
| **dnf** (Fedora) | `python3 python3-gobject gtk4 libadwaita libsoup3 gdk-pixbuf2` + bandeja `gtk3 libayatana-appindicator-gtk3` |
| **pacman** (Arch) | `python python-gobject gtk4 libadwaita libsoup3 gdk-pixbuf2` + bandeja `gtk3 libayatana-appindicator` |

Detalhes:

- A **bandeja é opcional**: se o pacote ayatana não existir na distro
  (Fedora < 40), o install avisa e segue — o app GTK4 vive sem ela
- O `install.sh` confere os imports do runtime antes de copiar qualquer
  arquivo (`Gtk 4 + libadwaita + libsoup 3`); Python 3.10+ é exigido
- O `/usr/bin/koia` é um **wrapper** com `exec`, não um symlink: `run.py`
  usa `os.path.abspath(__file__)`, que não segue symlink e quebraria o import
- O ícone (`icon.png`, 1254×1254) é **reduzido na hora** para os tamanhos do
  tema hicolor, via GdkPixbuf — zero dependência extra, sem ImageMagick
- O `uninstall.sh` para o app e a bandeja antes de apagar (D-Bus `Quit()` +
  `pkill`, já que o tray não expõe método no bus)
- **`~/Pictures/Wallpapers` nunca é tocado** — os wallpapers baixados são
  seus; o desinstalador só avisa que a pasta existe

`python3 run.py` continua funcionando sem instalar nada.

## Estrutura do projeto

```
koia/
├── run.py            # ponto de entrada
├── install.sh        # instalador: deps (apt/dnf/pacman) + código + atalho + ícone
├── uninstall.sh      # desinstalador: programa + dados (downloads intocados)
├── com.koia.Koia.desktop
├── icon.png
├── tests/            # suíte de regressão (GTK + D-Bus; ver tests/README.md)
└── koia/             # pacote principal
    ├── main.py       # inicialização do app
    ├── window.py     # janela principal e galeria
    ├── api.py        # cliente da API do wallhaven.cc
    ├── downloader.py # fila de downloads
    ├── config.py     # configurações
    ├── i18n.py       # idioma (neutro de GTK: app GTK4 e tray GTK3)
    ├── favorites*.py # model + view de favoritos
    ├── downloads_view.py
    ├── page_view.py  # visor da página inteira (▦ da HeaderBar)
    ├── image.py      # cache e processamento de imagem
    ├── background.py # mudança de wallpaper em background
    ├── tray.py       # daemon da bandeja (GTK3; roda com --tray)
    ├── ipc.py        # ponte D-Bus entre app e tray
    └── paths.py      # caminhos compartilhados (GTK-neutro)
```

## Licença

Ainda não definida. Entre em contato antes de redistribuir.
