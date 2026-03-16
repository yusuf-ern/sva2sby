#!/usr/bin/env python3
"""Local web GUI for running enhanced-oss-cad formal jobs."""

from __future__ import annotations

import argparse
import json
import mimetypes
import shlex
import subprocess
import sys
import threading
import time
import webbrowser
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import ParseResult, parse_qs, urlparse


SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import formal  # noqa: E402


EXAMPLE_DIR = formal.ROOT / "examples" / "sva"
GUI_JOBS_DIR = formal.ROOT / "build" / "gui_jobs"
ALLOWED_INPUT_SUFFIXES = {".sby", ".sv", ".v"}
TEXT_ARTIFACT_SUFFIXES = {
    ".json",
    ".log",
    ".sby",
    ".smt2",
    ".smtc",
    ".sv",
    ".txt",
    ".v",
    ".ys",
    ".yw",
}

INDEX_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Enhanced OSS-CAD</title>
  <style>
    :root {
      --bg: #f4efe2;
      --bg-deep: #d9c8a5;
      --paper: rgba(255, 252, 244, 0.9);
      --ink: #1f1a16;
      --muted: #61564b;
      --line: rgba(78, 60, 41, 0.16);
      --accent: #b24b1f;
      --accent-deep: #8e3512;
      --teal: #1f5f63;
      --ok: #1f6a3f;
      --warn: #ab6b11;
      --bad: #9d2f1b;
      --shadow: 0 20px 60px rgba(56, 39, 20, 0.12);
    }

    * { box-sizing: border-box; }

    body {
      margin: 0;
      min-height: 100vh;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, rgba(178, 75, 31, 0.22), transparent 28rem),
        radial-gradient(circle at bottom right, rgba(31, 95, 99, 0.18), transparent 26rem),
        linear-gradient(180deg, var(--bg), #efe6d1 60%, #e4d8bc);
      font-family: Georgia, "Palatino Linotype", "Book Antiqua", serif;
    }

    .shell {
      max-width: 1440px;
      margin: 0 auto;
      padding: 24px;
    }

    .hero {
      display: grid;
      grid-template-columns: 1.4fr 1fr;
      gap: 18px;
      margin-bottom: 18px;
    }

    .hero-card,
    .panel {
      background: var(--paper);
      border: 1px solid var(--line);
      border-radius: 24px;
      box-shadow: var(--shadow);
      backdrop-filter: blur(10px);
    }

    .hero-card {
      padding: 24px;
      position: relative;
      overflow: hidden;
    }

    .hero-card::after {
      content: "";
      position: absolute;
      inset: auto -6rem -6rem auto;
      width: 16rem;
      height: 16rem;
      border-radius: 999px;
      background: linear-gradient(135deg, rgba(178, 75, 31, 0.18), rgba(31, 95, 99, 0.08));
    }

    h1, h2, h3 {
      margin: 0;
      font-weight: 600;
      letter-spacing: 0.01em;
    }

    h1 {
      font-size: clamp(2rem, 5vw, 3.8rem);
      line-height: 0.95;
      max-width: 10ch;
    }

    .hero-copy {
      margin-top: 12px;
      max-width: 56ch;
      color: var(--muted);
      font-size: 1rem;
      line-height: 1.5;
    }

    .hero-meta {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      margin-top: 18px;
    }

    .pill {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      border-radius: 999px;
      padding: 8px 12px;
      background: rgba(31, 26, 22, 0.05);
      color: var(--muted);
      font-size: 0.9rem;
    }

    .grid {
      display: grid;
      grid-template-columns: minmax(320px, 420px) minmax(0, 1fr);
      gap: 18px;
      align-items: start;
    }

    .panel {
      padding: 18px;
    }

    .panel h2 {
      font-size: 1.2rem;
      margin-bottom: 14px;
    }

    .stack {
      display: grid;
      gap: 12px;
    }

    .row {
      display: grid;
      gap: 12px;
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }

    label {
      display: grid;
      gap: 6px;
      font-size: 0.9rem;
      color: var(--muted);
    }

    input,
    select,
    textarea,
    button {
      font: inherit;
    }

    input,
    select,
    textarea {
      width: 100%;
      padding: 11px 12px;
      border-radius: 14px;
      border: 1px solid rgba(71, 54, 36, 0.18);
      background: rgba(255, 255, 255, 0.75);
      color: var(--ink);
    }

    textarea {
      min-height: 90px;
      resize: vertical;
    }

    .field-inline {
      display: flex;
      gap: 8px;
      align-items: center;
    }

    .field-inline input {
      flex: 1 1 auto;
    }

    .field-inline button {
      flex: 0 0 auto;
      white-space: nowrap;
    }

    .check {
      display: flex;
      align-items: center;
      gap: 10px;
      color: var(--ink);
    }

    .check input {
      width: auto;
    }

    .actions {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
    }

    button {
      border: 0;
      border-radius: 999px;
      padding: 11px 16px;
      cursor: pointer;
      transition: transform 140ms ease, opacity 140ms ease, background 140ms ease;
    }

    button:hover { transform: translateY(-1px); }
    button:disabled { cursor: wait; opacity: 0.7; transform: none; }

    .primary {
      background: linear-gradient(135deg, var(--accent), var(--accent-deep));
      color: #fffaf6;
    }

    .ghost {
      background: rgba(31, 26, 22, 0.06);
      color: var(--ink);
    }

    .jobs {
      display: grid;
      gap: 10px;
      margin-top: 12px;
    }

    .job {
      border: 1px solid var(--line);
      border-radius: 16px;
      padding: 12px;
      background: rgba(255, 255, 255, 0.65);
      cursor: pointer;
    }

    .job.active {
      border-color: rgba(178, 75, 31, 0.45);
      box-shadow: inset 0 0 0 1px rgba(178, 75, 31, 0.16);
    }

    .job-head,
    .detail-head {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 10px;
      flex-wrap: wrap;
    }

    .status {
      padding: 6px 10px;
      border-radius: 999px;
      font-size: 0.82rem;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      background: rgba(31, 26, 22, 0.08);
    }

    .status.running { background: rgba(171, 107, 17, 0.14); color: var(--warn); }
    .status.succeeded { background: rgba(31, 106, 63, 0.12); color: var(--ok); }
    .status.failed { background: rgba(157, 47, 27, 0.12); color: var(--bad); }

    .meta {
      color: var(--muted);
      font-size: 0.9rem;
    }

    .detail-grid {
      display: grid;
      gap: 18px;
    }

    .detail-card {
      border: 1px solid var(--line);
      border-radius: 18px;
      background: rgba(255, 255, 255, 0.62);
      overflow: hidden;
    }

    .detail-card header {
      padding: 12px 14px;
      border-bottom: 1px solid var(--line);
      background: rgba(31, 26, 22, 0.03);
    }

    .detail-card .body {
      padding: 14px;
    }

    pre {
      margin: 0;
      white-space: pre-wrap;
      word-break: break-word;
      font-family: "Courier New", Courier, monospace;
      font-size: 0.88rem;
      line-height: 1.45;
      color: #1a2424;
    }

    .artifact-list {
      display: grid;
      gap: 8px;
    }

    .artifact {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      padding: 10px 12px;
      border: 1px solid var(--line);
      border-radius: 14px;
      background: rgba(255, 255, 255, 0.72);
    }

    .artifact small {
      color: var(--muted);
    }

    .artifact button {
      padding: 8px 12px;
    }

    .hint {
      color: var(--muted);
      font-size: 0.88rem;
      line-height: 1.45;
    }

    .browser-overlay[hidden] {
      display: none;
    }

    .browser-overlay {
      position: fixed;
      inset: 0;
      padding: 24px;
      background: rgba(31, 26, 22, 0.28);
      display: grid;
      place-items: center;
      z-index: 20;
    }

    .browser-panel {
      width: min(920px, 100%);
      max-height: min(82vh, 760px);
      overflow: hidden;
      background: var(--paper);
      border: 1px solid var(--line);
      border-radius: 24px;
      box-shadow: var(--shadow);
      display: grid;
      grid-template-rows: auto auto minmax(0, 1fr);
      gap: 12px;
      padding: 18px;
    }

    .browser-head {
      display: flex;
      justify-content: space-between;
      gap: 14px;
      align-items: start;
      flex-wrap: wrap;
    }

    .browser-path {
      word-break: break-all;
    }

    .browser-list {
      min-height: 220px;
      overflow: auto;
      border: 1px solid var(--line);
      border-radius: 18px;
      background: rgba(255, 255, 255, 0.72);
    }

    .browser-entry {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: center;
      padding: 12px 14px;
      border-bottom: 1px solid var(--line);
    }

    .browser-entry:last-child {
      border-bottom: 0;
    }

    .browser-meta {
      min-width: 0;
    }

    .browser-meta strong,
    .browser-meta code {
      display: block;
      word-break: break-all;
    }

    .browser-actions {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
      justify-content: flex-end;
    }

    @media (max-width: 980px) {
      .hero,
      .grid {
        grid-template-columns: 1fr;
      }
    }
  </style>
