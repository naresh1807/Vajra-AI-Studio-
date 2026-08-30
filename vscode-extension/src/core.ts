/** Detects the local Vajra Core and, if it's down, starts it (`vajra-api`).
 *  Streams its output to an "Vajra Core" channel and stops it on shutdown. */
import * as vscode from "vscode";
import * as os from "os";
import * as fs from "fs";
import * as path from "path";
import { ChildProcess, spawn } from "child_process";
import { VajraClient } from "./client";

export class CoreManager {
  private proc?: ChildProcess;
  private startedByUs = false;
  private readonly out: vscode.OutputChannel;
  private readonly _onState = new vscode.EventEmitter<"up" | "starting" | "down">();
  readonly onState = this._onState.event;

  constructor(private readonly client: VajraClient) {
    this.out = vscode.window.createOutputChannel("Vajra Core");
  }

  private cfg<T>(key: string, def: T): T {
    return vscode.workspace.getConfiguration("vajra").get<T>(key, def);
  }

  async isUp(): Promise<boolean> {
    try {
      return (await this.client.health()).status === "ok";
    } catch {
      return false;
    }
  }

  /** For a same-machine Core with no configured token, read its device secret. */
  private loadLocalSecret(cwd: string): void {
    if (vscode.workspace.getConfiguration("vajra").get<string>("pairingToken", "")) return;
    for (const dir of [cwd, path.join(cwd, ".."), process.cwd()]) {
      try {
        const j = JSON.parse(fs.readFileSync(path.join(dir, "data", "device.json"), "utf8"));
        if (j.device_secret) {
          this.client.setToken(j.device_secret);
          this.out.appendLine("[using the local device secret from data/device.json]");
          return;
        }
      } catch {
        /* keep looking */
      }
    }
  }

  /** Called on activation. Returns once the Core is reachable, or gives up. */
  async ensureRunning(): Promise<boolean> {
    const cwd =
      vscode.workspace.getConfiguration("vajra").get<string>("coreCwd", "").trim() ||
      vscode.workspace.workspaceFolders?.[0]?.uri.fsPath ||
      os.homedir();
    this.loadLocalSecret(cwd);
    if (await this.isUp()) {
      this._onState.fire("up");
      return true;
    }
    if (!this.cfg("autoStartCore", true)) {
      this._onState.fire("down");
      return false;
    }
    return this.start();
  }

  async start(): Promise<boolean> {
    if (this.proc) return true;
    if (await this.isUp()) {
      this._onState.fire("up");
      return true;
    }
    this._onState.fire("starting");

    const command = this.cfg("coreCommand", "vajra-api").trim() || "vajra-api";
    const cwd =
      this.cfg("coreCwd", "").trim() ||
      vscode.workspace.workspaceFolders?.[0]?.uri.fsPath ||
      os.homedir();
    const [file, ...args] = command.split(" ");

    this.out.appendLine(`$ ${command}   (cwd: ${cwd})`);
    try {
      this.proc = spawn(file, args, { cwd, shell: true, env: process.env });
    } catch (e) {
      this.out.appendLine(`failed to spawn: ${e}`);
      this.failHint();
      this._onState.fire("down");
      return false;
    }
    this.startedByUs = true;
    this.proc.stdout?.on("data", (d) => this.out.append(d.toString()));
    this.proc.stderr?.on("data", (d) => this.out.append(d.toString()));
    this.proc.on("exit", (code) => {
      this.out.appendLine(`\n[vajra-api exited ${code}]`);
      this.proc = undefined;
      this._onState.fire("down");
      if (code && this.startedByUs) this.failHint();
    });

    // poll health
    for (let i = 0; i < 40; i++) {
      await new Promise((r) => setTimeout(r, 1000));
      if (!this.proc) return false; // exited
      this.loadLocalSecret(cwd);
      if (await this.isUp()) {
        this.out.appendLine("[Vajra Core is up]");
        this._onState.fire("up");
        void this.checkCrashRecovery();
        return true;
      }
    }
    this.out.appendLine("[timed out waiting for the Core]");
    this._onState.fire("down");
    return false;
  }

  async stop(): Promise<void> {
    if (!this.proc?.pid) return;
    const pid = this.proc.pid;
    this.proc = undefined;
    if (process.platform === "win32") {
      spawn("taskkill", ["/pid", String(pid), "/T", "/F"]);
    } else {
      try {
        process.kill(-pid, "SIGTERM");
      } catch {
        process.kill(pid, "SIGTERM");
      }
    }
  }

  async restart(): Promise<void> {
    await this.stop();
    await new Promise((r) => setTimeout(r, 800));
    await this.start();
  }

  show(): void {
    this.out.show();
  }

  /** P30: on connect, surface any task that didn't finish last session. */
  private async checkCrashRecovery(): Promise<void> {
    const { interrupted } = await this.client.interrupted();
    if (!interrupted.length) return;
    const t = interrupted[0];
    const root = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
    const pick = await vscode.window.showWarningMessage(
      `A Vajra task did not finish last session: "${t.goal}" (${t.changed_files.length} files changed).`,
      "Review changes",
      "Roll back",
      "Dismiss",
    );
    if (pick === "Review changes") {
      void vscode.commands.executeCommand("workbench.view.scm");
    } else if (pick === "Roll back" && root) {
      const cps = await this.client.gitCheckpoints(root).catch(() => [] as Array<{ ref: string; label: string }>);
      const c = await vscode.window.showQuickPick(
        cps.map((x) => ({ label: x.label || x.ref, ref: x.ref })),
        { placeHolder: "Restore the project to which checkpoint?" },
      );
      if (c) {
        await this.client.gitRollback(root, c.ref);
        void vscode.window.showInformationMessage(`Rolled back to ${c.label || c.ref}`);
      }
    }
  }

  private failHint(): void {
    void vscode.window
      .showErrorMessage(
        "Couldn't start the Vajra Core. Install it (`pip install -e \".[dev]\"` in the Vajra repo) " +
          "or set `vajra.coreCommand` / `vajra.coreCwd`.",
        "Open Settings",
        "Show Log",
      )
      .then((pick) => {
        if (pick === "Open Settings")
          void vscode.commands.executeCommand("workbench.action.openSettings", "vajra.core");
        else if (pick === "Show Log") this.show();
      });
  }

  dispose(): void {
    if (this.startedByUs) void this.stop();
    this.out.dispose();
    this._onState.dispose();
  }
}
