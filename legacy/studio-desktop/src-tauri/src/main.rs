// Vajra AI Studio desktop shell.
//
// Renders the Studio UI and can start / stop the local Vajra Core (`vajra-api`)
// as a managed sidecar so the user does not have to run it by hand.
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::sync::Mutex;
use tauri::Manager;
use tauri_plugin_shell::process::{CommandChild, CommandEvent};
use tauri_plugin_shell::ShellExt;

#[derive(Default)]
struct CoreProcess(Mutex<Option<CommandChild>>);

#[tauri::command]
async fn start_core(app: tauri::AppHandle) -> Result<String, String> {
    let state = app.state::<CoreProcess>();
    if state.0.lock().unwrap().is_some() {
        return Ok("already running".into());
    }
    let (mut rx, child) = app
        .shell()
        .command("vajra-api")
        .spawn()
        .map_err(|e| e.to_string())?;

    tauri::async_runtime::spawn(async move {
        while let Some(event) = rx.recv().await {
            if let CommandEvent::Stdout(line) | CommandEvent::Stderr(line) = event {
                println!("[vajra-core] {}", String::from_utf8_lossy(&line));
            }
        }
    });

    *state.0.lock().unwrap() = Some(child);
    Ok("started".into())
}

#[tauri::command]
fn stop_core(app: tauri::AppHandle) -> Result<(), String> {
    if let Some(child) = app.state::<CoreProcess>().0.lock().unwrap().take() {
        let _ = child.kill();
    }
    Ok(())
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .manage(CoreProcess::default())
        .invoke_handler(tauri::generate_handler![start_core, stop_core])
        .run(tauri::generate_context!())
        .expect("error while running Vajra AI Studio");
}
