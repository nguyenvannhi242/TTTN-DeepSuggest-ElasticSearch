// app.js 
const API_URL = 'http://localhost:8001';
const RESULTS_PER_PAGE = 20; // Số sản phẩm tải mỗi lần

// === BIẾN TOÀN CỤC ĐỂ THEO DÕI SỐ TRANG ===
let currentProductPage = 1;
let isLoading = false; // Cờ để tránh click "Tải thêm" nhiều lần
let currentPriceFilter = null; // Lưu trữ bộ lọc giá hiện tại

// === DOM ELEMENTS ===
const appContent = document.getElementById('app-content');
const docContent = document.getElementById('doc-content');
const navTabApp = document.getElementById('nav-tab-app');
const navTabDoc = document.getElementById('nav-tab-doc');
const productGrid = document.getElementById('product-grid');
const allProductsSection = document.getElementById('all-products-section');
const keywordResultsSection = document.getElementById('keyword-results-section');
const keywordResultsTitle = document.getElementById('keyword-results-title');
const keywordResultsGrid = document.getElementById('keyword-results-grid');
const keywordMessage = document.getElementById('keyword-message');
const semanticSuggestionsSection = document.getElementById('semantic-suggestions-section');
const semanticTitle = document.getElementById('semantic-title');
const semanticSuggestionsGrid = document.getElementById('semantic-suggestions-grid');
const semanticMessage = document.getElementById('semantic-message');
const searchForm = document.getElementById('search-form');
const searchInput = document.getElementById('search-input');
const categorySelect = document.getElementById('category-select');
const loadMoreProductsBtn = document.getElementById('load-more-products');
const modalElement = document.getElementById('product-modal');
const modalTitle = document.getElementById('modal-title');
const modalContent = document.getElementById('modal-content-main').querySelector('.modal-product-details');
const modalRecoList = document.getElementById('modal-recommendation-list');

let allCategories = [];
const formatter = new Intl.NumberFormat('vi-VN', { style: 'currency', currency: 'VND' });

// === HÀM MỚI: TÍNH SAO TỪ SỐ LƯỢT CLICK ===
function calculateRatingFromCount(count) {
    if (count > 50) return 5;    // Rất hot
    if (count > 30) return 4.5;
    if (count > 20) return 4;
    if (count > 10) return 3.5;
    if (count > 0) return 3;     // Có click
    return 2.5; // Mặc định cho sản phẩm 0 click (trông đẹp hơn 0)
}

// === HÀM TẠO SAO ===
function createStarRating(rating) {
    // Hàm này nhận rating (từ 0-5) và vẽ sao
    const roundedRating = Math.round(rating * 2) / 2;
    const fullStars = Math.floor(roundedRating);
    const halfStar = roundedRating % 1 !== 0 ? 1 : 0;
    const emptyStars = 5 - fullStars - halfStar;
    let starsHTML = '';
    for (let i = 0; i < fullStars; i++) starsHTML += '<i class="fas fa-star"></i>';
    if (halfStar) starsHTML += '<i class="fas fa-star-half-alt"></i>';
    for (let i = 0; i < emptyStars; i++) starsHTML += '<i class="far fa-star"></i>';
    return `<div class="card-rating">${starsHTML}</div>`;
}

// === HÀM CHUYỂN ĐỔI KHOẢNG GIÁ THÀNH QUERY ===
function priceRangeToQuery(priceRange) {
    const priceMap = {
        '0-5': 'dưới 5 triệu',
        '5-10': '5-10 triệu',
        '10-15': '10-15 triệu',
        '15-20': '15-20 triệu',
        '20-25': '20-25 triệu',
        '25-30': '25-30 triệu',
        '30-50': '30-50 triệu',
        '50+': 'trên 50 triệu'
    };
    return priceMap[priceRange] || priceRange;
}

/**
 * Chuyển đổi price range sang min/max VND
 */
function priceRangeToMinMax(priceRange) {
    const priceMap = {
        '0-5': { min: 0, max: 5_000_000 },
        '5-10': { min: 5_000_000, max: 10_000_000 },
        '10-15': { min: 10_000_000, max: 15_000_000 },
        '15-20': { min: 15_000_000, max: 20_000_000 },
        '20-25': { min: 20_000_000, max: 25_000_000 },
        '25-30': { min: 25_000_000, max: 30_000_000 },
        '30-50': { min: 30_000_000, max: 50_000_000 },
        '50+': { min: 50_000_000, max: Number.MAX_SAFE_INTEGER }
    };
    return priceMap[priceRange] || { min: null, max: null };
}

