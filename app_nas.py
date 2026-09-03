import os
import sys
import shutil
import urllib.parse
import re
import asyncio
import aiohttp
import primp  
import subprocess
from fastapi.responses import StreamingResponse
from pathlib import Path
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from bs4 import BeautifulSoup
from fastapi.staticfiles import StaticFiles

# 👉 IMPORT KẾT NỐI DATABASE TỪ FILE database.py
from database import get_db_connection

# 1. Khai báo biến đường dẫn gốc trước
if getattr(sys, 'frozen', False):
    base_path = sys._MEIPASS
else:
    base_path = os.path.dirname(os.path.abspath(__file__))

# 2. Khởi tạo app FastAPI trước
app = FastAPI(title="Turbo NAS Ultimate Hub Pro")

# 3. Sau đó mới mount thư mục static và templates
STATIC_DIR = os.path.join(base_path, "static")
os.makedirs(STATIC_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

TEMPLATES_DIR = os.path.join(base_path, "templates")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

# --- CẤU HÌNH ĐƯỜNG DẪN Ổ E (hoặc D) ---
if os.path.exists("D:\\"):
    NAS_PHIM_DIR = Path(r"D:\phim")
    NAS_NHAC_DIR = Path(r"D:\nhac")
    NAS_TRUYEN_DIR = Path(r"D:\truyen")
else:
    data_backup_dir = Path(base_path) / "NAS_DATA"
    NAS_PHIM_DIR = data_backup_dir / "phim"
    NAS_NHAC_DIR = data_backup_dir / "nhac"
    NAS_TRUYEN_DIR = data_backup_dir / "truyen"

NAS_PHIM_DIR.mkdir(parents=True, exist_ok=True)
NAS_NHAC_DIR.mkdir(parents=True, exist_ok=True)
NAS_TRUYEN_DIR.mkdir(parents=True, exist_ok=True)

VIDEO_EXTENSIONS = {'.mp4', '.mkv', '.webm', '.avi', '.mov'}
AUDIO_EXTENSIONS = {'.mp3', '.flac', '.wav', '.m4a', '.ogg'}
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.gif'}

DOWNLOAD_TASKS = {} 
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7",
}

# --- 🚀 HÀM ĐỒNG BỘ Ổ CỨNG VÀO SQLITE KHI KHỞI ĐỘNG ---
def sync_nas_to_db():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Quét và đồng bộ phim & shorts
        if NAS_PHIM_DIR.exists():
            for item in NAS_PHIM_DIR.rglob('*'):
                if item.is_file() and item.suffix.lower() in VIDEO_EXTENSIONS:
                    rel_path = item.relative_to(NAS_PHIM_DIR).as_posix()
                    ext = item.suffix.upper().replace('.', '')
                    cursor.execute('''
                        INSERT OR IGNORE INTO media_files (name, path, category, ext)
                        VALUES (?, ?, 'phim', ?)
                    ''', (item.stem, rel_path, ext))
                    
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"❌ Lỗi đồng bộ Database: {e}")

# Chạy đồng bộ ngay khi khởi động app
sync_nas_to_db()


def get_disk_info():
    try:
        target_path = "D:\\" if os.path.exists("D:\\") else base_path
        total, used, free = shutil.disk_usage(target_path)
        return f"{free / (1024**3):.1f} GB trống / {total / (1024**3):.1f} GB"
    except: 
        return "N/A"

def find_movie_thumbnail(movie_file_path: Path):
    try:
        for ext in IMAGE_EXTENSIONS:
            possible_img = movie_file_path.with_suffix(ext)
            if possible_img.exists():
                rel_p = possible_img.relative_to(NAS_PHIM_DIR).as_posix()
                return f"/thumbnail/{urllib.parse.quote(rel_p)}"
        
        parent_dir = movie_file_path.parent
        if parent_dir != NAS_PHIM_DIR:
            video_stem_lower = movie_file_path.stem.lower()
            img_files = [f for f in parent_dir.iterdir() if f.is_file() and f.suffix.lower() in IMAGE_EXTENSIONS]
            if img_files:
                for img in img_files:
                    if img.stem.lower() in video_stem_lower or video_stem_lower in img.stem.lower():
                        rel_p = img.relative_to(NAS_PHIM_DIR).as_posix()
                        return f"/thumbnail/{urllib.parse.quote(rel_p)}"
                rel_p = img_files[0].relative_to(NAS_PHIM_DIR).as_posix()
                return f"/thumbnail/{urllib.parse.quote(rel_p)}"
    except: 
        pass
    return "/static/images/default_thumb.jpg"

