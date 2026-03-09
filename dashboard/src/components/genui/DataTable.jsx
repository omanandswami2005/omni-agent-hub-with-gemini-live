/**
 * GenUI: DataTable — Dynamic data table with sorting and filtering.
 */

export default function DataTable({ columns = [], rows = [], title = '' }) {
  return (
    <div className="overflow-x-auto rounded-lg border border-border">
      {title && <h3 className="border-b border-border px-4 py-2 text-sm font-medium">{title}</h3>}
      <table className="w-full text-sm">
        <thead className="bg-muted">
          <tr>
            {columns.map((col) => (
              <th key={col} className="px-4 py-2 text-left font-medium">{col}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i} className="border-t border-border">
              {columns.map((col) => (
                <td key={col} className="px-4 py-2">{row[col]}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
