export const CONFIG = {
    TOKEN_KEY: "auth_token",
    USER_DB: "all_users",
    LOGIN_KEY: "login_user",
    HISTORY_KEY: "user_history_",
    LAND_INFO_KEY: "land_info_",
    THEME_KEY: "app_theme",
    DETECT_CONFIG_KEY: "detect_config",
    get API_BASE_URL() {
        const hostname = window.location.hostname;
        // file:// 协议或空 host 时默认指向本地后端
        if (!hostname || hostname === '') return 'http://localhost:8000';
        const port = (hostname === 'localhost' || hostname === '127.0.0.1') ? '8000' : window.location.port;
        return `${window.location.protocol}//${hostname}${port ? ':' + port : ''}`;
    },
    REQUEST_TIMEOUT: 120000,  // 2分钟，多模型对比推理需要更长时间
    MAX_FILE_SIZE: 10 * 1024 * 1024,
    BATCH_CONCURRENCY: 3,
    ACCEPTED_IMAGE_TYPES: ['image/jpeg', 'image/png', 'image/tiff', 'image/tif', 'image/bmp'],
    GUEST_QUOTA_KEY: "guest_detect_quota",
    GUEST_MAX_QUOTA: 3
};