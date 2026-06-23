-- =====================================================================
-- Aging dates por Producto-Planta-Mes  (arquitectura nueva 2VR_)
-- Fuentes nuevas: 2VR_MD_MARC_01 (PP) + 2VR_SCM_MATDOC_02 (matdoc)
--
-- Se AÑADE LastActivityDate (lógica de GIMovementInd/GRMovementInd del
-- SELECT viejo), adaptada a campos y fuentes nuevos:
--   DI_ProductPlant      -> 2VR_MD_MARC_01
--   HA_GV_SCM_TR_MATDOC  -> 2VR_SCM_MATDOC_02
--   Plant/Product/PostingDate/IsReversalMovementType
--                        -> PLANT/MATERIAL(JOIN)/POSTINGDATE/ISREVERSALMOVEMENTTYPE
--   (GIMovementInd, GRMovementInd, GI_Max_Date, GR_Min_Date, PostingMonth,
--    CreationDateProdPlant conservan su nombre en las fuentes nuevas)
--
-- MESES: se ELIMINA el CROSS JOIN al spine (DS_AD.AD_GV_CBA_MD_MONTH ...
-- MONTHS:0). CALMONTH = PostingMonth, igual que ya hace Aging_Date_V2.
-- Implicación: LastActivityDate queda POR mes-con-actividad (no acumulado
-- "a la fecha de cada mes"). Si se necesita densificar/arrastrar por todos
-- los meses, eso debe vivir en la capa de Inventory Balance. (ver chat)
-- =====================================================================
SELECT
    PP."PLANT",
    PP."PRODUCT",
    matdoc."PostingMonth" AS "CALMONTH",
    PP."CreationDateProdPlant",

    MAX(CASE WHEN matdoc."GI_Max_Date" = 'X' THEN matdoc."POSTINGDATE" END) AS GI_MAX_DATE,
    MIN(CASE WHEN matdoc."GR_Min_Date" = 'X' THEN matdoc."POSTINGDATE" END) AS GR_MIN_DATE,

    -- Aging_Date_V2 (sin cambios)
    CASE
        WHEN MAX(CASE WHEN matdoc."GI_Max_Date" = 'X' THEN matdoc."POSTINGDATE" END) != '00000000'
             THEN MAX(CASE WHEN matdoc."GIMovementInd" = 'X' THEN matdoc."POSTINGDATE" END)
        WHEN MIN(CASE WHEN matdoc."GR_Min_Date" = 'X' THEN matdoc."POSTINGDATE" END) != '00000000'
             THEN MIN(CASE WHEN matdoc."GRMovementInd" = 'X' THEN matdoc."POSTINGDATE" END)
        ELSE MAX(PP."CreationDateProdPlant")
    END AS Aging_Date_V2,

    -- ===== NUEVO: Last Activity Date =====
    -- check y valor usan GIMovementInd/GRMovementInd (los indicadores de movimiento)
    CASE
        WHEN MAX(CASE WHEN matdoc."GIMovementInd" = 'X' THEN matdoc."POSTINGDATE" END) != '00000000'
             THEN MAX(CASE WHEN matdoc."GIMovementInd" = 'X' THEN matdoc."POSTINGDATE" END)
        WHEN MIN(CASE WHEN matdoc."GRMovementInd" = 'X' THEN matdoc."POSTINGDATE" END) != '00000000'
             THEN MIN(CASE WHEN matdoc."GRMovementInd" = 'X' THEN matdoc."POSTINGDATE" END)
        ELSE MAX(PP."CreationDateProdPlant")
    END AS LastActivityDate

FROM "2VR_MD_MARC_01" AS PP
    INNER JOIN "2VR_SCM_MATDOC_02" AS matdoc
        ON matdoc."PLANT" = PP."PLANT"
        AND matdoc."MATERIAL" = PP."PRODUCT"
WHERE matdoc."ISREVERSALMOVEMENTTYPE" = ''
GROUP BY PP."PLANT",
    PP."PRODUCT",
    matdoc."PostingMonth",
    PP."CreationDateProdPlant";
