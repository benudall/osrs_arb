-- SQLite
SELECT id, name, (highalch * 2 / 3) as lowalch, updated_at 
FROM items 
WHERE members = 0 and lowalch > 167 
ORDER BY lowalch DESC