def get_manga_thumbnail(manga_path: Path):
    try:
        for f in manga_path.iterdir():
            if f.is_file() and f.suffix.lower() in IMAGE_EXTENSIONS:
                return f"/comic-img/{urllib.parse.quote(manga_path.name)}/{urllib.parse.quote(f.name)}"
        for root, dirs, files in os.walk(str(manga_path)):
            img_files = sorted([f for f in files if Path(f).suffix.lower() in IMAGE_EXTENSIONS])
            if img_files:
                full_img_path = Path(root) / img_files[0]
                rel_parts = full_img_path.relative_to(NAS_TRUYEN_DIR).parts
                url_path = "/".join([urllib.parse.quote(part) for part in rel_parts])
                return f"/comic-img/{url_path}"
    except: 
        pass
    return None

def scan_directory_tree(base_dir: Path, current_dir: Path, allowed_exts: set, tab_type: str):
    node_list = []
    try:
        for item in sorted(current_dir.iterdir()):
            rel_path = item.relative_to(base_dir).as_posix()
            if item.is_dir():
                children = scan_directory_tree(base_dir, item, allowed_exts, tab_type)
                node_list.append({"name": item.name, "type": "folder", "path": rel_path, "children": children})
            elif item.is_file() and item.suffix.lower() in allowed_exts:
                node_list.append({"name": item.name, "type": "file", "path": rel_path})
    except: 
        pass
    return node_list

async def async_download_image(session, client_rust, url, save_path, referer_url):
    img_headers = HEADERS.copy()
    img_headers["Referer"] = referer_url
    img_headers["Accept"] = "image/webp,image/*,*/*;q=0.8"
    
    for attempt in range(1, 4):
        try:
            def call_primp_img():
                return client_rust.get(url, headers=img_headers, timeout=20)
            
            res = await asyncio.get_event_loop().run_in_executor(None, call_primp_img)
            if res.status_code == 200 and len(res.content) > 5120:
                await asyncio.get_event_loop().run_in_executor(None, lambda: save_path.write_bytes(res.content))
                return True
        except: 
            await asyncio.sleep(attempt * 1)
    return False

