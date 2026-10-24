# Rotevo

**Transforme um roteiro em um vídeo vertical narrado por IA, com gameplay ao fundo e legendas sincronizadas.**

O Rotevo recebe um texto e entrega um **mp4 em 1080x1920 (9:16)**, o formato de TikTok, Instagram Reels e YouTube Shorts. Tudo roda no seu computador, **sem chave de API e sem conta paga**.

Projeto acadêmico de Análise e Desenvolvimento de Sistemas (AEMS), desenvolvido por Bruno. A arquitetura foi inspirada no RedditVideoMakerBot, mas sem nada do Reddit: a entrada é o seu próprio texto.

---

## Sumário

- [Funcionalidades](#funcionalidades)
- [Como funciona](#como-funciona)
- [Estilos de legenda](#estilos-de-legenda)
- [Requisitos](#requisitos)
- [Instalação](#instalação)
- [Como usar](#como-usar)
- [Configuração](#configuração)
- [Fundos (gameplay)](#fundos-gameplay)
- [Estrutura do projeto](#estrutura-do-projeto)
- [Tecnologias](#tecnologias)
- [Segurança](#segurança)
- [Privacidade e direitos autorais](#privacidade-e-direitos-autorais)
- [Limitações](#limitações)
- [Solução de problemas](#solução-de-problemas)
- [Autor](#autor)

---

## Funcionalidades

- Interface web moderna, com marca Rotevo, tema claro e escuro automáticos e navegação completa por teclado.
- Narração por IA com vozes neurais em português (Edge TTS), com ajuste de velocidade e tom.
- Legendas sincronizadas palavra por palavra, queimadas no vídeo, com **6 estilos** à escolha.
- Vários vídeos de fundo (Minecraft, GTA e outros), baixados uma única vez e cortados no tamanho da narração.
- Música de fundo opcional.
- Contador de caracteres, blocos e duração estimada em tempo real.
- Barra de progresso, player e download direto na página, além do histórico dos últimos vídeos.
- Versão em linha de comando para gerar vídeos sem abrir o navegador.
- Atalho na área de trabalho que sobe o servidor sem janela de terminal.
- Reforço de segurança para uso local e janelas de Privacidade/LGPD, Termos, Cookies, Direitos autorais e Acessibilidade.

## Como funciona

1. **Limpeza e divisão** (`svm/textsplit.py`): remove links, markdown e anotações como `[pausa]` ou `(música sobe)` e divide o roteiro em blocos de cerca de uma frase.
2. **Narração** (`svm/tts.py`): cada bloco vira áudio no Edge TTS, em paralelo. O serviço devolve também o tempo de cada palavra (`WordBoundary`), que garante a sincronia das legendas.
3. **Faixa única** (`svm/pipeline.py`): os blocos viram wav, entram numa linha do tempo com uma pausa curta entre eles e são concatenados em `narration.wav`.
4. **Legendas** (`svm/captions.py`): gera um arquivo `.ass` no estilo escolhido, com os tempos do passo 2. Se o tempo das palavras não estiver disponível, distribui proporcionalmente ao tamanho de cada palavra.
5. **Fundo** (`svm/background.py`): baixa o gameplay do YouTube uma vez e sorteia um trecho do tamanho da narração. Se o vídeo for mais curto que o áudio, ele entra em loop.
6. **Render**: um único comando do FFmpeg corta para 9:16, queima as legendas, mixa a narração (e a música, se houver) e exporta o mp4.

Fluxo na interface web: a página envia os dados em JSON para `/api/generate`, o servidor cria uma tarefa em segundo plano e a página consulta `/api/status/<id>` a cada segundo para mostrar o progresso.

## Estilos de legenda

| Estilo | Descrição |
|---|---|
| **Clássico** | Branca, com contorno preto grosso e entrada suave |
| **Karaokê** | Mostra o bloco inteiro e destaca em amarelo a palavra que está sendo falada |
| **Pop** | Uma palavra por vez, grande e amarela, com efeito de crescimento |
| **Caixa** | Texto sobre uma faixa escura |
| **Neon** | Ciano com brilho e contorno magenta |
| **Minimalista** | Fonte menor e contorno fino |

Além do estilo, dá para ajustar o tamanho da legenda e ativar MAIÚSCULAS. Na linha de comando, use `--caption-style` com `classico`, `karaoke`, `pop`, `caixa`, `neon` ou `minimalista`.

## Requisitos

- Windows (os scripts de instalação e o atalho são `.bat` e `.ps1`).
- **Python 3.10 ou superior.**
- **FFmpeg e FFprobe** (`ffmpeg.exe` e `ffprobe.exe` na pasta `bin/` do projeto ou no PATH).
- Internet, para a narração e para baixar os fundos.
- Espaço em disco: cada gameplay de 80 min em 1080p passa de 3 GB.

## Instalação

```bash
git clone https://github.com/brunof3l/Rotevo.git
cd Rotevo
setup.bat
```

O `setup.bat` cria a pasta `venv` e instala as dependências do `requirements.txt` (Flask, edge-tts e yt-dlp).

Depois, coloque `ffmpeg.exe` e `ffprobe.exe` na pasta `bin/` (ou instale o FFmpeg no PATH).

> Dica: se o disco `C:` for apertado, deixe o projeto em outro disco. Os caminhos do `config.json` são relativos, então a pasta inteira pode ser movida sem quebrar nada. Depois de mover, rode `criar_atalho.ps1` de novo.

## Como usar

### Atalho da área de trabalho (recomendado)

Clique com o botão direito em `criar_atalho.ps1`, escolha **Executar com o PowerShell** e use o atalho **Rotevo** criado na área de trabalho. Ele sobe o servidor escondido e abre o site. Se o servidor já estiver ligado, só abre o site. Para encerrar, use o botão **Desligar servidor** no topo da página.

### Interface web pelo terminal

```bash
run.bat
```

Mesma coisa, mas com o terminal aberto mostrando os logs, útil para depurar. O site abre em `http://127.0.0.1:5000`.

Passo a passo na página:

1. Cole o roteiro (até 10.000 caracteres) e, se quiser, dê um título ao vídeo.
2. Escolha a voz, a velocidade e o tom.
3. Escolha o vídeo de fundo.
4. Escolha o estilo da legenda e o tamanho.
5. Clique em **Gerar vídeo**. Os arquivos ficam na pasta `outputs/`.

### Linha de comando

```bash
venv\Scripts\python.exe make_video.py roteiro.txt --title "Minha história"
```

Opções úteis:

```bash
venv\Scripts\python.exe make_video.py --list-voices
venv\Scripts\python.exe make_video.py --list-backgrounds
venv\Scripts\python.exe make_video.py roteiro.txt --voice pt-BR-FranciscaNeural --rate +12% --background minecraft-2 --caption-style karaoke
venv\Scripts\python.exe make_video.py roteiro.txt --no-captions
```

O arquivo `roteiro.txt` do repositório é um exemplo pronto para testar.

## Configuração

Tudo fica no `config.json`:

| Campo | O que faz |
|---|---|
| `tts.voice` / `rate` / `pitch` | Voz e entonação (ex.: `pt-BR-AntonioNeural`, `+8%`, `+0Hz`) |
| `tts.gap_seconds` | Pausa entre as frases da narração |
| `tts.concurrency` | Quantos blocos são sintetizados em paralelo (3 é seguro) |
| `video.width` / `height` / `fps` | Resolução e taxa de quadros (padrão 1080x1920 a 30 fps) |
| `video.encoder` | `libx264` (padrão) ou `h264_nvenc` para usar a GPU NVIDIA |
| `video.crf` | Qualidade: menor é melhor e mais pesado (18 a 28) |
| `captions.enabled` | Liga ou desliga as legendas |
| `captions.style` | Estilo da legenda (`classico`, `karaoke`, `pop`, `caixa`, `neon`, `minimalista`) |
| `captions.font_size` | Tamanho base da legenda |
| `captions.margin_v` | Altura da legenda na tela |
| `captions.uppercase` | Legendas em MAIÚSCULAS |
| `background.choice` | Chave do `backgrounds.json` ou `file:seu-video.mp4` |
| `background.music_file` | Música de fundo opcional (caminho relativo à pasta do projeto) |
| `background.music_volume` | Volume da música (ex.: `0.07`) |
| `keep_temp` | `true` mantém os arquivos intermediários para depurar |

Na página, marque **Salvar estas escolhas como padrão** para gravar voz, legenda e fundo no `config.json`.

## Fundos (gameplay)

O `backgrounds.json` lista os gameplays disponíveis. O download só acontece na primeira vez que cada um é usado, e são arquivos grandes.

Para baixar todos de uma vez, ou refazer algum que veio em baixa resolução:

```bash
venv\Scripts\python.exe baixar_fundos.py
```

Para usar um vídeo seu, coloque o `.mp4` na pasta de fundos. Ele aparece sozinho na lista da interface como "arquivo local".

## Estrutura do projeto

```
Rotevo/
├── app.py                 Servidor Flask (rotas, validação e segurança)
├── make_video.py          Versão em linha de comando
├── baixar_fundos.py       Baixa todos os fundos de uma vez
├── config.json            Configurações do usuário
├── backgrounds.json       Lista de gameplays (YouTube)
├── requirements.txt       Dependências Python
├── roteiro.txt            Roteiro de exemplo
├── setup.bat              Cria a venv e instala as dependências
├── run.bat                Sobe o servidor com o terminal aberto
├── criar_atalho.ps1       Cria o atalho na área de trabalho
├── templates/
│   └── index.html         Front-end (HTML, CSS e JavaScript)
└── svm/
    ├── textsplit.py       Limpeza e divisão do roteiro
    ├── tts.py             Narração (Edge TTS)
    ├── captions.py        Legendas ASS e estilos
    ├── background.py      Download e corte do fundo
    ├── ffmpeg_utils.py    Funções de apoio ao FFmpeg
    ├── pipeline.py        Orquestra todas as etapas
    └── settings.py        Carrega o config.json
```

Pastas criadas durante o uso (fora do Git): `venv/`, `bin/`, `backgrounds/video/`, `outputs/` e `temp/`.

## Tecnologias

**Back-end:** Python 3.10+, Flask, edge-tts, yt-dlp e FFmpeg/FFprobe.

**Front-end:** HTML5, CSS3 (variáveis, grid e flexbox) e JavaScript puro, sem frameworks e sem fontes externas. Template Jinja2 do Flask.

**Formatos e conceitos:** legendas ASS (renderizadas pela libass dentro do FFmpeg), WordBoundary do Edge TTS para sincronia, tarefas em segundo plano com `threading`.

## Segurança

O servidor escuta apenas em `127.0.0.1`. Medidas aplicadas:

- Validação do cabeçalho Host (contra DNS rebinding) e da Origin nos envios (contra CSRF).
- Requisições JSON obrigatórias, com corpo limitado a 64 KB.
- Validação de voz, fundo, estilo e limites numéricos; roteiro de no máximo 10.000 caracteres.
- Content Security Policy com nonce, além de `X-Frame-Options`, `X-Content-Type-Options`, `Referrer-Policy` e `Permissions-Policy`.
- Rota de vídeos restrita a nomes simples de arquivos `.mp4`.
- Erros sem exposição de caminhos do computador.
- Texto dinâmico inserido na página com `textContent`, nunca como HTML.

Onze ataques locais simulados (Host falso, CSRF, travessia de pastas, corpo gigante, voz e fundo maliciosos, entre outros) foram barrados. Foi uma verificação local, não uma auditoria profissional.

> O Rotevo foi pensado para uso local. Não o publique na internet sem antes adicionar login, HTTPS, limites de uso e armazenamento próprio. Ele também não é adequado para plataformas serverless como a Vercel, porque usa disco, FFmpeg e tarefas longas.

## Privacidade e direitos autorais

- Tudo roda no seu computador. Não há conta, cookie, rastreador nem análise de uso.
- Para gerar a voz, o texto de cada frase é enviado ao serviço Edge TTS da Microsoft. Não coloque dados pessoais ou sigilosos no roteiro.
- Os fundos são baixados do YouTube.
- **Gameplay e músicas de fundo são de terceiros.** Confira a licença e a política da plataforma antes de publicar. Os créditos aparecem na lista de fundos.
- A voz é sintética. Ao divulgar o vídeo, informe que a narração é feita por IA.

## Limitações

- Precisa de internet para a narração e para baixar os fundos.
- O YouTube pode responder **403** depois de vários gigabytes baixados em sequência. É temporário: o `baixar_fundos.py` espera e tenta de novo sozinho, retomando de onde parou.
- O `edge-tts` precisa estar atualizado, senão a Microsoft recusa as requisições.
- Um vídeo de cerca de 1 minuto renderiza em torno de 30 segundos em um computador comum. A narração depende da internet.
- Um vídeo é gerado por vez.

## Solução de problemas

**Erro 403 na narração:** atualize as bibliotecas.

```bash
venv\Scripts\python.exe -m pip install -U edge-tts yt-dlp
```

**Erro 403 ao baixar fundo:** aguarde e rode `baixar_fundos.py` novamente.

**O site não abre ou diz que o servidor não responde:** clique no atalho outra vez, ou use `run.bat` para ver os logs no terminal.

**Atalho sumiu depois de mover a pasta:** rode `criar_atalho.ps1` de novo.

**Legendas fora do lugar:** ajuste `captions.margin_v` e `captions.font_size` no `config.json`.

**Quer investigar um vídeo com problema:** coloque `"keep_temp": true` no `config.json` para manter os arquivos intermediários.

## Autor

Desenvolvido por **Bruno**, estudante de Análise e Desenvolvimento de Sistemas na AEMS.

Projeto acadêmico, sem fins comerciais.
