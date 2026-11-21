# Koia

**Koia 2.0.0** é um visualizador de wallpapers nativo para Linux, feito com
**GTK 4/libadwaita** e integrado à API pública do
[wallhaven.cc](https://wallhaven.cc). Permite procurar imagens, navegar por
páginas, manter favoritos locais, baixar arquivos e aplicar wallpapers no GNOME.

## Novidades da versão 2.0.0

- **Painel superior centralizado:** dez botões com o mesmo visual, incluindo
  os quatro antigos controles do cabeçalho (Downloads, Favoritos, Visor de
  página e Configurações). O painel desliza para cima ao desaparecer.
- **Exibição por teclado e mouse:** Tab/Shift+Tab revelam a barra; o mouse
  revela e mantém o painel aberto **somente ao entrar na área dos botões**.
  Fora dessa área, o painel se recolhe após 5 segundos, com animação de 250 ms.
  O foco de teclado, sozinho, não impede a ocultação.
- **Pesquisa mais previsível:** texto de busca só é enviado ao pressionar
  **Enter**. Alterações dos filtros aguardam 2 segundos de inatividade antes
  de atualizar os resultados. Se houver uma requisição em curso, a pesquisa
  mais recente é processada após sua conclusão.
- **Favoritos:** coração diretamente em cada imagem para remover o favorito
  sem abrir ou apagar o arquivo; atualização imediata da grade e do indicador.
  O **marcador (bookmark)** abre a coleção de favoritos; o coração da barra
  adiciona ou remove somente a imagem atual.
- **Configurações integradas:** `Adw.PreferencesDialog` no lugar da janela
  separada; clique no fundo escurecido ou pressione Esc para fechar.
  Restaurar padrões utiliza uma confirmação `Adw.AlertDialog`.
- **Navegação e acessibilidade:** correções de foco duplicado em grades e
  controles de preferências. **Toplist period** é ignorado pelo Tab quando a
  ordenação selecionada não é Toplist.

Consulte [CHANGELOG.md](CHANGELOG.md) para o histórico desta versão.

## Funcionalidades

- **Busca e filtros:** termo, categorias, níveis de pureza, ordenação,
  direção, período Toplist, resolução, proporção e cores.
- **Favoritos locais:** coleção persistida no computador; não sincroniza
  automaticamente com os favoritos da conta Wallhaven.
- **Downloads:** galeria dos arquivos locais com miniaturas carregadas em
  segundo plano, botão de exclusão por imagem e confirmação antes de apagar.
- **Visor de página:** grade de resultados com destaque da foto atual,
  navegação entre páginas, campo numérico e salto para a imagem escolhida.
  As páginas já visitadas podem ser reutilizadas do cache da sessão.
- **Aplicar wallpaper:** usa o arquivo local para definir o fundo do GNOME.
- **Idiomas:** inglês e português (Brasil), com troca imediata e preservação
  do contexto da galeria.
- **Bandeja opcional:** processo GTK3 separado, com slideshow, pausa,
  retomada e navegação pelos arquivos baixados.

> A chave de API do Wallhaven é opcional. Quando informada, permite acessar
> conteúdo restrito conforme as permissões da conta. Ela é salva localmente
> nas preferências; **não** sincroniza os favoritos locais com a conta.

## Painel superior e navegação

A ordem dos botões, da esquerda para a direita, é:

| Posição | Ação |
|---:|---|
| 1 | Imagem anterior |
| 2 | Próxima imagem |
| 3 | Adicionar/remover favorito da imagem atual |
| 4 | Baixar imagem atual / apagar arquivo já baixado |
| 5 | Entrar/sair da tela cheia |
| 6 | Aplicar como wallpaper |
| 7 | Abrir Downloads |
| 8 | Abrir galeria de Favoritos |
| 9 | Abrir Visor de página |
| 10 | Abrir Configurações |

O cabeçalho continua com o título e os controles da janela, mas os quatro
atalhos de galeria/preferências ficam **no fim do painel superior centralizado**.
O botão de favoritar a imagem usa um coração; o botão de **abrir a coleção**
usa um marcador, para diferenciar as ações.

- **Tab** revela o painel e percorre os controles; **Shift+Tab** permite
  percorrê-los no sentido inverso.
- Mover o mouse por qualquer outra parte da janela **não ativa** o painel.
  O hover fica restrito à região do painel no alto da galeria, inclusive
  quando está recolhido. Enquanto o ponteiro estiver ali, ele fica visível.
- Ao deixar a área, a contagem de **5 s** recomeça. A animação de **250 ms**
  revela descendo e recolhe para cima.
- O foco em um botão não mantém o painel aberto indefinidamente. Ao recolher,
  o foco dos controles ocultos é liberado.

### Configurações e pesquisa

**Configurações** é um `Adw.PreferencesDialog`, apresentado sobre a galeria
como os demais diálogos (`Adw.Dialog`) de **Favoritos**, **Downloads** e
**Visor de página**. Clique fora da caixa, no fundo escurecido, ou use **Esc**
para fechar; cliques nos controles internos não fecham o painel. Restaurar
padrões exige uma confirmação integrada `Adw.AlertDialog`.

Na configuração de ordenação, **Toplist period** só fica disponível e entra
na navegação por Tab quando **Sort by = Toplist**. Em outros modos, o foco
pula essa opção. Para buscar por palavra-chave, confirme o campo com Enter;
os demais filtros aplicam-se automaticamente após a pausa de 2 segundos.

## Requisitos

- Linux, Python **3.10+**, PyGObject
- GTK 4, **libadwaita 1.5+** (para `Adw.PreferencesDialog`), libsoup 3
  e GdkPixbuf. Distros com libadwaita mais antiga precisam atualizar essa
  dependência; apenas instalar GTK 4 não é suficiente.
- Para a bandeja: GTK 3 e libayatana-appindicator3; no GNOME, uma extensão
  compatível com AppIndicator/StatusNotifierItem pode ser necessária

## Instalação ou atualização

O instalador detecta **Debian/Ubuntu** (apt), **Fedora** (dnf) ou **Arch Linux**
(pacman) e instala o programa, o atalho e os ícones. Reexecutá-lo atualiza a
instalação existente.

```bash
git clone https://github.com/usr-kmasx/koia.git
cd koia
sudo ./install.sh
```

Para atualizar uma cópia já clonada:

```bash
cd ~/Projects/koia
git pull --ff-only
sudo ./install.sh
```

O comando `./install.sh --dry-run` mostra o que seria executado sem alterar
o sistema. A instalação utiliza `/opt/koia`, `/usr/bin/koia` e o menu de
aplicativos. Reinicie completamente o Koia e sua bandeja após atualizar.

Para executar sem instalar (com as dependências já presentes):

```bash
python3 run.py
```

O daemon da bandeja pode ser iniciado separadamente:

```bash
python3 run.py --tray
```

A desinstalação utiliza `sudo ./uninstall.sh`. Ela remove o programa e os
dados locais do Koia, mas **não apaga os wallpapers baixados** da pasta de
imagens. Faça backup de favoritos/configurações antes de desinstalar.

## Bandeja e slideshow

A bandeja roda em processo separado (GTK3) e se comunica com a interface
principal (GTK4) por D-Bus:

- **Abrir/Fechar:** o X esconde a janela principal; o processo pode
  continuar na bandeja.
- **Próximo/Anterior:** navega pelos wallpapers já baixados, sem fazer
  novos downloads.
- **Slide koia:** alterna automaticamente em 5/10/15/30/60 segundos ou
  1/3/5/30/60 minutos; permite pausar e retomar.
- **Sair:** encerra a aplicação e o processo da bandeja.

A configuração fica em `~/.config/koia/settings.ini`; os favoritos, em
`~/.config/koia/favorites.json`. Logs da bandeja ficam em
`~/.cache/koia/tray.log`. O autostart da bandeja é criado em
`~/.config/autostart/com.koia.Tray.desktop`.

## Desenvolvimento e testes

Execute os testes GTK sem apresentar as janelas:

```bash
GSETTINGS_BACKEND=memory python3 tests/tab_revealer_test.py
GSETTINGS_BACKEND=memory python3 tests/search_input_test.py
GSETTINGS_BACKEND=memory python3 tests/preferences_dialog_test.py
GSETTINGS_BACKEND=memory python3 tests/favorites_remove_test.py
GSETTINGS_BACKEND=memory python3 tests/downloads_delete_test.py
GSETTINGS_BACKEND=memory python3 tests/page_view_test.py
GSETTINGS_BACKEND=memory python3 tests/page_button_test.py
GSETTINGS_BACKEND=memory python3 tests/i18n_test.py
python3 tests/installer_test.py
```

A lista completa, com testes adicionais de downloads, memória e D-Bus,
está em [tests/README.md](tests/README.md).

## Estrutura do projeto

```text
koia/
├── README.md            # instalação, uso e arquitetura
├── CHANGELOG.md         # histórico de versões
├── run.py               # entrada da aplicação e do tray
├── install.sh           # dependências + instalação
├── uninstall.sh         # remoção (sem apagar wallpapers)
├── com.koia.Koia.desktop
├── icon.png
├── tests/               # regressões GTK, IPC, instalação e tray
└── koia/
    ├── __init__.py      # versão do aplicativo
    ├── main.py          # inicialização e estilo
    ├── window.py        # galeria, painel superior e navegação
    ├── config.py        # configurações, foco e persistência
    ├── api.py           # API Wallhaven
    ├── downloader.py    # downloads de imagens
    ├── downloads_view.py
    ├── favorites.py     # armazenamento local
    ├── favorites_view.py
    ├── page_view.py     # visor de página
    ├── image.py         # miniaturas e cache
    ├── background.py    # wallpaper GNOME
    ├── i18n.py          # traduções
    ├── tray.py          # bandeja GTK3
    ├── ipc.py           # integração D-Bus
    └── paths.py         # diretórios compartilhados
```

## Licença

Ainda não foi definida uma licença de redistribuição. Consulte o autor
antes de redistribuir o projeto.
