import type { Plugin, PluginInput, PluginOptions } from "@opencode-ai/plugin";
import { execSync } from "node:child_process";
import { join } from "node:path";
import { homedir } from "node:os";

// Path to parley.py. Override with the PARLEY_SCRIPT env var, otherwise
// defaults to ~/.opencode/scripts/parley.py
const SCRIPT =
  process.env.PARLEY_SCRIPT ||
  join(homedir(), ".opencode/scripts/parley.py");

function run(args: string, timeoutMs = 15000): string {
  try {
    return execSync(`python3 ${SCRIPT} ${args}`, {
      timeout: timeoutMs,
      encoding: "utf-8",
      maxBuffer: 1024 * 1024,
    }).trim();
  } catch (e: any) {
    const stderr = e.stderr?.toString() || "";
    const stdout = e.stdout?.toString() || "";
    return JSON.stringify({ error: stderr || stdout || e.message });
  }
}

export default (async (_input: PluginInput, _options?: PluginOptions) => {
  return {
    "tool.list": async () => {
      return [
        {
          name: "browser_list_tabs",
          description:
            "List all open browser tabs (Brave/Chrome via CDP). Returns tab IDs, titles, and URLs. Use this to find the tab ID for ChatGPT, Gemini, Claude, or any other web app.",
          parameters: {
            type: "object",
            properties: {},
            required: [],
          },
        },
        {
          name: "browser_read",
          description:
            "Read text content from a browser tab. Without selector, auto-detects the latest AI chat response (works with ChatGPT, Gemini, Claude). With CSS selector, reads that element. Returns text only (no images).",
          parameters: {
            type: "object",
            properties: {
              tab_id: { type: "string", description: "Tab ID from browser_list_tabs" },
              selector: { type: "string", description: "Optional CSS selector to read specific element" },
            },
            required: ["tab_id"],
          },
        },
        {
          name: "browser_send",
          description:
            "Type text and press Enter in a browser tab. Use this to send a message to ChatGPT, Gemini, Claude, or any web chat. Automatically finds the input field.",
          parameters: {
            type: "object",
            properties: {
              tab_id: { type: "string", description: "Tab ID from browser_list_tabs" },
              text: { type: "string", description: "Text to type and send" },
            },
            required: ["tab_id", "text"],
          },
        },
        {
          name: "browser_send_wait",
          description:
            "Send a message to an AI chat tab AND wait for the full streamed response before returning it. Recommended over browser_send when you need the reply - it will not return a half-written answer.",
          parameters: {
            type: "object",
            properties: {
              tab_id: { type: "string", description: "Tab ID from browser_list_tabs" },
              text: { type: "string", description: "Message to send" },
              timeout_ms: { type: "number", description: "Max wait in ms (default: 60000)" },
            },
            required: ["tab_id", "text"],
          },
        },
        {
          name: "browser_type",
          description:
            "Type text into a browser tab WITHOUT pressing Enter. Use for filling forms or composing messages before sending.",
          parameters: {
            type: "object",
            properties: {
              tab_id: { type: "string", description: "Tab ID from browser_list_tabs" },
              text: { type: "string", description: "Text to type" },
            },
            required: ["tab_id", "text"],
          },
        },
        {
          name: "browser_click",
          description:
            "Click an element in a browser tab by CSS selector.",
          parameters: {
            type: "object",
            properties: {
              tab_id: { type: "string", description: "Tab ID from browser_list_tabs" },
              selector: { type: "string", description: "CSS selector of element to click" },
            },
            required: ["tab_id", "selector"],
          },
        },
        {
          name: "browser_navigate",
          description:
            "Navigate a browser tab to a URL.",
          parameters: {
            type: "object",
            properties: {
              tab_id: { type: "string", description: "Tab ID from browser_list_tabs" },
              url: { type: "string", description: "URL to navigate to" },
            },
            required: ["tab_id", "url"],
          },
        },
        {
          name: "browser_eval",
          description:
            "Evaluate JavaScript in a browser tab and return the result. Use for custom DOM queries, extracting structured data, or complex interactions.",
          parameters: {
            type: "object",
            properties: {
              tab_id: { type: "string", description: "Tab ID from browser_list_tabs" },
              code: { type: "string", description: "JavaScript code to evaluate (must return a value)" },
            },
            required: ["tab_id", "code"],
          },
        },
        {
          name: "browser_bridge",
          description:
            "Bridge a conversation between two browser tabs. Reads the latest response from tab_from and sends it to tab_to. Repeat for multiple rounds. Use to make ChatGPT talk to Gemini, etc.",
          parameters: {
            type: "object",
            properties: {
              tab_from: { type: "string", description: "Source tab ID (read responses from here)" },
              tab_to: { type: "string", description: "Target tab ID (send messages here)" },
              rounds: { type: "number", description: "Number of back-and-forth rounds (default: 3)" },
            },
            required: ["tab_from", "tab_to"],
          },
        },
        {
          name: "browser_poll",
          description:
            "Wait for a browser tab's chat response to finish streaming, then return the text. Use after browser_send to wait for the AI to finish responding.",
          parameters: {
            type: "object",
            properties: {
              tab_id: { type: "string", description: "Tab ID from browser_list_tabs" },
              interval_ms: { type: "number", description: "Poll interval in ms (default: 2000)" },
            },
            required: ["tab_id"],
          },
        },
      ];
    },

    "tool.execute.before": async (input, output) => {
      // Not used - we handle everything in execute.after
    },

    "tool.execute.after": async (input, output) => {
      const args = output.args as Record<string, unknown> | undefined;
      if (!args) return;

      let result = "";

      switch (input.tool) {
        case "browser_list_tabs":
          result = run("list");
          break;

        case "browser_read":
          result = run(
            `read ${args.tab_id}${args.selector ? ` "${args.selector}"` : ""}`
          );
          break;

        case "browser_send":
          result = run(
            `send ${args.tab_id} "${String(args.text).replace(/"/g, '\\"')}"`,
            30000
          );
          break;

        case "browser_send_wait":
          result = run(
            `send-wait ${args.tab_id} "${String(args.text).replace(/"/g, '\\"')}" --timeout ${args.timeout_ms || 60000}`,
            (Number(args.timeout_ms) || 60000) + 15000
          );
          break;

        case "browser_type":
          result = run(
            `type ${args.tab_id} "${String(args.text).replace(/"/g, '\\"')}"`,
            30000
          );
          break;

        case "browser_click":
          result = run(`click ${args.tab_id} "${args.selector}"`);
          break;

        case "browser_navigate":
          result = run(`navigate ${args.tab_id} "${args.url}"`);
          break;

        case "browser_eval":
          result = run(
            `eval ${args.tab_id} "${String(args.code).replace(/"/g, '\\"')}"`,
            20000
          );
          break;

        case "browser_bridge":
          result = run(
            `bridge ${args.tab_from} ${args.tab_to} ${args.rounds || 3}`,
            120000
          );
          break;

        case "browser_poll":
          result = run(
            `poll ${args.tab_id} ${args.interval_ms || 2000}`,
            120000
          );
          break;

        default:
          return;
      }

      if (result) {
        output.output = result;
      }
    },

    dispose: async () => {},
  };
}) satisfies Plugin;
