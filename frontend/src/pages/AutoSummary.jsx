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
import { API, apiFetch } from "../services/api";
import { formatSummaryText } from "../utils/formatSummary";

const ACTIVE_TASK_KEY = "researchmate.activeSummaryTask";
const PROGRESS_SAMPLES_KEY = "researchmate.progressSamples";

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
  const uploadControllerRef = useRef(null);
  const progressControllerRef = useRef(null);
  const progressSamplesRef = useRef({ taskId: "", samples: [] });

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
          setError(update.message || "Processing failed.");
          setStatus("error");
          setTaskFinishedAt(update.updated_at * 1000);
          uploadControllerRef.current?.abort();
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

  async function handleUpload() {
    if (!file || status === "processing") return;

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
    setProgress(0);
    setMessage("Connecting to ResearchMate...");
    setResult(null);
    setPartialResult(null);
    setError("");
    setProgressSyncIssue("");
    setLastSyncedAt(null);
    setBackendUpdatedAt(null);
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
      formData.append("file", file);

      let response;
      try {
        response = await apiFetch(API.upload, {
          method: "POST",
          headers: { "X-Task-ID": currentTaskId },
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
        setError(err.message || "Something went wrong.");
        setStatus("error");
        progressController.abort();
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
            setMessage("Ready to upload.");
            setProgressSyncIssue("");
            setLastSyncedAt(null);
            setBackendUpdatedAt(null);
            setTaskStartedAt(null);
            setTaskFinishedAt(null);
          }}
          disabled={isProcessing}
        />

        <button className="primary-button full-width" onClick={handleUpload} disabled={!file || isProcessing}>
          {isProcessing ? <LoaderCircle className="spin" size={17} /> : <Sparkles size={17} />}
          {isProcessing ? "Analyzing paper..." : "Generate summary"}
        </button>
      </section>

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
              <strong className="progress-number">{progress}%</strong>
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

          <div className="progress-track" role="progressbar" aria-valuenow={progress} aria-valuemin="0" aria-valuemax="100">
            <div className="progress-fill" style={{ width: `${progress}%` }} />
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
        <TimedFeedback className="error-message" role="alert" message={error}>
          <AlertCircle size={18} />
          {error}
        </TimedFeedback>
      )}

      {result && (
        <>
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
