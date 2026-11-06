// Bottom sheet (docs/24): slides up on phones, a centred panel on computers. Esc, scrim tap and the close button
// close it; focus moves into the sheet and returns on close. Motion is off under "reduce motion" (kit.css).
import { useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import Icon from "../Icon";
import { useFocusTrap } from "../Ui";

// `headed`: the content supplies its own visible heading, so the title bar keeps the dialog's
// accessible name but stops printing a string the next 40px repeat.
export function BottomSheet({ open, onClose, title, children, footer, headed = false, testid = "ui-sheet" }) {
  const ref = useRef(null);
  const closeRef = useRef(onClose);
  closeRef.current = onClose;
  useEffect(() => {
    if (!open) return undefined;
    const back = document.activeElement;
    const key = (e) => { if (e.key === "Escape") closeRef.current?.(); };
    document.addEventListener("keydown", key);
    document.body.style.overflow = "hidden";
    ref.current?.focus();
    return () => { document.removeEventListener("keydown", key); document.body.style.overflow = ""; back?.focus?.(); };
  }, [open]);
  // The sheet declared aria-modal="true" and only moved focus into itself once, so Tab walked
  // straight out onto the page behind -- measured at 22 presses. Every overlay in the product is
  // built on this component, so one trap fixes all of them. The hook was already written.
  useFocusTrap(ref, open);
  if (!open) return null;
  return createPortal(
    <div className="k-scrim" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }} data-testid={`${testid}-scrim`}>
      <div className="k-sheet" role="dialog" aria-modal="true" aria-label={title} tabIndex={-1} ref={ref} data-testid={testid}>
        <span className="k-grab" aria-hidden="true" />
        <header className="k-sheet-head">
          <h2 className={headed ? "sr-only" : undefined}>{title}</h2>
          <button type="button" className="k-icon-btn" onClick={onClose} aria-label="Close" data-testid={`${testid}-close`}><Icon name="x" size={20} /></button>
        </header>
        <div className="k-sheet-body">{children}</div>
        {footer && <footer className="k-sheet-foot">{footer}</footer>}
      </div>
    </div>,
    document.body,
  );
}
