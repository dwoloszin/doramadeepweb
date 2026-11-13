# Dorama da Deep Web — vídeo-novela em Shorts

Cada cena escrita em `scenes/` vira um **episódio** com três produtos:

| Produto | Arquivo | Para quê |
|---|---|---|
| Vídeo vertical (≤ 3 min) | `output/epXX/epXX.mp4` | YouTube Shorts + Instagram Reels |
| Audiobook | `output/epXX/epXX_audiobook.mp3` | a história inteira só em áudio |
| Carrossel do capítulo | `output/epXX/carousel/*.jpg` + `caption.txt` | o capítulo para ler (Instagram 4:5) |
| Legenda | `output/epXX/epXX.srt` | closed caption do YouTube |

Nada é publicado sem aprovação (ver "Publicação").

## Como uma cena vira episódio

1. Você coloca o texto em `scenes/sceneN.txt`.
2. Ele é adaptado para `story/epNN.yaml` (a partir de `story/_TEMPLATE_ep.yaml`,
   respeitando o cânone de `story/ENREDO.md`): o roteiro com as cenas, as falas
   (narrador / pensamento / personagem), o enquadramento, a câmera, a trilha,
   os efeitos e o texto do carrossel.
3. `python main.py all epNN` → imagens, narração, vídeo, carrossel.
4. Você assiste, pede ajustes, e no fim roda `python main.py approve epNN`.

## Regras de roteiro (valem para TODO episódio)

0. **Abertura sempre mágica (pedido do autor, 12/11).** Todo episódio começa
   com uma história "além do real", em estilo dorama: algo **lindo e mágico**
   (luz dourada, partículas brilhando, estrelas, câmera lenta, piano ou harpa).
   O cold open e a primeira cena são o sonho. A realidade só entra depois,
   com o `card: shock`.
1. **Pergunta final (enquete nos comentários).** Todo vídeo termina com a voz
   perguntando ao público sobre a decisão, o dilema ou o conflito do episódio.
   Exemplos: "Teria entregado as cartas… ou faria igual a mim?", "Você acha que
   eu fiz certo?", "Quem está certo nessa briga?".
   - No vídeo, a última cena é `card: question` com a fala da pergunta
     (`lines`) e os textos em `cards.question`. A legenda queimada some nas
     cartelas, porque a pergunta já está escrita na tela.
   - No carrossel, o último slide é `type: question`.
   - Em `publish.description` e `publish.instagram_caption`, a mesma pergunta
     com "conta nos comentários".
2. **Som de cena sempre (imersão).** Nenhuma cena fica muda por baixo da voz:
   - **ambiente** do lugar (`ambience:` em `bible.yaml` → `locations`), como
     vento ao ar livre, rua com motos, sala barulhenta, quarto à noite com grilos.
     A cena pode trocar com `ambience: "..."` (mudou a hora ou o clima) ou
     desligar com `ambience: none`.
   - **efeitos pontuais** (`sfx:` com `gen:`): passos, giz, gaveta, cama
     rangendo, moto, cachorro, porta…
   - **instrumentos e música como efeito**: harpa, piano, violoncelo, corda
     subindo, impacto de suspense, nos momentos de emoção.
   - Sincronia: `word: "piano"` entra quando a voz diz a palavra;
     `line: 0` no começo da fala; `after_line: 0` depois dela; `at: 1.5`
     soma segundos. `dur` é a duração e `db` ajusta o volume.
   - Os sons são gerados pelo ElevenLabs Sound Effects e guardados em
     `assets/sfx/gen/`, reaproveitados entre episódios (o mesmo lugar soa sempre igual).
3. **Transição não é fala.** A virada (sonho → realidade, salto no tempo) é
   imagem e som (flash, glitch, troca de trilha). A narração conta o
   *sentimento* da virada, para quem só ouve entender
   ("Mas aí… o sonho se quebrava em mil pedaços."). Nada de "Corta.".
   - **Choque de realidade (sonho → real) = `card: shock`**, uma cena própria
     de ~1,5 s entre a última cena do sonho e a primeira da realidade. O sonho
     congela e perde a cor, o vidro racha, a imagem estilhaça, entra um chiado
     de TV e a realidade bate na tela, estourada e tremendo. Os sons ficam em
     `sfx` (arranhão de disco, vidro, estática, impacto grave), com
     `music: none`, e a cena seguinte entra com `transition: cut`.
     A virada precisa ser inconfundível para quem assiste.
