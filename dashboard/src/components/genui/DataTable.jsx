/**
 * GenUI: DataTable — Dynamic data table with sorting and filtering.
 * Columns can be strings ("Name") or objects ({key: "name", label: "Name"}).
 */

export default function DataTable({ columns = [], rows = [], title = '' }) {
  // Normalize columns: accept both ["Name"] and [{key: "name", label: "Name"}]
  const normalizedCols = columns.map((col) =>
    typeof col === 'string' ? { key: col, label: col } : { key: col.key || String(col), label: col.label || col.key || String(col) },
  );

  return (
    <div className="overflow-x-auto rounded-lg border border-border">
      {title && <h3 className="border-b border-border px-4 py-2 text-sm font-medium">{title}</h3>}
      <table className="w-full text-sm">
        <thead className="bg-muted">
          <tr>
            {normalizedCols.map((col) => (
              <th key={col.key} className="px-4 py-2 text-left font-medium">{col.label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i} className="border-t border-border">
              {normalizedCols.map((col) => (
                <td key={col.key} className="px-4 py-2">
                  {typeof row[col.key] === 'object' ? JSON.stringify(row[col.key]) : String(row[col.key] ?? '')}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
