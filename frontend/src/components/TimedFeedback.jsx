import { useEffect, useState } from "react";

const DISMISS_DELAY_MS = 5000;

export default function TimedFeedback({
  as: Element = "div",
  className,
  role,
  message,
  children,
}) {
  const [visible, setVisible] = useState(true);

  useEffect(() => {
    setVisible(true);
    const timeoutId = window.setTimeout(() => setVisible(false), DISMISS_DELAY_MS);
    return () => window.clearTimeout(timeoutId);
  }, [message]);

  if (!visible) return null;

  return (
    <Element className={className} role={role} aria-atomic="true">
      {children}
    </Element>
  );
}
