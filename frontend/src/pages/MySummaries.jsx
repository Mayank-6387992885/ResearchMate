
import { useEffect, useMemo, useState } from "react";
import {
  Search,
  FileText,
  FileDown,
  Bookmark,
  Trash2,
  Eye,
  Pencil,
  Tags,
  RefreshCw,
  AlertCircle,
  LoaderCircle,
  X,
  ArrowUpDown,
  Sparkles
} from "lucide-react";

import { API, apiFetch } from "../services/api";
import TimedFeedback from "../components/TimedFeedback";
import {
  CLASSIFICATION_LABELS,
  CLASSIFICATION_OPTIONS,
  PAPER_CATEGORIES
} from "../data/classificationTaxonomy";
import { formatSummaryText } from "../utils/formatSummary";

const EMPTY_CLASSIFICATION = Object.fromEntries(
  Object.keys(CLASSIFICATION_OPTIONS).map((field) => [field, []])
);

function TaxonomyPicker({ field, selected, onChange }) {
  const [query, setQuery] = useState("");
  const options = CLASSIFICATION_OPTIONS[field];
  const filteredOptions = options.filter((option) =>
    option.toLowerCase().includes(query.toLowerCase())
  );

  function toggleOption(option) {
    onChange(
      selected.includes(option)
        ? selected.filter((item) => item !== option)
        : [...selected, option]
    );
  }

  return (
    <details className="taxonomy-picker">
      <summary>
        <span>{CLASSIFICATION_LABELS[field]}</span>
        <strong>{selected.length} selected</strong>
      </summary>
      <input
        className="taxonomy-search"
        type="search"
        placeholder={`Find ${CLASSIFICATION_LABELS[field].toLowerCase()}...`}
        value={query}
        onChange={(event) => setQuery(event.target.value)}
      />
      <div className="taxonomy-options">
        {filteredOptions.map((option) => (
          <label key={option}>
            <input
              type="checkbox"
              checked={selected.includes(option)}
              onChange={() => toggleOption(option)}
            />
            {option}
          </label>
        ))}
        {filteredOptions.length === 0 && (
          <span className="muted">No matching categories.</span>
        )}
      </div>
    </details>
  );
}

function classificationLabels(paper, field) {
  return paper.classification?.[field] || [];
}

function paperGroupLabel(paper, field) {
  const value = classificationLabels(paper, field)[0];
  return value || "Unclassified";
}

function formatDuration(seconds) {
  if (seconds < 60) return `${seconds}s`;
  return `${Math.floor(seconds / 60)}m ${seconds % 60}s`;
}

function ClassificationProgress({ task, now }) {
  const elapsed = Math.max(0, Math.floor((now - task.startedAt) / 1000));
  const steadyStageDurations = task.stageDurations.slice(1);
  const averageStageDuration = steadyStageDurations.length
    ? steadyStageDurations.reduce((total, duration) => total + duration, 0)
      / steadyStageDurations.length
    : null;
  const remaining = averageStageDuration !== null && task.completed < task.total
    ? Math.ceil(averageStageDuration * (task.total - task.completed))
    : null;
  const waitingForModel = task.status === "processing" && task.completed === 0;
  const dimension = CLASSIFICATION_LABELS[task.currentDimension] || "Classification";

  return (
    <div className={`classification-progress ${task.status === "error" ? "has-error" : ""}`}>
      <div className="classification-progress-heading">
        <strong>
          {task.status === "error"
            ? "Classification failed"
            : task.status === "completed"
              ? "Classification complete"
              : waitingForModel
                ? "Preparing AI classification"
                : `Classifying ${dimension}`}
        </strong>
        <span>{waitingForModel ? "Working..." : `${task.progress}%`}</span>
      </div>
      <div
        className={`classification-progress-track ${waitingForModel ? "is-indeterminate" : ""}`}
        role="progressbar"
        aria-label="Paper classification progress"
        aria-valuemin={0}
        aria-valuemax={100}
        {...(waitingForModel
          ? { "aria-valuetext": "AI is reading the paper and preparing classifications." }
          : { "aria-valuenow": task.progress })}
      >
        <div
          className={`classification-progress-fill ${waitingForModel ? "is-indeterminate" : ""}`}
          style={waitingForModel ? undefined : { width: `${task.progress}%` }}
        />
      </div>
      <p className="classification-progress-message">
        {waitingForModel
          ? "The local AI model is reading the paper. Progress updates as each category is returned."
          : task.message}
      </p>
      <p className="classification-progress-timing">
        {task.completed} of {task.total} stages · Elapsed {formatDuration(elapsed)}
        {task.status === "processing" && (
          remaining === null
            ? " · Estimating time remaining..."
            : ` · About ${formatDuration(remaining)} remaining`
        )}
      </p>
    </div>
  );
}

