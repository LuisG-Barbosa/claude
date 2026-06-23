import json, os

A = json.load(open("input/invbalance/INVBALANCE_A_1.json"))["definitions"]
INV = A["2VR_SCM_INVBALANCE_01"]["elements"]   # superset 88 col con tipos

VIEW = "3VR_INVBALANCEFOROBSMAT_01"

SQL = r'''-- 3VR_INVBALANCEFOROBSMAT_01
-- Consume el 2VR_SCM_INVBALANCE_01 ORIGINAL (sin enriquecer) y le aplica
-- la capa de obsolescencia (goods movement + aging + age band + storage loc name)
-- que antes vivia dentro del 2VR (y que inflaba sus registros).
SELECT
    enr."PRODUCT",
    enr."PLANT",
    enr."CALMONTH",
    enr."PostingMonth",
    enr."STORAGELOCATION",
    slt."STORAGELOCATIONNAME",
    enr."SnapshotDate",
    enr."CreationDateProdPlant",
    -- medidas base (vienen del 2VR original)
    enr."OwnedStockQuantity",
    enr."OwnedStockValueInCC",
    enr."OwnedStockValueInGC",
    enr."OwnedStockOnHandQuantity",
    enr."OwnedStockOnHandValueInCC",
    enr."OwnedStockOnHandValueInGC",
    enr."OwnedTransferQuantity",
    enr."OwnedTransferValueInCC",
    enr."OwnedTransferValueInGC",
    enr."OwnedTransitQuantity",
    enr."OwnedTransitValueInCC",
    enr."OwnedTransitValueInGC",
    -- enriquecimiento
    enr."Goods_Movement_Type",
    enr."Aging_Date_V2",
    enr."GI_MAX_DATE",
    enr."GR_MIN_DATE",
    enr."LastActivityDate",
    enr."Count",
    enr."Inventory_Age_V2",
    TO_NVARCHAR(age."Age")           AS "Age_V2",
    age."ActiveStockIndicator"       AS "Active_Stock_Indicator_V2",
    age."InventoryAgeBand"           AS "Inventory_Age_Band_V2",
    enr."ProductPlant"
FROM (
    SELECT
        j."PRODUCT", j."PLANT", j."CALMONTH", j."PostingMonth", j."STORAGELOCATION",
        j."SnapshotDate", j."CreationDateProdPlant",
        j."OwnedStockQuantity", j."OwnedStockValueInCC", j."OwnedStockValueInGC",
        j."OwnedStockOnHandQuantity", j."OwnedStockOnHandValueInCC", j."OwnedStockOnHandValueInGC",
        j."OwnedTransferQuantity", j."OwnedTransferValueInCC", j."OwnedTransferValueInGC",
        j."OwnedTransitQuantity", j."OwnedTransitValueInCC", j."OwnedTransitValueInGC",
        j."Goods_Movement_Type", j."Aging_Date_V2", j."GI_MAX_DATE", j."GR_MIN_DATE",
        j."LastActivityDate", j."Count",
        -- Inventory_Age_V2 = meses entre la fecha de aging (o creacion) y el snapshot
        CASE WHEN j."Aging_Date_V2" IS NULL
             THEN IFNULL(MONTHS_BETWEEN(j."CreationDateProdPlant", j."SnapshotDate"), 0)
             ELSE IFNULL(MONTHS_BETWEEN(j."Aging_Date_V2", j."SnapshotDate"), 0) END AS "Inventory_Age_V2",
        -- ProductPlant (MaterialPlantKEY) = material sin ceros a la izq || '-' || planta
        CASE WHEN LTRIM(j."PRODUCT", '0') = '' THEN '0' ELSE LTRIM(j."PRODUCT", '0') END
            || '-' || j."PLANT" AS "ProductPlant"
    FROM (
        SELECT
            gm."Product"        AS "PRODUCT",
            gm."PL"             AS "PLANT",
            gm."PostingMonth"   AS "CALMONTH",
            gm."PostingMonth"   AS "PostingMonth",
            gm."Goods_Movement_Type",
            base."STORAGELOCATION",
            base."SnapshotDate",
            obs."CreationDateProdPlant",
            obs."Aging_Date_V2", obs."GI_MAX_DATE", obs."GR_MIN_DATE", obs."LastActivityDate",
            cnt."Count",
            base."OwnedStockQuantity", base."OwnedStockValueInCC", base."OwnedStockValueInGC",
            base."OwnedStockOnHandQuantity", base."OwnedStockOnHandValueInCC", base."OwnedStockOnHandValueInGC",
            base."OwnedTransferQuantity", base."OwnedTransferValueInCC", base."OwnedTransferValueInGC",
            base."OwnedTransitQuantity", base."OwnedTransitValueInCC", base."OwnedTransitValueInGC"
        FROM "2SR_MATDOCGM_01" AS gm
        LEFT JOIN "2SR_OBSMATDOCPPMONTHAGGR_01" AS obs
            ON  gm."Product"     = obs."PRODUCT"
            AND gm."PL"          = obs."PLANT"
            AND gm."PostingMonth"= obs."CALMONTH"
        LEFT JOIN "2VR_SCM_INVBALANCE_01" AS base
            ON  gm."PL"          = base."PLANT"
            AND gm."PostingMonth"= base."CALMONTH"
            AND gm."Product"     = base."PRODUCT"
        LEFT JOIN (
            SELECT "PRODUCT", "PLANT", SUM(1) AS "Count"
            FROM "2VR_MD_MARC_01"
            GROUP BY "PRODUCT", "PLANT"
        ) AS cnt
            ON  base."PLANT"     = cnt."PLANT"
            AND base."PRODUCT"   = cnt."PRODUCT"      -- corregido: el nuevo unia solo por PLANT (inflaba)
    ) AS j
) AS enr
LEFT JOIN "3VR_MD_AGE_01" AS age
    ON enr."Inventory_Age_V2" = age."Age"
LEFT JOIN "2VR_MD_STORAGELOCATIONTEXT_01" AS slt
    ON  enr."PLANT"           = slt."PLANT"
    AND enr."STORAGELOCATION" = slt."STORAGELOCATION";
'''

