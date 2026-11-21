# Histórico de versões — Koia

As mudanças significativas são registradas aqui. A versão do aplicativo
fica definida em `koia/__init__.py`.

## [2.0.0] — 2026-11-21

### Interface e navegação

- Unificada a barra inferior em **dez botões**: anterior, próximo, favoritar,
  download/excluir, tela cheia, aplicar wallpaper, Downloads, Favoritos,
  Visor de página e Configurações. Os quatro últimos saíram do cabeçalho.
- Todos os botões da barra inferior utilizam o mesmo estilo visual.
- A barra agora é revelada por **Tab/Shift+Tab** ou por hover do mouse
  **somente na região do painel** (não no restante da janela).
- A barra permanece aberta enquanto o mouse está sobre ela; ao sair, recolhe
  após **5 segundos**, com animação de **250 ms**. O foco de teclado não
  impede a ocultação e é liberado quando a barra recolhe.
- Corrigida a navegação com Tab/Shift+Tab após ocultação e reconstrução da
  interface ao trocar de idioma.

### Pesquisa e configurações

- O texto de busca é confirmado apenas com **Enter**, evitando pesquisas
  em cada caractere.
- Alterações de filtros têm espera de **2 segundos**; pesquisas mais recentes
  não são descartadas enquanto uma requisição anterior está em andamento.
- Eliminadas paradas de foco duplicadas em controles e linhas de preferência.
- **Toplist period** perde sensibilidade e foco quando a ordenação não é
  Toplist, e recupera ambos ao selecionar Toplist.
- Mantido `Adw.PreferencesWindow` para Configurações; os demais painéis
  continuam em `Adw.Dialog`.

### Favoritos, downloads e visor

- Favoritos agora podem ser removidos diretamente na grade pelo coração
  individual, sem abrir a imagem ou apagar o arquivo.
- Ao remover um favorito, a grade, o estado vazio, o foco e o indicador
  principal são atualizados.
- Removido o foco duplicado dos contêineres de cards em Favoritos e Downloads.
- Aperfeiçoada a navegação do visor por páginas e o comportamento do Enter
  no campo de número da página, com testes de regressão.

### Qualidade e documentação

- Adicionados testes de barra/hover/teclado, remoção de favoritos e busca.
- Expandidos os testes de idioma, configurações, downloads e visor de página.
- Atualizados README e instruções de testes para o comportamento da 2.0.0.
- Atualizada a identificação de versão no aplicativo e no User-Agent HTTP.

## [1.0.0] — versão anterior

- Visualizador GTK4/libadwaita com busca Wallhaven, favoritos locais,
  downloads, visor de página, wallpapers do GNOME e slideshow na bandeja.
- Cliente de rede assíncrono, cache de imagens e instalador para
  Debian/Ubuntu, Fedora e Arch Linux.
- Melhorias de retenção de memória incluídas no último commit anterior
  (`e830ac2`).
