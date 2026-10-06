use std::borrow::Cow;
use std::fs;
use std::io::Write;
use std::path::{Component, Path, PathBuf};

use tauri::Manager;

/// Personal data stays in the configured local vault, never in bundled resources.
fn scoped_path(root: &Path, requested: &Path) -> Result<PathBuf, String> {
    if requested
        .components()
        .any(|part| matches!(part, Component::ParentDir))
        || !requested.starts_with(root)
    {
        return Err("path is outside configured vault".into());
    }
    let canonical_root = root.canonicalize().map_err(|err| err.to_string())?;
    let mut existing = requested;
    while !existing.exists() {
        existing = existing.parent().ok_or("invalid path")?;
    }
    let canonical_existing = existing.canonicalize().map_err(|err| err.to_string())?;
    if !canonical_existing.starts_with(&canonical_root) {
        return Err("path resolves outside configured vault".into());
    }
    Ok(requested.to_path_buf())
}

fn user_path(app: &tauri::AppHandle, requested: &str) -> Result<PathBuf, String> {
    let raw = get_config(app.clone())?;
    let config: serde_json::Value = serde_json::from_str(&raw).map_err(|err| err.to_string())?;
    let root = config
        .get("vaultDir")
        .and_then(|value| value.as_str())
        .ok_or("configure vaultDir first")?;
    scoped_path(Path::new(root), Path::new(requested))
}

#[tauri::command]
fn read_text(app: tauri::AppHandle, path: String) -> Result<String, String> {
    fs::read_to_string(user_path(&app, &path)?).map_err(|err| err.to_string())
}

#[tauri::command]
fn file_exists(app: tauri::AppHandle, path: String) -> bool {
    user_path(&app, &path)
        .map(|file| file.is_file())
        .unwrap_or(false)
}

#[tauri::command]
fn write_text(app: tauri::AppHandle, path: String, contents: String) -> Result<(), String> {
    let file = user_path(&app, &path)?;
    if let Some(parent) = file.parent() {
        fs::create_dir_all(parent).map_err(|err| err.to_string())?;
    }
    fs::write(file, contents).map_err(|err| err.to_string())
}

#[tauri::command]
fn append_line(app: tauri::AppHandle, path: String, line: String) -> Result<(), String> {
    let file = user_path(&app, &path)?;
    if let Some(parent) = file.parent() {
        fs::create_dir_all(parent).map_err(|err| err.to_string())?;
    }
    let mut file = fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(file)
        .map_err(|err| err.to_string())?;
    writeln!(file, "{}", line).map_err(|err| err.to_string())
}

fn config_path(app: &tauri::AppHandle) -> Result<PathBuf, String> {
    let dir = app.path().app_config_dir().map_err(|err| err.to_string())?;
    fs::create_dir_all(&dir).map_err(|err| err.to_string())?;
    Ok(dir.join("wenshu-config.json"))
}

#[tauri::command]
fn get_config(app: tauri::AppHandle) -> Result<String, String> {
    let path = config_path(&app)?;
    if path.exists() {
        fs::read_to_string(path).map_err(|err| err.to_string())
    } else {
        let vault = app
            .path()
            .app_data_dir()
            .map_err(|err| err.to_string())?
            .join("vault");
        fs::create_dir_all(&vault).map_err(|err| err.to_string())?;
        let raw = serde_json::json!({ "vaultDir": vault }).to_string();
        fs::write(path, &raw).map_err(|err| err.to_string())?;
        Ok(raw)
    }
}

#[tauri::command]
fn set_config(app: tauri::AppHandle, contents: String) -> Result<(), String> {
    let config: serde_json::Value =
        serde_json::from_str(&contents).map_err(|err| err.to_string())?;
    if !config.is_object() {
        return Err("config must be a JSON object".into());
    }
    for field in ["vaultDir", "webVaultDir"] {
        if let Some(value) = config.get(field) {
            let dir = value.as_str().ok_or("vault paths must be strings")?;
            if !Path::new(dir).is_absolute() || !Path::new(dir).is_dir() {
                return Err(format!("{field} must be an existing absolute directory"));
            }
        }
    }
    let path = config_path(&app)?;
    fs::write(path, contents).map_err(|err| err.to_string())
}

