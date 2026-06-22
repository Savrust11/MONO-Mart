SELECT
  product_code,
  cost_price                                                                       AS cost,
  retail_price                                                                     AS list_price,
  selling_price                                                                    AS sell,
  ROUND(gross_margin_pct, 1)                                                       AS gm_new,
  ROUND(SAFE_DIVIDE(selling_price - cost_price, NULLIF(selling_price, 0)) * 100,1) AS gm_check,
  ROUND(SAFE_DIVIDE(retail_price  - cost_price, NULLIF(retail_price,  0)) * 100,1) AS gm_old
FROM `mono-back-office-system.mart_layer.order_analysis`
WHERE analysis_date = '2026-05-05'
  AND cost_price > 0 AND selling_price > 0 AND retail_price > 0
  AND selling_price != retail_price
LIMIT 10;
