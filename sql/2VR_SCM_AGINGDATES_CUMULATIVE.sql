-- =====================================================================
-- Aging dates POR MES, ACUMULATIVO (denso) — arquitectura nueva 2VR_
-- Replica el comportamiento del SQL viejo (arrastra valores mes a mes
-- aunque no haya consumo) usando un spine de meses + join acumulativo.
--
-- Clave: el join  m."CALMONTH" >= matdoc."PostingMonth"  hace que, para
-- cada mes, se incluyan TODOS los movimientos hasta ese mes -> los MAX/MIN
-- se mantienen (carry-forward) en meses sin movimiento nuevo.
--
-- Spine: 2VR_MD_TIMEDIMENSIONS_01 (la MISMA time dim que usa tu INVBALANCE,
-- CALMONTH 'YYYYMM', acotada con MONTHS => '36'). No se necesita la tabla
-- vieja DS_AD.AD_GV_CBA_MD_MONTH.
-- =====================================================================
SELECT
    PP."PLANT",
    PP."PRODUCT",
    m."CALMONTH",
    PP."CreationDateProdPlant",

    MAX(CASE WHEN matdoc."GI_Max_Date" = 'X' THEN matdoc."POSTINGDATE" END) AS "GI_MAX_DATE",
    MIN(CASE WHEN matdoc."GR_Min_Date" = 'X' THEN matdoc."POSTINGDATE" END) AS "GR_MIN_DATE",

    CASE
        WHEN MAX(CASE WHEN matdoc."GI_Max_Date" = 'X' THEN matdoc."POSTINGDATE" END) != '00000000'
             THEN MAX(CASE WHEN matdoc."GIMovementInd" = 'X' THEN matdoc."POSTINGDATE" END)
        WHEN MIN(CASE WHEN matdoc."GR_Min_Date" = 'X' THEN matdoc."POSTINGDATE" END) != '00000000'
             THEN MIN(CASE WHEN matdoc."GRMovementInd" = 'X' THEN matdoc."POSTINGDATE" END)
        ELSE MAX(PP."CreationDateProdPlant")
    END AS "Aging_Date_V2",

    -- LastActivityDate (misma lógica con GIMovementInd/GRMovementInd)
    CASE
        WHEN MAX(CASE WHEN matdoc."GIMovementInd" = 'X' THEN matdoc."POSTINGDATE" END) != '00000000'
             THEN MAX(CASE WHEN matdoc."GIMovementInd" = 'X' THEN matdoc."POSTINGDATE" END)
        WHEN MIN(CASE WHEN matdoc."GRMovementInd" = 'X' THEN matdoc."POSTINGDATE" END) != '00000000'
             THEN MIN(CASE WHEN matdoc."GRMovementInd" = 'X' THEN matdoc."POSTINGDATE" END)
        ELSE MAX(PP."CreationDateProdPlant")
    END AS "LastActivityDate"

FROM "2VR_MD_MARC_01" AS PP
    INNER JOIN "2VR_SCM_MATDOC_02" AS matdoc
        ON  matdoc."PLANT"    = PP."PLANT"
        AND matdoc."MATERIAL" = PP."PRODUCT"
    -- spine de meses + join acumulativo (esto es lo que faltaba)
    INNER JOIN "2VR_MD_TIMEDIMENSIONS_01"(MONTHS => '36') AS m
        ON  m."CALMONTH" >= matdoc."PostingMonth"
WHERE matdoc."ISREVERSALMOVEMENTTYPE" = ''
GROUP BY
    PP."PLANT",
    PP."PRODUCT",
    m."CALMONTH",
    PP."CreationDateProdPlant";


-- =====================================================================
-- ALTERNATIVA con la fuente de la imagen: SAP.TIME.VIEW_DIMENSION_MONTH
-- (trae TODOS los meses -> hay que ACOTAR para no explotar el cross join).
-- Verifica el nombre real de la columna de mes (suele ser CALMONTH 'YYYYMM').
-- =====================================================================
-- ... mismas SELECT/GROUP BY que arriba, cambiando solo el spine: ...
--    INNER JOIN "SAP.TIME.VIEW_DIMENSION_MONTH" AS m
--        ON  m."CALMONTH" >= matdoc."PostingMonth"
--       AND m."CALMONTH" <= TO_VARCHAR(CURRENT_DATE, 'YYYYMM')   -- cota superior
-- (opcional cota inferior para limitar histórico:
--       AND m."CALMONTH" >= '202001' )
