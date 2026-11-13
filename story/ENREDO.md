# Dorama da Deep Web — escopo do enredo

> Documento vivo. Atualize ao fechar cada episódio: o que virou **cânone**
> (não pode mais mudar) e quais **fios** ficaram soltos.
> Título da série é provisório.

## Premissa

Davi, adulto, conta a própria história. Ele cresceu num bairro periférico,
era gordinho, tímido e estudioso, e escrevia cartas de amor que nunca
entregou para a professora de inglês, a Teacher Clara. Na cabeça dele, a vida
era um dorama coreano. A realidade era outra. Uma madrugada (1h da manhã) muda
tudo, e é aí que começa a "deep web" do título.

**Tom:** novela romântica com suspense. Primeira paixão, vergonha do próprio
corpo, vontade de sair daquela realidade. Cada episódio alterna o **sonho**
(dorama, dourado, piano) e o **real** (periferia, barulho, cor fria) e termina
num **gancho**.

**Voz narrativa:** primeira pessoa, Davi adulto lembrando, com ironia
carinhosa sobre si mesmo. O pensamento do Davi adolescente aparece
como "voz de dentro da cabeça".

## Personagens

| id (bible.yaml) | Quem | Visual / voz | Arco até agora |
|---|---|---|---|
| `davi` | Davi, 17 anos, protagonista | foto-modelo (fase 17 anos): gordinho, pele clara, cabelo curto espetado, sem óculos · voz Liam | tímido, romântico, quer sair da periferia; 47 cartas nunca entregues |
| `davi_sonho` | Davi como ele se imagina | mesmo rosto, magro, galã de dorama, blazer | só existe no sonho |
| `davi_adulto` | Davi de 20 a 42 anos (fase galã) | foto-modelo em `assets/characters/davi_adulto/modelo/` · ainda **não** está na bíblia | é o narrador; ainda não apareceu em cena |
| `clara` | Teacher Clara, 28, professora de inglês | pele alva, cabelo preto liso, **olhos verdes**, lábios carnudos · fala em inglês (voz Lily) | a paixão platônica; não sabe de nada |
| `pai` | Pai do Davi, 48, entregador de hortifrúti | bigode grisalho; trabalho: camisa xadrez, botas, boné · casa: regata branca, bermuda, chinelo · voz **Bill** (estreia no Ep. 3) | trabalha com o Davi de madrugada; cuida dele ("Leva água, filho") |
| `porteiro` | Porteiro de fábrica, ~50 | careca, barba grisalha, palito na boca, uniforme azul-marinho · voz **Will** | "Deixa aí em cima, garoto. Se tiver vaga, eles ligam." (Ep. 3) |
| `mae` | Mãe do Davi, 44 | coque bagunçado, avental, pano de prato no ombro · voz **Alice** | enérgica, manda na casa (estreia no Ep. 4) |
| `camila` | Camila, 17, prima do interior | loira, cabelo longo, **olhos verdes**, jaqueta jeans · voz **Matilda** | o coração do Davi dispara (Ep. 4); **o romance só é contado do Ep. 5 em diante** |
| `primos` | Mateus 14, Ricardo 12, Joana 7, Patrícia 4 | sempre os 4 juntos (folha de grupo) · Mateus fala pelo grupo (voz **Harry**) | chegam com a Camila (Ep. 4) |

## Referências salvas (continuidade visual)

| Tipo | id | Arquivo | Nasceu de |
|---|---|---|---|
| lugar | `quarto_davi` | assets/locations/quarto_davi.png | Ep. 1 |
| lugar | `casa_davi` (fachada) | assets/locations/casa_davi.png | Ep. 2 s18/s16 |
| lugar | `entreposto`, `rua_kombi`, `centro_sp`, `rua_sonho_madrugada` | assets/locations/ | Ep. 2 |
| objeto | `bicicleta` | assets/props/bicicleta.png | Ep. 2 s19 |
| objeto | `kombi` | assets/props/kombi.png | Ep. 2 s16/s13/s10 |
| objeto | `mochila` | assets/props/mochila.png | Ep. 2 s18 |
| objeto | `bicicleta_sonho` (creme, vintage) | assets/props/bicicleta_sonho.png | Ep. 3 (sonho) |
| lugar | `sala_casa` (sala com telefone fixo bege) | assets/locations/sala_casa.png | Ep. 3 |
| lugar | `zona_industrial`, `portaria_fabrica`, `avenida_sonho` | assets/locations/ | Ep. 3 |
| lugar | `cozinha_casa`, `mercadinho` | assets/locations/ | Ep. 4 |