/**
 * Tạo HTML cho một thẻ sản phẩm 
 */
function createProductCardHTML(productData) {
    // productData giờ có 'rating_count'
    const isSemanticResult = productData && productData.hasOwnProperty('product') && productData.hasOwnProperty('score');
    
    let product = null;
    let docId = productData ? productData._id : null;
    let score = null;

    if (isSemanticResult) {
        product = productData.product;
        score = productData.score;
    } else {
        product = productData;
    }

    if (!product || !docId) {
        console.error("Dữ liệu không hợp lệ:", productData);
        return `<div class="product-card error-card"><p>Lỗi</p></div>`;
    }

    // === TÍNH TOÁN SAO THẬT ===
    const ratingCount = product.rating_count || 0; // Lấy rating_count
    const rating = calculateRatingFromCount(ratingCount); // Tính toán
    const starsHTML = createStarRating(rating); // Vẽ sao
    // ===========================

    return `
        <div class="product-card" data-doc-id="${docId}" tabindex="0" title="${product.name || 'Sản phẩm'}">
            <div class="card-image-container">
                <img src="${product.image_url || 'placeholder.png'}" alt="${product.name || 'N/A'}" loading="lazy" onerror="this.onerror=null; this.src='placeholder.png';">
            </div>
            <div class="card-content">
                <h4>${product.name || 'N/A'}</h4>
                <span class="category">${product.category || 'N/A'}</span>
                ${starsHTML} <div class="card-footer">
                    <span class="price">${product.price ? formatter.format(product.price) : 'Liên hệ'}</span>
                    <button class="btn-detail" aria-label="Chi tiết ${product.name || ''}">Chi tiết</button>
                </div>
            </div>
            ${score ? `<div class="reco-score" title="Độ tương đồng: ${(score * 100).toFixed(1)}%">${(score * 100).toFixed(0)}%</div>` : ''}
            <div class="click-count" title="Lượt xem chi tiết">${ratingCount} <i class="fas fa-eye"></i></div>
        </div>
    `;
}

/**
 * Hiển thị sản phẩm 
 */
function displayProducts(products, gridElement, messageElement, append = false) {
    if (!append) gridElement.innerHTML = '';
    if (messageElement) messageElement.textContent = '';
    
    if (!append && gridElement === productGrid) {
        const loadingMsg = gridElement.querySelector('p.message');
        if (loadingMsg) loadingMsg.remove();
    }
    
    if (!products || products.length === 0) {
        if (!append) {
            const noProductMsg = 'Không có kết quả tìm kiếm.';
            if (messageElement) messageElement.textContent = noProductMsg;
            gridElement.innerHTML = `<p class="message">${noProductMsg}</p>`;
        }
        return;
    }

    const cardsHTML = products.map(productData => {
         if(productData && productData._id) { return createProductCardHTML(productData); }
         else { console.warn("Dữ liệu không hợp lệ:", productData); return ''; }
    }).join('');
    
    gridElement.insertAdjacentHTML('beforeend', cardsHTML);
    // Gắn listener 1 lần cho grid
    addCardClickListeners(gridElement); 
}

/**
 * Gọi API lấy sản phẩm
 */
async function fetchProducts(category = null, page = 1, grid = productGrid, section = allProductsSection, msg = null, btn = loadMoreProductsBtn) {
    if (isLoading) return; 
    isLoading = true;
    if (page === 1) grid.innerHTML = '<p class="message"><i class="fas fa-spinner fa-spin"></i> Đang tải...</p>';
    else { btn.textContent = 'Đang tải...'; btn.disabled = true; }
    if (section) section.style.display = 'block';
    if(grid !== keywordResultsGrid) keywordResultsSection.style.display = 'none';
    if(grid !== semanticSuggestionsGrid) semanticSuggestionsSection.style.display = 'none';
    if(grid !== productGrid) allProductsSection.style.display = 'none';
    try {
        const params = new URLSearchParams({ page: page, size: RESULTS_PER_PAGE });
        if (category) params.append('category', category);
        const url = `${API_URL}/products?${params.toString()}`;
        const response = await fetch(url);
        if (!response.ok) throw await createApiError(response, 'Không tải được sản phẩm');
        
        // Đọc response 
        const result = await response.json(); 
        
        displayProducts(result.data, grid, msg, page > 1);
        
        const totalLoaded = (page * RESULTS_PER_PAGE);
        if (totalLoaded < result.total) btn.style.display = 'block';
        else btn.style.display = 'none';
        
        if (category && grid === keywordResultsGrid) {
            keywordResultsTitle.textContent = `Sản phẩm thuộc loại "${category}" (Tìm thấy ${result.total} sản phẩm)`;
        }
    } catch (error) {
        console.error('Lỗi khi tải sản phẩm:', error);
        const errorMsg = `❌ ${error.message}.`;
        if (msg) msg.textContent = errorMsg;
        else if (page === 1) grid.innerHTML = `<p class="message error">${errorMsg}</p>`;
        btn.style.display = 'none';
    } finally {
       isLoading = false;
        btn.textContent = 'Tải thêm';
        btn.disabled = false;
    } 
}

