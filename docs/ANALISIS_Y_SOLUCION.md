# Migración HA_ → 2VR_ : análisis del flujo de columnas y solución

Vista: `HA_GV_EAM_TR_MATDOCBYGOODSRECEIPT_01` (vieja, funciona) →
`2VR_TR_MATDOCBYGOODSRECEIPT_01` (nueva arquitectura).

---

## 1. Resumen ejecutivo (qué estaba mal y qué se hizo)

Un export de Datasphere tiene **dos representaciones paralelas** de la misma vista:

| Parte | Qué es | Estado en tu `2VR_..._02.json` |
|---|---|---|
| `definitions[view].query` | La **query CSN** → genera el SQL que se despliega y ejecuta | ✅ **Correcta** |
| `editorSettings[view].uiModel` | El **modelo gráfico** (string JSON con 2.034 nodos) que el editor dibuja y **valida** | ❌ **Roto** → de ahí el error |

El error *“The node 'Aggregation 4' must have at least one aggregation defined”* **no** venía de las
agregaciones (sus flags estaban intactas), sino de que el **linaje de columnas del `uiModel`
quedó inconsistente**, y al no poder resolver las columnas, el editor invalida los nodos de agregación.

**Causa raíz** — el intento en chat hizo un *reemplazo global ciego* tratando
`Product / Plant / PostingDate / GoodsMovementType` como si fueran columnas de fuente **en todos lados**.
En realidad esos nombres son **alias internos** en todo el flujo **excepto en el borde donde se lee la
fuente**. El reemplazo rompió el modelo por los dos extremos:

1. Dejó las **Entity leyendo `Product`** (y `Plant`, `PostingDate`…), columnas que **ya no existen** en
   `2VR_SCM_MATDOC_02` (ahora se llaman `MATERIAL`, `PLANT`, `POSTINGDATE`).
2. Cambió a MAYÚSCULAS **174 expresiones internas** (`Product` → `MATERIAL`, etc.) que debían
   permanecer como alias internos → cada `CalculatedElements`/`Aggregation`/`Join` quedó referenciando
   columnas que su predecesor no produce.
3. Cambió **Filter 9** (`Product is not null` → `MATERIAL is not null`), pero Filter 9 está **al final**
   del flujo y usa el alias interno `Product`, no la fuente.

**Solución** — se reconstruyó el `uiModel` partiendo del **original que funciona** y aplicando el rename
**solo en el borde de lectura**, dejando el 99 % interno **byte-idéntico** al original. El contenedor del
archivo (definitions + query CSN + meta) se toma del `_02` (que ya era correcto). Resultado:
`output/2VR_TR_MATDOCBYGOODSRECEIPT_01.FIXED.json`.

---

## 2. La arquitectura del flujo (idéntica en vieja y nueva)

8 fuentes convergen en 1 salida a través de 80 nodos:

```
7× MATDOC (alias: 200 date, 100 date, 200 goods, 100 goods, (3), (4), 561)
1× ProductPlant (alias: DI_ProductPlant)
        │
   [Entity] → [Filter] → [Projection] → [Calculated] → [Aggregation] → … → [Join]×6 → [Union] → … → [Output: 5 cols]
```

Salida final (5 columnas): `Goods_Movement_Type`, `Has_Had_200_Flag`, `PostingMonth`, `PL`, `Product`.

### Cómo se enlazan los nodos (esto es lo que el chat no entendió)

- `uiModel.contents` es un **diccionario plano `UUID → nodo`** (ahí viven los 2.034 nodos completos).
- Un nodo de query (Aggregation, Projection…) lista sus columnas como **referencias ligeras**
  `elements: { UUID: {name} }`. La **definición completa** (con `expression`, `defaultAggregation`,
  `isAggregated`, etc.) está en `contents[UUID]`.
- El flujo de datos se sigue por dos enlaces:
  - `successorNode`  : nodo → nodo siguiente.
  - `successorElement`: columna → misma columna en el nodo siguiente (el **linaje**).
- En cada `Element`: `name` = etiqueta/identidad, `newName` = nombre que **expone** a la salida,
  `expression` = fórmula o columna de entrada que **consume**. El editor resuelve el linaje por
  `successorElement` + `newName`/`expression`.

> La función de agregación **no** está en el nodo Aggregation; está en sus `Element` hijos
> (`isAggregated:true` + `defaultAggregation`). En tu `_02` estas flags estaban **bien**; el problema
> era que las columnas que alimentan esos hijos no resolvían.

---

## 3. Flujo de una columna de principio a fin (vieja vs nueva)

Clave del asunto: en la vieja, la fuente `HA_GV_SCM_TR_MATDOC` tenía una columna **literalmente llamada
`Product`**, así que `Product` fluía sin rename de punta a punta. En la nueva, la fuente expone
`MATERIAL`, así que hay que **renombrar `MATERIAL → Product` una sola vez, en el borde**, y dejar el
resto igual.

### Ejemplo: `Product` desde el alias `200 date`

| Hop | Nodo | VIEJA (`name` / `newName` / `expr`) | NUEVA — CORRECTA (FIXED) |
|----:|------|-------------------------------------|--------------------------|
| 0 | Entity | `Product` / `Product` / – | **`MATERIAL` / `MATERIAL` / –** |
| 1 | Filter 2 | `Product` / `Product` / – | **`MATERIAL` / `MATERIAL` / –** |
| 2 | **Projection 1** (puente) | `Product` / `Product` / – | **`MATERIAL` / `Product` / –** ← rename aquí |
| 3 | Calculated Columns 1 | `Product` / `Product` / `Product` | `Product` / `Product` / `Product` (igual) |
| 4 | Aggregation 1 | … `Product` … | … `Product` … (igual) |
| … | … hasta Projection 28 | `Product` | `Product` (igual) |

