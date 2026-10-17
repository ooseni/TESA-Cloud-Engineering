-- Best value picks: points per million, highest first. Columns are named, never SELECT *.
USE squad_planner;
GO

SELECT player_name,
       position,
       club,
       price_millions,
       total_points,
       CAST(total_points / price_millions AS DECIMAL(6, 1)) AS points_per_million
FROM fantasy.target_squad
ORDER BY points_per_million DESC, player_name;
GO
