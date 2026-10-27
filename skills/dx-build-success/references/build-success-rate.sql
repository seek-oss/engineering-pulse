-- Parameterized by scripts/dx_studio.py: __PERIOD__ (e.g. 3 months), __TEAM_ILIKE__ (e.g. %Example Team%)
WITH time_series AS (
  SELECT date_trunc('week', dates) AS week_start
  FROM generate_series(
    (CURRENT_DATE - INTERVAL '__PERIOD__')::date,
    CURRENT_DATE::date,
    '1 week'::interval
  ) AS dates
),
talent_search_users AS (
  SELECT dxu.id AS dx_user_id
  FROM dx_teams dxt
  JOIN dx_team_hierarchies h ON dxt.id = h.ancestor_id
  JOIN dx_users dxu ON h.descendant_id = dxu.team_id
  WHERE dxt.name ILIKE '__TEAM_ILIKE__'
    AND dxt.deleted_at IS NULL
),
weekly_build_stats AS (
  SELECT
    date_trunc('week', pr.finished_at) AS week_start,
    SUM(CASE WHEN pr.status ILIKE 'succ%' THEN 1 ELSE 0 END) AS successful_builds,
    SUM(CASE WHEN pr.status ILIKE 'succ%' OR pr.status ILIKE 'fail%' THEN 1 ELSE 0 END) AS total_builds,
    ROUND(
      SUM(CASE WHEN pr.status ILIKE 'succ%' THEN 1 ELSE 0 END) * 100.0
      / NULLIF(SUM(CASE WHEN pr.status ILIKE 'succ%' OR pr.status ILIKE 'fail%' THEN 1 ELSE 0 END), 0),
      2
    ) AS success_rate_pct
  FROM pipeline_runs pr
  WHERE pr.dx_user_id IN (SELECT dx_user_id FROM talent_search_users)
    AND pr.finished_at >= CURRENT_DATE - INTERVAL '__PERIOD__'
    AND pr.finished_at <= CURRENT_DATE
  GROUP BY date_trunc('week', pr.finished_at)
)
SELECT
  ts.week_start,
  COALESCE(ws.successful_builds, 0) AS successful_builds,
  COALESCE(ws.total_builds, 0) AS total_builds,
  ws.success_rate_pct
FROM time_series ts
LEFT JOIN weekly_build_stats ws ON ts.week_start = ws.week_start
ORDER BY ts.week_start;