Regra: personagem, lugar ou objeto novo que possa voltar → referência salva na `bible.yaml`
quando aparecer (ver README > Continuidade).

## Cânone (não contradizer)

- Nome do protagonista: **Davi**. A professora chama-o de "Davi" (no texto
  original estava "narrative").
- **47 cartas** de amor, todas para a Clara, nenhuma entregue, guardadas na
  gaveta do quarto e no fundo do caderno. (O número foi inventado na adaptação
  e agora é cânone.)
- Cidade: **periferia de São Paulo** (dito na descrição do canal).
- Escola pública na periferia; uniforme = camiseta branca com brasão azul e
  calça de moletom azul-marinho com listra branca; relógio digital preto no
  pulso esquerdo.
- Clara no dia 1: blusa de seda marfim, saia lápis preta, colar dourado,
  salto preto.
- O quarto do Davi: tijolo aparente, cama de solteiro, gaveta de madeira,
  despertador digital barato.
- Fim do Ep. 1: ele dorme de uniforme; **1h da manhã o alarme toca**.
- Ep. 2: o alarme de 1h toca **1 a 2 vezes por semana**. Davi, no fim do ensino médio e sem
  emprego, ajuda o **pai, entregador de hortifrúti**: Kombi velha branca e enferrujada →
  entreposto no centro de SP (carrinho de madeira alugado, ~2h nos galpões) → separação na
  calçada (tomate por maturação, batata grande p/ fritas, pequena p/ outro grupo) → ~7h devolve
  o carrinho → entregas em bares e restaurantes do centro → volta ~meio-dia.
- Pai: 48 anos, mesmos olhos/sobrancelhas do Davi, bigode grisalho, camisa xadrez, botas de
  borracha, boné azul. Ainda não falou em cena.
- Roupa de trabalho do Davi: moletom cinza com zíper, camiseta branca, jeans sujo, tênis velho, relógio.
- Nos dias de folga: mochila, bicicleta e **20 folhas impressas** (currículos — ainda não dito em cena).

## Episódios

| Ep | Título | Fonte | Resumo | Gancho | Pergunta ao público |
|---|---|---|---|---|---|
| 1 | O Garoto do Fundo da Sala e os Olhos Verdes | scenes/scene1.txt | O sonho de dorama na aula de inglês × a realidade da periferia. Davi revela que era ele o garoto, e que nunca entregou as 47 cartas. | 1h da manhã, o alarme toca. "O que me esperava do outro lado daquela madrugada gelada?" | Teria entregado as cartas… ou faria igual a ele? |
| 2 | O Perfume das Frutas e a Madrugada Gelada | scenes/scene2.txt | A madrugada de dorama (névoa, Kombi de colecionador) × choque de realidade: 1h da manhã, entreposto, carrinho rangendo, entregas até o meio-dia com o pai. "É assim que a minha vida vai ser pra sempre?" | Vinte folhas de papel, uma bicicleta, quilômetros de estrada. "Até onde um sonho pode te levar quando você não tem nada a perder?" | Encararia essa madrugada com o seu pai… ou adolescente devia só estudar? |

## Fios soltos (resolver nos próximos)

- ~~Por que o alarme tocou à 1h?~~ Resolvido no Ep. 2 (trabalho com o pai).
- Ep. 3: a maratona de bicicleta com as 20 folhas (currículos) sob o sol. Até onde ele chega?
- O pai ainda não tem voz. **No Ep. 3 ele estreia com falas próprias** (o Ep. 2 fica como
  está, por decisão do autor): escolher e testar uma voz masculina mais velha e grave, sem
  sotaque estrangeiro, e criar `voices.pai` no `config.yaml`.
- A "deep web" do título ainda não apareceu.
- A Clara vai descobrir as cartas?
- Quando e como entra o Davi adulto (fase galã) em cena?

## Como escrever o próximo episódio

1. Coloque o texto em `scenes/sceneN.txt`.
2. Copie `story/_TEMPLATE_ep.yaml` para `story/epNN.yaml` e adapte seguindo
   as regras do README ("Regras de roteiro").
3. Personagem, roupa ou lugar novo vão na `bible.yaml` **antes**; depois rode
   `python main.py refs`.
4. `python main.py all epNN`, assista e ajuste.
5. Ao aprovar, **atualize este arquivo**: cânone, linha da tabela, fios soltos.
