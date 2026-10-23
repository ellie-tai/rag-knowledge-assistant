-- 資料庫第一次建立時自動執行（docker-compose.yml 把這個資料夾掛到 /docker-entrypoint-initdb.d）。
-- 啟用 pgvector，讓 PostgreSQL 能儲存向量並做相似度搜尋。
CREATE EXTENSION IF NOT EXISTS vector;
