# Visualitzacions

L'aplicació ofereix 4 modes de visualització, seleccionables des de la barra superior del panell dret.

## Colors per gènere

Cada gènere té un color fix consistent a totes les visualitzacions:

| Gènere | Color | Hex |
|---|---|---|
| Pop | Vermell coral | `#FF6B6B` |
| Rock | Verd turquesa | `#00BFA5` |
| Folk | Blau clar | `#4FC3F7` |
| Electrònica | Violeta | `#AB47BC` |
| Hip-hop | Taronja | `#FFB74D` |
| Rumba | Salmó | `#FF8A65` |

Definits a `src/components/visualizations/genreColors.js`.

## Mode 1: Dispersió 2D

**Tecnologia:** deck.gl `ScatterplotLayer` + `OrthographicView`

- Cada cançó és un punt al pla 2D
- Posicions: coordenades t-SNE 2D del backend
- Top 10 cançons: punts grans (5px), opacitat alta
- Resta: punts petits (2.5px), opacitat baixa
- Hover: punt creix (8px), vora blanca, tooltip amb títol + artista
- Click: obre popup de detalls
- Controles: zoom (scroll), pan (arrossegar)

## Mode 2: Dispersió 3D

**Tecnologia:** deck.gl `ScatterplotLayer` + `OrbitView`

- Igual que 2D però amb 3 eixos (coordenades t-SNE 3D)
- Controles: rotació orbital (arrossegar), zoom (scroll)

## Mode 3: Navegació 2D (Edificis)

**Tecnologia:** deck.gl `ColumnLayer` + `OrthographicView`

- Cada cançó és una columna/edifici que s'alça del pla
- **Alçada = puntuació de similaritat** (score × 40)
  - Sense cerca: totes les columnes tenen la mateixa alçada (score=0.5)
  - Amb cerca: les columnes més altes són les més rellevants
- Color: segons gènere
- Top 10: columnes amb opacitat completa
- Hover: la columna creix un 30%, tooltip amb títol + artista + percentatge
- Click: obre popup
- Llegenda inclou "Alçada = similaritat"

## Mode 4: Navegació 3D (Sistema Solar)

**Tecnologia:** @react-three/fiber + @react-three/drei

- L'espai és un "sistema solar" amb estrelles de fons (`Stars`)
- Cada cançó és una esfera/planeta:
  - **Mida = score** (base × (0.5 + score × 0.8))
  - Top 10: esferes grans amb emissió lumínica forta (glowing)
  - Resta: esferes petites, menys brillants
  - Color: segons gènere
- Il·luminació: ambient + 2 llums puntuals (blanca + violeta)
- Top 10 cançons roten lentament
- Hover: l'esfera creix, apareix etiqueta flotant (Html de drei)
- Click: obre popup
- Controles: OrbitControls per navegar lliurement per l'espai

## Comportament amb filtratge

- Quan es fa una cerca, les projeccions es recalculen (t-SNE nou al backend)
- La visualització mostra TOTES les cançons supervivents
- Top 10 es destaquen, la resta es difuminen
- Quan queden ≤ 5 cançons: `faded=true`, la visualització es torna semi-transparent i apareix un overlay amb el missatge "Explora les N cançons per tu"

## Interacció bidireccional

- Hover sobre una cançó a la llista → es ressalta el punt/esfera corresponent a la visualització
- Hover sobre un punt/esfera a la visualització → es ressalta la cançó corresponent a la llista
- Això es gestiona via l'estat `highlightedId` a App.jsx, compartit entre TopResults i la visualització activa