4. **Voz dirigida.** Cada fala leva marcação de atuação (`[whispers]`,
   `[excited]`, `[sighs]`…). Comece com `[Brazilian accent]` as falas que
   puxarem sotaque. Evite falas muito curtas, porque o v3 se perde nelas.
4b. **Pensamento com energia (aprovado pelo ouvido, 12/11).** É a mesma voz
   do narrador (Liam), no modo **criativo** (`stability: 0.0`), com efeito
   leve (`thought_light`). O texto conta mais do que o efeito:
   - frase **completa e com energia**, de preferência falando com ele mesmo:
     *"Fala alguma coisa, Davi… qualquer coisa!"*;
   - uma emoção forte por trecho (`[panicking]`, `[excited]`, `[urgently]`,
     `[determined]`, `[pleading]`, `[sad]`) e pontuação viva (…!, ?!);
   - **evitar** falas curtinhas ("Olhos verdes. De novo.") e as marcações
     `[whispers]`, `[gasps]` e `[nervous laugh]`, que soam robotizadas ou
     puxam sotaque.
4c. **Pensamento mais grave a partir do Ep. 7 (pedido do autor, 12/11).** O
   pensamento soava "afeminado". Davi vai crescer e precisa soar mais
   imponente. Mesma voz (Liam), com ajuste de entonação e grave leve:
   `stability: 0.5`, `tempo: 1.0`, `fx: thought_mid` (~meio semitom abaixo,
   grave sutil; o `thought_deep` de 1 semitom ficou "grosso demais"). Fica no `voices:` do próprio `epNN.yaml`, e os
   episódios 2 a 6 continuam como foram aprovados. Marcações: `[deep voice]`
   mais uma emoção firme (`[confident]`, `[determined]`, `[calmly]`,
   `[amused]`, `[proudly]`). Evite `[panicking]`, `[pleading]`, `[desperate]`
   e `[breathless]`, que afinam a voz. O Davi falando em voz alta usa
   `voices.davi` (Liam, `fx: mid_dry`). Amostras para escolher:
   `output/amostras_voz/escolha_pensamento_masculino/`.
   - **Voz por episódio:** `voices:` no `epNN.yaml` sobrescreve só os campos
     informados do `config.yaml`.
5. **Personagem em cena fala.** Personagem novo (ou que ainda não falou) ganha
   falas próprias e uma voz própria em `config.yaml → voices`. Diálogo deixa a
   história mais viva do que só a narração.
   - **Escolha da voz:** gere a mesma fala, com `[Brazilian accent]`, em 3 a 5
     vozes do ElevenLabs. Mande cada amostra ao Gemini para ele ouvir e dar
     nota de 0 a 10 ao sotaque paulista nativo, e só use as vozes com nota 9 ou
     10. As amostras ficam em `output/amostras_voz/`.
   - Em uso: **pai = Bill**, **porteiro = Will**, **mãe = Sarah**,
     **Camila = Jessica**, **primos (Mateus) = Harry**. Vozes femininas
     aprovadas pelo ouvido do autor: Jessica, River, Sarah (e Aoede, Leda,
     Sulafat do Gemini TTS). Reprovadas: Alice, Bella, Laura, Matilda.
     Reprovadas: Eric (5) e Roger (4), por sotaque americano. A voz Andrea Lot
     (brasileira) foi desativada pela dona.
6. **Mais de 3 min?** Divida o episódio em partes, cortando num gancho.

## Continuidade dos personagens (`story/bible.yaml`)

- **identity**: o que nunca muda (rosto, corpo, cabelo, óculos…).
- **wardrobe**: roupas com nome. No episódio, `days:` diz que roupa cada
  personagem usa em cada dia. **Mesmo dia = mesma roupa em todas as cenas.**
  Dia novo = roupa nova (crie a entrada na bíblia).
- Cada roupa tem uma **folha de referência** em `assets/characters/<id>/`,
  enviada junto em toda imagem de cena. Os lugares têm foto de referência em
  `assets/locations/`.
- **Foto-modelo (opcional):** coloque 1 a 3 fotos em
  `assets/characters/<id>/modelo/` (ex.: `assets/characters/davi/modelo/`).
  O retrato-base nasce delas e todo o resto (roupas, cenas) herda o rosto.
  Depois: `python main.py refs davi --force` (+ `davi_sonho`) e `frames epNN --force`.