// --- Hàm fetchCategories, populateCategoryDropdown   ---
async function fetchCategories() {
    try {
        const response = await fetch(`${API_URL}/categories`);
        if (!response.ok) { console.warn(`Lỗi ${response.status} khi tải categories.`); allCategories = []; }
        else { allCategories = await response.json(); }
        populateCategoryDropdown();
    } catch (error) { console.error('Lỗi mạng khi tải categories:', error); }
}
function populateCategoryDropdown() {
    const selectedValue = categorySelect.value;
    categorySelect.innerHTML = '<option value="">-- Tất cả loại --</option>';
    allCategories.forEach(category => {
        const option = document.createElement('option');
        option.value = category; option.textContent = category;
        categorySelect.appendChild(option);
    });
    if (allCategories.includes(selectedValue)) { categorySelect.value = selectedValue; }
}

/**
 * Gọi API tìm kiếm keyword  
 */
async function fetchKeywordSearch(queryText, category, priceMin = null, priceMax = null) {
    keywordResultsGrid.innerHTML = '<p class="message"><i class="fas fa-spinner fa-spin"></i> Đang tìm theo từ khóa...</p>';
    keywordMessage.textContent = '';
    keywordResultsTitle.textContent = `Kết quả khớp từ khóa cho "${queryText}"`+ (category ? ` trong "${category}"` : '');
    keywordResultsSection.style.display = 'block';
    try {
        const params = new URLSearchParams({ query: queryText, size: RESULTS_PER_PAGE, page: 1 });
        if (category) params.append('category', category);
        if (priceMin !== null) params.append('price_min', priceMin);
        if (priceMax !== null) params.append('price_max', priceMax);
        const url = `${API_URL}/search-keyword?${params.toString()}`;
        const response = await fetch(url);
        if (!response.ok) throw await createApiError(response, 'Tìm kiếm từ khóa thất bại');
        
        const results = await response.json(); 
        
        displayProducts(results, keywordResultsGrid, keywordMessage, false);
    } catch (error) {
        console.error('Lỗi khi tìm kiếm keyword:', error);
        keywordResultsGrid.innerHTML = '';
        keywordMessage.textContent = `❌ ${error.message}.`;
    }
}

/**
 * Gọi API lấy gợi ý semantic  
 */
async function fetchSemanticSuggestions(queryText, category, priceMin = null, priceMax = null) {
    semanticSuggestionsGrid.innerHTML = '<p class="message"><i class="fas fa-spinner fa-spin"></i> Đang tìm gợi ý...</p>';
    semanticMessage.textContent = '';
    semanticTitle.textContent = 'Gợi ý liên quan (Semantic)';
    semanticSuggestionsSection.style.display = 'block';
    try {
        const params = new URLSearchParams({ query: queryText });
        if (category) params.append('category', category);
        if (priceMin !== null) params.append('price_min', priceMin);
        if (priceMax !== null) params.append('price_max', priceMax);
        const url = `${API_URL}/search-semantic-suggestions?${params.toString()}`;
        const response = await fetch(url);
        if (!response.ok) throw await createApiError(response, 'Lấy gợi ý thất bại');
        
        const suggestions = await response.json(); 
        
        displayProducts(suggestions, semanticSuggestionsGrid, semanticMessage, false);
    } catch (error) {
        console.error('Lỗi khi lấy gợi ý semantic:', error);
        semanticSuggestionsGrid.innerHTML = '';
        semanticMessage.textContent = `❌ ${error.message}.`;
    }
}


/**
 * Gọi API lấy chi tiết sản phẩm và gợi ý 
 */
