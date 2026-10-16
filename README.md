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

```bash
install -Dm644 com.koia.Koia.desktop ~/.local/share/applications/com.koia.Koia.desktop
```

## Estrutura do projeto

```
koia/
├── run.py            # ponto de entrada
├── com.koia.Koia.desktop
├── icon.png
├── tests/            # suíte de regressão (GTK + D-Bus; ver tests/README.md)
└── koia/             # pacote principal
    ├── main.py       # inicialização do app
    ├── window.py     # janela principal e galeria
    ├── api.py        # cliente da API do wallhaven.cc
    ├── downloader.py # fila de downloads
    ├── config.py     # configurações
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