/// 用系统默认浏览器打开 http(s)，不要在应用 WebView 里加载外网页面。
#[tauri::command]
fn open_external(url: String) -> Result<(), String> {
    if !url.starts_with("http://") && !url.starts_with("https://") {
        return Err("unsupported url".into());
    }
    if url.chars().any(|ch| ch.is_control() || ch == '"') {
        return Err("invalid url".into());
    }

    #[cfg(target_os = "windows")]
    {
        fn to_wide(text: &str) -> Vec<u16> {
            text.encode_utf16().chain(std::iter::once(0)).collect()
        }

        #[link(name = "shell32")]
        extern "system" {
            fn ShellExecuteW(
                hwnd: *mut core::ffi::c_void,
                lp_operation: *const u16,
                lp_file: *const u16,
                lp_parameters: *const u16,
                lp_directory: *const u16,
                n_show_cmd: i32,
            ) -> isize;
        }

        let operation = to_wide("open");
        let file = to_wide(&url);
        let result = unsafe {
            ShellExecuteW(
                std::ptr::null_mut(),
                operation.as_ptr(),
                file.as_ptr(),
                std::ptr::null(),
                std::ptr::null(),
                1,
            )
        };
        if result <= 32 {
            return Err(format!("failed to open url ({result})"));
        }
    }
    #[cfg(target_os = "macos")]
    {
        std::process::Command::new("open")
            .arg(&url)
            .spawn()
            .map_err(|err| err.to_string())?;
    }
    #[cfg(all(unix, not(target_os = "macos")))]
    {
        std::process::Command::new("xdg-open")
            .arg(&url)
            .spawn()
            .map_err(|err| err.to_string())?;
    }
    Ok(())
}

fn vault_mime(path: &Path) -> &'static str {
    let ext = path
        .extension()
        .and_then(|ext| ext.to_str())
        .unwrap_or("")
        .to_ascii_lowercase();
    match ext.as_str() {
        "png" => "image/png",
        "jpg" | "jpeg" => "image/jpeg",
        "webp" => "image/webp",
        "gif" => "image/gif",
        "svg" => "image/svg+xml",
        "pdf" => "application/pdf",
        "json" => "application/json",
        "md" | "txt" => "text/plain; charset=utf-8",
        "html" => "text/html; charset=utf-8",
        _ => "application/octet-stream",
    }
}

/// vault 静态内容根目录：配置里的 webVaultDir 优先（本机直读 public/vault，
/// 新论文同步后无需重装应用），否则回退安装包资源目录。
fn web_vault_dir(app: &tauri::AppHandle) -> Option<PathBuf> {
    if let Ok(path) = config_path(app) {
        if let Ok(raw) = fs::read_to_string(&path) {
            if let Ok(value) = serde_json::from_str::<serde_json::Value>(&raw) {
                if let Some(dir) = value.get("webVaultDir").and_then(|item| item.as_str()) {
                    let dir = PathBuf::from(dir);
                    if dir.is_dir() {
                        return Some(dir);
                    }
                }
            }
        }
    }
    app.path()
        .resource_dir()
        .ok()
        .map(|dir| dir.join("vault"))
        .filter(|dir| dir.is_dir())
}

fn vault_response(
    status: u16,
    mime: &str,
    body: Vec<u8>,
) -> tauri::http::Response<Cow<'static, [u8]>> {
    tauri::http::Response::builder()
        .status(status)
        .header("Content-Type", mime)
        .header("Access-Control-Allow-Origin", "*")
        .body(Cow::Owned(body))
        .expect("static response")
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        // vault 静态资源不再嵌进二进制（1GB+ 会把 rlib 撑爆），改走自定义协议从磁盘读：
        // 前端 http://vault.localhost/vault/... -> <webVaultDir>/...
        .register_uri_scheme_protocol("vault", |ctx, request| {
            let decoded = percent_encoding::percent_decode_str(request.uri().path())
                .decode_utf8()
                .map(|text| text.to_string())
                .unwrap_or_default();
            let rel = decoded.trim_start_matches('/');
            let rel = rel.strip_prefix("vault/").unwrap_or(rel);
            if rel.is_empty() || rel.split(['/', '\\']).any(|seg| seg == "..") {
                return vault_response(404, "text/plain", Vec::new());
            }
            let Some(root) = web_vault_dir(ctx.app_handle()) else {
                return vault_response(404, "text/plain", Vec::new());
            };
            let Ok(file) = scoped_path(&root, &root.join(rel)) else {
                return vault_response(404, "text/plain", Vec::new());
            };
            match fs::read(&file) {
                Ok(bytes) => vault_response(200, vault_mime(&file), bytes),
                Err(_) => vault_response(404, "text/plain", Vec::new()),
            }
        })
        .invoke_handler(tauri::generate_handler![
            read_text,
            file_exists,
            write_text,
            append_line,
            get_config,
            set_config,
            open_external
        ])
        .run(tauri::generate_context!())
        .expect("error while running wenshu app");
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn rejects_parent_and_outside_paths() {
        let root = std::env::temp_dir();
        assert!(scoped_path(&root, &root.join("../outside.md")).is_err());
        let outside = root.parent().unwrap();
        assert!(scoped_path(&root, outside).is_err());
    }

    #[test]
    fn permits_new_nested_file_inside_vault() {
        let root = std::env::temp_dir();
        let nested = root.join("wenshu-path-scope-test/nested/note.md");
        assert_eq!(scoped_path(&root, &nested).unwrap(), nested);
    }
}
