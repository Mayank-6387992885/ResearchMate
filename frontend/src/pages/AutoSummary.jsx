import { useEffect, useRef, useState } from "react";
import {
  AlertCircle,
  CheckCircle2,
  LoaderCircle,
  Sparkles,
} from "lucide-react";

import FileUpload from "../components/FileUpload";
import SummaryCard from "../components/SummaryCard";
import ResearchChart from "../components/ResearchChart";
import TimedFeedback from "../components/TimedFeedback";
import { API, apiFetch, isLocalApi, setApiTarget } from "../services/api";
import { formatSummaryText } from "../utils/formatSummary";

const ACTIVE_TASK_KEY = "researchmate.activeSummaryTask";
const PROGRESS_SAMPLES_KEY = "researchmate.progressSamples";

export const AI_MODELS = [
  {
    key: "gemini:gemini-2.5-flash",
    provider: "gemini",
    model: "gemini-2.5-flash",
    label: "⚡ Google Gemini 2.5 Flash (Free & Recommended)",
    badge: "Free Cloud",
  },
  {
    key: "gemini:gemini-2.5-flash-lite",
    provider: "gemini",
    model: "gemini-2.5-flash-lite",
    label: "⚡ Google Gemini 2.5 Flash Lite (Fast & Free)",
    badge: "Free Cloud",
  },
  {
    key: "gemini:gemini-2.0-flash",
    provider: "gemini",
    model: "gemini-2.0-flash",
    label: "⚡ Google Gemini 2.0 Flash (Stable & Free)",
    badge: "Free Cloud",
  },
  {
    key: "groq:llama-3.3-70b-versatile",
    provider: "groq",
    model: "llama-3.3-70b-versatile",
    label: "⚡ Groq Cloud - Llama 3.3 70B (High Speed & Free)",
    badge: "Groq Cloud",
  },
  {
    key: "groq:llama-3.1-8b-instant",
    provider: "groq",
    model: "llama-3.1-8b-instant",
    label: "⚡ Groq Cloud - Llama 3.1 8B (Fast & Free)",
    badge: "Groq Cloud",
  },
  {
    key: "grok:grok-2-latest",
    provider: "grok",
    model: "grok-2-latest",
    label: "🚀 xAI Grok 2 (Requires Paid xAI Credits)",
    badge: "xAI API",
  },
  {
    key: "grok:grok-beta",
    provider: "grok",
    model: "grok-beta",
    label: "🚀 xAI Grok Beta (Requires Paid xAI Credits)",
    badge: "xAI API",
  },
  {
    key: "ollama:default",
    provider: "ollama",
    model: "default",
    label: "💻 Local Ollama (localhost:11434 / Offline)",
    badge: "Local PC",
  },
];

const MODEL_FAILOVER_CHAIN = [
  "gemini:gemini-2.5-flash",
  "gemini:gemini-2.5-flash-lite",
  "gemini:gemini-2.0-flash",
  "groq:llama-3.3-70b-versatile",
  "groq:llama-3.1-8b-instant",
  "grok:grok-2-latest",
  "ollama:default",
];

function pickNextFallbackModel(currentKey, triedKeysSet) {
  for (const key of MODEL_FAILOVER_CHAIN) {
    if (key !== currentKey && !triedKeysSet.has(key)) {
      return key;
    }
  }
  for (const item of AI_MODELS) {
    if (item.key !== currentKey && !triedKeysSet.has(item.key)) {
      return item.key;
    }
  }
  return null;
}

function formatRemainingTime(seconds) {
  const totalSeconds = Math.ceil(seconds);
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const remainingSeconds = totalSeconds % 60;

  if (hours > 0) return `${hours} hr ${minutes} min`;
  if (minutes > 0) return `${minutes} min ${remainingSeconds} sec`;
  return `${remainingSeconds} sec`;
}

function formatElapsedTime(seconds) {
  const totalSeconds = Math.max(0, Math.floor(seconds));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const remainingSeconds = totalSeconds % 60;

  if (hours > 0) return `${hours} hr ${minutes} min`;
  if (minutes > 0) return `${minutes} min ${remainingSeconds} sec`;
  return `${remainingSeconds} sec`;
}

function waitForNextPoll(delay, signal) {
  return new Promise((resolve, reject) => {
    const timeout = window.setTimeout(() => {
      signal.removeEventListener("abort", cancel);
      resolve();
    }, delay);
    const cancel = () => {
      window.clearTimeout(timeout);
      reject(new DOMException("Progress tracking was cancelled.", "AbortError"));
    };

    signal.addEventListener("abort", cancel, { once: true });
    if (signal.aborted) cancel();
  });
}