- **Regra de referência (sempre):** surgiu um personagem novo, um ambiente
  específico (a casa, o entreposto…) ou um objeto que pode voltar (bicicleta,
  Kombi, mochila…)? Ele ganha uma referência salva na **hora em que aparece**:
  - personagem → `characters` (rosto + folha de cada roupa);
  - lugar → `locations` (foto do lugar + som ambiente);
  - objeto → `props` (folha com 3 vistas em `assets/props/<id>.png`). Na cena,
    use `props: [bicicleta]`.
  - Se ele já apareceu num episódio, `from_frames: [output/epNN/frames/sXX.png]`
    faz a referência nascer daquela imagem, para continuar **igual ao que o
    público viu**.
- **Regra de elenco (automática):**
  - **Figurantes são sempre outras pessoas.** Toda cena com personagem leva no
    pedido a ordem de que qualquer outra pessoa (passante, segurança,
    funcionário) tenha rosto, idade, cabelo, pele e corpo **diferentes** dos
    personagens. Assim ninguém vira clone do Davi.
  - **Personagem recorrente é sempre a mesma pessoa.** Cada um tem `aliases`
    na bíblia (porteiro → `porter`, pai → `father`). Se o `visual` citar o
    alias sem o personagem no `cast`, o `frames` **para com erro**. Se o
    porteiro aparece, ele está no `cast` e usa a referência dele.
  - **Quem fala está em cena.** Fala de um personagem fora do `cast` gera um
    aviso. Para voz fora do quadro de propósito, use `offscreen: [pai]`.
  - Figurante descrito no `visual` deve ser bem diferente do protagonista,
    por exemplo "an older Black man with short grey hair".
- Referências ficam **travadas** depois de geradas. Para refazer uma:
  apague o `.png` e rode `python main.py refs`, ou use `python main.py refs <id> --force`.

## Vozes (config.yaml → voices)

| Quem | Voz | Estilo na legenda |
|---|---|---|
| narrador | Davi adulto (pt-BR Antonio) | Poppins branca, palavra falada em dourado |
| pensamento | voz interna, com eco | Lora itálico lilás, entre aspas |
| clara | Teacher Clara (inglês, en-US Ava) | Cormorant itálico + tradução embaixo |

## Comandos

```
python main.py refs                      # referências (1x)
python main.py frames ep01               # imagens das cenas (só o que mudou)
python main.py frames ep01 s13 --force   # refaz uma cena (lote batch)
python main.py frames ep01 s13 --force --now  # refaz NA HORA (preço cheio)
python main.py video ep01                # vídeo + audiobook + srt
python main.py carousel ep01             # carrossel
python main.py all ep01
python main.py approve ep01
python main.py publish ep01 --youtube --instagram        # dry run
python main.py publish ep01 --youtube --instagram --yes  # publica
```

## Publicação (travada até a aprovação)

Para publicar, três condições precisam valer ao mesmo tempo:
1. `youtube.enabled` / `instagram.enabled` = `true` no `config.yaml`;
2. o episódio aprovado (`approve`);
3. a flag `--yes`.

Contas da série: YouTube **doramadadeepweb@gmail.com** e Instagram **@doramadadeepweb**.

- **YouTube**: o `client_secret.json` é o mesmo app OAuth do Bem na Mosca. Quem
  decide o canal é o login: `python main.py check` abre o navegador. Entre com
  doramadadeepweb@gmail.com e grave o `channel_id` mostrado em `config.yaml`.
  O token fica em `token.json`.
- **Instagram**: app **próprio** da Meta ("Dorama da Deep Web", separado do Bem na Mosca). O
  `INSTAGRAM_ACCESS_TOKEN` é **do @doramadadeepweb** e se renova sozinho a cada
  30 dias (`output/instagram_token.json`). O `DB_ARCHIVE_GITHUB_TOKEN` hospeda o
  arquivo num repositório público temporário enquanto o Instagram o baixa.
- **Trava de conta**: o `publish` confere o canal (`youtube.channel_id`) e o
  perfil (`instagram.username`) e se recusa a publicar em outra conta.

## Divulgação: alerta de spoiler (ideia do autor, 13/11)

Os episódios ficam prontos antes e saem **1x por semana**. Entre um episódio e outro
(no meio da semana), solte um **teaser** do PRÓXIMO episódio, sem contar a história:

- **Imagem**: um close do rosto do Davi numa reação engraçada ou intrigante, recortado
  de um frame do próximo episódio (ex.: `output/ep08/frames/s18.png`, o Davi sorrindo
  feito bobo no travesseiro). Escolher reações divertidas, nunca a cena que entrega a virada.