async def background_manga_downloader_pro(start_url, folder_name, limit):
    global DOWNLOAD_TASKS
    current_url = start_url.strip()
    DOWNLOAD_TASKS[folder_name] = {"status": "📡 Đang khởi động hệ thống bắt tử...", "current_chap": "Đang đồng bộ", "progress": 1}
    
    try: 
        domain = re.match(r"https?://[^/]+", current_url).group(0)
    except: 
        DOWNLOAD_TASKS[folder_name]["status"] = "❌ Lỗi định dạng URL"
        return

    client_rust = primp.Client(impersonate="chrome_125", follow_redirects=True)
    chaps_downloaded = 0
    connector = aiohttp.TCPConnector(limit_per_host=5)
    
    async with aiohttp.ClientSession(connector=connector) as session:
        while current_url and chaps_downloaded < limit:
            is_chapter_valid = False
            soup = None
            
            for attempt in range(1, 4):
                try:
                    DOWNLOAD_TASKS[folder_name]["status"] = f"📡 Đang tải: {current_url.split('/')[-1] or current_url.split('/')[-2]}"
                    
                    def call_primp_page():
                        return client_rust.get(current_url, headers=HEADERS, timeout=20)
                    
                    res = await asyncio.get_event_loop().run_in_executor(None, call_primp_page)
                    if res.status_code != 200: 
                        await asyncio.sleep(2)
                        continue
                    
                    soup = BeautifulSoup(res.text, 'html.parser')
                    img_tags = (
                        soup.select(".chapter-content img") or 
                        soup.select(".page-chapter img") or 
                        soup.select(".chapter_content img") or 
                        soup.select(".story-see-content img") or 
                        soup.select(".reading-detail img") or
                        soup.select(".page-content img") or
                        soup.select(".list-image img")
                    )
                    
                    if not img_tags or len(img_tags) == 0:
                        await asyncio.sleep(2)
                        continue
                    
                    title_text = soup.find('h1') or soup.find('title')
                    chap_name = ""
                    if title_text:
                        match = re.search(r"Chapter\s*(\d+(\.\d+)?)", title_text.text, re.IGNORECASE) or re.search(r"Chương\s*(\d+(\.\d+)?)", title_text.text, re.IGNORECASE)
                        if match:
                            chap_num = float(match.group(1))
                            chap_name = f"Chapter {int(chap_num):03d}" if chap_num.is_integer() else f"Chapter {chap_num:05.1f}"
                    
                    if not chap_name: 
                        chap_name = f"Chapter_{chaps_downloaded + 1:03d}"
                    
                    DOWNLOAD_TASKS[folder_name]["current_chap"] = chap_name
                    chapter_dir = NAS_TRUYEN_DIR / folder_name / chap_name
                    chapter_dir.mkdir(parents=True, exist_ok=True)
                    
                    clean_img_urls = []
                    for img in img_tags:
                        src = img.get('data-original') or img.get('src') or img.get('data-src') or img.get('data-cdn') or img.get('data-url')
                        if not src or src.strip() == "#" or "logo" in src.lower() or "loading" in src.lower(): 
                            continue
                        if src.startswith('//'): src = 'https:' + src
                        clean_img_urls.append(src)
                    
                    expected_count = len(clean_img_urls)
                    if expected_count > 0:
                        DOWNLOAD_TASKS[folder_name]["status"] = f"📥 Đang tải {expected_count} trang của {chap_name}..."
                        tasks = [async_download_image(session, client_rust, url, chapter_dir / f"{i:03d}.jpg", current_url) for i, url in enumerate(clean_img_urls, start=1)]
                        results = await asyncio.gather(*tasks)
                        success_count = sum(1 for r in results if r)
                        
                        if success_count < int(expected_count * 0.5):
                            if chapter_dir.exists(): 
                                shutil.rmtree(chapter_dir)
                            await asyncio.sleep(1)
                            continue
                    
                    is_chapter_valid = True
                    break
                except Exception as e:
                    await asyncio.sleep(1)
            
            next_url = None
            if soup:
                nav_tags = soup.find_all('a', class_=re.compile(r"prev|next|btn-next|btn-prev", re.IGNORECASE))
                for tag in nav_tags:
                    href = tag.get('href')
                    if href and href != "#" and "javascript" not in href:
                        if href.startswith('//'): next_url = 'https:' + href
                        elif href.startswith('/'): next_url = domain + href
                        elif href.startswith('http'): next_url = href
                        break
            
            if not next_url:
                match_num = re.search(r'(-|/)(chuong|chapter|chap)-?(\d+(\.\d+)?)', current_url, re.IGNORECASE)
                if match_num:
                    prefix_word = match_num.group(2)
                    current_num_val = float(match_num.group(3))
                    next_num_val = current_num_val - 1
                    if next_num_val > 0:
                        num_str = str(int(next_num_val)) if next_num_val.is_integer() else str(next_num_val)
                        next_url = re.sub(r'(-|/)' + prefix_word + r'-?\d+(\.\d+)?', rf'\1{prefix_word}-{num_str}', current_url, flags=re.IGNORECASE)

            if is_chapter_valid:
                chaps_downloaded += 1
                DOWNLOAD_TASKS[folder_name]["progress"] = int((chaps_downloaded / limit) * 100)

            if next_url and next_url != current_url:
                current_url = next_url
                await asyncio.sleep(1.0)
            else: 
                break
                
    DOWNLOAD_TASKS[folder_name]["status"] = f"🎉 Hoàn thành! Đã hốt gọn {chaps_downloaded} chương."
    DOWNLOAD_TASKS[folder_name]["progress"] = 100
    await asyncio.sleep(15)
    DOWNLOAD_TASKS.pop(folder_name, None)

