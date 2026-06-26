// FIX TRIỆT ĐỂ 404 TRUYỆN TRANH: Điều hướng chuẩn ký tự gốc
function goToManga(folderName) {
    if(!folderName) return;
    // Chuyển hướng trực tiếp thông qua giữ nguyên text, tránh bị lỗi gộp dấu của thẻ <a>
    window.location.href = "/manga/" + encodeURIComponent(folderName).replace(/%20/g, ' ');
}

// KHỞI TẠO MENU THANH TRƯỢT
function initMagicNav() {
    const container = document.querySelector('.magic-nav-container');
    if(!container) return;
    const indicator = document.getElementById('magicIndicator');
    const activeItem = container.querySelector('.magic-nav-item.active');
    if(activeItem && indicator) {
        const idx = parseInt(activeItem.getAttribute('data-index')) || 0;
        indicator.style.transform = `translateX(${idx * 89}px)`;
    }
}

// ĐÓNG MỞ DANH MỤC PHIM
function toggleMovieFolder(headerEl) {
    const parent = headerEl.parentElement;
    const content = parent.querySelector('.folder-content-anim');
    const chevron = parent.querySelector('.chevron-rotate');
    if(content) content.classList.toggle('collapsed');
    if(chevron) chevron.classList.toggle('collapsed');
}

// KÍNH NHÌN ĐÊM (TACTICAL HUD)
function toggleTacticalHUD() {
    document.body.classList.toggle('tactical-hud-mode');
    localStorage.setItem('tactical-hud', document.body.classList.contains('tactical-hud-mode') ? 'true' : 'false');
}

// TRÌNH PHÁT VIDEO SHORTS TỰ ĐỘNG KHÔNG LỖI
function initShortsHandler() {
    const container = document.getElementById('shortsContainer');
    if(!container) return;

    const videos = container.querySelectorAll('.short-video-player');

    videos.forEach(video => {
        video.addEventListener('click', () => {
            const icon = video.parentElement.querySelector('.play-status-icon');
            if (video.paused) {
                video.play().catch(()=>{});
                if(icon) icon.classList.add('opacity-0');
            } else {
                video.pause();
                if(icon) icon.classList.remove('opacity-0');
            }
        });
    });

    const muteBtns = container.querySelectorAll('.btn-mute-short');
    muteBtns.forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation();
            const wrapper = btn.closest('.shorts-snap-card');
            const video = wrapper.querySelector('video');
            if(video) {
                video.muted = !video.muted;
                btn.innerText = video.muted ? "Bật Âm Thanh" : "Tắt Âm Thanh";
            }
        });
    });

    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            const video = entry.target;
            if(entry.isIntersecting) {
                video.play().catch(() => {});
            } else {
                video.pause();
            }
        });
    }, { threshold: 0.6 });

    videos.forEach(v => observer.observe(v));
}

// VÒNG XOAY TRUYỆN TRANH (MANGA CAROUSEL)
let currentMangaIdx = 0;
function updateMangaCarousel() {
    const container = document.getElementById('mangaTrackContainer');
    if(!container) return;
    const items = container.querySelectorAll('.manga-item-fixed');
    if(items.length === 0) return;
    
    items.forEach((item, idx) => {
        item.className = 'manga-item-fixed flex flex-col justify-between p-4';
        let offset = idx - currentMangaIdx;
        if (offset === 0) {
            item.classList.add('active-center');
            const titleEl = document.getElementById('currentMangaCarouselTitle');
            const h4 = item.querySelector('h4');
            if(titleEl && h4) titleEl.innerText = h4.innerText;
        } else if (offset === -1 || (currentMangaIdx === 0 && idx === items.length - 1)) {
            item.classList.add('pos-left-1');
        } else if (offset === 1 || (currentMangaIdx === items.length - 1 && idx === 0)) {
            item.classList.add('pos-right-1');
        }
    });
}

function rotateMangaCarousel(dir) {
    const container = document.getElementById('mangaTrackContainer');
    if(!container) return;
    const items = container.querySelectorAll('.manga-item-fixed');
    if(items.length === 0) return;
    currentMangaIdx = (currentMangaIdx + dir + items.length) % items.length;
    updateMangaCarousel();
}

// LẤY DANH SÁCH TIẾN TRÌNH REALTIME
async function fetchDownloadTasks() {
    const container = document.getElementById('downloadTasksContainer');
    if(!container) return;
    try {
        const res = await fetch('/api/tasks');
        if(res.ok) {
            const data = await res.json();
            if(Object.keys(data).length > 0) {
                container.innerHTML = '';
                Object.keys(data).forEach(k => {
                    const t = data[k];
                    const itemHtml = `
                        <div class="bg-slate-950 p-3 rounded-xl border border-white/5 space-y-2">
                            <div class="flex justify-between font-bold text-xs font-mono text-slate-300">
                                <span class="truncate max-w-[200px]">${k}</span>
                                <span class="text-green-400">${t.current_chap || 'N/A'}</span>
                            </div>
                            <div class="w-full bg-slate-900 rounded-full h-1.5 overflow-hidden">
                                <div class="bg-green-500 h-1.5 transition-all duration-300" style="width: ${t.progress || 0}%"></div>
                            </div>
                            <div class="text-[10px] text-slate-500 font-mono">${t.status || 'Đang xử lý...'}</div>
                        </div>
                    `;
                    container.insertAdjacentHTML('beforeend', itemHtml);
                });
            }
        }
    } catch(e) {}
}

// LẮP RÁP KHI SẴN SÀNG
document.addEventListener('DOMContentLoaded', () => {
    initMagicNav();
    initShortsHandler();
    updateMangaCarousel();
    
    if(localStorage.getItem('tactical-hud') === 'true') {
        document.body.classList.add('tactical-hud-mode');
    }

    if(document.getElementById('downloadTasksContainer')) {
        setInterval(fetchDownloadTasks, 3000);
    }
});