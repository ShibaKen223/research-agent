"use client";

import { useEffect, useRef, type RefObject } from "react";

type Ripple = { x: number; y: number; r: number; life: number };

export function RippleCanvas({ containerRef }: { containerRef: RefObject<HTMLElement | null> }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    const root = containerRef.current;
    if (!canvas || !root) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let dpr = Math.min(window.devicePixelRatio || 1, 2);
    const ripples: Ripple[] = [];
    const mouse = { x: -9999, y: -9999, has: false };
    const glow = { x: 0, y: 0 };
    let last = { x: 0, y: 0 };
    let raf = 0;

    const resize = () => {
      dpr = Math.min(window.devicePixelRatio || 1, 2);
      const r = root.getBoundingClientRect();
      canvas.width = Math.max(1, Math.round(r.width * dpr));
      canvas.height = Math.max(1, Math.round(r.height * dpr));
    };
    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(root);

    const onMove = (e: MouseEvent) => {
      const r = root.getBoundingClientRect();
      const x = e.clientX - r.left;
      const y = e.clientY - r.top;
      if (x < 0 || y < 0 || x > r.width || y > r.height) {
        mouse.has = false;
        return;
      }
      mouse.x = x;
      mouse.y = y;
      if (!mouse.has) {
        glow.x = x;
        glow.y = y;
        last = { x, y };
      }
      mouse.has = true;
      const dx = x - last.x;
      const dy = y - last.y;
      if (Math.hypot(dx, dy) > 46) {
        ripples.push({ x, y, r: 6, life: 1 });
        if (ripples.length > 40) ripples.shift();
        last = { x, y };
      }
    };
    const onLeave = () => {
      mouse.has = false;
    };
    window.addEventListener("mousemove", onMove);
    root.addEventListener("mouseleave", onLeave);

    const tick = () => {
      const W = canvas.width;
      const H = canvas.height;
      ctx.clearRect(0, 0, W, H);
      ctx.save();
      ctx.scale(dpr, dpr);

      const Wc = W / dpr;
      const Hc = H / dpr;

      for (let i = ripples.length - 1; i >= 0; i--) {
        const p = ripples[i];
        p.r += 2.8;
        p.life -= 0.009;
        if (p.life <= 0) ripples.splice(i, 1);
      }

      if (mouse.has) {
        glow.x += (mouse.x - glow.x) * 0.16;
        glow.y += (mouse.y - glow.y) * 0.16;
      }

      const step = 26;
      const band = 24;
      const cursorR = 92;
      for (let gx = step / 2; gx < Wc; gx += step) {
        for (let gy = step / 2; gy < Hc; gy += step) {
          let emph = 0;
          for (let k = 0; k < ripples.length; k++) {
            const p = ripples[k];
            const d = Math.hypot(gx - p.x, gy - p.y);
            const off = Math.abs(d - p.r);
            if (off < band) emph = Math.max(emph, (1 - off / band) * p.life);
          }
          let cur = 0;
          if (mouse.has) {
            const dc = Math.hypot(gx - glow.x, gy - glow.y);
            if (dc < cursorR) cur = 1 - dc / cursorR;
          }
          const baseR = 0.7;
          const r = baseR + emph * 1.4 + cur * 0.5;
          if (emph > 0.04 || cur > 0.04) {
            const t = Math.max(emph, cur * 0.7);
            ctx.fillStyle = `rgba(218,75,38,${(0.05 + t * 0.22).toFixed(3)})`;
          } else {
            ctx.fillStyle = "rgba(27,23,20,0.022)";
          }
          ctx.beginPath();
          ctx.arc(gx, gy, r, 0, Math.PI * 2);
          ctx.fill();
        }
      }

      ctx.restore();
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);

    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
      window.removeEventListener("mousemove", onMove);
      root.removeEventListener("mouseleave", onLeave);
    };
  }, [containerRef]);

  return (
    <canvas
      ref={canvasRef}
      className="pointer-events-none absolute inset-0 z-0 h-full w-full"
    />
  );
}