</head>
<body>
  <div class="shell">
    <section class="hero">
      <article class="hero-card">
        <h1>Enhanced OSS-CAD control room</h1>
        <p class="hero-copy">
          Launch the existing formal wrapper against any local project, inspect generated
          work directories, and keep ad hoc runs and repo samples in one place.
        </p>
        <div class="hero-meta">
          <span class="pill">Wrapper-backed execution</span>
          <span class="pill">Local only</span>
          <span class="pill">Artifacts from <code>build/formal_runs/</code></span>
        </div>
      </article>
      <article class="panel">
        <h2>Usage</h2>
        <div class="stack hint">
          <div>Set a project root, then enter a relative or absolute <code>.sby</code>, <code>.sv</code>, or <code>.v</code> path from that project.</div>
          <div>Generated runs default to <code>&lt;project-root&gt;/build/formal_runs/</code>, and you can override the work root when needed.</div>
          <div>Generated text artifacts can be previewed directly; waveform files remain downloadable from the run directory.</div>
        </div>
      </article>
    </section>

    <section class="grid">
      <aside class="panel">
        <h2>Run Job</h2>
        <form id="run-form" class="stack">
          <label>
            Project Root
            <div class="field-inline">
              <input id="project-root" name="project_root" placeholder="/path/to/project" required>
              <button type="button" class="ghost browse-button" data-target="project-root" data-files="0">Browse</button>
            </div>
          </label>
          <label>
            Work Root
            <div class="field-inline">
              <input id="work-root" name="work_root" placeholder="/path/to/project/build/formal_runs">
              <button type="button" class="ghost browse-button" data-target="work-root" data-files="0">Browse</button>
            </div>
          </label>
          <label>
            Input Path
            <div class="field-inline">
              <input id="input-path" name="input_path" placeholder="path/to/project.sby" required>
              <button type="button" class="ghost browse-button" data-target="input-path" data-files="1">Browse</button>
            </div>
          </label>
          <label>
            Tasks
            <input id="tasks" name="tasks" placeholder="prove cover">
          </label>
          <label>
            Repo Samples
            <select id="example-select">
              <option value="">Optional repo sample</option>
            </select>
          </label>
          <div class="actions">
            <button type="button" class="ghost" id="use-example">Load Sample</button>
            <button type="button" class="ghost" id="reload-examples">Reload Samples</button>
          </div>
          <div class="row">
            <label>
              Top
              <input id="top" name="top" placeholder="top module for direct .sv/.v input">
            </label>
            <label>
              Engine
              <input id="engine" name="engine" placeholder="smtbmc yices">
            </label>
          </div>
          <div class="row">
            <label>
              Mode
              <select id="mode" name="mode">
                <option value="bmc">bmc</option>
                <option value="prove">prove</option>
                <option value="cover">cover</option>
              </select>
            </label>
            <label>
              Backend
              <select id="backend" name="backend">
                <option value="auto">auto</option>
                <option value="sby">sby</option>
                <option value="ebmc">ebmc</option>
              </select>
            </label>
          </div>
          <div class="row">
            <label>
              Depth
              <input id="depth" name="depth" type="number" min="1" value="5">
            </label>
            <label class="check">
              <span>Compatibility Mode</span>
              <input id="compat" name="compat" type="checkbox">
            </label>
          </div>
          <div class="actions">
            <button type="submit" class="primary" id="run-button">Launch Run</button>
            <button type="button" class="ghost" id="cancel-button">Stop Selected Job</button>
          </div>
          <div class="hint" id="form-hint">No job launched yet.</div>
        </form>

        <h2 style="margin-top: 22px;">Recent Jobs</h2>
        <div id="jobs" class="jobs">
          <div class="hint">No jobs yet.</div>
        </div>
      </aside>

      <main class="panel">
        <div class="detail-head">
          <h2>Run Details</h2>
          <span id="detail-status" class="status">idle</span>
        </div>
        <div id="details" class="detail-grid">
          <div class="detail-card">
            <header><strong>Summary</strong></header>
            <div class="body hint" id="summary">
              Select a job to inspect command details, logs, and generated artifacts.
            </div>
          </div>
          <div class="detail-card">
            <header><strong>Command</strong></header>
            <div class="body"><pre id="command-view">No job selected.</pre></div>
          </div>
          <div class="detail-card">
            <header><strong>Live Log</strong></header>
            <div class="body"><pre id="log-view">No log available.</pre></div>
          </div>
          <div class="detail-card">
            <header><strong>Artifacts</strong></header>
            <div class="body artifact-list" id="artifacts">
              <div class="hint">No artifacts available.</div>
            </div>
          </div>
          <div class="detail-card">
            <header><strong>Artifact Preview</strong></header>
            <div class="body"><pre id="artifact-view">Choose a text artifact to preview it here.</pre></div>
          </div>
        </div>
      </main>
    </section>
  </div>
  <div id="browser-overlay" class="browser-overlay" hidden>
    <section class="browser-panel" role="dialog" aria-modal="true" aria-labelledby="browser-title">
      <div class="browser-head">
        <div class="stack" style="gap: 6px;">
          <h2 id="browser-title">Browse Paths</h2>
          <div class="hint browser-path" id="browser-path">/</div>
        </div>
        <div class="actions">
          <button type="button" class="ghost" id="browser-up">Parent</button>
          <button type="button" class="ghost" id="browser-choose-folder">Use This Folder</button>
          <button type="button" class="ghost" id="browser-close">Close</button>
        </div>
      </div>
      <div class="hint" id="browser-hint">Choose a directory or formal input file.</div>
      <div id="browser-list" class="browser-list">
        <div class="hint" style="padding: 14px;">No path loaded.</div>
      </div>
    </section>
  </div>
  <script>
    const state = {
      config: null,
      jobs: [],
      selectedJobId: null,
      pollHandle: null,
      browser: {
        fieldId: null,
        includeFiles: false,
        basePath: "",
        currentPath: "",
        parentPath: "",
      },
    };

    async function fetchJson(url, options = {}) {
      const response = await fetch(url, options);
      if (!response.ok) {
        const message = await response.text();
        throw new Error(message || `${response.status} ${response.statusText}`);
      }
      return response.json();
    }

    function setHint(message, isError = false) {
      const hint = document.getElementById("form-hint");
      hint.textContent = message;
      hint.style.color = isError ? "var(--bad)" : "var(--muted)";
    }

    function setBrowserHint(message, isError = false) {
      const hint = document.getElementById("browser-hint");
      hint.textContent = message;
      hint.style.color = isError ? "var(--bad)" : "var(--muted)";
    }

    function tasksFromInput(value) {
      return value.split(/[\\s,]+/).map((entry) => entry.trim()).filter(Boolean);
    }

    function normalizePathValue(value) {
      const trimmed = (value || "").trim();
      if (!trimmed) return "";
      if (trimmed === "/") return "/";
      return trimmed.replace(/\/+$/, "");
    }

    function joinPath(base, segment) {
      const normalizedBase = normalizePathValue(base);
      if (!normalizedBase || normalizedBase === "/") {
        return `/${segment}`;
      }
      return `${normalizedBase}/${segment}`;
    }

    function defaultWorkRootFor(projectRoot) {
      return joinPath(joinPath(projectRoot, "build"), "formal_runs");
    }

    function relativizePath(path, base) {
      const normalizedPath = normalizePathValue(path);
      const normalizedBase = normalizePathValue(base);
      if (!normalizedPath || !normalizedBase) return path;
      if (normalizedPath === normalizedBase) return ".";
      const prefix = normalizedBase === "/" ? "/" : `${normalizedBase}/`;
      if (normalizedPath.startsWith(prefix)) {
        return normalizedPath.slice(prefix.length);
      }
      return path;
    }

    function formatSelectedPath(fieldId, path) {
      if (fieldId === "project-root") {
        return path;
      }
      const projectRoot = document.getElementById("project-root").value.trim();
      const relative = relativizePath(path, projectRoot);
      if (relative && relative !== ".") {
        return relative;
      }
      return path;
    }

    function setProjectRoot(path) {
      const projectInput = document.getElementById("project-root");
      const workInput = document.getElementById("work-root");
      const previousProjectRoot = normalizePathValue(projectInput.value);
      const previousWorkRoot = normalizePathValue(workInput.value);
      const previousDefault = previousProjectRoot ? normalizePathValue(defaultWorkRootFor(previousProjectRoot)) : "";
      const shouldResetWorkRoot = !previousWorkRoot || (previousDefault && previousWorkRoot === previousDefault);
      projectInput.value = path;
      if (shouldResetWorkRoot) {
        workInput.value = defaultWorkRootFor(path);
      }
    }

    function statusClass(status) {
      if (status === "running") return "status running";
      if (status === "succeeded") return "status succeeded";
      if (status === "failed") return "status failed";
      return "status";
    }

    function renderJobs() {
      const container = document.getElementById("jobs");
      if (!state.jobs.length) {
        container.innerHTML = '<div class="hint">No jobs yet.</div>';
        return;
      }

      container.innerHTML = "";
      for (const job of state.jobs) {
        const node = document.createElement("button");
        node.type = "button";
        node.className = `job${job.id === state.selectedJobId ? " active" : ""}`;
        node.innerHTML = `
          <div class="job-head">
            <strong>${job.label}</strong>
            <span class="${statusClass(job.status)}">${job.status}</span>
          </div>
          <div class="meta">${job.input_display}</div>
          <div class="meta">Started ${new Date(job.created_at * 1000).toLocaleTimeString()}</div>
        `;
        node.addEventListener("click", () => {
          state.selectedJobId = job.id;
          renderJobs();
          renderSelectedJob();
        });
        container.appendChild(node);
      }
    }

    function renderArtifacts(job) {
      const container = document.getElementById("artifacts");
      if (!job.artifacts.length) {
        container.innerHTML = '<div class="hint">No artifacts available.</div>';
        return;
      }

      container.innerHTML = "";
      for (const artifact of job.artifacts) {
        const row = document.createElement("div");
        row.className = "artifact";
        row.innerHTML = `
          <div>
            <strong>${artifact.path}</strong><br>
            <small>${artifact.kind}</small>
          </div>
        `;

        const action = document.createElement("button");
        action.type = "button";
        action.className = "ghost";
        action.textContent = artifact.previewable ? "Preview" : "Open";
        action.addEventListener("click", async () => {
          if (!artifact.previewable) {
            window.open(`/api/jobs/${job.id}/artifact?path=${encodeURIComponent(artifact.path)}`, "_blank");
            return;
          }
          try {
            const response = await fetch(`/api/jobs/${job.id}/artifact?path=${encodeURIComponent(artifact.path)}`);
            if (!response.ok) {
              throw new Error(await response.text());
            }
            document.getElementById("artifact-view").textContent = await response.text();
          } catch (error) {
            document.getElementById("artifact-view").textContent = String(error);
          }
        });
        row.appendChild(action);
        container.appendChild(row);
      }
    }

    function renderSelectedJob() {
      const statusNode = document.getElementById("detail-status");
      const summary = document.getElementById("summary");
      const commandView = document.getElementById("command-view");
      const logView = document.getElementById("log-view");
      const artifactView = document.getElementById("artifact-view");
      artifactView.textContent = artifactView.textContent || "Choose a text artifact to preview it here.";

      const job = state.jobs.find((item) => item.id === state.selectedJobId);
      if (!job) {
        statusNode.className = "status";
        statusNode.textContent = "idle";
        summary.textContent = "Select a job to inspect command details, logs, and generated artifacts.";
        commandView.textContent = "No job selected.";
        logView.textContent = "No log available.";
        renderArtifacts({ artifacts: [], id: "" });
        return;
      }

      statusNode.className = statusClass(job.status);
      statusNode.textContent = job.status;
      summary.textContent = `${job.input_display} -> ${job.workdir_display}` + (job.returncode === null ? "" : ` (rc=${job.returncode})`);
      commandView.textContent = job.command_display;
      logView.textContent = job.log_tail || "Log file is empty.";
      renderArtifacts(job);
    }

    function renderBrowser(payload) {
      const pathNode = document.getElementById("browser-path");
      const list = document.getElementById("browser-list");
      const chooseFolder = document.getElementById("browser-choose-folder");
      const upButton = document.getElementById("browser-up");

      pathNode.textContent = payload.current_path;
      chooseFolder.hidden = state.browser.includeFiles;
      upButton.disabled = payload.parent_path === payload.current_path;

      if (!payload.entries.length) {
        list.innerHTML = '<div class="hint" style="padding: 14px;">No matching entries in this directory.</div>';
        return;
      }

      list.innerHTML = "";
      for (const entry of payload.entries) {
        const row = document.createElement("div");
        row.className = "browser-entry";

        const meta = document.createElement("div");
        meta.className = "browser-meta";
        const nameNode = document.createElement("strong");
        nameNode.textContent = entry.name;
        const pathNode = document.createElement("code");
        pathNode.textContent = entry.path;
        meta.appendChild(nameNode);
        meta.appendChild(pathNode);

        const actions = document.createElement("div");
        actions.className = "browser-actions";

        if (entry.kind === "dir") {
          const openButton = document.createElement("button");
          openButton.type = "button";
          openButton.className = "ghost";
          openButton.textContent = "Open";
          openButton.addEventListener("click", () => {
            loadBrowser(entry.path).catch((error) => setBrowserHint(String(error), true));
          });
          actions.appendChild(openButton);

          if (!state.browser.includeFiles) {
            const chooseButton = document.createElement("button");
            chooseButton.type = "button";
            chooseButton.className = "primary";
            chooseButton.textContent = "Use";
            chooseButton.addEventListener("click", () => chooseBrowserPath(entry.path));
            actions.appendChild(chooseButton);
          }
        } else {
          const chooseButton = document.createElement("button");
          chooseButton.type = "button";
          chooseButton.className = "primary";
          chooseButton.textContent = "Use";
          chooseButton.addEventListener("click", () => chooseBrowserPath(entry.path));
          actions.appendChild(chooseButton);
        }

        row.appendChild(meta);
        row.appendChild(actions);
        list.appendChild(row);
      }
    }

    async function loadBrowser(path) {
      const query = new URLSearchParams({
        path: path || "",
        base: state.browser.basePath || "",
        files: state.browser.includeFiles ? "1" : "0",
      });
      const payload = await fetchJson(`/api/browse?${query.toString()}`);
      state.browser.currentPath = payload.current_path;
      state.browser.parentPath = payload.parent_path;
      renderBrowser(payload);
      setBrowserHint(state.browser.includeFiles ? "Choose a formal input file." : "Choose a directory.");
    }

    function closeBrowser() {
      document.getElementById("browser-overlay").hidden = true;
      state.browser = {
        fieldId: null,
        includeFiles: false,
        basePath: "",
        currentPath: "",
        parentPath: "",
      };
    }

    async function openBrowser(fieldId, includeFiles) {
      if (!state.config) {
        setHint("GUI configuration is still loading.", true);
        return;
      }
      const projectRoot = document.getElementById("project-root").value.trim() || state.config.project_root;
      const field = document.getElementById(fieldId);
      state.browser = {
        fieldId,
        includeFiles,
        basePath: projectRoot,
        currentPath: field.value.trim() || projectRoot,
        parentPath: projectRoot,
      };
      document.getElementById("browser-overlay").hidden = false;
      document.getElementById("browser-list").innerHTML =
        '<div class="hint" style="padding: 14px;">Loading...</div>';
      setBrowserHint("Loading paths...");
      try {
        await loadBrowser(state.browser.currentPath);
      } catch (error) {
        setBrowserHint(String(error), true);
      }
    }

    function chooseBrowserPath(path) {
      if (!state.browser.fieldId) {
        return;
      }
      if (state.browser.fieldId === "project-root") {
        setProjectRoot(path);
      } else {
        document.getElementById(state.browser.fieldId).value = formatSelectedPath(state.browser.fieldId, path);
      }
      closeBrowser();
    }

    async function loadConfig() {
      const config = await fetchJson("/api/config");
      state.config = config;
      document.getElementById("project-root").value = config.project_root;
      document.getElementById("work-root").value = config.work_root;
    }

    async function refreshExamples() {
      const examples = await fetchJson("/api/examples");
      const select = document.getElementById("example-select");
      select.innerHTML = '<option value="">Optional repo sample</option>';
      for (const example of examples.examples) {
        const option = document.createElement("option");
        option.value = example.path;
        option.textContent = `${example.path} (${example.kind})`;
        select.appendChild(option);
      }
    }

    async function refreshJobs() {
      const payload = await fetchJson("/api/jobs");
      state.jobs = payload.jobs;
      if (!state.selectedJobId && state.jobs.length) {
        state.selectedJobId = state.jobs[0].id;
      }
      renderJobs();
      renderSelectedJob();
    }

    async function submitRun(event) {
      event.preventDefault();
      const button = document.getElementById("run-button");
      button.disabled = true;
      try {
        const payload = {
          project_root: document.getElementById("project-root").value.trim(),
          work_root: document.getElementById("work-root").value.trim(),
          input_path: document.getElementById("input-path").value.trim(),
          tasks: tasksFromInput(document.getElementById("tasks").value),
          top: document.getElementById("top").value.trim(),
          mode: document.getElementById("mode").value,
          depth: Number(document.getElementById("depth").value),
          backend: document.getElementById("backend").value,
          engine: document.getElementById("engine").value.trim(),
          compat: document.getElementById("compat").checked,
        };
        const result = await fetchJson("/api/jobs", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        state.selectedJobId = result.job.id;
        setHint(`Started ${result.job.label} in ${result.job.workdir_display}`);
        await refreshJobs();
      } catch (error) {
        setHint(String(error), true);
      } finally {
        button.disabled = false;
      }
    }

    async function cancelSelectedJob() {
      if (!state.selectedJobId) {
        setHint("Select a running job first.", true);
        return;
      }
      try {
        const result = await fetchJson(`/api/jobs/${state.selectedJobId}/cancel`, { method: "POST" });
        setHint(result.message);
        await refreshJobs();
      } catch (error) {
        setHint(String(error), true);
      }
    }

    function startPolling() {
      if (state.pollHandle !== null) {
        clearInterval(state.pollHandle);
      }
      state.pollHandle = setInterval(() => {
        refreshJobs().catch((error) => setHint(String(error), true));
      }, 1000);
    }

    document.getElementById("run-form").addEventListener("submit", submitRun);
    document.getElementById("cancel-button").addEventListener("click", cancelSelectedJob);
    document.getElementById("reload-examples").addEventListener("click", () => {
      refreshExamples().catch((error) => setHint(String(error), true));
    });
    document.getElementById("use-example").addEventListener("click", () => {
      const value = document.getElementById("example-select").value;
      if (value && state.config) {
        setProjectRoot(state.config.repo_root);
        document.getElementById("input-path").value = value;
      }
    });
    document.querySelectorAll(".browse-button").forEach((button) => {
      button.addEventListener("click", () => {
        openBrowser(button.dataset.target, button.dataset.files === "1")
          .catch((error) => setHint(String(error), true));
      });
    });
    document.getElementById("browser-close").addEventListener("click", closeBrowser);
    document.getElementById("browser-up").addEventListener("click", () => {
      loadBrowser(state.browser.parentPath).catch((error) => setBrowserHint(String(error), true));
    });
    document.getElementById("browser-choose-folder").addEventListener("click", () => {
      chooseBrowserPath(state.browser.currentPath);
    });
    document.getElementById("browser-overlay").addEventListener("click", (event) => {
      if (event.target.id === "browser-overlay") {
        closeBrowser();
      }
    });

    loadConfig().catch((error) => setHint(String(error), true));
    refreshExamples().catch((error) => setHint(String(error), true));
    refreshJobs().catch((error) => setHint(String(error), true));
    startPolling();
  </script>
</body>
</html>
"""


@dataclass(slots=True)
class RunRequest:
    project_root: Path
    input_path: Path
    tasks: list[str]
    top: str | None
    mode: str
    depth: int
    backend: str
    engine: str | None
    compat: bool
    work_root: Path


@dataclass(slots=True)
class GuiJob:
    id: str
    label: str
    request: RunRequest
    command: list[str]
    workdir: Path
    job_dir: Path
    log_path: Path
    process: subprocess.Popen[str]
    created_at: float


def display_path(path: Path, *base_dirs: Path) -> str:
    resolved = path.resolve()
    for base_dir in base_dirs:
        try:
            return str(resolved.relative_to(base_dir.resolve()))
        except ValueError:
            continue
    return str(resolved)


def discover_examples() -> list[dict[str, str]]:
    if not EXAMPLE_DIR.exists():
        return []
    examples: list[dict[str, str]] = []
    for path in sorted(EXAMPLE_DIR.rglob("*")):
        if not path.is_file() or path.suffix not in ALLOWED_INPUT_SUFFIXES:
            continue
        examples.append(
            {
                "path": display_path(path, formal.ROOT),
                "kind": path.suffix[1:],
            }
        )
    return examples


def normalize_tasks(raw_tasks: object) -> list[str]:
    if raw_tasks is None:
        return []
    if isinstance(raw_tasks, str):
        pieces = raw_tasks.replace(",", " ").split()
        return [piece for piece in pieces if piece]
    if isinstance(raw_tasks, list):
        tasks: list[str] = []
        for item in raw_tasks:
            if not isinstance(item, str):
                raise ValueError("tasks must be a list of strings")
            tasks.extend(normalize_tasks(item))
        return tasks
    raise ValueError("tasks must be a string or a list of strings")


def resolve_directory(
    raw_path: object,
    default_dir: Path,
    field_name: str,
    *,
    must_exist: bool = True,
) -> Path:
    if raw_path is None or (isinstance(raw_path, str) and not raw_path.strip()):
        resolved = default_dir.resolve()
    elif isinstance(raw_path, str):
        candidate = Path(raw_path.strip()).expanduser()
        if not candidate.is_absolute():
            candidate = default_dir / candidate
        resolved = candidate.resolve()
    else:
        raise ValueError(f"{field_name} must be a string")
    if not resolved.exists():
        if not must_exist:
            return resolved
        raise ValueError(f"{field_name} does not exist: {resolved}")
    if not resolved.is_dir():
        raise ValueError(f"{field_name} is not a directory: {resolved}")
    return resolved


def resolve_input_path(raw_path: object, base_dir: Path) -> Path:
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise ValueError("input_path is required")
    candidate = Path(raw_path.strip()).expanduser()
    if not candidate.is_absolute():
        candidate = base_dir / candidate
    resolved = candidate.resolve()
    if not resolved.exists():
        raise ValueError(f"input path does not exist: {resolved}")
    if not resolved.is_file():
        raise ValueError(f"input path is not a file: {resolved}")
    if resolved.suffix not in ALLOWED_INPUT_SUFFIXES:
        raise ValueError("input_path must end with .sby, .sv, or .v")
    return resolved


def resolve_browser_directory(raw_path: str | None, base_dir: Path) -> Path:
    if raw_path is None or not raw_path.strip():
        candidate = base_dir.resolve()
    else:
        candidate_path = Path(raw_path.strip()).expanduser()
        if not candidate_path.is_absolute():
            candidate_path = base_dir / candidate_path
        candidate = candidate_path.resolve()

    if candidate.exists() and candidate.is_file():
        return candidate.parent

    current = candidate
    while not current.exists() and current != current.parent:
        current = current.parent
    if current.exists() and current.is_dir():
        return current
    return base_dir.resolve()


def browse_directory_entries(directory: Path, include_files: bool) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    for entry in sorted(directory.iterdir(), key=lambda path: (not path.is_dir(), path.name.casefold())):
        if entry.is_dir():
            entries.append({"name": entry.name, "path": str(entry.resolve()), "kind": "dir"})
            continue
        if include_files and entry.suffix in ALLOWED_INPUT_SUFFIXES:
            entries.append({"name": entry.name, "path": str(entry.resolve()), "kind": "file"})
    return entries[:200]


def default_work_root(project_root: Path) -> Path:
    return project_root / "build" / "formal_runs"


def default_gui_workdir_for_input(
    work_root: Path,
    input_path: Path,
    tasks: list[str],
    top: str | None,
) -> Path:
    stem = input_path.stem
    suffix = "_".join(tasks) if tasks else (top or stem)
    if suffix == stem:
        return work_root / stem
    return work_root / f"{stem}__{suffix}"


def parse_run_request(payload: dict[str, object], default_project_root: Path) -> RunRequest:
    project_root = resolve_directory(payload.get("project_root"), default_project_root, "project_root")
    input_path = resolve_input_path(payload.get("input_path"), project_root)
    tasks = normalize_tasks(payload.get("tasks"))
    top = payload.get("top")
    engine = payload.get("engine")
    mode = payload.get("mode", "bmc")
    depth = payload.get("depth", 5)
    backend = payload.get("backend", "auto")
    compat = bool(payload.get("compat", False))
    work_root_raw = payload.get("work_root")
    if work_root_raw is None or (isinstance(work_root_raw, str) and not work_root_raw.strip()):
        work_root = default_work_root(project_root)
    else:
        work_root = resolve_directory(
            work_root_raw,
            project_root,
            "work_root",
            must_exist=False,
        )

    if top is not None and not isinstance(top, str):
        raise ValueError("top must be a string")
    if engine is not None and not isinstance(engine, str):
        raise ValueError("engine must be a string")
    if not isinstance(mode, str) or mode not in {"bmc", "prove", "cover"}:
        raise ValueError("mode must be one of: bmc, prove, cover")
    if backend not in {"auto", "sby", "ebmc"}:
        raise ValueError("backend must be one of: auto, sby, ebmc")
    try:
        depth_value = int(depth)
    except (TypeError, ValueError) as exc:
        raise ValueError("depth must be an integer") from exc
    if depth_value < 1:
        raise ValueError("depth must be at least 1")

    top_value = top.strip() if isinstance(top, str) and top.strip() else None
    engine_value = engine.strip() if isinstance(engine, str) and engine.strip() else None
    if input_path.suffix == ".sby":
        top_value = None
    else:
        if tasks:
            raise ValueError("tasks are only valid for .sby inputs")
        if compat:
            raise ValueError("compatibility mode is only valid for .sby inputs")

    return RunRequest(
        project_root=project_root,
        input_path=input_path,
        tasks=tasks,
        top=top_value,
        mode=mode,
        depth=depth_value,
        backend=backend,
        engine=engine_value,
        compat=compat,
        work_root=work_root,
    )


def build_formal_command(request: RunRequest) -> tuple[list[str], Path]:
    workdir = default_gui_workdir_for_input(
        request.work_root,
        request.input_path,
        request.tasks,
        request.top,
    )
    command = [
        sys.executable,
        str(SCRIPT_DIR / "formal.py"),
        "sby",
        str(request.input_path),
        *request.tasks,
        "--workdir",
        str(workdir),
        "--backend",
        request.backend,
    ]
    if request.compat:
        command.append("--compat")
    if request.engine is not None:
        command.extend(["--engine", request.engine])
    if request.input_path.suffix != ".sby":
        if request.top is not None:
            command.extend(["--top", request.top])
        command.extend(["--mode", request.mode, "--depth", str(request.depth)])
    return command, workdir


def read_tail(path: Path, max_chars: int = 24000) -> str:
    if not path.exists():
        return ""
    text = path.read_text(errors="replace")
    if len(text) <= max_chars:
        return text
    return text[-max_chars:]


def artifact_kind(path: Path) -> str:
    if path.suffix in TEXT_ARTIFACT_SUFFIXES:
        return "text"
    return path.suffix[1:] if path.suffix else "file"


def collect_artifacts(workdir: Path) -> list[dict[str, object]]:
    if not workdir.exists():
        return []

    preferred = ["run.sby", "lowered.sv"]
    seen: set[Path] = set()
    artifacts: list[dict[str, object]] = []

    def add_path(path: Path) -> None:
        if not path.exists() or not path.is_file():
            return
        rel = path.relative_to(workdir)
        if rel in seen:
            return
        seen.add(rel)
        artifacts.append(
            {
                "path": rel.as_posix(),
                "kind": artifact_kind(path),
                "previewable": path.suffix in TEXT_ARTIFACT_SUFFIXES,
            }
        )

    for name in preferred:
        add_path(workdir / name)
    for path in sorted(workdir.rglob("*")):
        if path.is_file():
            add_path(path)
        if len(artifacts) >= 60:
            break
    return artifacts


def resolve_artifact_path(workdir: Path, raw_path: str) -> Path:
    candidate = workdir / raw_path
    resolved = candidate.resolve()
    try:
        resolved.relative_to(workdir.resolve())
    except ValueError as exc:
        raise ValueError("artifact path escapes workdir") from exc
    if not resolved.exists() or not resolved.is_file():
        raise ValueError("artifact does not exist")
    return resolved


class JobRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: dict[str, GuiJob] = {}
        self._counter = 0

    def create_job(self, request: RunRequest) -> GuiJob:
        command, workdir = build_formal_command(request)
        created_at = time.time()
        label = request.input_path.stem

        with self._lock:
            self._counter += 1
            job_id = f"job-{int(created_at)}-{self._counter:04d}"
            job_dir = GUI_JOBS_DIR / job_id
            job_dir.mkdir(parents=True, exist_ok=True)
            log_path = job_dir / "job.log"
            with log_path.open("w") as log_handle:
                process = subprocess.Popen(
                    command,
                    cwd=formal.ROOT,
                    stdout=log_handle,
                    stderr=subprocess.STDOUT,
                    text=True,
                )
            job = GuiJob(
                id=job_id,
                label=label,
                request=request,
                command=command,
                workdir=workdir,
                job_dir=job_dir,
                log_path=log_path,
                process=process,
                created_at=created_at,
            )
            self._jobs[job_id] = job
            return job

    def list_jobs(self) -> list[GuiJob]:
        with self._lock:
            return sorted(self._jobs.values(), key=lambda job: job.created_at, reverse=True)

    def get_job(self, job_id: str) -> GuiJob | None:
        with self._lock:
            return self._jobs.get(job_id)

    def cancel_job(self, job_id: str) -> bool:
        with self._lock:
            job = self._jobs.get(job_id)
        if job is None:
            return False
        if job.process.poll() is not None:
            return False
        job.process.terminate()
        return True


def job_to_dict(job: GuiJob) -> dict[str, object]:
    returncode = job.process.poll()
    status = "running" if returncode is None else ("succeeded" if returncode == 0 else "failed")
    return {
        "id": job.id,
        "label": job.label,
        "status": status,
        "returncode": returncode,
        "created_at": job.created_at,
        "project_root_display": str(job.request.project_root),
        "input_display": display_path(job.request.input_path, job.request.project_root, formal.ROOT),
        "workdir_display": display_path(job.workdir, job.request.project_root, formal.ROOT),
        "command_display": shlex.join(job.command),
        "log_tail": read_tail(job.log_path),
        "artifacts": collect_artifacts(job.workdir),
    }


class GuiHandler(BaseHTTPRequestHandler):
    server: "GuiServer"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._respond_html(INDEX_HTML)
            return
        if parsed.path == "/api/examples":
            self._respond_json({"examples": discover_examples()})
            return
        if parsed.path == "/api/config":
            self._respond_json(
                {
                    "project_root": str(self.server.project_root),
                    "work_root": str(default_work_root(self.server.project_root)),
                    "repo_root": str(formal.ROOT),
                }
            )
            return
        if parsed.path == "/api/browse":
            self._browse_paths(parsed)
            return
        if parsed.path == "/api/jobs":
            self._respond_json({"jobs": [job_to_dict(job) for job in self.server.registry.list_jobs()]})
            return
        if parsed.path.startswith("/api/jobs/") and parsed.path.endswith("/artifact"):
            self._serve_artifact(parsed)
            return
        self._respond_error(HTTPStatus.NOT_FOUND, "not found")

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/jobs":
            self._create_job()
            return
        if parsed.path.startswith("/api/jobs/") and parsed.path.endswith("/cancel"):
            self._cancel_job(parsed.path)
            return
        self._respond_error(HTTPStatus.NOT_FOUND, "not found")

    def log_message(self, fmt: str, *args: object) -> None:
        del fmt, args

    def _create_job(self) -> None:
        try:
            payload = self._read_json()
            request = parse_run_request(payload, self.server.project_root)
            job = self.server.registry.create_job(request)
        except ValueError as exc:
            self._respond_error(HTTPStatus.BAD_REQUEST, str(exc))
            return
        self._respond_json({"job": job_to_dict(job)}, status=HTTPStatus.CREATED)

    def _cancel_job(self, path: str) -> None:
        parts = path.strip("/").split("/")
        if len(parts) != 4:
            self._respond_error(HTTPStatus.NOT_FOUND, "not found")
            return
        job_id = parts[2]
        cancelled = self.server.registry.cancel_job(job_id)
        if not cancelled:
            self._respond_error(HTTPStatus.BAD_REQUEST, "job is not running or does not exist")
            return
        self._respond_json({"message": f"termination requested for {job_id}"})

    def _browse_paths(self, parsed: ParseResult) -> None:
        query = parse_qs(parsed.query)
        base_dir = resolve_browser_directory(query.get("base", [""])[0], self.server.project_root)
        directory = resolve_browser_directory(query.get("path", [""])[0], base_dir)
        include_files = query.get("files", ["0"])[0].strip().lower() not in {"", "0", "false", "no"}
        try:
            entries = browse_directory_entries(directory, include_files)
        except OSError as exc:
            self._respond_error(HTTPStatus.BAD_REQUEST, f"unable to browse {directory}: {exc}")
            return
        parent = directory.parent if directory.parent != directory else directory
        self._respond_json(
            {
                "current_path": str(directory),
                "parent_path": str(parent),
                "entries": entries,
            }
        )

    def _serve_artifact(self, parsed: ParseResult) -> None:
        parts = parsed.path.strip("/").split("/")
        if len(parts) != 4:
            self._respond_error(HTTPStatus.NOT_FOUND, "not found")
            return
        job_id = parts[2]
        job = self.server.registry.get_job(job_id)
        if job is None:
            self._respond_error(HTTPStatus.NOT_FOUND, "unknown job")
            return
        raw_path = parse_qs(parsed.query).get("path", [""])[0]
        try:
            artifact_path = resolve_artifact_path(job.workdir, raw_path)
        except ValueError as exc:
            self._respond_error(HTTPStatus.BAD_REQUEST, str(exc))
            return

        content_type, _ = mimetypes.guess_type(str(artifact_path))
        content_type = content_type or "application/octet-stream"
        if artifact_path.suffix in TEXT_ARTIFACT_SUFFIXES:
            self._respond_text(artifact_path.read_text(errors="replace"), content_type="text/plain; charset=utf-8")
            return
        data = artifact_path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _read_json(self) -> dict[str, object]:
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        try:
            payload = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError("request body must be valid JSON") from exc
        if not isinstance(payload, dict):
            raise ValueError("request body must be a JSON object")
        return payload

    def _respond_html(self, text: str) -> None:
        encoded = text.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _respond_text(self, text: str, content_type: str) -> None:
        encoded = text.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _respond_json(self, payload: dict[str, object], status: HTTPStatus = HTTPStatus.OK) -> None:
        encoded = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _respond_error(self, status: HTTPStatus, message: str) -> None:
        encoded = message.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


class GuiServer(ThreadingHTTPServer):
    def __init__(self, server_address: tuple[str, int], registry: JobRegistry, project_root: Path) -> None:
        super().__init__(server_address, GuiHandler)
        self.registry = registry
        self.project_root = project_root


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1", help="Bind host; defaults to 127.0.0.1")
    parser.add_argument("--port", type=int, default=8080, help="Bind port; defaults to 8080")
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path.cwd(),
        help="Default project root for relative input paths",
    )
    parser.add_argument(
        "--open-browser",
        action="store_true",
        help="Open the default browser after the server starts",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    GUI_JOBS_DIR.mkdir(parents=True, exist_ok=True)
    registry = JobRegistry()
    server = GuiServer((args.host, args.port), registry, args.project_root.resolve())
    url = f"http://{args.host}:{args.port}"
    print(f"enhanced-oss-cad GUI listening on {url}")
    if args.open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nshutting down GUI")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
