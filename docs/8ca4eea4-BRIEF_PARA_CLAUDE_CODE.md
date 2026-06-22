# Brief: Migración de Graphical View en SAP Datasphere (HA_ → 2VR_)

## Objetivo
Migrar una vista gráfica (graphical view) de SAP Datasphere de una arquitectura
antigua a una nueva, editando su archivo JSON (CSN export), de modo que al
importarla y abrirla en el editor gráfico de Datasphere **no marque errores** y
produzca el mismo resultado que la original.

La vista resultante debe llamarse `2VR_TR_MATDOCBYGOODSRECEIPT_01` (o `_02`).

---

## Archivos (pídelos al usuario y colócalos en el working dir)

1. **`HA_GV_EAM_TR_MATDOCBYGOODSRECEIPT_01.json`** — ORIGINAL que funciona.
   Es la fuente de verdad de la ESTRUCTURA correcta (nodos, agregaciones,
   funciones, vínculos). ~2.3 MB, ~2034 nodos en el uiModel.

2. **`2VR_TR_MATDOCBYGOODSRECEIPT_01__5_.json`** — Intento en progreso
   (re-exportado de Datasphere con las fuentes nuevas resueltas). Tiene las
   definiciones de las fuentes nuevas (`2VR_*`) ya resueltas, pero su uiModel
   quedó con estructura recortada/inconsistente. ~9 MB.

3. **`3VR_SCM_MATDOC_01__1_.json`** — Contiene las definiciones de las vistas
   fuente nuevas (para consultar nombres de columnas).

---

## Mapeo de migración (fuentes y columnas)

### Fuentes (reemplazos en `definitions` y en refs de la query)
| Vieja                         | Nueva                |
|-------------------------------|----------------------|
| `HA_GV_SCM_TR_MATDOC`         | `2VR_SCM_MATDOC_02`  |
| `CBA_MD.DI_ProductPlant`      | `2VR_MD_MARC_01`     |

### Columnas de la fuente MATDOC (`HA_GV_SCM_TR_MATDOC` → `2VR_SCM_MATDOC_02`)
| Vieja               | Nueva               |
|---------------------|---------------------|
| `GoodsMovementType` | `GOODSMOVEMENTTYPE` |
| `Product`           | `MATERIAL`          |
| `Plant`             | `PLANT`             |
| `PostingDate`       | `POSTINGDATE`       |
| `PostingMonth`      | `PostingMonth` (igual) |

### Columnas de la fuente ProductPlant (`CBA_MD.DI_ProductPlant` → `2VR_MD_MARC_01`)
| Vieja                   | Nueva                   |
|-------------------------|-------------------------|
| `Product`               | `PRODUCT`               |
| `Plant`                 | `PLANT`                 |
| `CreationDateProdPlant` | `CreationDateProdPlant` (igual) |

> NOTA IMPORTANTE: estos nombres NUEVOS aplican SOLO cuando se lee directamente
> de la fuente. Dentro de la vista, el flujo ya renombra todo a alias INTERNOS
> que NO deben cambiarse (ver sección "Niveles" abajo).

---

## Alias de los nodos fuente en la query (uiModel)
La fuente MATDOC aparece referenciada con estos 7 alias (son etiquetas de nodo,
no nombres de fuente):
`HA_GV_SCM_TR_MATDOC(3)`, `HA_GV_SCM_TR_MATDOC(4)`, `100 date`, `100 goods`,
`200 date`, `200 goods`, `561`.
La fuente ProductPlant usa el alias: `DI_ProductPlant`.

---

## EL PROBLEMA CRÍTICO (esto es lo que hay que resolver bien)

El `uiModel` (string JSON embebido en `editorSettings`) NO es solo nombres de
columnas. Cada nodo tiene metadata estructural por ID que el editor valida al
abrir. Reemplazar nombres a ciegas ROMPE estos vínculos.

### Síntoma observado
Al abrir la vista migrada, el editor marca:
> "The node 'Aggregation 4' must have at least one aggregation defined."