# columnas de salida (en orden) -> tomar tipo del superset INV (88 col)
OUT = ["PRODUCT","PLANT","CALMONTH","PostingMonth","STORAGELOCATION","STORAGELOCATIONNAME",
"SnapshotDate","CreationDateProdPlant","OwnedStockQuantity","OwnedStockValueInCC","OwnedStockValueInGC",
"OwnedStockOnHandQuantity","OwnedStockOnHandValueInCC","OwnedStockOnHandValueInGC",
"OwnedTransferQuantity","OwnedTransferValueInCC","OwnedTransferValueInGC",
"OwnedTransitQuantity","OwnedTransitValueInCC","OwnedTransitValueInGC",
"Goods_Movement_Type","Aging_Date_V2","GI_MAX_DATE","GR_MIN_DATE","LastActivityDate","Count",
"Inventory_Age_V2","Age_V2","Active_Stock_Indicator_V2","Inventory_Age_Band_V2","ProductPlant"]

missing = [c for c in OUT if c not in INV]
assert not missing, f"faltan tipos: {missing}"

def clean(elt):
    e = {k:v for k,v in elt.items() if not k.startswith("@DataWarehouse.")}
    e.pop("key", None); e.pop("notNull", None)
    return e

elements = {c: clean(INV[c]) for c in OUT}

view_def = {
    "kind": "entity",
    "elements": elements,
    "@ObjectModel.supportedCapabilities": [{"#": "DATA_STRUCTURE"}],
    "@EndUserText.label": "Inventory Balance for Obsolete Material",
    "@ObjectModel.modelingPattern": {"#": "DATA_STRUCTURE"},
    "@DataWarehouse.consumption.external": True,
    "@DataWarehouse.sqlEditor.query": SQL,
}
out = {"definitions": {VIEW: view_def}}

os.makedirs("output", exist_ok=True)
os.makedirs("sql", exist_ok=True)
open(f"sql/{VIEW}.sql","w").write(SQL)
json.dump(out, open(f"output/{VIEW}.json","w"), ensure_ascii=False, indent=2)
print("OK. columnas salida:", len(OUT))
print("SQL ->", f"sql/{VIEW}.sql", "| JSON ->", f"output/{VIEW}.json")
print("tamaño JSON:", os.path.getsize(f"output/{VIEW}.json"), "bytes")