Comparación con lo que tenía el **`_02` roto**:

| Hop | `_02` ROTO | Problema |
|----:|-----------|----------|
| 0 | Entity `name=Product` | ❌ `Product` no existe en `2VR_SCM_MATDOC_02` |
| 3+ | Calc/Agg `expr=MATERIAL` | ❌ el predecesor produce `Product`, no `MATERIAL` |

### Las tres topologías de borde (todas resueltas en FIXED)

| Rama | Cadena | Punto de puente | Rename |
|------|--------|-----------------|--------|
| MATDOC normal (×6) | Entity → Filter → **Projection** | 1ª RenameElements | `MATERIAL→Product`, `PLANT→Plant`, `POSTINGDATE→PostingDate`, `GOODSMOVEMENTTYPE→GoodsMovementType` |
| 561 | Entity → **Projection 27** → Filter 8 | 1ª RenameElements | `MATERIAL→Product561`, `PLANT→Plant_561`, … (Filter 8 usa el alias interno `GoodsMovementType561`, **no se toca**) |
| ProductPlant | Entity → **Projection 29** → Join 1 | 1ª RenameElements | `PRODUCT→Product`, `PLANT→Plant` (CreationDateProdPlant igual) |

> **Coherencia verificada:** los renames del borde en el `uiModel` coinciden 1-a-1 con los `as` de los
> *leaf SELECT* de la query CSN (p. ej. `{"as":"Product","ref":["2VR_SCM_MATDOC_02(3)","MATERIAL"]}`).

---

## 4. Mapeo de columnas de fuente aplicado (solo en el borde)

`2VR_SCM_MATDOC_02` (MATDOC):

| Vieja | Nueva | Tipo |
|---|---|---|
| `Product` | `MATERIAL` | semántico |
| `Plant` | `PLANT` | mayúsculas |
| `PostingDate` | `POSTINGDATE` | mayúsculas |
| `GoodsMovementType` | `GOODSMOVEMENTTYPE` | mayúsculas |
| `PostingMonth` | `PostingMonth` | igual |

`2VR_MD_MARC_01` (ProductPlant): `Product`→`PRODUCT`, `Plant`→`PLANT`, `CreationDateProdPlant` igual.

Filtros: **Filter 1–6** (leen de fuente, pre-puente) → nombres nuevos. **Filter 8 y Filter 9**
(post-puente) → alias internos, **sin tocar**.

---

## 5. Qué se cambió exactamente (mínima superficie)

- 8 Entity: `name`/`alias`/`label` → fuente nueva (copiado del `_02`).
- 197 columnas renombradas **solo en el borde** (Entity, Filter pre-puente y el `name` de la 1ª
  RenameElements). El `newName` del puente conserva el alias interno.
- 6 condiciones de Filter (1–6).
- Eliminado el nodo de contexto `CBA_MD` (tenía `crossSpace` a otro space) y `Model.contexts`.
- `Model.name`/`label` y la etiqueta de la entidad → `2VR_…`.
- **Todo lo demás del `uiModel` (366 elementos internos post-puente) quedó byte-idéntico al original.**
- `definitions` + query CSN + `meta`: tomados tal cual del `_02` (ya correctos).

---

## 6. Validación realizada (script `src/validate.py`)

```
✅ (a) Las 10 Aggregation tienen ≥1 hijo agregado
✅ (b) Roles de agregación idénticos al OLD
✅ (c) Todas las RenameElements tienen columnas
✅ (d) Todos los successorNode/Element resuelven a IDs existentes
✅ (e) Los 366 elementos internos (post-puente) son IDÉNTICOS al OLD
✅ (f) Columnas clave de entidad existen en la fuente nueva
✅ (g) Salida = 5 columnas correctas
✅ (h) Sin rastros de arquitectura vieja (HA_GV/CBA_MD/crossSpace)
```

---

## 7. Riesgo residual y plan B

- **Único residual conocido:** cada Entity todavía lista ~27 (MATDOC) / ~20 (MARC) columnas “stale”
  del esquema viejo que no existen en la fuente nueva (p. ej. `EntryUnit`, `GLAccount`). **Se descartan
  aguas abajo** (nunca llegan a calc/agregación/salida/query) y **el propio `_02` ya las tenía y
  Datasphere las toleró** (su único error era el de Aggregation). Datasphere refresca la lista de
  columnas de la fuente al abrir, así que no deberían estorbar. Si se desea un export 100 % limpio,
  se pueden eliminar (pídemelo y lo hago).
- **No puedo abrir esto en tu Datasphere**, así que la validación es estructural (consistencia interna +
  identidad con el original que funciona), no contra el editor real. Por la naturaleza no documentada
  del `uiModel`, queda un riesgo bajo de que el editor valide algún campo que no hayamos identificado.
- **Plan B garantizado:** la query CSN es correcta y se despliega igual. Si el editor gráfico diera
  problemas, se pega el SQL generado en una **SQL View** nueva y funciona idéntico (solo se pierde el
  diagrama visual).

---

## 8. Cómo reproducir

```bash
python3 src/transform.py     # genera output/...FIXED.json desde el OLD + contenedor _02
python3 src/validate.py      # 8/8 checks
```

Archivos: `input/HA_OLD.json` (viejo), `input/2VR_NEW.json` (tu intento _02),
`output/2VR_TR_MATDOCBYGOODSRECEIPT_01.FIXED.json` (resultado).
