# Koia

**Koia** é um visualizador de wallpapers GTK4 para Linux, movido pela API pública do
[wallhaven.cc](https://wallhaven.cc). Explore, favorite e baixe wallpapers com uma
interface limpa e nativa do GNOME.

## Funcionalidades

- 🔍 **Busca** — filtros por categoria, pureza (SFW / sketchy / NSFW), resolução e cores
- ❤️ **Favoritos** — listinha local, sincroniza com os favoritos da sua conta wallhaven
- ⬇️ **Downloads** — fila de download com progresso e visual dedicado
- 🖼️ **Definir wallpaper** — para GNOME e derivados, direto da galeria
- 🏷️ **Tags e metadados** — veja os detalhes de cada wallpaper antes de baixar

> A API key do wallhaven é opcional (só para conteúdo NSFW e favoritos da conta).
> Ela é salva localmente, nas configurações do app — nunca vai para o código.

## Captura de tela

*(por enquanto, veja `icon.png` — screenshots em breve)*

## Requisitos

- Python 3.10+
- GTK 4 + **libadwaita**
- **libsoup 3**
- PyGObject (`python3-gobject`)

## Como rodar

```bash
python3 run.py
```

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
└── koia/             # pacote principal
    ├── main.py       # inicialização do app
    ├── window.py     # janela principal e galeria
    ├── api.py        # cliente da API do wallhaven.cc
    ├── downloader.py # fila de downloads
    ├── config.py     # configurações
    ├── favorites*.py # model + view de favoritos
    ├── downloads_view.py
    ├── image.py      # cache e processamento de imagem
    └── background.py # mudança de wallpaper em background
```

## Licença

Ainda não definida. Entre em contato antes de redistribuir.
