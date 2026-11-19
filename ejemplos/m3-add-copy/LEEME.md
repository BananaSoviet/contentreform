# `m3-add-copy` · F19-C3

Paquete de ejemplo para que Edu lo pruebe en el banco en 3 minutos. **No contiene
texto del juego**: el bloque fuente se lee del contenedor en memoria y el texto
que se escribe es una cadena inventada para la prueba.

## Qué hace

| dato | valor |
|---|---|
| tabla | `#983` (4600 filas × 68 B) |
| fila origen | 4001 (`nameIndex` +34 = 1 → `r = 4`) |
| fila nueva | 4600 (`count` 4600 → 4601) |
| id de texto fuente | 4 (en jp solo tiene el slot +0, que se sobrescribe) |
| id de texto nuevo | 3001 (el mayor id usado es 3000; el bloque 3001 está vacío en las 9 tablas) |
| `nameIndex` nuevo | 2998 (`r - 3`) |
| idioma escrito | `jp`; los otros 8 suben su `count` y se quedan sin texto |

## Comandos (desde la raíz del repo, con `PKP_ROMFS` apuntando al dump)

```bash
bash informes/m3-add-copy/demo.sh
```

El script copia el dump a `build/m3-add-copy/base` (solo lectura del original),
hace una copia de trabajo en `build/m3-add-copy/copia`, valida, aplica y deja las
salidas literales en `informes/m3-add-copy/salida-cli.txt` y
`salida-verificacion.txt`. Para mirar a mano:

```bash
pkp mod validate ejemplos/m3-add-copy --container build/m3-add-copy/base
pkp mod apply ejemplos/m3-add-copy --container build/m3-add-copy/copia --yes
pkp row 983 4600 --container build/m3-add-copy/copia --modificado
pkp row 4645 3001 --container build/m3-add-copy/copia --modificado --texto
```

`--modificado` es obligatorio al leer la copia: el lector estricto sigue
rechazando un `count` por encima del declarado, tal como fija
`docs/AÑADIR-FILAS.md` §4. No es un parche del lector, es su contrato.

## En el juego (banco de Edu, no ejecutado en esta tarjeta)

El mod de esta carpeta no está instalado en el RomFS.img. Para verlo en pantalla
haría falta empaquetarlo con `pkp mod pack` e instalarlo en el overlay; eso es
M3-bis y necesita el juego encendido con el OK explícito de Edu (D-021).
