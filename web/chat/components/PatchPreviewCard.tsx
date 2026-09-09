import type { PatchPreviewState } from "../state/types";

export function PatchPreviewCard({ preview }: { preview: PatchPreviewState }) {
  return (
    <section aria-label="Patch preview">
      <h3>Patch {preview.patch_id.slice(0, 12)}</h3>
      <ul>
        {preview.files.map((file) => (
          <li key={file.path}>
            <strong>{file.path}</strong> {file.operation}; {file.hunk_count} hunk(s);{" "}
            {file.baseline_status}; {file.summary.slice(0, 240)}
          </li>
        ))}
      </ul>
    </section>
  );
}