async function fetchProductDetailsAndRecommendations(docId) {
    modalContent.innerHTML = '<p class="message"><i class="fas fa-spinner fa-spin"></i> Đang tải...</p>';
    modalRecoList.innerHTML = '<p class="message"><i class="fas fa-spinner fa-spin"></i> Đang tải...</p>';
    modalTitle.textContent = 'Đang tải...';
    MicroModal.show('product-modal', {
          onShow: (modal) => { const c = modal.querySelector('.modal-container'); if(c) c.scrollTop = 0; },
    });
    try {
        const response = await fetch(`${API_URL}/recommend/${docId}`);
        if (!response.ok) throw await createApiError(response, 'Lỗi tải chi tiết/gợi ý');
        const data = await response.json();
        const product = data.original_product;
        const recommendations = data.recommendations;
        
        if (!product) throw new Error("Không có dữ liệu sản phẩm gốc.");
        
        // === TÍNH SAO THẬT CHO SẢN PHẨM GỐC ===
        const productRatingCount = product.rating_count || 0;
        const productRating = calculateRatingFromCount(productRatingCount);
        const productStarsHTML = createStarRating(productRating);
        // ======================================

        // === BẮT ĐẦU SỬA (Thêm 2 dòng này) ===
        // 1. Lấy mô tả gốc
        const originalDescription = product.description || 'Không có.';
        // 2. Định dạng lại, thay ", " bằng thẻ <br> (xuống hàng)
        const formattedDescription = originalDescription.replace(/; /g, "<br>");
        // === KẾT THÚC SỬA ===

        modalTitle.textContent = product.name || 'Chi tiết';
        
        // 3. Dùng "formattedDescription" đã được dọn dẹp ở đây
        modalContent.innerHTML = `<img src="${product.image_url || 'placeholder.png'}" alt="${product.name || 'N/A'}" onerror="this.onerror=null; this.src='placeholder.png';"><h3>${product.name || 'N/A'}</h3><div class="category">Loại: ${product.category || 'N/A'}</div>${productStarsHTML}<div class="price">${product.price ? formatter.format(product.price) : 'Liên hệ'}</div><h4>Mô tả</h4><p class="description">${formattedDescription}</p>`;
        
        if (recommendations && recommendations.length > 0) {
            modalRecoList.innerHTML = '';
            recommendations.forEach(item => {
                const recoProduct = item.product; 
                const recoDocId = item._id;
                if (!recoProduct) { console.warn("Lỗi gợi ý:", item); return; }
                
                // === TÍNH SAO THẬT CHO SẢN PHẨM GỢI Ý ===
                const recoRatingCount = recoProduct.rating_count || 0;
                const recoRating = calculateRatingFromCount(recoRatingCount);
                const recoStarsHTML = createStarRating(recoRating);
                // =========================================

                modalRecoList.insertAdjacentHTML('beforeend',
`<div class="reco-card-modal" data-doc-id="${recoDocId}" tabindex="0" title="${recoProduct.name || 'Sản phẩm'} - Độ tương đồng: ${(item.score * 100).toFixed(1)}%">
                        <img src="${recoProduct.image_url || 'placeholder.png'}" alt="${recoProduct.name || 'N/A'}" loading="lazy" onerror="this.onerror=null; this.src='placeholder.png';">
                        <div class="reco-card-modal-info">
                            <p>${recoProduct.name || 'N/A'}</p>
                            ${recoStarsHTML}
                        </div>
                        <div class="reco-card-modal-clicks">${recoRatingCount} <i class="fas fa-eye"></i></div>
                    </div>`
                );
            });
            addModalRecoClickListeners(modalRecoList);
        } else { modalRecoList.innerHTML = '<p class="message">Không có gợi ý.</p>'; }
    } catch (error) {
        console.error('Lỗi fetch chi tiết/gợi ý:', error);
        modalTitle.textContent = 'Lỗi';
        modalContent.innerHTML = `<p class="message error">❌ ${error.message}.</p>`;
        modalRecoList.innerHTML = '<p class="message error">❌ Lỗi tải gợi ý.</p>';
    }
}

/**
 * Xử lý lỗi từ API response  
 */
async function createApiError(response, defaultMessage = 'Có lỗi xảy ra') {
    let detail = defaultMessage;
    try {
        const contentType = response.headers.get("content-type");
        if (contentType && contentType.indexOf("application/json") !== -1) {
            const errData = await response.json(); detail = errData.detail || errData.message || detail;
        } else { detail = await response.text() || detail; }
    } catch (e) { console.warn("Không thể parse lỗi:", e); }
    const statusText = response.statusText ? ` (${response.statusText})` : '';
    return new Error(`Lỗi API ${response.status}${statusText}: ${detail}`);
}

