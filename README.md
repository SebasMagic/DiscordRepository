# Discord Liquid Text Generator

Este repositorio incluye un generador de imágenes de texto con efecto líquido
pensado para banners o stickers de Discord. El generador está impulsado por un
script en Python que consume un archivo de configuración JSON con todos los
parámetros visuales (tipografía, colores, goteos, brillos y patrones) y genera
imágenes PNG con fondo transparente listas para Canva u otras plataformas.

## Requisitos

- Python 3.9 o superior
- [Pillow](https://python-pillow.org/) (`pip install pillow`)

## Uso

```bash
python src/image_generator.py --output output
```

El comando anterior renderiza todos los *presets* definidos en el archivo
`src/liquid_config.json` dentro de la carpeta `output/`. Si quieres renderizar
únicamente un *preset*, pasa el nombre como argumento:

```bash
python src/image_generator.py LIQUID_GOLD --output output
```

## Características destacadas

- Canvas 2048×2048 px a 300 dpi y fondo transparente.
- Tipografía de estilo caligráfico líquido, con familias preferidas y *fallbacks*.
- Efecto de goteo configurable (densidad, longitud y ancho de los goteos).
- Brillo especular, sombra interna y resplandor externo por palabra.
- Paletas de colores predefinidas (oro, naranja, azul, vino, blanco, negro y
  un tono "plano blanco" sin brillo) además de patrones tipo camuflaje.
- Presets listos para usar, incluyendo una variante "Plano Blanco" sin glow
  para cumplir con la solicitud de un acabado plano y blanco.

## Notas

- El script intenta cargar las fuentes especificadas. Si no están disponibles,
  usará `DejaVuSans.ttf` como alternativa.
- El efecto líquido es una aproximación simplificada pensada para prototipos.
