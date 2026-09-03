import sqlite3

DB_NAME = "nas_database.db"

def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row # Giúp trả về dữ liệu dạng dictionary dễ thao tác
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Tạo bảng lưu thông tin file media (Phim, Nhạc, Truyện, Shorts)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS media_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            path TEXT UNIQUE NOT NULL,
            category TEXT NOT NULL, -- 'phim', 'shorts', 'nhac', 'truyen'
            ext TEXT,
            thumb TEXT,
            size INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()

# Khởi tạo database ngay khi chạy file
init_db()