### Causa raíz (CONFIRMADA por inspección del original)
En un nodo `AggregatedElements`, la metadata del nodo en sí NO contiene la
función de agregación. La función vive en los **nodos `Element` hijos** (que se
referencian por el ID del elemento). Un Element agregado se ve así:

```json
{
  "classDefinition": "sap.cdw.querybuilder.Element",
  "name": "PostingDate",
  "label": "Posting Date",
  "newName": "PostingDate",
  "expression": "PostingDate",
  "isCalculated": true,
  "defaultAggregation": "MAX",   <-- CLAVE
  "isAggregated": true,          <-- CLAVE
  "dataType": "cds.Integer",
  ...
}
```

Las columnas de AGRUPACIÓN (Product, Plant, PostingMonth) del mismo Aggregation
NO tienen `defaultAggregation` ni `isAggregated`. Solo la columna agregada
(PostingDate con MAX) los tiene.

**Cuando se reconstruye/edita el uiModel sin preservar `defaultAggregation` e
`isAggregated`, el nodo Aggregation queda inválido** → ese es el error.

Esto aplica a TODOS los nodos Aggregation de la vista, no solo Aggregation 4.

---

## Niveles: dónde cambiar nombres y dónde NO (regla esencial)

La query (en `definitions[viewName].query`) está organizada en niveles anidados:

1. **Nivel hoja (lee de la fuente):** las columnas usan el nombre NUEVO de
   fuente. Ej: `{"as":"Product", "ref":["2VR_SCM_MATDOC_02(3)","MATERIAL"]}`.
   Aquí `MATERIAL` (nuevo) entra y se renombra a `Product` (alias interno) de
   inmediato.
2. **Niveles intermedios y superiores:** TODO usa los alias INTERNOS ya
   renombrados: `Product`, `PL`, `Goods_Movement_Type` (con guión bajo),
   `Product561`, `Plant_561`, `GoodsMovementType561`, `GMT`, `MAT`, `concat`,
   `GOODS_AND_DATE`, etc. ESTOS NO SE TOCAN.

### Heurística para detectar nivel interno (no tocar nombres de fuente ahí):
Una expresión es de nivel interno si contiene cualquiera de:
`"Goods_Movement_Type"` (con guión bajo y comillas), `"PL"`, `561`, `0s`,
`_561`, `GOODS_AND_DATE`, `Goods_Movement_Type=`.
En esas, dejar `GoodsMovementType`/`Product`/`Plant` como están.

### Filtros (campo `condition` en nodos Filter):
- Filter 1-6 y 9 leen de la fuente → usar `GOODSMOVEMENTTYPE` y `MATERIAL`.
- Filter 8 usa `GoodsMovementType561 = '561'` → es alias interno, NO tocar.

---

## Salida esperada de la vista (5 columnas — CRÍTICO)
La vista DEBE exponer exactamente estas 5, tanto en `definitions[view].elements`
como en la proyección externa de la query:
`Goods_Movement_Type`, `Has_Had_200_Flag`, `PostingMonth`, `PL`, `Product`.

En un intento previo se perdió `Product`. La columna final es:
`{"as":"Product","key":true,"ref":["DI_ProductPlant","PRODUCT"]}`
(ojo: en la proyección externa, `Product` debe propagarse a través de toda la
cadena de nodos, no referenciarse directo a la fuente, porque el alias
`DI_ProductPlant` solo es accesible en el nivel del join final).

---

## Estrategia recomendada (en este orden)

### PASO 1 — Construir un VALIDADOR estructural (antes de editar nada)
Escribe un script que parsee el uiModel (es un string JSON dentro de
`editorSettings[viewName].uiModel`) y verifique reglas, comparando contra el
ORIGINAL como referencia:

- a) Todo nodo `AggregatedElements` tiene ≥1 Element hijo con
     `isAggregated:true` y `defaultAggregation` definido.
- b) Para cada Aggregation, el conjunto de Elements hijos (agrupación +
     agregados) coincide en cantidad y roles con el del original (mapeando
     nombres viejos↔nuevos).