/**
 * === HÀM MỚI: GỬI LOG CLICK LÊN SERVER ===
 */
function logProductClick(docId) {
    // console.log("Logging click cho:", docId); // Debug
    fetch(`${API_URL}/log-click`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ product_id: docId })
    })
    .catch(error => console.error('Lỗi khi log click:', error));
}


/**
 * Thêm event listener cho các thẻ sản phẩm
 */
function addCardClickListeners(gridElement) {
    if (!gridElement || gridElement.dataset.listenerAttached === 'true') {
        return;
    }
    gridElement.dataset.listenerAttached = 'true';

    gridElement.addEventListener('click', (event) => {
        const card = event.target.closest('.product-card');
        if (!card) return;
        const docId = card.dataset.docId;
        const isDetailButtonClick = event.target.classList.contains('btn-detail') || event.target.closest('.btn-detail');
        
        if (docId && isDetailButtonClick) {
            // === GỬI LOG KHI CLICK ===
            logProductClick(docId);
            // Cập nhật giao diện ngay
            const countEl = card.querySelector('.click-count');
            if (countEl) {
                const currentCount = parseInt(countEl.textContent, 10) || 0;
                countEl.innerHTML = `${currentCount + 1} <i class="fas fa-eye"></i>`;
            }
            // ========================
            fetchProductDetailsAndRecommendations(docId);
        }
    });
    
    gridElement.addEventListener('keydown', (event) => {
        if (event.key === 'Enter' || event.key === ' ') {
            const card = event.target.closest('.product-card');
            if (card) {
                event.preventDefault();
                const docId = card.dataset.docId;
                if(docId) {
                    logProductClick(docId); // Gửi log
                    fetchProductDetailsAndRecommendations(docId);
                }
            }
        }
    });
}

/**
 * Thêm event listener cho các thẻ gợi ý trong modal
 */
function addModalRecoClickListeners(listElement) {
     if (!listElement || listElement.dataset.recoListenerBound === 'true') return;
     listElement.dataset.recoListenerBound = 'true';
     
    listElement.addEventListener('click', (event) => {
        const card = event.target.closest('.reco-card-modal');
        if (!card) return;
        const docId = card.dataset.docId;
        if (docId) {
            logProductClick(docId); // Gửi log
            MicroModal.close('product-modal');
            setTimeout(() => { fetchProductDetailsAndRecommendations(docId); }, 150);
        }
    });
    
    listElement.addEventListener('keydown', (event) => {
        if (event.key === 'Enter' || event.key === ' ') {
            const card = event.target.closest('.reco-card-modal');
            if (card) {
                event.preventDefault();
                const docId = card.dataset.docId;
                if(docId) {
                    logProductClick(docId); // Gửi log
                    MicroModal.close('product-modal');
                    setTimeout(() => fetchProductDetailsAndRecommendations(docId), 150);
                }
            }
        }
    });
}


