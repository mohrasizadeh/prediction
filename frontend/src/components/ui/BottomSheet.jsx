// Bottom sheet (docs/24): slides up on phones, a centred panel on computers. Esc, scrim tap and the close button
// close it; focus moves into the sheet and returns on close. Motion is off under "reduce motion" (kit.css).
import { useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import Icon from "../Icon";

export function BottomSheet({ open, onClose, title, children, footer, testid = "ui-sheet" }) {
  const ref = useRef(null);
  useEffect(() => {
    if (!open) return undefined;
    const back = document.activeElement;
    const key = (e) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("keydown", key);
    document.body.style.overflow = "hidden";
    ref.current?.focus();
    return () => { document.removeEventListener("keydown", key); document.body.style.overflow = ""; back?.focus?.(); };
  }, [open, onClose]);
  if (!open) return null;
  return createPortal(
    <div className="k-scrim" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }} data-testid={`${testid}-scrim`}>
      <div className="k-sheet" role="dialog" aria-modal="true" aria-label={title} tabIndex={-1} ref={ref} data-testid={testid}>
        <span className="k-grab" aria-hidden="true" />
        <header className="k-sheet-head">
          <h2>{title}</h2>
          <button type="button" className="k-icon-btn" onClick={onClose} aria-label="Close" data-testid={`${testid}-close`}><Icon name="x" size={20} /></button>
        </header>
        <div className="k-sheet-body">{children}</div>
        {footer && <footer className="k-sheet-foot">{footer}</footer>}
      </div>
    </div>,
    document.body,
  );
}
