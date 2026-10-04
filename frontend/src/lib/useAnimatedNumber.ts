import { useEffect, useRef, useState } from "react";

/** Tween a number toward `target` (ease-out), so the balance visibly ticks down. */
export function useAnimatedNumber(target: number | null, ms = 1400): number | null {
  const [value, setValue] = useState<number | null>(target);
  const from = useRef<number | null>(target);

  useEffect(() => {
    if (target === null) return;
    const start = from.current ?? target;
    if (start === target) {
      setValue(target);
      return;
    }
    const t0 = performance.now();
    let raf = 0;
    const tick = (now: number) => {
      const p = Math.min((now - t0) / ms, 1);
      const eased = 1 - Math.pow(1 - p, 4);
      const v = start + (target - start) * eased;
      setValue(v);
      from.current = v;
      if (p < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target, ms]);

  return value;
}
