# Script Video Maker

Cole um roteiro, escolha a voz e receba um mp4 vertical (1080x1920) com **narração feita por IA**,
**gameplay de Minecraft no fundo** e **legendas sincronizadas** queimadas no vídeo.

Inspirado na arquitetura do RedditVideoMakerBot (pasta irmã), mas sem nada do Reddit:
a entrada é o seu texto.

---

## Instalação (uma vez)

1. Rode `setup.bat` (cria a `venv` e instala as dependências).
2. FFmpeg: o projeto usa automaticamente o `ffmpeg.exe` que já existe em `../RedditVideoMakerBot/`.
   Se você mover a pasta, instale o FFmpeg no PATH ou copie `ffmpeg.exe` e `ffprobe.exe` para `bin/`.

Não precisa de API key: a narração usa **Edge TTS** (vozes neurais da Microsoft, gratuitas).

## Uso

### Atalho da área de trabalho (recomendado)

Clique no atalho **Script Video Maker** na área de trabalho: ele sobe o servidor escondido
(sem janela preta) e abre o site no navegador. Se o servidor já estiver de pé, só abre o site.
Para encerrar, use o botão **Desligar servidor** no topo da página.
Se o atalho sumir, recrie com `criar_atalho.ps1` (botão direito &rarr; Executar com o PowerShell).

### Interface web pelo terminal

```bash
run.bat
```

Mesma coisa, mas com o terminal aberto mostrando os logs — útil para depurar.
Abre em `http://127.0.0.1:5000`. Cole o roteiro, ajuste voz/velocidade/legenda e clique em **Gerar vídeo**.
A barra de progresso mostra cada etapa e no final o vídeo toca ali mesmo, com link de download.
Os arquivos ficam em `outputs/`.

### Linha de comando

```bash
venv\Scripts\python.exe make_video.py roteiro.txt --title "Minha historia"
```

Opções úteis:

```bash
venv\Scripts\python.exe make_video.py --list-voices
venv\Scripts\python.exe make_video.py --list-backgrounds
venv\Scripts\python.exe make_video.py roteiro.txt --voice pt-BR-FranciscaNeural --rate +12% --background minecraft-2 --no-captions
```

## Como funciona

1. **Limpeza e divisão** (`svm/textsplit.py`) — remove links, markdown e anotações tipo `[pausa]`
   ou `(música sobe)`, e quebra o roteiro em blocos de ~1 frase.
2. **Narração** (`svm/tts.py`) — cada bloco vira um mp3 no Edge TTS, em paralelo. O Edge devolve
   também o tempo de cada palavra (`WordBoundary`), que é o que dá a sincronia exata das legendas.
3. **Faixa única** (`svm/pipeline.py`) — os blocos viram wav, entram numa linha do tempo com uma
   pausa curta entre eles e são concatenados em `narration.wav`.
4. **Legendas** (`svm/captions.py`) — gera um `.ass` (estilo TikTok: fonte pesada, contorno grosso)
   com os tempos vindos do passo 2.
5. **Fundo** (`svm/background.py`) — baixa o gameplay do YouTube **uma vez** e sorteia um trecho do
   tamanho da narração. Se o vídeo for mais curto que o áudio, ele entra em loop.
6. **Render** — um único comando ffmpeg: corta para 9:16, queima as legendas, mixa a narração
   (e a música de fundo, se houver) e exporta o mp4.

## Configuração (`config.json`)

| Campo | O que faz |
|---|---|
| `tts.voice` / `rate` / `pitch` | voz e entonação (ex.: `pt-BR-AntonioNeural`, `+8%`, `+0Hz`) |
| `tts.gap_seconds` | pausa entre as frases da narração |
| `tts.concurrency` | quantos blocos sintetiza em paralelo (3 é seguro) |
| `video.encoder` | `libx264` (padrão) ou `h264_nvenc` para usar a GPU NVIDIA |
| `video.crf` | qualidade: menor = melhor e mais pesado (18–28) |
| `captions.*` | fonte, tamanho, contorno, altura na tela (`margin_v`), MAIÚSCULAS |
| `background.choice` | chave do `backgrounds.json` ou `file:seu-video.mp4` |
| `background.music_file` | música de fundo opcional (caminho relativo à pasta do projeto) |
| `keep_temp` | `true` mantém os arquivos intermediários em `assets/temp/` para depurar |

## Fundos

`backgrounds.json` lista os gameplays (Minecraft parkour, GTA, etc.). O download só acontece na
primeira vez que você usa cada um — são arquivos grandes (vídeos de horas em 1080p).

Para baixar todos de uma vez (ou consertar algum que veio em baixa resolução):

```bash
venv\Scripts\python.exe baixar_fundos.py
```

Para usar um vídeo seu, jogue o `.mp4` na pasta de fundos: ele aparece sozinho na lista da
interface como `arquivo local`.

## Onde os arquivos ficam

O projeto inteiro mora em `E:\ScriptVideoMaker` — o disco `C:` desta máquina vive quase cheio e
um único gameplay de 80 min em 1080p já passa de 3 GB.

```
E:\ScriptVideoMaker\
  app.py, svm\, templates\   código
  venv\                      ambiente Python
  bin\                       ffmpeg.exe e ffprobe.exe (não depende de nada no C:)
  backgrounds\video\         gameplays baixados
  outputs\                   vídeos gerados
  temp\                      intermediários (apagados ao final de cada vídeo)
```

Os caminhos no `config.json` são relativos, então a pasta toda pode ser movida para outro disco
sem quebrar nada — só rode `criar_atalho.ps1` depois, para o atalho apontar para o lugar novo.

## Notas

- Vídeo de ~1 min renderiza em torno de 30 s numa máquina comum; a narração depende da internet.
- `edge-tts` precisa estar atualizado — versões antigas tomam **403** do servidor da Microsoft
  (`pip install -U edge-tts` resolve).
- O YouTube responde **403** depois de vários GB baixados seguidos. É temporário: o
  `baixar_fundos.py` espera e tenta de novo sozinho, retomando de onde parou.
- Direitos: gameplay e música de fundo são de terceiros; confira a licença antes de publicar.