@app.get("/", response_class=HTMLResponse)
async def index(request: Request, tab: str = "phim"):
    folders_data = []
    movie_sections = {}
    shorts_list = []
    tree_data = []
    
    if tab == "phim" or tab == "shorts":
        try:
            # 👉 TRUY VẤN TRỰC TIẾP TỪ SQLITE THAY VÌ OS.RGALL (CỰC KỲ NHANH)
            conn = get_db_connection()
            db_movies = conn.execute("SELECT * FROM media_files WHERE category = 'phim'").fetchall()
            conn.close()

            for row in db_movies:
                item_path = NAS_PHIM_DIR / row['path']
                parent_name = item_path.parent.name
                
                is_short_video = "shorts" in parent_name.lower() or "shorts" in row['name'].lower() or "short" in row['name'].lower()
                thumb_url = find_movie_thumbnail(item_path)
                
                movie_item = {
                    "name": row['name'],
                    "filename": item_path.name,
                    "ext": row['ext'],
                    "path": row['path'],
                    "thumb": thumb_url
                }
                
                if is_short_video:
                    shorts_list.append(movie_item)
                
                section_name = "Phim Tổng Hợp" if item_path.parent == NAS_PHIM_DIR else item_path.parent.name
                if section_name not in movie_sections:
                    movie_sections[section_name] = []
                movie_sections[section_name].append(movie_item)
        except Exception as e:
            print(f"❌ Lỗi lấy phim từ DB: {e}")
            
    elif tab == "nhac":
        tree_data = scan_directory_tree(NAS_NHAC_DIR, NAS_NHAC_DIR, AUDIO_EXTENSIONS, "nhac")
        
    elif tab == "truyen":
        if NAS_TRUYEN_DIR.exists():
            for item in sorted(NAS_TRUYEN_DIR.iterdir()):
                if item.is_dir():
                    chap_count = len([c for c in item.iterdir() if c.is_dir()])
                    thumb = get_manga_thumbnail(item)
                    folders_data.append({
                        "name": item.name, "path": item.name, "chaps": chap_count,
                        "thumb": thumb or "https://images.unsplash.com/photo-1607604276583-eef5d076aa5f?w=400"
                    })

    return templates.TemplateResponse(
        request=request, name="index.html",
        context={"tab": tab, "folders": folders_data, "movie_sections": movie_sections, "shorts_list": shorts_list, "tree": tree_data, "disk": get_disk_info()}
    )
    
@app.get("/stream-transcode/{file_path:path}")
async def stream_transcode(file_path: str):
    full_path = NAS_PHIM_DIR / urllib.parse.unquote(file_path)
    if not full_path.exists():
        raise HTTPException(status_code=404, detail="Không tìm thấy file phim")

    # Lệnh FFmpeg: Chuyển đổi on-the-fly sang H.264/AAC và tối ưu hóa để stream web ngay lập tức
    cmd = [
        "ffmpeg",
        "-i", str(full_path),
        "-c:v", "libx264",       # Encode video sang H.264 (trình duyệt nào cũng đọc được)
        "-preset", "ultrafast",  # Siêu tốc để giảm độ trễ (giảm tải CPU)
        "-crf", "28",            # Chất lượng hình ảnh (từ 18-28, số càng cao dung lượng stream càng nhẹ)
        "-c:a", "aac",           # Encode âm thanh sang AAC
        "-b:a", "128k",
        "-f", "mp4",             # Xuất ra định dạng container MP4
        "-movflags", "frag_keyframe+empty_moov", # Cho phép stream mượt mà không cần quét xong toàn bộ file
        "pipe:1"                 # Xuất dữ liệu ra luồng chuẩn (stdout) để Python bắt lấy
    ]

    # Khởi chạy tiến trình FFmpeg ngầm
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    # Hàm generator đọc dữ liệu từ FFmpeg và trả về trình duyệt từng cục nhỏ (chunks)
    def generate():
        try:
            while True:
                chunk = process.stdout.read(1024 * 64) # Đọc từng 64KB
                if not chunk:
                    break
                yield chunk
        finally:
            process.terminate()

    return StreamingResponse(generate(), media_type="video/mp4")

