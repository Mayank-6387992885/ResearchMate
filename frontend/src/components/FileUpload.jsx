import { useRef } from "react";
import { FileUp, FileText } from "lucide-react";

export default function FileUpload({ file, onFileSelect, disabled }) {
  const inputRef = useRef(null);

  function handleChange(event) {
    const selected = event.target.files?.[0];
    if (selected) onFileSelect(selected);
    event.target.value = "";
  }

  return (
    <div
      className={`upload-box ${disabled ? "upload-disabled" : ""}`}
      onDragOver={(event) => event.preventDefault()}
      onDrop={(event) => {
        event.preventDefault();
        if (!disabled) {
          const dropped = event.dataTransfer.files?.[0];
          if (dropped) onFileSelect(dropped);
        }
      }}
    >
      <input
        ref={inputRef}
        type="file"
        accept="application/pdf,.pdf"
        hidden
        onChange={handleChange}
        disabled={disabled}
      />
      <div className="upload-icon">{file ? <FileText size={25} /> : <FileUp size={25} />}</div>
      {file ? (
        <>
          <strong>{file.name}</strong>
          <span>{(file.size / (1024 * 1024)).toFixed(2)} MB</span>
          <button className="text-button" onClick={() => inputRef.current?.click()} disabled={disabled}>
            Choose a different PDF
          </button>
        </>
      ) : (
        <>
          <strong>Drop your research paper here</strong>
          <span>or choose a PDF from your computer</span>
          <button className="secondary-button" onClick={() => inputRef.current?.click()} disabled={disabled}>
            Browse files
          </button>
          <small>PDF only · Maximum file size: 10 MB</small>
        </>
      )}
    </div>
  );
}