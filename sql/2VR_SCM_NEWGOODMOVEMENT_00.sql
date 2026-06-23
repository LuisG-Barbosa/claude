-- =====================================================================
-- VISTA SQL 2 (nueva arquitectura)  ->  nombrar:  2VR_SCM_NEWGOODMOVEMENT_00
-- Space: UNIFIED_SAP
-- Fuente: 2VR_SCM_MATDOCMONTHS_00 (la vista SQL 1 de arriba)
-- Cambio vs original: SOLO el nombre de la fuente (HA_GV_SCM_MATDOCMONTHS_00
--                     -> 2VR_SCM_MATDOCMONTHS_00). Campos idénticos.
-- =====================================================================
SELECT
    base.Product,
    base.PL,
    base.PostingMonth,
    base.Goods_Movement_Type,
    CASE
        -- Prioridad 1: Movimientos 2xx si existe el flag
        WHEN sub.Goods_Movement_Type IS NOT NULL AND base.Has_Had_200_Flag3 = 'X' THEN sub.Goods_Movement_Type
        -- Prioridad 2: Movimientos 1xx, 901 y ahora 561 (Agrupados)
        WHEN sub2.Goods_Movement_Type IS NOT NULL THEN sub2.Goods_Movement_Type
        -- Prioridad 3: Movimiento 309
        ELSE sub3_309.Goods_Movement_Type
    END AS New_Good_Movement,
    base.Has_Had_200_Flag3
FROM 2VR_SCM_MATDOCMONTHS_00 base
LEFT JOIN (
    SELECT
        s.Product,
        s.PL,
        s.PostingMonth,
        s.Goods_Movement_Type,
        ROW_NUMBER() OVER (
            PARTITION BY s.Product, s.PL, s.PostingMonth
            ORDER BY s.PostingMonth DESC
        ) AS rn
    FROM 2VR_SCM_MATDOCMONTHS_00 s
    WHERE s.Goods_Movement_Type IN (261, 201, 221, 241, 291, 541)
) sub
    ON sub.Product = base.Product
    AND sub.PL = base.PL
    AND sub.PostingMonth = (
        SELECT MAX(s2.PostingMonth) AS MaxPostingMonth
        FROM 2VR_SCM_MATDOCMONTHS_00 s2
        WHERE s2.Product = base.Product
          AND s2.PL = base.PL
          AND s2.Goods_Movement_Type IN (261, 201, 221, 241, 291, 541)
          AND s2.PostingMonth <= base.PostingMonth
    )
    AND sub.rn = 1
LEFT JOIN (
    SELECT
        s.Product,
        s.PL,
        s.PostingMonth,
        s.Goods_Movement_Type,
        ROW_NUMBER() OVER (
            PARTITION BY s.Product, s.PL, s.PostingMonth
            ORDER BY s.PostingMonth ASC
        ) AS rn
    FROM 2VR_SCM_MATDOCMONTHS_00 s
    -- MODIFICADO: Se agrega 561 a la lista
    WHERE s.Goods_Movement_Type IN (101, 103, 105, 107, 109, 901, 561)
) sub2
    ON sub2.Product = base.Product
    AND sub2.PL = base.PL
    AND sub2.PostingMonth = (
        SELECT MIN(s2.PostingMonth) AS MinPostingMonth
        FROM 2VR_SCM_MATDOCMONTHS_00 s2
        WHERE s2.Product = base.Product
          AND s2.PL = base.PL
          AND s2.Goods_Movement_Type IN (101, 103, 105, 107, 109, 901, 561)
          AND s2.PostingMonth <= base.PostingMonth
    )
    AND sub2.rn = 1
LEFT JOIN (
    SELECT
        s.Product,
        s.PL,
        s.PostingMonth,
        s.Goods_Movement_Type,
        ROW_NUMBER() OVER (
            PARTITION BY s.Product, s.PL, s.PostingMonth
            ORDER BY s.PostingMonth ASC
        ) AS rn
    FROM 2VR_SCM_MATDOCMONTHS_00 s
    WHERE s.Goods_Movement_Type IN (309)
) sub3_309
    ON sub3_309.Product = base.Product
    AND sub3_309.PL = base.PL
    AND sub3_309.PostingMonth = (
        SELECT MIN(s2.PostingMonth) AS MinPostingMonth
        FROM 2VR_SCM_MATDOCMONTHS_00 s2
        WHERE s2.Product = base.Product
          AND s2.PL = base.PL
          AND s2.Goods_Movement_Type IN (309)
          AND s2.PostingMonth <= base.PostingMonth
    )
    AND sub3_309.rn = 1;
