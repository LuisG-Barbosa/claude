-- =====================================================================
-- VISTA SQL 1 (nueva arquitectura)  ->  nombrar:  2VR_SCM_MATDOCMONTHS_00
-- Space: UNIFIED_SAP
-- Fuente: 2VR_TR_MATDOCBYGOODSRECEIPT_01 (la graphical view migrada)
-- Cambio vs original: SOLO el nombre de la fuente en los FROM.
--                     Los campos (Product, PL, PostingMonth,
--                     Goods_Movement_Type, Has_Had_200_Flag) son idénticos.
-- =====================================================================
SELECT
    p.Product,
    p.PL,
    m.PostingMonth,
    -- Valor (si existe) del Goods_Movement_Type en ese Product-PL-Mes
    (
        SELECT MAX(s.Goods_Movement_Type)
        FROM 2VR_TR_MATDOCBYGOODSRECEIPT_01 s
        WHERE s.Product = p.Product
          AND s.PL = p.PL
          AND s.PostingMonth = m.PostingMonth
    ) AS Goods_Movement_Type,
    -- Flag (si existe) en ese Product-PL-Mes
    (
        SELECT MAX(s.Has_Had_200_Flag)
        FROM 2VR_TR_MATDOCBYGOODSRECEIPT_01 s
        WHERE s.Product = p.Product
          AND s.PL = p.PL
          AND s.PostingMonth = m.PostingMonth
    ) AS Has_Had_200_Flag,
    -- Flag acumulado: ¿ya tuvo un 200 en o antes de este mes?
    (
        SELECT MAX(s.Has_Had_200_Flag)
        FROM 2VR_TR_MATDOCBYGOODSRECEIPT_01 s
        WHERE s.Product = p.Product
          AND s.PL = p.PL
          AND m.PostingMonth >= (
              SELECT MIN(s.PostingMonth)
              FROM 2VR_TR_MATDOCBYGOODSRECEIPT_01 s
              WHERE s.Product = p.Product
                AND s.PL = p.PL
                AND s.Has_Had_200_Flag = 'X'
          )
    ) AS Has_Had_200_Flag3,
    (
        SELECT MAX(s.Has_Had_200_Flag)
        FROM 2VR_TR_MATDOCBYGOODSRECEIPT_01 s
        WHERE s.Product = p.Product
          AND s.PL = p.PL
          AND m.PostingMonth >= (
              SELECT MIN(s.PostingMonth)
              FROM 2VR_TR_MATDOCBYGOODSRECEIPT_01 s
              WHERE s.Product = p.Product
                AND s.PL = p.PL
                AND s.Has_Had_200_Flag = 'X'
          )
    ) AS GOODS_2
FROM (
    -- Primer mes por Product-PL
    SELECT
        Product,
        PL,
        MIN(PostingMonth) AS FirstMonth
    FROM 2VR_TR_MATDOCBYGOODSRECEIPT_01
    GROUP BY Product, PL
) p
JOIN (
    -- Todos los meses distintos en los datos
    SELECT DISTINCT PostingMonth
    FROM 2VR_TR_MATDOCBYGOODSRECEIPT_01
) m
  ON m.PostingMonth >= p.FirstMonth
 AND m.PostingMonth <= (
        SELECT MAX(s2.PostingMonth)
        FROM 2VR_TR_MATDOCBYGOODSRECEIPT_01 s2
    );