// --- INITIALIZATION   ---
document.addEventListener('DOMContentLoaded', () => {
    // Khởi tạo Micromodal
    try {
        MicroModal.init({
             closeTrigger: 'data-micromodal-close',
             disableScroll: true,
             disableFocus: false,
             awaitOpenAnimation: false,
             awaitCloseAnimation: true,
             debugMode: false
        });
    } catch (e) { console.error("Micromodal init error:", e); }

    // === LOGIC CHUYỂN TAB ===
    navTabApp.addEventListener('click', () => {
        navTabApp.classList.add('active');
        navTabDoc.classList.remove('active');
        appContent.classList.add('active');
        docContent.classList.remove('active');
    });
    navTabDoc.addEventListener('click', () => {
        navTabDoc.classList.add('active');
        navTabApp.classList.remove('active');
        docContent.classList.add('active');
        appContent.classList.remove('active');
    });
    document.getElementById('home-link-app').addEventListener('click', (e) => {
        e.preventDefault();
        currentProductPage = 1;
        fetchProducts(null, 1);
        searchInput.value = '';
        categorySelect.value = '';
    });

    // Tải categories và sản phẩm ban đầu
    fetchCategories();
    currentProductPage = 1;
    fetchProducts(null, currentProductPage);

    // --- SỰ KIỆN SUBMIT FORM ---
    searchForm.addEventListener('submit', (e) => {
        e.preventDefault();
        const query = searchInput.value.trim();
        const category = categorySelect.value;
        allProductsSection.style.display = 'none';
        loadMoreProductsBtn.style.display = 'none';
        currentProductPage = 1; 

        if (query) {
            fetchKeywordSearch(query, category);
            fetchSemanticSuggestions(query, category);
        }
        else if (!query && category) {
            keywordResultsTitle.textContent = `Sản phẩm thuộc loại "${category}"`;
            keywordResultsSection.style.display = 'block';
            semanticSuggestionsSection.style.display = 'none';
            // Tạo một nút giả để truyền vào
            const fakeBtn = document.createElement('button');
            fakeBtn.style.display = 'none';
            document.body.appendChild(fakeBtn); // Thêm vào DOM để tránh lỗi
            fetchProducts(category, 1, keywordResultsGrid, keywordResultsSection, keywordMessage, fakeBtn);
        }
        else {
            fetchProducts(null, currentProductPage);
        }
    });

     // --- SỰ KIỆN NÚT TẢI THÊM ---
     loadMoreProductsBtn.addEventListener('click', () => {
        if (!isLoading) {
            currentProductPage++;
            fetchProducts(null, currentProductPage, productGrid, allProductsSection, null, loadMoreProductsBtn);
        }
     });

     // --- SỰ KIỆN LỌC GIÁ (DISABLED) ---
     // Functionality disabled - price filtering now done through search query text
     // Users can type "dưới 5 triệu", "5-10 triệu", etc. in the search box to filter by price
     // Buttons remain visible in UI but don't have active event handlers
     /*
     document.querySelectorAll('.price-btn:not(.clear-btn)').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();
            const priceRange = btn.getAttribute('data-price-range');
            
            // Xóa trạng thái active của tất cả nút
            document.querySelectorAll('.price-btn').forEach(b => b.classList.remove('active'));
            
            // Đặt trạng thái active cho nút được click
            btn.classList.add('active');
            
            // Lưu bộ lọc giá hiện tại
            currentPriceFilter = priceRange;
            
            // Chuyển đổi price range sang min/max values
            const priceValues = priceRangeToMinMax(priceRange);
            const priceDisplay = priceRangeToQuery(priceRange);
            
            // Hiển thị price range trong search box (cho thông tin)
            searchInput.value = priceDisplay;
            categorySelect.value = ''; // Xóa category filter
            
            // Thực hiện tìm kiếm với price parameters (không text trong query)
            allProductsSection.style.display = 'none';
            loadMoreProductsBtn.style.display = 'none';
            currentProductPage = 1;
            // Sử dụng empty string '' cho query và truyền min/max values
            fetchKeywordSearch('', '', priceValues.min, priceValues.max);
            fetchSemanticSuggestions('', '', priceValues.min, priceValues.max);
        });
     });
     
     // --- NÚT XÓA LỌC GIÁ ---
     const clearPriceBtn = document.getElementById('clear-price-filter');
     if (clearPriceBtn) {
        clearPriceBtn.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();
            document.querySelectorAll('.price-btn').forEach(b => b.classList.remove('active'));
            currentPriceFilter = null;
            
            // Xóa query và reload danh sách
            searchInput.value = '';
            categorySelect.value = '';
            keywordResultsSection.style.display = 'none';
            semanticSuggestionsSection.style.display = 'none';
            allProductsSection.style.display = 'block';
            currentProductPage = 1;
            fetchProducts(null, currentProductPage);
        });
     }
     */

     // --- CÁC SỰ KIỆN KHÁC ---
     categorySelect.addEventListener('change', () => {
         if (categorySelect.value === '' && searchInput.value.trim() === '') {
             currentProductPage = 1;
             fetchProducts(null, currentProductPage);
         }
     });
    searchInput.addEventListener('input', () => {
        if (searchInput.value.trim() === '') {
             keywordResultsSection.style.display = 'none';
             semanticSuggestionsSection.style.display = 'none';
             allProductsSection.style.display = 'block';
             if (currentProductPage > 1) {
                currentProductPage = 1;
                fetchProducts(null, currentProductPage);
             }
        }
    });
    
    // Gắn listener 1 lần
    addCardClickListeners(productGrid);
    addCardClickListeners(keywordResultsGrid);
    addCardClickListeners(semanticSuggestionsGrid);
});