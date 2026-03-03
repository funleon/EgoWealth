import os
import psycopg2
from psycopg2 import pool
from dotenv import load_dotenv

load_dotenv()

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME", "egowealth")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "password")

# 建立資料庫連線池
try:
    connection_pool = psycopg2.pool.SimpleConnectionPool(
        1, 10,
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD
    )
except Exception as e:
    print(f"Error connecting to database: {e}")
    connection_pool = None

def get_db_connection():
    """從連線池租借連線"""
    if not connection_pool:
        raise Exception("Database connection pool is not initialized")
    conn = connection_pool.getconn()
    try:
        yield conn
    finally:
        connection_pool.putconn(conn)