- **Legenda curta e curiosa**: "🚨 ALERTA DE SPOILER 🚨 O que será que aconteceu pra
  deixar o Davi ASSIM? 👀 Não perca o próximo episódio!" + dia/horário da estreia.
- **Onde**: Story/post no Instagram, post da comunidade no YouTube e TikTok.
- Sem detalhes do enredo: o rosto faz a pergunta e o episódio responde.

**Como fazer** (`python main.py teaser epNN`): o autor assiste e diz o momento ("o s18 com
'o que aconteceu pra deixar o Davi assim?'" ou "uma imagem nova: Davi e Camila frente a frente").
Claude escreve o bloco `teaser:` no `story/epNN.yaml` (formato em `src/teaser.py`), completando a
legenda para ter impacto:
- `from: s18` usa um frame do vídeo (`zoom` = close, `focus` = onde está o rosto); ou
- `shot: {day, location, cast, visual...}` gera uma imagem NOVA com as referências da série.
- `style: poster` = **cartaz do próximo episódio** (o "tema"): selo "PRÓXIMO EPISÓDIO", número e
  título, SEM história. Usa a imagem da capa em outro recorte e um layout diferente da capa do
  carrossel (sem gancho, sem "deslize para ler"), para não confundir o leitor.

Saída em `output/epNN/teaser/`: `<id>_story.png` (9:16, Story/TikTok), `<id>_feed.png` (4:5, feed e
comunidade do YouTube) e `teaser.txt` (legendas). `teaser epNN t2 --force` refaz um só.

## Estrutura

```
scenes/            textos originais (você escreve)
story/ENREDO.md    escopo da história: premissa, cânone, episódios, fios soltos
story/_TEMPLATE_ep.yaml  molde de episódio (campos + checklist do roteirista)
story/bible.yaml   personagens, roupas, lugares (com som ambiente), estilo visual
story/epNN.yaml    roteiro adaptado de cada episódio
assets/            fontes, trilhas, efeitos, referências de personagem/lugar
src/               gemini_image, story, tts, subs, cards, render, carousel, publish
output/epNN/       frames/, _work/ (cache), vídeo, mp3, srt, carousel/, status.json
```

## Custo e modo Batch (imagens)

As cenas são geradas no **modo Batch do Gemini**, que custa metade do preço
(~US$ 0,05 por imagem 2K). Todas as cenas pendentes vão num único lote, e
as referências sobem uma vez para o Files API. O Google promete entregar em até
24 h, mas costuma levar uns 2 minutos. O comando espera até
`images.batch_wait_minutes` (30). Se o lote não terminar, **rode o mesmo comando
de novo**, porque ele retoma pelo `output/epNN/_work/batch.json`. Use `--now`
para gerar na hora, pagando o preço cheio. Referências de personagem e lugar são
geradas na hora, porque uma depende da outra (rosto → roupa).

Estimativa por episódio: ~R$ 7 a 9 em imagens. Voz e efeitos usam o pool
gratuito do ElevenLabs (ver `python main.py voices`).

## Automação futura (GitHub Actions, repositório público)

**Ainda não ativada.** Hoje tudo roda local, porque faltam as chaves dos canais.
O plano:

1. Um workflow agendado (cron) detecta um `scenes/sceneN.txt` novo sem `story/epNN.yaml`.
2. A adaptação para `epNN.yaml` usa a API do Claude (`ANTHROPIC_API_KEY`), seguindo
   `story/_TEMPLATE_ep.yaml` e `story/ENREDO.md`.
3. Roda `refs` → `frames` (batch; o cron seguinte retoma se o lote não terminou)
   → `video` → `carousel`.
4. O resultado sobe como *artifact* para revisão, e **só publica depois da aprovação**
   (`approve`, ou um `workflow_dispatch` manual), mantendo a trava de 3 condições.

Cuidados por ser público: chaves só em **GitHub Secrets** (`GEMINI_API_KEY_IMG`,
`ELEVENLABS_API_KEYS`, `ANTHROPIC_API_KEY`, `INSTAGRAM_ACCESS_TOKEN`,
`DB_ARCHIVE_GITHUB_TOKEN`, e o OAuth do YouTube serializado num secret).
`.env`, `token.json` e `client_secret.json` nunca vão para o git. Os caches
(`assets/characters`, `assets/locations`, `assets/sfx/gen`) devem ser
versionados, senão cada execução paga de novo. As fotos-modelo em
`assets/characters/*/modelo/` ficariam **públicas** no repositório.