export default function AutoSummary() {
  const [file, setFile] = useState(null);
  const [progress, setProgress] = useState(0);
  const [displayProgress, setDisplayProgress] = useState(0);
  const [message, setMessage] = useState("Choose a PDF to begin.");
  const [taskId, setTaskId] = useState(
    () => window.sessionStorage.getItem(ACTIVE_TASK_KEY) || "",
  );
  const [status, setStatus] = useState(() => (
    window.sessionStorage.getItem(ACTIVE_TASK_KEY) ? "processing" : "idle"
  ));
  const [result, setResult] = useState(null);
  const [partialResult, setPartialResult] = useState(null);
  const [error, setError] = useState("");
  const [progressSyncIssue, setProgressSyncIssue] = useState("");
  const [lastSyncedAt, setLastSyncedAt] = useState(null);
  const [taskStartedAt, setTaskStartedAt] = useState(null);
  const [taskFinishedAt, setTaskFinishedAt] = useState(null);
  const [backendUpdatedAt, setBackendUpdatedAt] = useState(null);
  const [clockNow, setClockNow] = useState(Date.now());
  const [selectedAiModelKey, setSelectedAiModelKey] = useState(() => {
    try {
      const savedKey = window.localStorage.getItem("researchmate.ai_model_key");
      if (savedKey) return savedKey;
      const savedProv = window.localStorage.getItem("researchmate.ai_provider");
      if (savedProv === "grok") return "grok:grok-2-latest";
      if (savedProv === "groq") return "groq:llama-3.3-70b-versatile";
      if (savedProv === "ollama") return "ollama:default";
      return isLocalApi() ? "ollama:default" : "gemini:gemini-2.5-flash";
    } catch {
      return isLocalApi() ? "ollama:default" : "gemini:gemini-2.5-flash";
    }
  });

  const selectedAiProvider = selectedAiModelKey.split(":")[0];
  const selectedAiModel = selectedAiModelKey.split(":")[1] || "";

  const [autoSwitchNotice, setAutoSwitchNotice] = useState(null);
  const triedModelsRef = useRef(new Set());
  const isSwitchingModelRef = useRef(false);
  const activeModelKeyRef = useRef(selectedAiModelKey);
  const currentFileRef = useRef(file);

  useEffect(() => {
    activeModelKeyRef.current = selectedAiModelKey;
  }, [selectedAiModelKey]);

  useEffect(() => {
    currentFileRef.current = file;
  }, [file]);

  const handleModelChange = (modelKey) => {
    setSelectedAiModelKey(modelKey);
    activeModelKeyRef.current = modelKey;
    const prov = modelKey.split(":")[0];
    try {
      window.localStorage.setItem("researchmate.ai_model_key", modelKey);
      window.localStorage.setItem("researchmate.ai_provider", prov);
    } catch {}
  };

  const triggerModelFailover = (failedModelKey, rawErrorMessage) => {
    if (isSwitchingModelRef.current) return;
    isSwitchingModelRef.current = true;

    const currentKey = failedModelKey || activeModelKeyRef.current;
    triedModelsRef.current.add(currentKey);

    const nextModelKey = pickNextFallbackModel(currentKey, triedModelsRef.current);

    if (!nextModelKey) {
      isSwitchingModelRef.current = false;
      setError(rawErrorMessage || "All available AI models failed.");
      setStatus("error");
      return;
    }

    const failedObj = AI_MODELS.find((m) => m.key === currentKey);
    const nextObj = AI_MODELS.find((m) => m.key === nextModelKey);
    const failedLabel = failedObj ? failedObj.label.replace(/^[⚡🚀💻]\s*/, "") : currentKey;
    const nextLabel = nextObj ? nextObj.label.replace(/^[⚡🚀💻]\s*/, "") : nextModelKey;

    // Record error notice banner
    setAutoSwitchNotice({
      error: rawErrorMessage,
      failedModelName: failedLabel,
      newModelName: nextLabel,
      newModelKey: nextModelKey,
      timestamp: Date.now(),
    });

    // Auto-update dropdown state
    handleModelChange(nextModelKey);
    setMessage(
      `⚠️ ${failedLabel.split("(")[0].trim()} error. Auto-switching to ${nextLabel.split("(")[0].trim()} and continuing without stopping...`
    );

    // Cancel old controllers
    uploadControllerRef.current?.abort();
    progressControllerRef.current?.abort();
    uploadControllerRef.current = null;
    progressControllerRef.current = null;

    // Continue summarizing process without stopping!
    window.setTimeout(() => {
      isSwitchingModelRef.current = false;
      const targetFile = currentFileRef.current;
      if (targetFile) {
        void handleUpload(nextModelKey, targetFile);
      }
    }, 450);
  };
  const uploadControllerRef = useRef(null);
  const progressControllerRef = useRef(null);
  const progressSamplesRef = useRef({ taskId: "", samples: [] });

  useEffect(() => {
    let active = true;
    apiFetch(API.authConfig)
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (active && data) {
          try {
            const saved = window.localStorage.getItem("researchmate.ai_provider");
            if (!saved && data.ai_provider) {
              setSelectedAiProvider(data.ai_provider);
            }
          } catch {}
        }
      })
      .catch(() => {});
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (status !== "processing" && status !== "completed") {
      if (status === "idle") {
        setDisplayProgress(0);
      }
      return;
    }

    let animationFrameId;
    let lastTime = performance.now();

    const tick = (now) => {
      const dt = Math.min((now - lastTime) / 1000, 0.1);
      lastTime = now;

      setDisplayProgress((current) => {
        if (status === "completed") {
          if (current >= 100) return 100;
          const step = Math.max(0.6, (100 - current) * 6 * dt);
          return Math.min(100, current + step);
        }

        const target = progress;

        // On initial task load / reconnect, quickly snap to target
        if (current === 0 && target > 0) {
          return target;
        }

        if (current < target) {
          // Smoothly glide towards the confirmed backend target
          const diff = target - current;
          const speed = Math.max(0.6, diff * 1.5);
          const step = speed * dt;
          return Math.min(target, current + step);
        }

        // When current >= target and analysis is still actively running:
        // Slowly and gradually trickle forward so progress moves continuously instead of jumping in instant parts
        const maxTrickle = Math.min(target + (target < 90 ? 3.5 : 0.8), 99.2);
        if (current < maxTrickle) {
          const trickleSpeed = 0.08; // ~0.08% per second gradual advancement
          return Math.min(maxTrickle, current + trickleSpeed * dt);
        }

        return current;
      });

      animationFrameId = requestAnimationFrame(tick);
    };

    animationFrameId = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(animationFrameId);
  }, [status, progress]);

  useEffect(() => {
    const clock = window.setInterval(() => setClockNow(Date.now()), 1000);

    if (taskId) {
      const controller = new AbortController();
      progressControllerRef.current = controller;
      setMessage("Reconnecting to the backend task...");
      void syncProgress(taskId, controller.signal).then(() => {
        if (progressControllerRef.current === controller) {
          progressControllerRef.current = null;
        }
      });
    }

    return () => {
      window.clearInterval(clock);
      uploadControllerRef.current?.abort();
      progressControllerRef.current?.abort();
      uploadControllerRef.current = null;
      progressControllerRef.current = null;
    };
  }, []);

  async function syncProgress(currentTaskId, signal, waitForCreation = false) {
    let retryDelay = 500;

    while (!signal.aborted) {
      const requestController = new AbortController();
      const timeout = window.setTimeout(() => requestController.abort(), 10000);
      const abortRequest = () => requestController.abort();
      signal.addEventListener("abort", abortRequest, { once: true });

      try {
        const response = await apiFetch(API.progress(currentTaskId), {
          signal: requestController.signal,
        });

        if (response.status === 404) {
          if (!waitForCreation) {
            setError("The backend no longer has a record for this analysis.");
            setStatus("error");
            return null;
          }
          setProgressSyncIssue("");
          await waitForNextPoll(500, signal);
          continue;
        }

        const update = await response.json();
        if (!response.ok) {
          throw new Error(update.detail || "Could not read processing progress.");
        }
        if (update.task_id !== currentTaskId) {
          throw new Error("Received progress for a different upload.");
        }

        setProgress(update.progress);
        setMessage(update.message);
        setLastSyncedAt(Date.now());
        setProgressSyncIssue("");
        if (Number.isFinite(update.updated_at)) {
          setBackendUpdatedAt(update.updated_at * 1000);
        }
        if (update.result?.partial_summary) {
          setPartialResult((previous) => (
            previous?.partial_summary === update.result.partial_summary
              ? previous
              : update.result
          ));
        }
        if (Number.isFinite(update.started_at)) {
          setTaskStartedAt(update.started_at * 1000);
        }

        if (Number.isFinite(update.updated_at)) {
          if (progressSamplesRef.current.taskId !== currentTaskId) {
            let samples = [];
            try {
              const stored = JSON.parse(
                window.sessionStorage.getItem(PROGRESS_SAMPLES_KEY) || "null",
              );
              if (stored?.taskId === currentTaskId && Array.isArray(stored.samples)) {
                samples = stored.samples;
              }
            } catch {
              window.sessionStorage.removeItem(PROGRESS_SAMPLES_KEY);
            }
            progressSamplesRef.current = { taskId: currentTaskId, samples };
          }

          const samples = progressSamplesRef.current.samples;
          const latestSample = samples[samples.length - 1];
          if (!latestSample || update.progress > latestSample.progress) {
            samples.push({
              progress: update.progress,
              timestamp: update.updated_at * 1000,
            });
            progressSamplesRef.current.samples = samples.slice(-6);
            window.sessionStorage.setItem(
              PROGRESS_SAMPLES_KEY,
              JSON.stringify(progressSamplesRef.current),
            );
          }
        }

        if (update.status === "error") {
          uploadControllerRef.current?.abort();
          triggerModelFailover(activeModelKeyRef.current, update.message || "Processing failed.");
          return update;
        }
        if (update.status === "completed") {
          if (update.result?.task_id !== currentTaskId) {
            throw new Error("The backend completed this task without its matching result.");
          }
          setResult(update.result);
          setPartialResult(null);
          setProgress(100);
          setMessage(update.message);
          setStatus("completed");
          setTaskFinishedAt(update.updated_at * 1000);
          uploadControllerRef.current?.abort();
          return update;
        }

        retryDelay = 500;
        await waitForNextPoll(500, signal);
      } catch (err) {
        if (signal.aborted) return null;

        setProgressSyncIssue("Backend progress unavailable. Retrying automatically...");
        await waitForNextPoll(retryDelay, signal);
        retryDelay = Math.min(retryDelay * 2, 5000);
      } finally {
        window.clearTimeout(timeout);
        signal.removeEventListener("abort", abortRequest);
      }
    }

    return null;
  }

  async function handleUpload(overrideModelKey = null, overrideFile = null) {
    const targetFile = overrideFile || file || currentFileRef.current;
    if (!targetFile) return;

    const isAutoSwitch = Boolean(overrideModelKey);
    const activeKey = overrideModelKey || selectedAiModelKey;
    activeModelKeyRef.current = activeKey;
    const providerToUse = activeKey.split(":")[0];
    const rawModelToUse = activeKey.split(":")[1] || "";
    const modelToUse = rawModelToUse === "default" ? "" : rawModelToUse;

    if (!isAutoSwitch) {
      triedModelsRef.current.clear();
      setAutoSwitchNotice(null);
    }
    triedModelsRef.current.add(activeKey);

    const currentTaskId = crypto.randomUUID();
    const uploadController = new AbortController();
    const progressController = new AbortController();
    uploadControllerRef.current = uploadController;
    progressControllerRef.current = progressController;
    window.sessionStorage.setItem(ACTIVE_TASK_KEY, currentTaskId);
    window.sessionStorage.removeItem(PROGRESS_SAMPLES_KEY);
    progressSamplesRef.current = { taskId: currentTaskId, samples: [] };
    setTaskId(currentTaskId);
    setStatus("processing");
    if (!isAutoSwitch) {
      setProgress(0);
      setDisplayProgress(0);
    }
    setMessage(
      isAutoSwitch
        ? `Auto-switched model. Continuing analysis...`
        : "Connecting to ResearchMate AI..."
    );
    setError("");
    setProgressSyncIssue("");
    setLastSyncedAt(null);
    setBackendUpdatedAt(null);
    setTaskStartedAt(null);
    setTaskFinishedAt(null);

    void syncProgress(currentTaskId, progressController.signal, true)
      .then(() => {
        if (progressControllerRef.current === progressController) {
          progressControllerRef.current = null;
        }
      })
      .catch((err) => {
        if (!progressController.signal.aborted) {
          setProgressSyncIssue(err.message || "Could not sync progress with the backend.");
        }
      });

    try {
      const formData = new FormData();
      formData.append("file", targetFile);

      let response;
      try {
        response = await apiFetch(API.upload, {
          method: "POST",
          headers: {
            "X-Task-ID": currentTaskId,
            "X-AI-Provider": providerToUse,
            "X-AI-Model": modelToUse,
          },
          body: formData,
          signal: uploadController.signal,
        });
      } catch (err) {
        if (!uploadController.signal.aborted) {
          setProgressSyncIssue(
            "Upload response interrupted. Checking the backend task status...",
          );
        }
        return;
      }

      let data;
      try {
        data = await response.json();
      } catch {
        if (response.ok) {
          setProgressSyncIssue(
            "Upload response could not be read. Waiting for the backend task result...",
          );
          return;
        }
        throw new Error("The backend returned an unreadable error response.");
      }
      if (!response.ok) {
        throw new Error(data.detail || "Upload or summarization failed.");
      }

      if (data.task_id !== currentTaskId) {
        throw new Error("The backend returned a result for a different upload.");
      }
      setResult(data);
      setPartialResult(null);
      setProgress(100);
      setMessage("Summary completed and saved to your library.");
      setStatus("completed");
      setLastSyncedAt(Date.now());
      setTaskFinishedAt(Date.now());
      progressController.abort();
    } catch (err) {
      if (!uploadController.signal.aborted) {
        triggerModelFailover(activeKey, err.message || "Something went wrong.");
      }
    } finally {
      if (uploadControllerRef.current === uploadController) {
        uploadControllerRef.current = null;
      }
      if (progressController.signal.aborted && progressControllerRef.current === progressController) {
        progressControllerRef.current = null;
      }
    }
  }

  const isProcessing = status === "processing";
  const progressSamples = progressSamplesRef.current.samples;
  const firstProgressSample = progressSamples[0];
  const lastProgressSample = progressSamples[progressSamples.length - 1];
  const sampleDuration = firstProgressSample && lastProgressSample
    ? (lastProgressSample.timestamp - firstProgressSample.timestamp) / 1000
    : 0;
  const sampleProgress = firstProgressSample && lastProgressSample
    ? lastProgressSample.progress - firstProgressSample.progress
    : 0;
  const progressRate = sampleDuration > 0 ? sampleProgress / sampleDuration : 0;
  const estimatedRemaining = progressRate > 0
    ? (100 - lastProgressSample.progress) / progressRate
      - (clockNow - lastProgressSample.timestamp) / 1000
    : null;
  const elapsedSeconds = taskStartedAt
    ? ((taskFinishedAt || clockNow) - taskStartedAt) / 1000
    : null;
  const estimatedTotalSeconds = elapsedSeconds !== null && estimatedRemaining !== null
    ? elapsedSeconds + Math.max(0, estimatedRemaining)
    : null;
  const secondsSinceProgressUpdate = backendUpdatedAt
    ? Math.max(0, (clockNow - backendUpdatedAt) / 1000)
    : 0;
  const progressIsStalled = isProcessing && secondsSinceProgressUpdate >= 120;

  return (
    <div className="page narrow-page">
      <div className="page-title">
        <p className="eyebrow">AI POWERED ANALYSIS</p>
        <h1>Research Paper Summarizer</h1>
        <p className="muted">Upload a PDF and get a beginner-friendly explanation of the research.</p>
      </div>

      <section className="panel">
        <div className="panel-heading">
          <div>
            <h2>Upload your paper</h2>
            <p className="muted">Choose a PDF file up to 10 MB.</p>
          </div>
          <Sparkles className="heading-sparkle" />
        </div>

        <div
          className="ai-model-selector-card"
          style={{
            margin: "0 0 16px 0",
            padding: "12px 14px",
            background: "var(--bg-subtle, rgba(0, 0, 0, 0.02))",
            border: "1px solid var(--border-color, rgba(0, 0, 0, 0.08))",
            borderRadius: "10px",
            display: "flex",
            flexDirection: "column",
            gap: "10px",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "10px" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
              <Sparkles size={16} color="var(--primary, #4f46e5)" />
              <div>
                <span style={{ fontSize: "13px", fontWeight: 600, color: "var(--text-primary)" }}>
                  AI Model & Server:
                </span>
                <span style={{ fontSize: "12px", color: "var(--text-secondary, #64748b)", marginLeft: "6px" }}>
                  {selectedAiProvider === "gemini" && "(Google Gemini Cloud - Free)"}
                  {selectedAiProvider === "groq" && "(Groq Cloud - Ultra Fast)"}
                  {selectedAiProvider === "grok" && "(xAI Grok API - Requires Credits)"}
                  {selectedAiProvider === "ollama" && "(Local Ollama - localhost:11434)"}
                </span>
              </div>
            </div>

            <div style={{ display: "flex", alignItems: "center", gap: "8px" }}>
              <label htmlFor="ai-model-dropdown" style={{ fontSize: "12px", color: "var(--text-secondary, #64748b)", fontWeight: 500 }}>
                Choose Model:
              </label>
              <select
                id="ai-model-dropdown"
                value={selectedAiModelKey}
                disabled={isProcessing}
                onChange={(e) => handleModelChange(e.target.value)}
                style={{
                  padding: "5px 12px",
                  borderRadius: "8px",
                  fontSize: "12px",
                  fontWeight: 600,
                  border: "1px solid var(--border-color, rgba(0, 0, 0, 0.15))",
                  background: "var(--bg-card, #ffffff)",
                  color: "var(--text-primary, #1e293b)",
                  cursor: isProcessing ? "not-allowed" : "pointer",
                  outline: "none",
                  boxShadow: "0 1px 3px rgba(0,0,0,0.06)",
                }}
              >
                <optgroup label="⚡ Google Gemini Cloud (Free Tier)">
                  <option value="gemini:gemini-2.5-flash">⚡ Gemini 2.5 Flash (Recommended)</option>
                  <option value="gemini:gemini-2.5-flash-lite">⚡ Gemini 2.5 Flash Lite</option>
                  <option value="gemini:gemini-2.0-flash">⚡ Gemini 2.0 Flash</option>
                </optgroup>
                <optgroup label="⚡ Groq Cloud (Free & Ultra Fast)">
                  <option value="groq:llama-3.3-70b-versatile">⚡ Groq - Llama 3.3 70B</option>
                  <option value="groq:llama-3.1-8b-instant">⚡ Groq - Llama 3.1 8B</option>
                </optgroup>
                <optgroup label="🚀 xAI Grok (Requires Paid Credits)">
                  <option value="grok:grok-2-latest">🚀 xAI Grok 2 (Latest)</option>
                  <option value="grok:grok-beta">🚀 xAI Grok Beta</option>
                </optgroup>
                <optgroup label="💻 Local Ollama (Offline)">
                  <option value="ollama:default">💻 Local Ollama (Default Model)</option>
                </optgroup>
              </select>
            </div>
          </div>

          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: "8px", paddingTop: "6px", borderTop: "1px solid var(--border-color, rgba(0,0,0,0.05))" }}>
            <div style={{ display: "flex", gap: "6px", flexWrap: "wrap" }}>
              {[
                { id: "gemini:gemini-2.5-flash", label: "⚡ Gemini" },
                { id: "groq:llama-3.3-70b-versatile", label: "⚡ Groq" },
                { id: "grok:grok-2-latest", label: "🚀 Grok" },
                { id: "ollama:default", label: "💻 Local" },
              ].map((p) => {
                const active = selectedAiModelKey === p.id || (p.id.startsWith("gemini") && selectedAiProvider === "gemini") || (p.id.startsWith("grok") && selectedAiProvider === "grok");
                return (
                  <button
                    key={p.id}
                    type="button"
                    disabled={isProcessing}
                    onClick={() => handleModelChange(p.id)}
                    style={{
                      padding: "4px 12px",
                      borderRadius: "16px",
                      fontSize: "11px",
                      fontWeight: active ? 600 : 500,
                      cursor: isProcessing ? "not-allowed" : "pointer",
                      border: active
                        ? "1px solid #4f46e5"
                        : "1px solid var(--border-color, rgba(0, 0, 0, 0.12))",
                      background: active ? "#4f46e5" : "transparent",
                      color: active ? "#ffffff" : "var(--text-primary)",
                    }}
                  >
                    {p.label}
                  </button>
                );
              })}
            </div>
            <span style={{ fontSize: "11px", color: "var(--text-secondary, #64748b)" }}>
              🛡️ <strong>Auto-Failover:</strong> Automatically switches models if quota or credit errors occur.
            </span>
          </div>
        </div>

        <FileUpload
          file={file}
          onFileSelect={(selected) => {
            window.sessionStorage.removeItem(ACTIVE_TASK_KEY);
            setTaskId("");
            setFile(selected);
            setResult(null);
            setPartialResult(null);
            setError("");
            setStatus("idle");
            setProgress(0);
            setDisplayProgress(0);
            setMessage("Ready to upload.");
            setProgressSyncIssue("");
            setLastSyncedAt(null);
            setBackendUpdatedAt(null);
            setTaskStartedAt(null);
            setTaskFinishedAt(null);
          }}
          disabled={isProcessing}
        />

        <button className="primary-button full-width" onClick={() => handleUpload()} disabled={!file || isProcessing}>
          {isProcessing ? <LoaderCircle className="spin" size={17} /> : <Sparkles size={17} />}
          {isProcessing ? "Analyzing paper..." : "Generate summary"}
        </button>
      </section>

      {/* Real-time AI Model Error & Auto-Switch Notification Banner */}
      {autoSwitchNotice && (
        <div
          className="auto-switch-notice-banner"
          role="status"
        >
          <div className="auto-switch-header">
            <div className="auto-switch-title">
              <AlertCircle size={18} color="#d97706" style={{ flexShrink: 0 }} />
              <strong>AI Model Error Detected · Auto-Switching Active</strong>
            </div>
            <span className={`auto-switch-badge ${isProcessing ? "processing" : "completed"}`}>
              {isProcessing && <LoaderCircle className="spin" size={12} />}
              {isProcessing ? "Continuing process without stopping..." : "Summary completed with fallback model"}
            </span>
          </div>

          <div className="auto-switch-error-box">
            <span className="auto-switch-error-label">
              Error on {autoSwitchNotice.failedModelName}:
            </span>{" "}
            <span className="auto-switch-error-text">{autoSwitchNotice.error}</span>
          </div>

          <div className="auto-switch-footer">
            <Sparkles size={15} color="#059669" style={{ flexShrink: 0 }} />
            <span>
              Automatically switched to <strong>{autoSwitchNotice.newModelName}</strong>. Summarization continues without interruption.
            </span>
          </div>
        </div>
      )}

      {(isProcessing || status === "completed") && (
        <section className="panel progress-panel" aria-live="polite">
          <div className="progress-title">
            <div>
              <p className="eyebrow">LIVE PROCESS · {taskId.slice(0, 8)}</p>
              <h2>AI Paper Analysis</h2>
            </div>
            <span className={`progress-status-badge ${isProcessing ? "processing" : "completed"}`}>
              {isProcessing ? "Processing" : "Complete"}
            </span>
          </div>

          <div className="progress-overview">
            <div className="progress-reading">
              <strong className="progress-number">{displayProgress.toFixed(2)}%</strong>
              <span className="progress-eta">
                {status === "completed"
                  ? "Complete"
                  : sampleProgress > 0 && sampleDuration >= 30 && estimatedRemaining > 0
                    ? `~ ${formatRemainingTime(estimatedRemaining)} remaining`
                    : isProcessing && sampleProgress > 0 && sampleDuration >= 30
                      ? "Updating estimate..."
                      : "Calculating time remaining..."}
              </span>
            </div>
          </div>

          <div className="progress-track" role="progressbar" aria-valuenow={Number(displayProgress.toFixed(2))} aria-valuemin="0" aria-valuemax="100">
            <div className="progress-fill" style={{ width: `${Math.min(100, Math.max(0, displayProgress)).toFixed(2)}%` }} />
          </div>

          <p className="progress-estimate-note">
            Estimated completion time updates as processing progresses.
          </p>

          <div className="progress-time-details">
            <div className="progress-time-row">
              <span>Elapsed time</span>
              <strong>{elapsedSeconds === null ? "Calculating..." : formatElapsedTime(elapsedSeconds)}</strong>
            </div>
            <div className="progress-time-row">
              <span>Estimated total time</span>
              <strong>
                {status === "completed" && elapsedSeconds !== null
                  ? formatElapsedTime(elapsedSeconds)
                  : estimatedTotalSeconds === null
                    ? "Calculating..."
                    : `~ ${formatElapsedTime(estimatedTotalSeconds)}`}
              </strong>
            </div>
          </div>

          <p className="progress-message">
            {status === "completed" ? <CheckCircle2 size={17} /> : <LoaderCircle className="spin" size={17} />}
            {message}
          </p>
          <p className={`progress-sync-status ${progressSyncIssue ? "has-issue" : ""}`} role="status">
            {progressSyncIssue || (
              lastSyncedAt
                ? `Synced with backend at ${new Date(lastSyncedAt).toLocaleTimeString()}`
                : "Connecting to backend progress..."
            )}
          </p>
          {progressIsStalled && (
            <div className="progress-stall-warning" role="status">
              <AlertCircle size={18} />
              <span>
                No new analysis progress has been reported for{" "}
                {formatElapsedTime(secondsSinceProgressUpdate)}. A section may
                be taking longer than usual. Completed section notes are shown
                below. Check that the backend and AI service are responding if
                this message continues.
              </span>
            </div>
          )}
        </section>
      )}

      {partialResult?.partial_summary && !result && (
        <section className="panel partial-summary-panel" aria-live="polite">
          <p className="eyebrow">EARLY FINDINGS</p>
          <h2>Partial summary</h2>
          <p className="muted">
            Preliminary notes from {partialResult.chunks_completed} of{" "}
            {partialResult.total_chunks} sections. The final summary will
            organize and combine these findings when analysis finishes.
          </p>
          <article className="summary-text">
            {formatSummaryText(partialResult.partial_summary)}
          </article>
        </section>
      )}

      {error && (
        <div className="error-message" role="alert" style={{ display: "flex", flexDirection: "column", gap: "12px", padding: "18px 22px", margin: "20px 0", background: "rgba(239, 68, 68, 0.08)", border: "1px solid rgba(239, 68, 68, 0.25)", borderRadius: "14px", width: "100%", boxSizing: "border-box" }}>
          <div style={{ display: "flex", alignItems: "flex-start", gap: "10px" }}>
            <AlertCircle size={20} style={{ color: "#ef4444", flexShrink: 0, marginTop: "2px" }} />
            <div style={{ display: "flex", flexDirection: "column", gap: "4px" }}>
              <strong style={{ color: "#b91c1c", fontSize: "14px" }}>AI Model Error</strong>
              <span style={{ fontSize: "13px", color: "var(--text-primary)" }}>{error}</span>
            </div>
          </div>

          {/* Dropdown Box to choose required AI model manually upon error */}
          <div style={{
            marginTop: "6px",
            padding: "10px 12px",
            background: "rgba(255, 255, 255, 0.8)",
            border: "1px solid rgba(0, 0, 0, 0.08)",
            borderRadius: "6px",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            flexWrap: "wrap",
            gap: "10px",
          }}>
            <div style={{ fontSize: "12px", color: "var(--text-primary)", fontWeight: 600 }}>
              🔄 Choose Model to Retry:
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: "8px", flexWrap: "wrap" }}>
              <select
                value={selectedAiModelKey}
                onChange={(e) => {
                  handleModelChange(e.target.value);
                  setError("");
                }}
                style={{
                  padding: "5px 10px",
                  borderRadius: "6px",
                  fontSize: "12px",
                  fontWeight: 500,
                  border: "1px solid rgba(0,0,0,0.18)",
                  background: "#fff",
                  color: "#1e293b",
                  outline: "none",
                }}
              >
                <optgroup label="⚡ Google Gemini Cloud (Free Tier)">
                  <option value="gemini:gemini-2.5-flash">⚡ Switch to Google Gemini 2.5 Flash (Free)</option>
                  <option value="gemini:gemini-2.5-flash-lite">⚡ Switch to Gemini 2.5 Flash Lite</option>
                  <option value="gemini:gemini-2.0-flash">⚡ Switch to Gemini 2.0 Flash</option>
                </optgroup>
                <optgroup label="⚡ Groq Cloud (Free & Ultra Fast)">
                  <option value="groq:llama-3.3-70b-versatile">⚡ Switch to Groq (Llama 3.3 70B)</option>
                  <option value="groq:llama-3.1-8b-instant">⚡ Switch to Groq (Llama 3.1 8B)</option>
                </optgroup>
                <optgroup label="🚀 xAI Grok (Requires Paid Credits)">
                  <option value="grok:grok-2-latest">🚀 Switch to xAI Grok 2</option>
                  <option value="grok:grok-beta">🚀 Switch to xAI Grok Beta</option>
                </optgroup>
                <optgroup label="💻 Local Ollama (Offline)">
                  <option value="ollama:default">💻 Switch to Local Ollama</option>
                </optgroup>
              </select>

              <button
                type="button"
                style={{
                  padding: "6px 14px",
                  background: "#4f46e5",
                  color: "#fff",
                  borderRadius: "6px",
                  border: "none",
                  fontSize: "12px",
                  fontWeight: 600,
                  cursor: "pointer",
                }}
                onClick={() => {
                  setError("");
                  if (file) {
                    handleUpload();
                  }
                }}
              >
                Retry Analysis
              </button>
            </div>
          </div>

          <div style={{ display: "flex", gap: "6px", flexWrap: "wrap", marginTop: "2px" }}>
            <button
              type="button"
              style={{
                padding: "4px 10px",
                background: selectedAiProvider === "gemini" ? "#4f46e5" : "transparent",
                color: selectedAiProvider === "gemini" ? "#fff" : "var(--text-primary)",
                borderRadius: "6px",
                border: "1px solid rgba(0,0,0,0.15)",
                fontSize: "11px",
                fontWeight: 500,
                cursor: "pointer",
              }}
              onClick={() => {
                handleModelChange("gemini:gemini-2.5-flash");
                setError("");
              }}
            >
              ⚡ Use Gemini (Free)
            </button>
            <button
              type="button"
              style={{
                padding: "4px 10px",
                background: selectedAiProvider === "groq" ? "#4f46e5" : "transparent",
                color: selectedAiProvider === "groq" ? "#fff" : "var(--text-primary)",
                borderRadius: "6px",
                border: "1px solid rgba(0,0,0,0.15)",
                fontSize: "11px",
                fontWeight: 500,
                cursor: "pointer",
              }}
              onClick={() => {
                handleModelChange("groq:llama-3.3-70b-versatile");
                setError("");
              }}
            >
              ⚡ Use Groq (Fast)
            </button>
            <button
              type="button"
              style={{
                padding: "4px 10px",
                background: selectedAiProvider === "ollama" ? "#4f46e5" : "transparent",
                color: selectedAiProvider === "ollama" ? "#fff" : "var(--text-primary)",
                borderRadius: "6px",
                border: "1px solid rgba(0,0,0,0.15)",
                fontSize: "11px",
                fontWeight: 500,
                cursor: "pointer",
              }}
              onClick={() => {
                handleModelChange("ollama:default");
                setError("");
              }}
            >
              💻 Use Local Ollama
            </button>
          </div>

          {!isLocalApi() && (error.toLowerCase().includes("ollama") || error.toLowerCase().includes("11434") || error.toLowerCase().includes("gemini") || error.toLowerCase().includes("grok")) && (
            <div style={{
              marginTop: "4px",
              padding: "10px 12px",
              background: "rgba(79, 70, 229, 0.08)",
              border: "1px solid rgba(79, 70, 229, 0.2)",
              borderRadius: "6px",
              fontSize: "13px",
              color: "var(--text-primary)"
            }}>
              <p style={{ margin: "0 0 8px 0" }}>
                💡 <strong>To run on Render Cloud:</strong> Add <code>GEMINI_API_KEY</code> (free from <a href="https://aistudio.google.com/app/apikey" target="_blank" rel="noreferrer" style={{ color: "#4f46e5", textDecoration: "underline" }}>Google AI Studio</a>), <code>GROQ_API_KEY</code> (free from <a href="https://console.groq.com" target="_blank" rel="noreferrer" style={{ color: "#4f46e5", textDecoration: "underline" }}>Groq Console</a>), or <code>XAI_API_KEY</code> to your Render Dashboard under Environment Variables.
              </p>
              <p style={{ margin: "0 0 10px 0" }}>
                Alternatively, switch to your local backend to summarize using your PC's local Ollama:
              </p>
              <button
                type="button"
                style={{
                  background: "#4f46e5",
                  color: "#ffffff",
                  border: "none",
                  borderRadius: "6px",
                  padding: "6px 14px",
                  fontSize: "12px",
                  fontWeight: 600,
                  cursor: "pointer",
                }}
                onClick={() => {
                  setApiTarget("local");
                  window.location.reload();
                }}
              >
                Switch to Local Backend (port 8000)
              </button>
            </div>
          )}
        </div>
      )}

      {result && (
        <>
          {result.fallback_notice && (
            <div style={{
              display: "flex",
              alignItems: "center",
              gap: "12px",
              padding: "18px 22px",
              background: "rgba(79, 70, 229, 0.08)",
              border: "1px solid rgba(79, 70, 229, 0.25)",
              borderRadius: "14px",
              fontSize: "13px",
              color: "var(--text-primary)",
              margin: "20px 0",
              boxSizing: "border-box",
              width: "100%",
            }}>
              <Sparkles size={18} color="#4f46e5" style={{ flexShrink: 0 }} />
              <span>
                <strong>Automatic Failover Notice:</strong> {result.fallback_notice}
              </span>
            </div>
          )}
          <div className="result-stats">
            <div className="panel stat-card"><span>Pages</span><strong>{result.pages}</strong></div>
            <div className="panel stat-card"><span>Characters extracted</span><strong>{Number(result.characters).toLocaleString()}</strong></div>
            <div className="panel stat-card"><span>Processing time</span><strong>{result.processing_time_seconds}s</strong></div>
          </div>
          {result.classification_error && (
            <div className="classification-warning" role="status">
              <AlertCircle size={18} />
              <span>
                The summary was saved, but automatic classification did not
                finish. Retry it from My Summaries: {result.classification_error}
              </span>
            </div>
          )}
          <SummaryCard summary={result.summary} filename={result.filename} />
          <ResearchChart data={result.chart_data || []} />
        </>
      )}
    </div>
  );
}