export default function MySummaries() {
  const [papers, setPapers] = useState([]);
  const [search, setSearch] = useState("");
  const [domainFilter, setDomainFilter] = useState("");
  const [sortBy, setSortBy] = useState("name");
  const [sortDirection, setSortDirection] = useState("asc");
  const [groupBy, setGroupBy] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [selectedPaper, setSelectedPaper] = useState(null);
  const [editingPaper, setEditingPaper] = useState(null);
  const [editValue, setEditValue] = useState("");
  const [editClassification, setEditClassification] = useState(EMPTY_CLASSIFICATION);
  const [editCategory, setEditCategory] = useState(PAPER_CATEGORIES[0]);
  const [classificationChanged, setClassificationChanged] = useState(false);
  const [savingEdit, setSavingEdit] = useState(false);
  const [classificationTask, setClassificationTask] = useState(null);
  const [clockNow, setClockNow] = useState(Date.now());

  const visiblePapers = useMemo(() => {
    const filtered = papers.filter((paper) => {
      if (!domainFilter) return true;
      if (domainFilter === "Unclassified") {
        return classificationLabels(paper, "research_domains").length === 0;
      }
      return classificationLabels(paper, "research_domains").includes(domainFilter);
    });

    return filtered.sort((first, second) => {
      const direction = sortDirection === "asc" ? 1 : -1;
      let firstValue;
      let secondValue;
      if (sortBy === "date") {
        firstValue = new Date(first.updated_at || first.uploaded_at || 0).getTime();
        secondValue = new Date(second.updated_at || second.uploaded_at || 0).getTime();
      } else if (sortBy === "type") {
        firstValue = paperGroupLabel(first, "paper_types");
        secondValue = paperGroupLabel(second, "paper_types");
      } else {
        firstValue = first.title;
        secondValue = second.title;
      }
      if (typeof firstValue === "string") {
        return direction * firstValue.localeCompare(secondValue, undefined, { sensitivity: "base" });
      }
      return direction * (firstValue - secondValue);
    });
  }, [papers, domainFilter, sortBy, sortDirection]);

  const groupedPapers = useMemo(() => {
    if (!groupBy) return [["", visiblePapers]];
    const groups = new Map();
    for (const paper of visiblePapers) {
      const labels = classificationLabels(paper, groupBy);
      for (const label of labels.length ? labels : ["Unclassified"]) {
        if (!groups.has(label)) groups.set(label, []);
        groups.get(label).push(paper);
      }
    }
    return [...groups.entries()];
  }, [visiblePapers, groupBy]);

  // Retrieve papers from the backend
  async function loadPapers(searchTerm = "") {
    try {
      setLoading(true);
      setError("");

      const params = new URLSearchParams();
      if (searchTerm.trim()) {
        params.set("search", searchTerm.trim());
      }

      const url = params.toString()
        ? `${API.papers}?${params.toString()}`
        : API.papers;

      const response = await apiFetch(url);
      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || "Unable to load papers.");
      }

      setPapers(data.papers || []);
    } catch (err) {
      setError(err.message || "Something went wrong.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    const timer = setTimeout(() => {
      loadPapers(search);
    }, 300);

    return () => clearTimeout(timer);
  }, [search]);

  useEffect(() => {
    if (classificationTask?.status !== "processing") return undefined;
    const timer = setInterval(() => setClockNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [classificationTask?.status]);

  // Bookmark or unbookmark a paper
  async function handleSave(id) {
    try {
      const response = await apiFetch(API.savePaper(id), {
        method: "PUT"
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || "Unable to update bookmark.");
      }

      setPapers((previous) =>
        previous.map((paper) =>
          paper.id === id
            ? { ...paper, is_saved: data.is_saved }
            : paper
        )
      );
    } catch (err) {
      setError(err.message);
    }
  }

  function openPaperEditor(paper, field) {
    setError("");
    setEditingPaper({ paper, field });
    setEditCategory(paper.category || PAPER_CATEGORIES[0]);
    setClassificationChanged(false);
    if (field === "title") {
      setEditValue(paper.title);
    } else {
      setEditClassification({
        ...EMPTY_CLASSIFICATION,
        ...(paper.classification || {})
      });
    }
  }

  async function handlePaperUpdate(event) {
    event.preventDefault();
    if (!editingPaper) return;

    const update = editingPaper.field === "title"
      ? { title: editValue }
      : {
          category: editCategory,
          ...(classificationChanged ? { classification: editClassification } : {})
        };

    try {
      setSavingEdit(true);
      setError("");
      const response = await apiFetch(API.updatePaper(editingPaper.paper.id), {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(update)
      });
      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || "Unable to update paper.");
      }

      setPapers((previous) =>
        previous.map((paper) => paper.id === data.id ? data : paper)
      );
      setSelectedPaper((previous) =>
        previous?.id === data.id ? data : previous
      );
      setEditingPaper(null);
    } catch (err) {
      setError(err.message || "Unable to update paper.");
    } finally {
      setSavingEdit(false);
    }
  }

  async function handleClassify(paper) {
    const startedAt = Date.now();
    setClassificationTask({
      paperId: paper.id,
      taskId: null,
      progress: 0,
      completed: 0,
      total: Object.keys(CLASSIFICATION_LABELS).length,
      currentDimension: Object.keys(CLASSIFICATION_LABELS)[0],
      message: "Preparing paper classification...",
      startedAt,
      lastStageAt: startedAt,
      stageDurations: [],
      status: "processing"
    });
    try {
      setError("");
      const requestTimeout = () => AbortSignal.timeout(10000);
      const response = await apiFetch(API.classifyPaper(paper.id), {
        method: "POST",
        signal: requestTimeout()
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data.detail || "Unable to classify paper.");
      }

      setClassificationTask((previous) => ({
        ...previous,
        taskId: data.task_id,
        message: "Classification started."
      }));

      while (true) {
        await new Promise((resolve) => setTimeout(resolve, 800));
        const progressResponse = await apiFetch(API.progress(data.task_id), {
          signal: requestTimeout()
        });
        const progressData = await progressResponse.json();
        if (!progressResponse.ok) {
          throw new Error(progressData.detail || "Unable to read classification progress.");
        }

        const detail = progressData.result?.classification_progress || {};
        setClassificationTask((previous) => {
          const completed = detail.completed || 0;
          const stageCompleted = completed > previous.completed;
          const now = Date.now();
          return {
            ...previous,
            taskId: data.task_id,
            progress: progressData.progress || 0,
            completed,
            total: detail.total || previous.total,
            currentDimension: detail.current_dimension || previous.currentDimension,
            message: progressData.message,
            lastStageAt: stageCompleted ? now : previous.lastStageAt,
            stageDurations: stageCompleted
              ? [...previous.stageDurations, (now - previous.lastStageAt) / 1000]
              : previous.stageDurations
          };
        });

        if (progressData.status === "error") {
          throw new Error(progressData.message || "Paper classification failed.");
        }
        if (progressData.status === "completed") break;
      }

      const paperResponse = await apiFetch(API.getPaper(paper.id), {
        signal: requestTimeout()
      });
      const updatedPaper = await paperResponse.json();
      if (!paperResponse.ok) {
        throw new Error(updatedPaper.detail || "Classification finished, but the paper could not be refreshed.");
      }
      setPapers((previous) =>
        previous.map((item) => item.id === updatedPaper.id ? updatedPaper : item)
      );
      setSelectedPaper((previous) =>
        previous?.id === updatedPaper.id ? updatedPaper : previous
      );
      setClassificationTask((previous) => ({
        ...previous,
        progress: 100,
        completed: previous.total,
        status: "completed",
        message: "Classification complete."
      }));
    } catch (err) {
      const message = err.message || "Unable to classify paper.";
      setError(message);
      setClassificationTask((previous) => ({
        ...previous,
        status: "error",
        message
      }));
    }
  }

  // Delete a paper
  async function handleDelete(id) {
    if (!window.confirm("Are you sure you want to delete this paper?")) {
      return;
    }

    try {
      const response = await apiFetch(API.deletePaper(id), {
        method: "DELETE"
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || "Unable to delete paper.");
      }

      setPapers((previous) =>
        previous.filter((paper) => paper.id !== id)
      );

      if (selectedPaper?.id === id) {
        setSelectedPaper(null);
      }
    } catch (err) {
      setError(err.message);
    }
  }

  function formatDate(date) {
    if (!date) return "Date unavailable";

    return new Date(date).toLocaleDateString("en-IN", {
      day: "2-digit",
      month: "short",
      year: "numeric"
    });
  }

  return (
    <div className="page">
      <div className="page-title">
        <p className="eyebrow">YOUR RESEARCH LIBRARY</p>
        <h1>My Summaries</h1>
        <p className="muted">
          Access and manage your previously summarized research papers.
        </p>
      </div>

      {/* Search and paper count */}
      <section className="panel">
        <div className="panel-heading">
          <div>
            <h2>Saved Research Papers</h2>
            <p className="muted">
              {visiblePapers.length} paper(s) found
            </p>
          </div>

          <button
            className="secondary-button"
            onClick={() => loadPapers(search)}
            disabled={loading}
          >
            <RefreshCw size={16} />
            Refresh
          </button>
        </div>

        <div className="search-box">
          <Search size={18} />
          <input
            type="text"
            placeholder="Search papers by title..."
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
        </div>
        <label className="category-filter">
          <span>Research domain</span>
          <select
            value={domainFilter}
            onChange={(event) => setDomainFilter(event.target.value)}
          >
            <option value="">All research domains</option>
            <option value="Unclassified">Unclassified</option>
            {CLASSIFICATION_OPTIONS.research_domains.map((domain) => (
              <option key={domain} value={domain}>{domain}</option>
            ))}
          </select>
        </label>
        <div className="paper-list-controls" aria-label="Sort and group papers">
          <label>
            <span>Sort by</span>
            <select value={sortBy} onChange={(event) => setSortBy(event.target.value)}>
              <option value="name">Name</option>
              <option value="date">Date modified</option>
              <option value="type">Paper type</option>
            </select>
          </label>
          <button
            className="secondary-button sort-direction-button"
            type="button"
            onClick={() => setSortDirection((direction) => direction === "asc" ? "desc" : "asc")}
            aria-label={`Sort ${sortDirection === "asc" ? "ascending" : "descending"}`}
          >
            <ArrowUpDown size={16} />
            {sortDirection === "asc" ? "Ascending" : "Descending"}
          </button>
          <label>
            <span>Group by</span>
            <select value={groupBy} onChange={(event) => setGroupBy(event.target.value)}>
              <option value="">None</option>
              <option value="research_domains">Research domain</option>
              <option value="paper_types">Paper type</option>
              <option value="methodologies">Methodology</option>
            </select>
          </label>
        </div>
      </section>

      {/* Error message */}
      {error && (
        <TimedFeedback className="error-message" role="alert" message={error}>
          <AlertCircle size={18} />
          {error}
        </TimedFeedback>
      )}

      {/* Loading */}
      {loading && (
        <div className="panel loading-state">
          <LoaderCircle className="spin" size={24} />
          <p>Loading your research papers...</p>
        </div>
      )}

      {/* Empty state */}
      {!loading && !error && visiblePapers.length === 0 && (
        <div className="panel empty-state">
          <FileText size={42} />
          <h2>{papers.length ? "No papers match those filters" : "No research papers found"}</h2>
          <p className="muted">
            {papers.length
              ? "Try another research domain or clear your search."
              : "Upload and summarize a research paper to see it here."}
          </p>
        </div>
      )}

      {/* Paper list */}
      {!loading && visiblePapers.length > 0 && (
        <div className="paper-groups">
          {groupedPapers.map(([groupLabel, groupPapers]) => (
            <section className="paper-group" key={groupLabel || "all"}>
              {groupLabel && <h2 className="paper-group-title">{groupLabel}</h2>}
              <div className="papers-grid">
                {groupPapers.map((paper) => (
            <section className="panel paper-card" key={paper.id}>
              <div className="paper-card-content">
                <div className="paper-card-heading">
                  <span className="paper-card-icon">
                    <FileText size={20} />
                  </span>
                  <div className="paper-card-title">
                    <h3>{paper.title.replace(/_/g, " ")}</h3>
                    <p className="paper-card-meta">
                      {paper.pages} pages <span aria-hidden="true">·</span> {formatDate(paper.uploaded_at)}
                    </p>
                  </div>
                  <button
                    className="icon-button"
                    title={paper.is_saved ? "Remove bookmark" : "Bookmark"}
                    onClick={() => handleSave(paper.id)}
                  >
                    <Bookmark
                      size={19}
                      fill={paper.is_saved ? "currentColor" : "none"}
                    />
                  </button>
                </div>

                <div className="paper-classification-preview">
                  <div className="paper-category-summary">
                    <span className="paper-category-label">Category</span>
                    <span className="paper-category-value">
                      {paper.category || PAPER_CATEGORIES[0]}
                    </span>
                  </div>
                  {Object.keys(CLASSIFICATION_LABELS).some(
                    (field) => classificationLabels(paper, field).length,
                  ) ? (
                    <details className="paper-classification-details">
                      <summary>AI classification details</summary>
                      <div className="paper-classification-fields">
                        {Object.entries(CLASSIFICATION_LABELS).map(([field, label]) => {
                          const tags = classificationLabels(paper, field);
                          if (!tags.length) return null;
                          return (
                            <div className="classification-preview-row" key={field}>
                              <span>{label}</span>
                              <div className="classification-tags">
                                {tags.map((tag) => (
                                  <span className="classification-tag" key={tag}>{tag}</span>
                                ))}
                              </div>
                            </div>
                          );
                        })}
                      </div>
                    </details>
                  ) : (
                    <p className="muted unclassified-note">AI classification not available yet.</p>
                  )}
                </div>

                {classificationTask?.paperId === paper.id && (
                  <ClassificationProgress task={classificationTask} now={clockNow} />
                )}
              </div>

              <div className="paper-card-actions">
                <button
                  className="secondary-button paper-action-button"
                  type="button"
                  onClick={() => setSelectedPaper(paper)}
                >
                  <Eye size={16} />
                  View
                </button>

                <button
                  className="secondary-button paper-action-button"
                  type="button"
                  onClick={() => openPaperEditor(paper, "title")}
                >
                  <Pencil size={15} />
                  Rename
                </button>

                <a
                  className="secondary-button paper-action-button"
                  href={API.downloadSummary(paper.id)}
                  download
                >
                  <FileDown size={16} />
                  Summary
                </a>

                <a
                  className="secondary-button paper-action-button"
                  href={API.downloadPaper(paper.id)}
                  download
                >
                  <FileDown size={16} />
                  PDF
                </a>

                <button
                  className="secondary-button paper-action-button"
                  type="button"
                  onClick={() => openPaperEditor(paper, "classification")}
                >
                  <Tags size={15} />
                  Category
                </button>
                <button
                  className="secondary-button paper-action-button"
                  type="button"
                  onClick={() => handleClassify(paper)}
                  disabled={classificationTask?.status === "processing"}
                >
                  {classificationTask?.paperId === paper.id
                    && classificationTask.status === "processing"
                    ? <LoaderCircle className="spin" size={15} />
                    : <Sparkles size={15} />}
                  {classificationTask?.paperId === paper.id
                    && classificationTask.status === "processing"
                    ? "Classifying..."
                    : "Classify with AI"}
                </button>

                <button
                  className="secondary-button paper-action-button delete-button paper-delete-action"
                  type="button"
                  onClick={() => handleDelete(paper.id)}
                >
                  <Trash2 size={16} />
                  Delete
                </button>
              </div>
            </section>
                ))}
              </div>
            </section>
          ))}
        </div>
      )}

      {/* Summary viewer */}
      {selectedPaper && (
        <div className="summary-overlay">
          <section className="panel summary-modal">
            <div className="panel-heading">
              <div>
                <p className="eyebrow">RESEARCH SUMMARY</p>
                <h2>{selectedPaper.title}</h2>
              </div>

              <button
                className="icon-button"
                onClick={() => setSelectedPaper(null)}
                aria-label="Close summary"
              >
                <X size={20} />
              </button>
            </div>

            <div className="summary-content">
              {formatSummaryText(selectedPaper.summary)}
            </div>

            <div className="paper-card-actions">
              <a
                className="primary-button"
                href={API.downloadSummary(selectedPaper.id)}
                download
              >
                <FileDown size={16} />
                Download Summary
              </a>

              <button
                className="secondary-button"
                onClick={() => setSelectedPaper(null)}
              >
                Close
              </button>
            </div>
          </section>
        </div>
      )}

      {editingPaper && (
        <div className="summary-overlay">
          <section
            className={`panel paper-edit-modal ${editingPaper.field === "classification" ? "classification-edit-modal" : ""}`}
            role="dialog"
            aria-modal="true"
          >
            <div className="panel-heading">
              <div>
                <p className="eyebrow">EDIT RESEARCH PAPER</p>
                <h2>{editingPaper.field === "title" ? "Rename paper" : "Edit paper categories"}</h2>
              </div>
              <button
                className="icon-button"
                type="button"
                onClick={() => setEditingPaper(null)}
                aria-label="Close editor"
              >
                <X size={20} />
              </button>
            </div>

            {error && (
              <TimedFeedback className="error-message" role="alert" message={error}>
                <AlertCircle size={18} />
                {error}
              </TimedFeedback>
            )}

            <form onSubmit={handlePaperUpdate}>
              {editingPaper.field === "title" ? (
                <label className="paper-edit-field">
                  <span>Paper name</span>
                  <input
                    autoFocus
                    maxLength={255}
                    required
                    value={editValue}
                    onChange={(event) => setEditValue(event.target.value)}
                  />
                </label>
              ) : (
                <div className="classification-edit-fields">
                  <p className="muted">
                    Set a paper category and choose any research labels that apply.
                  </p>
                  <label className="paper-edit-field">
                    <span>Paper category</span>
                    <select
                      value={editCategory}
                      onChange={(event) => setEditCategory(event.target.value)}
                    >
                      {PAPER_CATEGORIES.map((category) => (
                        <option key={category} value={category}>{category}</option>
                      ))}
                    </select>
                  </label>
                  {Object.keys(CLASSIFICATION_LABELS).map((field) => (
                    <TaxonomyPicker
                      key={field}
                      field={field}
                      selected={editClassification[field] || []}
                      onChange={(selected) => {
                        setClassificationChanged(true);
                        setEditClassification((previous) => ({
                          ...previous,
                          [field]: selected
                        }));
                      }}
                    />
                  ))}
                </div>
              )}
              <div className="paper-card-actions">
                <button
                  className="primary-button"
                  type="submit"
                  disabled={savingEdit || (
                    editingPaper.field === "title"
                      ? !editValue.trim()
                    : classificationChanged
                      && editClassification.research_domains.length === 0
                  )}
                >
                  {savingEdit ? "Saving..." : "Save changes"}
                </button>
                <button
                  className="secondary-button"
                  type="button"
                  onClick={() => setEditingPaper(null)}
                  disabled={savingEdit}
                >
                  Cancel
                </button>
              </div>
            </form>
          </section>
        </div>
      )}
    </div>
  );
}