- c) Toda `RenameElements` (projection) tiene ≥1 columna seleccionada.
- d) Cada `successorNode`/`successorElement` apunta a un ID que existe.
- e) Los `elements` de cada nodo son consistentes con los del nodo predecesor
     (que las columnas que consume existan en lo que produce el anterior).
- f) Las entidades fuente (`Entity`) referencian columnas que SÍ existen en la
     definición de la fuente nueva correspondiente.
- g) La proyección externa de la query produce las 5 columnas de salida.
- h) Cero rastros de arquitectura vieja: `HA_GV_SCM_TR_MATDOC`,
     `CBA_MD`, `crossSpace`, `PR_GV_`, `DI_ProductPlant` como NOMBRE de fuente
     (como alias sí es válido).

Este validador es lo que faltó en los intentos previos: permite iterar sin
estar a ciegas.

### PASO 2 — Transformar
Parte del ORIGINAL (estructura correcta y completa) y:
- Renombra la entidad principal a `2VR_TR_MATDOCBYGOODSRECEIPT_01`.
- Reemplaza fuentes raíz y columnas de fuente (solo nivel hoja) según el mapeo.
- Renombra los alias de nodo `HA_GV_SCM_TR_MATDOC(3)/(4)` →
  `2VR_SCM_MATDOC_02(3)/(4)`.
- Actualiza los `elements` de las entidades fuente en el uiModel a las columnas
  nuevas.
- **PRESERVA `defaultAggregation` e `isAggregated`** en todos los Element
  agregados (no los borres ni al copiar ni al renombrar).
- Trae del archivo `__5_` las `definitions` de las fuentes nuevas (`2VR_*`) y
  sus dependencias necesarias; elimina las definiciones huérfanas viejas
  (`CBA_MD*`, `HA_GV*`, `PR_*`). Conserva los contextos `SAP.CURRENCY.*`
  (vistas estándar de conversión de moneda, son legítimas).
- Limpia el `editorSettings`: elimina la rama embebida de la fuente vieja y el
  nodo de contexto `CBA_MD` (tiene `crossSpace` a otro space).

### PASO 3 — Validar e iterar
Corre el validador del Paso 1. Arregla cada hallazgo. Repite hasta 0 errores.
NO consideres terminado hasta que el validador pase Y un diff estructural contra
el original (mapeando nombres) no muestre diferencias en roles de agregación,
columnas seleccionadas, ni vínculos.

---

## LÍMITE CONOCIDO (importante, decirle al usuario)
El esquema interno del `uiModel` NO está documentado públicamente por SAP. Todo
lo de arriba es ingeniería inversa del archivo original. Hay riesgo de que
existan campos de metadata adicionales que el editor valida y que no hemos
identificado. Por eso el validador del Paso 1 debe construirse comparando
EXHAUSTIVAMENTE la forma de cada tipo de nodo contra el original, no asumiendo
que conocemos todos los campos.

Si tras varias iteraciones siguen apareciendo errores nuevos al abrir en el
editor, la alternativa robusta es: pegar el SQL generado (la query, que SÍ es
correcta) en un **SQL View** nuevo en Datasphere y olvidarse del diagrama
gráfico. Funciona igual, se despliega igual; solo se pierde el editor visual.

---

## Datos verificados (para que arranques con hechos, no suposiciones)
- Original: 2034 nodos en uiModel. La query expone 5 columnas.
- La fuente `2VR_SCM_MATDOC_02` SÍ expone: MATERIAL, PLANT, POSTINGDATE,
  GOODSMOVEMENTTYPE, PostingMonth (verificado).
- La fuente `2VR_MD_MARC_01` SÍ expone: PRODUCT, PLANT, CreationDateProdPlant.
- Hay 8 nodos Filter (condition), múltiples Aggregation, RenameElements
  (projections), CalculatedElements, Join y Union.
- La función de agregación está en Element hijos vía `defaultAggregation` +
  `isAggregated:true`.
