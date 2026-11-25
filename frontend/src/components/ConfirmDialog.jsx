import { AlertTriangle, X } from "lucide-react";

export default function ConfirmDialog({
  open,
  title = "Confirm Action",
  message,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  danger = false,
  onConfirm,
  onCancel,
}) {
  if (!open) return null;

  return (
    <div
      className="modal-backdrop"
      role="dialog"
      aria-modal="true"
      aria-labelledby="confirm-dialog-title"
      style={{
        position: "fixed",
        inset: 0,
        backgroundColor: "rgba(15, 23, 42, 0.55)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 1000,
        padding: "1rem",
      }}
      onClick={onCancel}
    >
      <div
        className="panel"
        style={{
          maxWidth: "420px",
          width: "100%",
          margin: 0,
          boxShadow: "0 20px 40px rgba(0, 0, 0, 0.2)",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="panel-heading" style={{ marginBottom: "0.75rem" }}>
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
            {danger && <AlertTriangle size={18} style={{ color: "#dc2626" }} />}
            <h3 id="confirm-dialog-title" style={{ margin: 0, fontSize: "1rem" }}>
              {title}
            </h3>
          </div>
          <button
            type="button"
            className="secondary-button compact"
            onClick={onCancel}
            aria-label="Close dialog"
          >
            <X size={16} />
          </button>
        </div>
        <p className="muted" style={{ margin: "0 0 1.25rem", fontSize: "0.92rem", lineHeight: 1.5 }}>
          {message}
        </p>
        <div style={{ display: "flex", justifyContent: "flex-end", gap: "0.6rem" }}>
          <button type="button" className="secondary-button compact" onClick={onCancel}>
            {cancelLabel}
          </button>
          <button
            type="button"
            className="primary-button compact"
            style={danger ? { backgroundColor: "#dc2626", borderColor: "#dc2626" } : undefined}
            onClick={onConfirm}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
