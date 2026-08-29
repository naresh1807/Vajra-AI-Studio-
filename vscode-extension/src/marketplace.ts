/** Extension gallery: switch between Open VSX and the Microsoft Marketplace at
 *  runtime (patches the app's product.json + restart), and a one-click installer
 *  for the popular AI coding extensions. */
import * as vscode from "vscode";
import * as fs from "fs";
import * as path from "path";

const GALLERIES: Record<string, Record<string, string>> = {
  openvsx: {
    serviceUrl: "https://open-vsx.org/vscode/gallery",
    itemUrl: "https://open-vsx.org/vscode/item",
    resourceUrlTemplate: "https://open-vsx.org/vscode/unpkg/{publisher}/{name}/{version}/{path}",
  },
  ms: {
    serviceUrl: "https://marketplace.visualstudio.com/_apis/public/gallery",
    itemUrl: "https://marketplace.visualstudio.com/items",
    resourceUrlTemplate: "https://{publisher}.vscode-unpkg.net/{publisher}/{name}/{version}/{path}",
    controlUrl: "https://main.vscode-cdn.net/extensions/marketplace.json",
    nlsBaseUrl: "https://www.vscode-unpkg.net/_lp/",
    publisherUrl: "https://marketplace.visualstudio.com/publishers",
  },
};

const AI_EXTENSIONS: Array<{ id: string; label: string; note: string }> = [
  { id: "anthropic.claude-code", label: "Claude Code", note: "Anthropic — needs the MS Marketplace" },
  { id: "GitHub.copilot", label: "GitHub Copilot", note: "needs the MS Marketplace" },
  { id: "GitHub.copilot-chat", label: "GitHub Copilot Chat", note: "needs the MS Marketplace" },
  { id: "openai.chatgpt", label: "ChatGPT / Codex", note: "OpenAI — needs the MS Marketplace" },
  { id: "google.geminicodeassist", label: "Gemini Code Assist", note: "needs the MS Marketplace" },
  { id: "Continue.continue", label: "Continue", note: "open-source, on Open VSX too" },
  { id: "Codeium.codeium", label: "Codeium / Windsurf", note: "on Open VSX too" },
  { id: "sourcegraph.cody-ai", label: "Sourcegraph Cody", note: "on Open VSX too" },
];

function productJsonPath(): string {
  return path.join(vscode.env.appRoot, "product.json");
}

export function registerMarketplace(ctx: vscode.ExtensionContext) {
  ctx.subscriptions.push(
    vscode.commands.registerCommand("vajra.setMarketplace", async () => {
      const pick = await vscode.window.showQuickPick(
        [
          { label: "Open VSX", detail: "Fully open. No Copilot / Claude Code / ChatGPT.", key: "openvsx" },
          {
            label: "Microsoft Marketplace",
            detail: "Copilot, Claude Code, ChatGPT, Gemini… Microsoft's ToU restrict it to MS products; they can rate-limit forks.",
            key: "ms",
          },
        ],
        { placeHolder: "Extension gallery for Vajra AI Studio" },
      );
      if (!pick) return;
      const file = productJsonPath();
      let product: any;
      try {
        product = JSON.parse(fs.readFileSync(file, "utf8"));
      } catch (e) {
        void vscode.window.showErrorMessage(`Can't read ${file}: ${e}`);
        return;
      }
      product.extensionsGallery = GALLERIES[pick.key];
      try {
        fs.writeFileSync(file, JSON.stringify(product, null, "\t") + "\n");
      } catch (e) {
        void vscode.window.showErrorMessage(
          `Can't write product.json (${e}). Run Studio as admin once, or re-run studio\\scripts\\set-marketplace.mjs.`,
        );
        return;
      }
      const r = await vscode.window.showInformationMessage(
        `Gallery set to ${pick.label}. Restart to apply.`,
        "Restart",
      );
      if (r === "Restart") void vscode.commands.executeCommand("workbench.action.reloadWindow");
    }),

    vscode.commands.registerCommand("vajra.installAIExtensions", async () => {
      const picks = await vscode.window.showQuickPick(
        AI_EXTENSIONS.map((x) => ({ label: x.label, description: x.id, detail: x.note, id: x.id })),
        { canPickMany: true, placeHolder: "Install AI coding extensions (some need the MS Marketplace — Vajra: Set Extension Gallery)" },
      );
      if (!picks?.length) return;
      for (const p of picks) {
        try {
          await vscode.commands.executeCommand("workbench.extensions.installExtension", p.id);
          void vscode.window.showInformationMessage(`Installed ${p.label}`);
        } catch (e) {
          void vscode.window.showWarningMessage(
            `Couldn't install ${p.label} (${p.id}) — it may need the Microsoft Marketplace. ${e}`,
          );
        }
      }
    }),
  );
}