@app.post("/download-manga")
async def start_manga_download(request: Request, background_tasks: BackgroundTasks):
    form_data = await request.form()
    url = form_data.get("url")
    folder = form_data.get("folder")
    limit = int(form_data.get("limit", 100))
    background_tasks.add_task(background_manga_downloader_pro, url, folder, limit)
    return HTMLResponse("<script>alert('Đã kích hoạt tiến trình tải truyện ngầm!'); window.location.href='/?tab=truyen';</script>")

@app.get("/download-status-json")
async def get_all_tasks_status(): 
    return JSONResponse(DOWNLOAD_TASKS)

@app.get("/stream/audio/{file_path:path}")
async def stream_audio(file_path: str):
    clean_name = os.path.basename(urllib.parse.unquote(file_path))
    target_audio_path = Path(r"D:\NHAC") / clean_name
    
    if not target_audio_path.exists():
        matches = list(Path(r"D:\NHAC").rglob(clean_name))
        if matches:
            target_audio_path = matches[0]
            
    if not target_audio_path.exists():
        raise HTTPException(status_code=404, detail=f"Không tìm thấy file nhạc: {clean_name}")
        
    return FileResponse(str(target_audio_path), media_type="audio/mpeg")

@app.get("/stream/{file_path:path}")
async def stream_video(file_path: str): 
    full_path = NAS_PHIM_DIR / urllib.parse.unquote(file_path)
    return FileResponse(str(full_path), media_type="video/mp4")

@app.get("/thumbnail/{file_path:path}")
async def get_movie_local_image(file_path: str):
    full_path = NAS_PHIM_DIR / urllib.parse.unquote(file_path)
    if full_path.exists() and full_path.is_file(): return FileResponse(str(full_path))
    raise HTTPException(status_code=404)

@app.get("/watch/{file_path:path}", response_class=HTMLResponse)
async def watch_movie(request: Request, file_path: str):
    decoded = urllib.parse.unquote(file_path)
    return templates.TemplateResponse(request=request, name="watch.html", context={"title": Path(decoded).stem, "movie_path": file_path})

@app.get("/comic/{manga_name}", response_class=HTMLResponse)
async def list_manga_chapters(request: Request, manga_name: str):
    manga_dir = NAS_TRUYEN_DIR / manga_name
    chapters = sorted([d.name for d in manga_dir.iterdir() if d.is_dir()], key=lambda x: [float(c) if c.isdigit() else c for c in re.split(r'(\d+)', x)])
    return templates.TemplateResponse(request=request, name="manga.html", context={"manga_name": manga_name, "chapters": chapters})

@app.get("/comic/{manga_name}/{chapter_name}", response_class=HTMLResponse)
async def read_manga_chapter(request: Request, manga_name: str, chapter_name: str):
    manga_dir = NAS_TRUYEN_DIR / manga_name
    all_chaps = sorted([d.name for d in manga_dir.iterdir() if d.is_dir()], key=lambda x: [float(c) if c.isdigit() else c for c in re.split(r'(\d+)', x)])
    current_idx = all_chaps.index(chapter_name)
    return templates.TemplateResponse(
        request=request, name="reader.html",
        context={
            "manga_name": manga_name, "manga_path": manga_name, "chapter_name": chapter_name,
            "images": sorted([f.name for f in (manga_dir / chapter_name).iterdir() if f.is_file() and f.suffix.lower() in IMAGE_EXTENSIONS]),
            "prev_chap": all_chaps[current_idx - 1] if current_idx > 0 else None,
            "next_chap": all_chaps[current_idx + 1] if current_idx < len(all_chaps) - 1 else None
        }
    )

@app.get("/comic-img/{file_path:path}")
async def get_comic_image(file_path: str):
    full_path = NAS_TRUYEN_DIR / urllib.parse.unquote(file_path)
    if full_path.exists() and full_path.is_file(): return FileResponse(str(full_path))
    raise HTTPException(status_code=404)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app_nas:app", host="0.0.0.0", port=8000, reload=True)