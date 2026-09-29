"use client";

export function PrintButton() {
  return (
    <button
      type="button"
      onClick={() => window.print()}
      className="no-print text-sm px-3 py-1.5 border border-hairline rounded text-ink2 hover:text-ink hover:border-control"
      data-testid="print"
    >
      Print
    </button>
  );
}
