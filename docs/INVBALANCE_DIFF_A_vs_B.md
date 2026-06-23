# Diff `2VR_SCM_INVBALANCE_01`: B (75 col) → A_1 (88 col)

`B` es subconjunto de `A_1`. `A_1` añade **13 columnas** (bloque aging / movimiento /
storage location). De dónde sale cada una en el SQL de la GV (`Join 9_0`):

## 1) De `2SR_OBSMATDOCPPMONTHAGGR_01`  (la vista de aging que adaptamos)
Join: `2SR_MATDOCGM_01 ⟕ 2SR_OBSMATDOCPPMONTHAGGR_01`
ON `Product=PRODUCT AND PL=PLANT AND PostingMonth=CALMONTH`  (nivel "Join 5_7")

| Columna | Origen |
|---|---|
| `Aging_Date_V2` | `2SR_OBSMATDOCPPMONTHAGGR_01.Aging_Date_V2` |
| `GI_MAX_DATE` | `2SR_OBSMATDOCPPMONTHAGGR_01.GI_MAX_DATE` |
| `GR_MIN_DATE` | `2SR_OBSMATDOCPPMONTHAGGR_01.GR_MIN_DATE` |
| `LastActivityDate` | `2SR_OBSMATDOCPPMONTHAGGR_01.LastActivityDate` |

## 2) De `2SR_MATDOCGM_01`  (la vista de goods movement)
Misma rama "Join 5_7".

| Columna | Origen |
|---|---|
| `Goods_Movement_Type` | `2SR_MATDOCGM_01.Goods_Movement_Type` |
| `PostingMonth` | `2SR_MATDOCGM_01.PostingMonth` |

## 3) De `3VR_MD_AGE_01`  (maestro de age band)
Join: `Calculated Columns 5_3 ⟕ 3VR_MD_AGE_01` ON `Inventory_Age_V2 = Age` (nivel "Join 8_2")

| Columna | Origen |
|---|---|
| `Age_V2` | `TO_NVARCHAR(3VR_MD_AGE_01.Age)` |
| `Active_Stock_Indicator_V2` | `3VR_MD_AGE_01.ActiveStockIndicator` |
| `Inventory_Age_Band_V2` | `3VR_MD_AGE_01.InventoryAgeBand` |

## 4) De `2VR_MD_STORAGELOCATIONTEXT_01`  (texto de storage location)
Join (el más externo): `Calculated Columns 6_1 ⟕ 2VR_MD_STORAGELOCATIONTEXT_01`
ON `PLANT=PLANT AND STORAGELOCATION=STORAGELOCATION` (nivel "Join 9_0")

| Columna | Origen |
|---|---|
| `STORAGELOCATIONNAME` | `2VR_MD_STORAGELOCATIONTEXT_01.STORAGELOCATIONNAME` |

## 5) De `2VR_MD_MARC_01` (2º uso) → `Aggregation 3_6`
`SELECT PRODUCT, PLANT, SUM(1) AS Count ... FROM 2VR_MD_MARC_01 GROUP BY PRODUCT, PLANT, CreationDateProdPlant`
Join: `Join 6_5 ⟕ Aggregation 3_6` ON `PLANT = PLANT`  (nivel "Join 7_4")

| Columna | Origen |
|---|---|
| `Count` | `SUM(1)` de `2VR_MD_MARC_01` por producto-planta |

> ⚠️ Ojo: ese join de `Count` está **solo ON PLANT** (no Product+Plant). Si la intención
> es contar por material-planta, probablemente falte `AND Product = PRODUCT`; tal como está,
> el Count se "infla" a nivel planta. Verificar.

## 6) Calculadas en la propia GV (no vienen de una fuente)

| Columna | Fórmula |
|---|---|
| `Inventory_Age_V2` | `CASE WHEN Aging_Date_V2 IS NULL THEN IFNULL(MONTHS_BETWEEN(CreationDateProdPlant, SnapshotDate),0) ELSE IFNULL(MONTHS_BETWEEN(Aging_Date_V2, SnapshotDate),0) END` |
| `ProductPlant` | `CASE WHEN LTRIM(PRODUCT,'0')='' THEN '0' ELSE LTRIM(PRODUCT,'0') END || '-' || PLANT` |

---

## Notas que conectan con lo anterior

- **El "months" sí se mantuvo** como spine, pero con fuente nativa de Datasphere:
  `CROSS JOIN 2VR_MD_TIMEDIMENSIONS_01("MONTHS" => '36')` (36 meses). Reemplaza al viejo
  `DS_AD.AD_GV_CBA_MD_MONTH`. La densificación/arrastre (CurrMonth/PrevMonth/cumulativos)
  vive aquí, en la capa de inventory balance — por eso el aging puede ir por mes-con-actividad.
- **`SnapshotDate`** sale del time dimension:
  `CASE WHEN CURRENT_DATE BETWEEN MonthStartDate AND MonthEndDate THEN CURRENT_DATE ELSE MonthEndDate END`.
- Las fuentes `2SR_OBSMATDOCPPMONTHAGGR_01` (aging+LastActivityDate) y `2SR_MATDOCGM_01`
  (goods movement) son las contrapartes nuevas de lo que veníamos trabajando.

## Resumen: para pasar de B (75) a A_1 (88)
Añadir, sobre la inventory balance base, estos joins:
1. `⟕ 2SR_OBSMATDOCPPMONTHAGGR_01` (Product+Plant+Month) → Aging_Date_V2, GI_MAX_DATE, GR_MIN_DATE, LastActivityDate
2. `⟕ 2SR_MATDOCGM_01` (Product+Plant+Month) → Goods_Movement_Type, PostingMonth
3. calcular `Inventory_Age_V2`
4. `⟕ 3VR_MD_AGE_01` (Inventory_Age_V2 = Age) → Age_V2, Active_Stock_Indicator_V2, Inventory_Age_Band_V2
5. calcular `ProductPlant`
6. `⟕ Count` desde `2VR_MD_MARC_01` (revisar key)
7. `⟕ 2VR_MD_STORAGELOCATIONTEXT_01` (Plant+StorageLocation) → STORAGELOCATIONNAME
